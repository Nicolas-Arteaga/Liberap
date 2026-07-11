import pandas as pd
import requests
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .schemas import (
    FvgAnalyzeRequest, FvgAnalyzeResponse, FvgZone, VolumeProfileBin,
    FvgScanRequest, FvgScanResponse, FvgScanItem,
    FvgCascadeRequest, FvgCascadeResult, FvgCascadeScanRequest, FvgCascadeScanResponse,
)
from .detector import detect_fvgs
from .volume_profile import build_volume_profile, poc_distance_pct

logger = logging.getLogger("FVG")

# Pesos del score de confluencia. El componente dominante ahora es "está en
# punto de entrada" (W_ENTRY) — un Top-5 de gaps enormes que el precio ya
# dejó atrás hace 2 días no sirve para nada, lo que importa es si HOY el
# precio está tocando (o a punto de tocar) la zona. El resto son
# desempates entre candidatos igualmente "entrables".
W_ENTRY = 0.45
W_GAP = 0.20
W_POC = 0.20
W_FRESH = 0.15
GAP_PCT_EXCELLENT = 0.30   # gap_pct >= esto ya puntúa 100 en ese componente
POC_DIST_PCT_ZERO_AT = 0.5  # distancia al HVN a partir de la cual el componente da 0

# "Punto de entrada": el precio está DENTRO de la zona (IN_ZONE, ideal) o a
# menos de este % de distancia de su borde más cercano (APPROACHING, "está
# por llegar"). Más lejos que esto = FAR, no es una entrada accionable hoy.
ENTRY_APPROACH_PCT = 0.15

# Si el precio está "adentro" de la zona pero el gap ya se rellenó más de
# esto, la entrada YA PASÓ — el precio está a punto de atravesar la zona
# entera, no es una entrada fresca. Se marca EXHAUSTED y se descarta igual
# que una zona lejana, aunque geométricamente el precio esté "adentro".
FRESH_FILL_MAX_PCT = 40.0

# "Relleno" y "progreso hacia el TP" son cosas DISTINTAS: relleno mide si el
# precio volvió A ENTRAR al gap; progreso hacia el TP mide si el precio ya
# se ALEJÓ hacia el objetivo. Un gap puede estar 0% relleno (nunca se volvió
# a tocar) mientras el precio ya recorrió el 90% del camino hacia el TP —
# entrar ahí da un riesgo/beneficio pésimo aunque la zona en sí sea "fresca".
# Si ya se alcanzó el TP del todo, la zona queda sin sentido (TP_HIT,
# excluida igual que EXHAUSTED/FAR). Entre la mitad y el TP, se penaliza el
# score proporcionalmente en vez de excluir de una — sigue siendo una zona
# válida para verla, solo con peor relación riesgo/beneficio.
TP_PROGRESS_PENALTY_START_PCT = 50.0

# SL/TP dibujados como si el propio trader hubiera marcado el FVG a mano:
# el SL queda un poco MAS ALLA del borde de invalidación de la zona (no
# pegado al borde). El TP apunta al próximo nivel de liquidez real (el
# máximo/mínimo previo que el impulso que formó el gap dejó atrás) — no una
# proyección arbitraria — con un múltiplo del gap como fallback si no hay
# un swing más favorable en la ventana.
SL_BUFFER_RATIO = 0.15
TP_PROJECTION_RATIO = 2.0

# Las IFVG (FVG invalidado con cierre de cuerpo, dado vuelta) son señal de
# mayor calidad según ICT/la literatura — bonus flat al score, no un peso
# multiplicativo, para no desbalancear el resto de los componentes.
IFVG_SCORE_BONUS = 10.0


class FvgAnalyzer:
    def __init__(self):
        self.timeout = 8

    # ── Fetch ────────────────────────────────────────────────────────────
    def _fetch_klines(self, symbol: str, interval: str, limit: int) -> Optional[list]:
        clean_symbol = symbol.replace("/", "").replace("-", "").upper()
        try:
            r = requests.get(
                "https://fapi.binance.com/fapi/v1/klines",
                params={"symbol": clean_symbol, "interval": interval, "limit": limit},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"[FVG] Binance Futures falló para {symbol}, intento spot: {e}")
            try:
                r = requests.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": clean_symbol, "interval": interval, "limit": limit},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e2:
                logger.error(f"[FVG] Binance Spot también falló para {symbol}: {e2}")
                return None

    def _klines_to_df(self, raw: list) -> pd.DataFrame:
        df = pd.DataFrame(raw).iloc[:, :6]
        df.columns = ["open_time", "open", "high", "low", "close", "volume"]
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
        return df

    def _entry_status(self, zone: dict, current_price: float) -> tuple:
        """
        ¿Está el precio ADENTRO de la zona ahora mismo (IN_ZONE), a punto de
        llegar (APPROACHING), lejos (FAR) o ya la atravesó casi entera
        (EXHAUSTED — geométricamente "adentro" pero la entrada ya pasó,
        el gap está a punto de romperse del todo, no es una entrada fresca)?
        """
        top, bottom = zone["top"], zone["bottom"]
        if bottom <= current_price <= top:
            if zone["fill_progress_pct"] > FRESH_FILL_MAX_PCT:
                return "EXHAUSTED", 0.0
            return "IN_ZONE", 0.0
        dist = (current_price - top) if current_price > top else (bottom - current_price)
        dist_pct = abs(dist) / current_price * 100.0 if current_price else 999.0
        status = "APPROACHING" if dist_pct <= ENTRY_APPROACH_PCT else "FAR"
        return status, round(dist_pct, 4)

    def _tp_progress_pct(self, zone: dict, current_price: float, tp_price: float) -> float:
        """
        Cuánto del camino entre la entrada y el TP ya recorrió el precio.
        0% = todavía no arrancó el movimiento hacia el TP. 100%+ = TP ya
        alcanzado. Se mide desde el borde de la zona más cercano al TP
        (top para alcista, bottom para bajista), no desde el otro extremo.
        """
        if zone["direction"] == "bullish":
            entry_edge = zone["top"]
            total = tp_price - entry_edge
            if total <= 0:
                return 0.0
            progress = (current_price - entry_edge) / total * 100.0
        else:
            entry_edge = zone["bottom"]
            total = entry_edge - tp_price
            if total <= 0:
                return 0.0
            progress = (entry_edge - current_price) / total * 100.0
        return round(max(0.0, progress), 2)

    def _score_zone(self, zone: dict, bins: list, current_price: float, df: pd.DataFrame) -> dict:
        dist_pct, overlapping = poc_distance_pct(zone["top"], zone["bottom"], bins)
        entry_status, dist_to_entry_pct = self._entry_status(zone, current_price)

        tp_price = self._liquidity_target(zone, df)
        tp_progress_pct = self._tp_progress_pct(zone, current_price, tp_price)
        if tp_progress_pct >= 100.0 and entry_status in ("IN_ZONE", "APPROACHING"):
            # El TP ya se alcanzó — no queda recorrido, no tiene sentido
            # mostrarla como lista para entrar aunque geométricamente el
            # precio siga tocando la zona.
            entry_status = "TP_HIT"

        norm_gap_score = min(zone["gap_pct"] / GAP_PCT_EXCELLENT, 1.0) * 100.0
        poc_proximity = max(0.0, 1.0 - dist_pct / POC_DIST_PCT_ZERO_AT) * 100.0
        freshness_score = 100.0 - zone["fill_progress_pct"]
        if entry_status == "IN_ZONE":
            entry_score = 100.0
        elif entry_status == "APPROACHING":
            entry_score = max(0.0, (1.0 - dist_to_entry_pct / ENTRY_APPROACH_PCT)) * 100.0
        else:
            entry_score = 0.0

        # Penaliza progresivamente si ya se recorrió más de la mitad del
        # camino al TP — la zona sigue siendo válida, pero el riesgo/beneficio
        # real de entrar ahora es mucho peor que el que muestra el gap "fresco".
        if entry_score > 0 and tp_progress_pct > TP_PROGRESS_PENALTY_START_PCT:
            rr_quality = max(0.15, 1.0 - (tp_progress_pct - TP_PROGRESS_PENALTY_START_PCT) / (100.0 - TP_PROGRESS_PENALTY_START_PCT))
            entry_score *= rr_quality

        confluence_score = W_ENTRY * entry_score + W_GAP * norm_gap_score + W_POC * poc_proximity + W_FRESH * freshness_score
        if zone.get("is_ifvg"):
            confluence_score += IFVG_SCORE_BONUS
        confluence_score = round(min(confluence_score, 100.0), 1)
        zone["poc_distance_pct"] = dist_pct
        zone["poc_confluence"] = overlapping
        zone["entry_status"] = entry_status
        zone["dist_to_entry_pct"] = dist_to_entry_pct
        zone["tp_price"] = tp_price
        zone["tp_progress_pct"] = tp_progress_pct
        zone["confluence_score"] = confluence_score
        return zone

    def _liquidity_target(self, zone: dict, df: pd.DataFrame) -> float:
        """
        TP = próximo nivel de liquidez real (el máximo/mínimo que el impulso
        que formó el gap dejó atrás), no una proyección arbitraria. Si no hay
        un swing más favorable en la ventana, cae a un múltiplo del gap.
        """
        gap_size = zone["top"] - zone["bottom"]
        if zone["direction"] == "bullish":
            swing_high = float(df["high"].max())
            if swing_high > zone["top"]:
                return swing_high
            return zone["top"] + gap_size * TP_PROJECTION_RATIO
        else:
            swing_low = float(df["low"].min())
            if swing_low < zone["bottom"]:
                return swing_low
            return zone["bottom"] - gap_size * TP_PROJECTION_RATIO

    def _build_fvg_zone(self, z: dict, df: pd.DataFrame, interval: str) -> FvgZone:
        gap_size = z["top"] - z["bottom"]
        tp_price = z["tp_price"]  # ya calculado en _score_zone
        if z["direction"] == "bullish":
            # SL un poco MAS ALLA del borde de invalidacion (no en el
            # borde mismo, para que la franja se vea y no quede pegado).
            sl_price = z["bottom"] - gap_size * SL_BUFFER_RATIO
        else:
            sl_price = z["top"] + gap_size * SL_BUFFER_RATIO
        return FvgZone(
            id=f"{interval}_{z['direction']}_{z['candle_index']}_{'ifvg' if z.get('is_ifvg') else 'fvg'}",
            direction=z["direction"],
            top=z["top"],
            bottom=z["bottom"],
            gap_pct=z["gap_pct"],
            formed_at=datetime.fromtimestamp(z["formed_at_ms"] / 1000, tz=timezone.utc).isoformat(),
            formed_at_ms=z["formed_at_ms"],
            candle_index=z["candle_index"],
            fill_progress_pct=z["fill_progress_pct"],
            poc_confluence=z["poc_confluence"],
            poc_distance_pct=z["poc_distance_pct"],
            entry_status=z["entry_status"],
            dist_to_entry_pct=z["dist_to_entry_pct"],
            tp_progress_pct=z["tp_progress_pct"],
            confluence_score=z["confluence_score"],
            sl_price=round(sl_price, 8),
            tp_price=round(tp_price, 8),
            is_ifvg=bool(z.get("is_ifvg", False)),
            source_interval=interval,
        )

    def _zones_overlap(self, a: dict, b: dict) -> bool:
        return not (a["top"] < b["bottom"] or a["bottom"] > b["top"])

    def _scored_zones_for_interval(self, symbol: str, interval: str, limit: int = 200):
        """
        Fetch + detectar + puntuar todas las zonas de un símbolo en un
        timeframe. Devuelve (df, current_price, scored_zone_dicts) ordenados
        por score descendente, o None si no hay velas suficientes.
        """
        raw = self._fetch_klines(symbol, interval, limit)
        if not raw or len(raw) < 100:
            return None
        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        zones_raw = detect_fvgs(df)
        bins_raw, _ = build_volume_profile(df)
        scored = [self._score_zone(z, bins_raw, current_price, df) for z in zones_raw]
        scored.sort(key=lambda z: z["confluence_score"], reverse=True)
        return df, current_price, scored

    # ── Single symbol (chart view) ──────────────────────────────────────
    def analyze_symbol(self, req: FvgAnalyzeRequest) -> Optional[FvgAnalyzeResponse]:
        raw = self._fetch_klines(req.symbol, req.interval, req.limit)
        if not raw or len(raw) < 100:
            return None

        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        zones_raw = detect_fvgs(df)
        bins_raw, poc_price = build_volume_profile(df)

        zones: List[FvgZone] = []
        for z in zones_raw:
            z = self._score_zone(z, bins_raw, current_price, df)
            zones.append(self._build_fvg_zone(z, df, req.interval))

        zones.sort(key=lambda x: x.confluence_score, reverse=True)
        zones = zones[:20]

        bins = [VolumeProfileBin(**b) for b in bins_raw]

        return FvgAnalyzeResponse(
            symbol=req.symbol,
            interval=req.interval,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            current_price=current_price,
            poc_price=poc_price,
            zones=zones,
            volume_profile=bins,
        )

    # ── Batch scan (top-5 across watchlist) ─────────────────────────────
    def scan(self, req: FvgScanRequest) -> FvgScanResponse:
        logger.info(f"[FVG-SCAN] Escaneando {len(req.symbols)} símbolos en {req.interval}...")
        items: List[FvgScanItem] = []

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._scan_symbol, s, req.interval): s for s in req.symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item = future.result()
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning(f"[FVG-SCAN] Error analizando {symbol}: {e}")

        items.sort(key=lambda x: x.confluence_score, reverse=True)
        top_5 = items[:5]
        logger.info(f"[FVG-SCAN] Completo: {len(items)} con zonas válidas, top-5 devuelto")

        return FvgScanResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _scan_symbol(self, symbol: str, interval: str) -> Optional[FvgScanItem]:
        raw = self._fetch_klines(symbol, interval, 200)
        if not raw or len(raw) < 100:
            return None

        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        zones_raw = detect_fvgs(df)
        if not zones_raw:
            return None

        bins_raw, _ = build_volume_profile(df)
        scored = [self._score_zone(z, bins_raw, current_price, df) for z in zones_raw]

        # El Top-5 es para setups ACCIONABLES HOY, no para el catálogo
        # completo de gaps históricos — ni para zonas ya tan atravesadas que
        # la entrada real ya pasó (EXHAUSTED), ni para las que ya alcanzaron
        # su propio TP (TP_HIT). Solo IN_ZONE/APPROACHING cuentan.
        actionable = [z for z in scored if z["entry_status"] in ("IN_ZONE", "APPROACHING")]
        if not actionable:
            return None
        best = max(actionable, key=lambda z: z["confluence_score"])
        tp_price = best["tp_price"]

        return FvgScanItem(
            symbol=symbol,
            direction=best["direction"],
            top=best["top"],
            bottom=best["bottom"],
            gap_pct=best["gap_pct"],
            current_price=current_price,
            poc_confluence=best["poc_confluence"],
            poc_distance_pct=best["poc_distance_pct"],
            entry_status=best["entry_status"],
            dist_to_entry_pct=best["dist_to_entry_pct"],
            tp_price=round(tp_price, 8),
            confluence_score=best["confluence_score"],
            fill_progress_pct=best["fill_progress_pct"],
            formed_at=datetime.fromtimestamp(best["formed_at_ms"] / 1000, tz=timezone.utc).isoformat(),
        )

    # ── Cascada 15m -> 5m -> 1m (dirección -> confirmación -> ejecución) ──
    def analyze_cascade(self, req: FvgCascadeRequest) -> Optional[FvgCascadeResult]:
        """
        15m define el sesgo (la mejor zona ahí). Si hay una zona en 5m, misma
        dirección, que se solapa con la de 15m, eso CONFIRMA el sesgo. Si
        además hay una zona en 1m, misma dirección, solapada con la de 5m,
        esa define la EJECUCIÓN (entrada/SL más ajustados). La zona real a
        operar es siempre la más fina disponible: ejecución > confirmación > sesgo.
        """
        bias_data = self._scored_zones_for_interval(req.symbol, "15m", req.limit)
        if bias_data is None:
            return None
        df_15m, price_15m, zones_15m = bias_data

        now = datetime.now(timezone.utc).isoformat()
        if not zones_15m:
            return FvgCascadeResult(
                symbol=req.symbol, cascade_status="NONE", current_price=price_15m,
                confluence_score=0.0, analyzed_at=now,
            )

        bias_raw = zones_15m[0]
        bias_zone = self._build_fvg_zone(bias_raw, df_15m, "15m")

        confirmation_zone = None
        execution_zone = None
        cascade_status = "AWAITING_CONFIRMATION"
        entry_zone = bias_zone
        current_price = price_15m

        conf_data = self._scored_zones_for_interval(req.symbol, "5m", 200)
        if conf_data is not None:
            df_5m, price_5m, zones_5m = conf_data
            current_price = price_5m
            matching_5m = [
                z for z in zones_5m
                if z["direction"] == bias_raw["direction"] and self._zones_overlap(z, bias_raw)
            ]
            if matching_5m:
                confirmation_raw = matching_5m[0]
                confirmation_zone = self._build_fvg_zone(confirmation_raw, df_5m, "5m")
                cascade_status = "AWAITING_EXECUTION"
                entry_zone = confirmation_zone

                exec_data = self._scored_zones_for_interval(req.symbol, "1m", 200)
                if exec_data is not None:
                    df_1m, price_1m, zones_1m = exec_data
                    current_price = price_1m
                    matching_1m = [
                        z for z in zones_1m
                        if z["direction"] == bias_raw["direction"] and self._zones_overlap(z, confirmation_raw)
                    ]
                    if matching_1m:
                        execution_raw = matching_1m[0]
                        execution_zone = self._build_fvg_zone(execution_raw, df_1m, "1m")
                        cascade_status = "READY"
                        entry_zone = execution_zone

        return FvgCascadeResult(
            symbol=req.symbol,
            cascade_status=cascade_status,
            bias_zone=bias_zone,
            confirmation_zone=confirmation_zone,
            execution_zone=execution_zone,
            entry_price_zone=entry_zone,
            current_price=current_price,
            confluence_score=entry_zone.confluence_score,
            analyzed_at=now,
        )

    def scan_cascade(self, req: FvgCascadeScanRequest) -> FvgCascadeScanResponse:
        logger.info(f"[FVG-CASCADE-SCAN] Escaneando {len(req.symbols)} símbolos...")
        results: List[FvgCascadeResult] = []

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {
                executor.submit(self.analyze_cascade, FvgCascadeRequest(symbol=s)): s
                for s in req.symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                    if result and result.cascade_status in ("AWAITING_EXECUTION", "READY"):
                        entry = result.entry_price_zone
                        if entry and entry.entry_status in ("IN_ZONE", "APPROACHING"):
                            results.append(result)
                except Exception as e:
                    logger.warning(f"[FVG-CASCADE-SCAN] Error analizando {symbol}: {e}")

        results.sort(key=lambda r: r.confluence_score, reverse=True)
        top_5 = results[:5]
        logger.info(f"[FVG-CASCADE-SCAN] Completo: {len(results)} accionables, top-5 devuelto")

        return FvgCascadeScanResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )
