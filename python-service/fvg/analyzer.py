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
from shared_kline_cache import get_or_fetch

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
# 0.15 era demasiado estricto: en pares volátiles (los que ahora prioriza el
# scan) el ruido normal de UNA sola vela de 5m/1m ya supera eso, así que un
# resultado "EN ZONA" en el scan aparecía como FAR/NONE segundos después sin
# que el precio se hubiera alejado de verdad de la oportunidad.
ENTRY_APPROACH_PCT = 0.5

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

# 2026-07-12: el TP apuntaba al máximo/mínimo absoluto de TODA la ventana
# (200 velas) como si fuera siempre un nivel de liquidez alcanzable. Caso
# real (BEATUSDT, VELVETUSDT): ese extremo a veces es la punta de un
# impulso MUCHO más grande y ya viejo/agotado — el impulso actual (el que
# formó el gap) nunca llega tan lejos, avanza 70-85% del camino y se da
# vuelta, devolviendo la ganancia. Se compara el alcance de una ventana
# RECIENTE (la pata actual) contra el de la ventana completa: si el
# extremo lejano implica un recorrido desproporcionado respecto a la pata
# reciente, es un pico/valle ajeno — el objetivo pasa a ser solo la MITAD
# del camino restante hasta ahí, no el extremo entero (medida clásica de
# "impulso que se repite más débil que el anterior"). Si no hay
# desproporción (el extremo de la ventana completa es básicamente el de
# la propia pata reciente, o un nivel de liquidez cercano y proporcional
# — swept level / medida AB=CD estándar), se usa entero como siempre.
# Además, SIEMPRE se recorta el resultado final (haircut): nunca se
# apunta al 100% del nivel calculado, porque el precio suele reaccionar
# un poco ANTES del nivel "obvio" (mismo motivo por el que un TP/SL exacto
# en un número redondo es el primer lugar que barre un stop hunt).
RECENT_IMPULSE_LOOKBACK = 40
DISPROPORTION_RATIO = 1.5
FADING_IMPULSE_TARGET_RATIO = 0.5
TP_HAIRCUT_RATIO = 0.9

# 2026-07-12, caso AGLDUSDT: un SHORT armado mientras el precio cotiza
# claramente POR ENCIMA de sus propias MA25/50 (tendencia alcista de fondo)
# es una apuesta de CORRECCIÓN, no de reversión — lo lógico es que vaya a
# "respirar" hasta la media más próxima y de ahí siga la tendencia de
# fondo, no que dé la vuelta entera hacia un swing lejano. Mismo espejo
# para un LONG armado con precio por debajo de sus MA25/50 (rebote dentro
# de una tendencia bajista). Si el precio ya está DEBAJO de sus MAs en un
# SHORT (o arriba en un LONG), es una entrada a favor de la tendencia de
# fondo, no una corrección — no se aplica este tope, se deja correr con
# la lógica de arriba.
MA_CORRECTION_FAST_SPAN = 25
MA_CORRECTION_SLOW_SPAN = 50

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

        def _do_fetch():
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

        return get_or_fetch(clean_symbol, interval, limit, _do_fetch)

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

    def _compute_mas(self, df: pd.DataFrame) -> tuple:
        """EMA25/EMA50 de cierre, o (None, None) si no hay velas suficientes."""
        if len(df) < MA_CORRECTION_SLOW_SPAN:
            return None, None
        close = df["close"]
        ma_fast = float(close.ewm(span=MA_CORRECTION_FAST_SPAN, adjust=False).mean().iloc[-1])
        ma_slow = float(close.ewm(span=MA_CORRECTION_SLOW_SPAN, adjust=False).mean().iloc[-1])
        return ma_fast, ma_slow

    def _is_trend_aligned(self, zone: dict, current_price: float, df: pd.DataFrame) -> bool:
        """
        2026-07-12: FVG solo detecta el hueco de 3 velas — no tiene noción de
        tendencia de fondo. La metodología de la que sale este patrón
        (ICT/SMC) siempre lo usa con un filtro de sesgo direccional: gaps
        alcistas solo en tendencia alcista, bajistas solo en bajista. Acá no
        existía ese filtro, y el 56% de las pérdidas de FVG-1m de un día
        entero (auditado 1 a 1 contra Bybit) resultaron ser exactamente
        entradas contra-tendencia (short con precio ya arriba de sus propias
        EMA25/50, o long por debajo) — de esas, 7 de 19 fueron directo en
        contra desde el segundo uno, sin margen a favor NUNCA: ningún ajuste
        de TP las salva, la entrada nunca debió abrirse.
        Devuelve False (rechazar) solo cuando el precio está claramente del
        lado equivocado de AMBAS medias — no exige estar del lado correcto
        de las dos, solo que no esté franca y establecidamente en contra.
        """
        ma_fast, ma_slow = self._compute_mas(df)
        if ma_fast is None:
            return True  # sin datos suficientes, no bloquear
        if zone["direction"] == "bullish":
            return not (current_price < ma_fast and current_price < ma_slow)
        else:
            return not (current_price > ma_fast and current_price > ma_slow)

    def _score_zone(self, zone: dict, bins: list, current_price: float, df: pd.DataFrame) -> dict:
        dist_pct, overlapping = poc_distance_pct(zone["top"], zone["bottom"], bins)
        entry_status, dist_to_entry_pct = self._entry_status(zone, current_price)
        zone["trend_aligned"] = self._is_trend_aligned(zone, current_price, df)

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

        Si ese extremo pertenece a un impulso ANTERIOR desproporcionadamente
        más grande que la pata reciente (ver constantes arriba), se corta a
        la mitad del camino restante en vez del extremo entero. Siempre se
        aplica un haircut final (nunca el 100% del nivel calculado).
        """
        gap_size = zone["top"] - zone["bottom"]
        recent_df = df.tail(RECENT_IMPULSE_LOOKBACK)
        ma_fast, ma_slow = self._compute_mas(df)

        if zone["direction"] == "bullish":
            entry_edge = zone["top"]
            swing_high = float(df["high"].max())
            local_high = float(recent_df["high"].max())

            if swing_high <= entry_edge:
                raw_target = entry_edge + gap_size * TP_PROJECTION_RATIO
            elif local_high <= entry_edge:
                # Sin pata local propia con la que comparar — no hay base
                # para juzgar desproporción, usar la proyección conservadora.
                raw_target = entry_edge + gap_size * TP_PROJECTION_RATIO
            else:
                local_reach = local_high - entry_edge
                full_reach = swing_high - entry_edge
                if full_reach > local_reach * DISPROPORTION_RATIO:
                    raw_target = entry_edge + full_reach * FADING_IMPULSE_TARGET_RATIO
                else:
                    raw_target = swing_high

            # Rebote dentro de una tendencia bajista de fondo (precio por
            # debajo de ambas MAs): el objetivo natural es la media más
            # próxima, no un swing lejano — solo si eso acota MÁS que lo
            # ya calculado arriba.
            if ma_fast is not None and entry_edge < ma_fast and entry_edge < ma_slow:
                ma_target = min(ma_fast, ma_slow)
                if ma_target < raw_target:
                    raw_target = ma_target

            return entry_edge + (raw_target - entry_edge) * TP_HAIRCUT_RATIO
        else:
            entry_edge = zone["bottom"]
            swing_low = float(df["low"].min())
            local_low = float(recent_df["low"].min())

            if swing_low >= entry_edge:
                raw_target = entry_edge - gap_size * TP_PROJECTION_RATIO
            elif local_low >= entry_edge:
                raw_target = entry_edge - gap_size * TP_PROJECTION_RATIO
            else:
                local_reach = entry_edge - local_low
                full_reach = entry_edge - swing_low
                if full_reach > local_reach * DISPROPORTION_RATIO:
                    raw_target = entry_edge - full_reach * FADING_IMPULSE_TARGET_RATIO
                else:
                    raw_target = swing_low

            # Corrección dentro de una tendencia alcista de fondo (precio
            # por encima de ambas MAs): el objetivo natural es la media más
            # próxima ("va a respirar ahí y sigue"), no un swing lejano —
            # solo si eso acota MÁS que lo ya calculado arriba.
            if ma_fast is not None and entry_edge > ma_fast and entry_edge > ma_slow:
                ma_target = max(ma_fast, ma_slow)
                if ma_target > raw_target:
                    raw_target = ma_target

            return entry_edge - (entry_edge - raw_target) * TP_HAIRCUT_RATIO

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
            trend_aligned=bool(z.get("trend_aligned", True)),
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
        logger.info(f"[FVG-SCAN] Escaneando {len(req.symbols)} símbolos en {req.interval} (sort_by={req.sort_by})...")
        items: List[FvgScanItem] = []
        trend_blocked_count = 0

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._scan_symbol, s, req.interval, req.sort_by): s for s in req.symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item, rejection = future.result()
                    if item:
                        items.append(item)
                    elif rejection == "trend_blocked":
                        trend_blocked_count += 1
                except Exception as e:
                    logger.warning(f"[FVG-SCAN] Error analizando {symbol}: {e}")

        if req.sort_by == "range":
            items.sort(key=lambda x: x.tp_distance_pct, reverse=True)
        else:
            items.sort(key=lambda x: x.confluence_score, reverse=True)
        top_5 = items[:5]
        # Visibilidad explícita del filtro de tendencia (pedido del usuario:
        # que no sea una caja negra que pueda dejar el sistema sin candidatos
        # sin que se note). Si algún día esto se acerca a `scanned_count`,
        # es una señal real de que el filtro está siendo demasiado estricto
        # para las condiciones de mercado del momento — hoy (2026-07-12,
        # baseline) fueron 19 de 400 símbolos, no un problema.
        logger.info(
            f"[FVG-SCAN] Completo: {len(items)} con zonas válidas | "
            f"{trend_blocked_count} bloqueados solo por contra-tendencia | top-5 devuelto"
        )

        return FvgScanResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            trend_blocked_count=trend_blocked_count,
            actionable_count=len(items),
        )

    def _scan_symbol(self, symbol: str, interval: str, sort_by: str = "score") -> tuple:
        """Devuelve (item, rejection_reason). item es None si no hay setup accionable;
        rejection_reason distingue "trend_blocked" (había un gap accionable pero
        contra-tendencia) del resto, para poder medir el impacto real del filtro."""
        raw = self._fetch_klines(symbol, interval, 200)
        if not raw or len(raw) < 100:
            return None, "insufficient_data"

        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        zones_raw = detect_fvgs(df)
        if not zones_raw:
            return None, "no_gaps"

        bins_raw, _ = build_volume_profile(df)
        scored = [self._score_zone(z, bins_raw, current_price, df) for z in zones_raw]

        # El Top-5 es para setups ACCIONABLES HOY, no para el catálogo
        # completo de gaps históricos — ni para zonas ya tan atravesadas que
        # la entrada real ya pasó (EXHAUSTED), ni para las que ya alcanzaron
        # su propio TP (TP_HIT). Solo IN_ZONE/APPROACHING cuentan. Tampoco
        # cuentan las zonas contra-tendencia (ver _is_trend_aligned) —
        # auditoría 2026-07-12 sobre un día entero de FVG-1m mostró que el
        # 56% de las pérdidas eran exactamente este caso.
        entry_ok = [z for z in scored if z["entry_status"] in ("IN_ZONE", "APPROACHING")]
        actionable = [z for z in entry_ok if z.get("trend_aligned", True)]
        if not actionable:
            # Si había una zona accionable y lo único que la descartó fue la
            # tendencia, contarlo aparte — distinto de "no había nada".
            reason = "trend_blocked" if entry_ok else "not_actionable"
            return None, reason

        for z in actionable:
            z["tp_distance_pct"] = abs(z["tp_price"] - current_price) / current_price * 100.0 if current_price else 0.0

        if sort_by == "range":
            # Ignora el score compuesto — la estrategia FVG del agente busca
            # "la mejor entrada armada" (3 velas del gap + mayor recorrido
            # simple hasta el TP), no la que mejor puntúe en conjunto.
            best = max(actionable, key=lambda z: z["tp_distance_pct"])
        else:
            best = max(actionable, key=lambda z: z["confluence_score"])

        gap_size = best["top"] - best["bottom"]
        if best["direction"] == "bullish":
            sl_price = best["bottom"] - gap_size * SL_BUFFER_RATIO
        else:
            sl_price = best["top"] + gap_size * SL_BUFFER_RATIO

        item = FvgScanItem(
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
            sl_price=round(sl_price, 8),
            tp_price=round(best["tp_price"], 8),
            tp_distance_pct=round(best["tp_distance_pct"], 4),
            confluence_score=best["confluence_score"],
            fill_progress_pct=best["fill_progress_pct"],
            formed_at=datetime.fromtimestamp(best["formed_at_ms"] / 1000, tz=timezone.utc).isoformat(),
        )
        return item, None

    # ── Cascada, anclada a la temporalidad elegida ──────────────────────
    CASCADE_CHAIN = ["15m", "5m", "1m"]

    def analyze_cascade(self, req: FvgCascadeRequest) -> Optional[FvgCascadeResult]:
        """
        La temporalidad elegida (anchor_interval) define dónde arranca la
        cascada: 15m -> cadena completa 15m->5m->1m (default). 5m -> cadena
        corta 5m->1m. 1m -> análisis directo en 1m, sin cascada (no hay
        temporalidad más chica en la cadena). El primer eslabón define el
        sesgo (la mejor zona ACCIONABLE ahí — nunca un gap viejo que el
        precio ya dejó atrás, ver W_ENTRY). Cada eslabón siguiente CONFIRMA
        si hay una zona en la misma dirección que se solapa con la anterior.
        La zona real a operar es siempre la más fina alcanzada.
        """
        anchor = req.anchor_interval if req.anchor_interval in self.CASCADE_CHAIN else "15m"
        chain = self.CASCADE_CHAIN[self.CASCADE_CHAIN.index(anchor):]

        now = datetime.now(timezone.utc).isoformat()

        first_data = self._scored_zones_for_interval(req.symbol, chain[0], req.limit)
        if first_data is None:
            return None
        df0, price0, zones0 = first_data

        bias_raw = next(
            (
                z for z in zones0
                if z["entry_status"] in ("IN_ZONE", "APPROACHING") and z.get("trend_aligned", True)
            ),
            None,
        )
        if bias_raw is None:
            return FvgCascadeResult(
                symbol=req.symbol, cascade_status="NONE", current_price=price0,
                confluence_score=0.0, analyzed_at=now,
            )

        built_by_interval: dict = {chain[0]: self._build_fvg_zone(bias_raw, df0, chain[0])}
        raw_by_step = [bias_raw]
        current_price = price0

        for interval in chain[1:]:
            data = self._scored_zones_for_interval(req.symbol, interval, 200)
            if data is None:
                break
            df_i, price_i, zones_i = data
            current_price = price_i
            prev_raw = raw_by_step[-1]
            matching = [
                z for z in zones_i
                if z["direction"] == prev_raw["direction"] and self._zones_overlap(z, prev_raw)
            ]
            if not matching:
                break
            raw = matching[0]
            built_by_interval[interval] = self._build_fvg_zone(raw, df_i, interval)
            raw_by_step.append(raw)

        remaining = len(chain) - len(raw_by_step)
        cascade_status = "READY" if remaining == 0 else ("AWAITING_EXECUTION" if remaining == 1 else "AWAITING_CONFIRMATION")
        entry_zone = built_by_interval[chain[len(raw_by_step) - 1]]

        return FvgCascadeResult(
            symbol=req.symbol,
            cascade_status=cascade_status,
            bias_zone=built_by_interval.get("15m"),
            confirmation_zone=built_by_interval.get("5m"),
            execution_zone=built_by_interval.get("1m"),
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
                    # AWAITING_CONFIRMATION ya es válido para el Top-5: desde el
                    # fix de analyze_cascade, el sesgo de 15m solo se elige si es
                    # accionable (IN_ZONE/APPROACHING) de verdad — exigir ADEMÁS
                    # que 5m ya haya confirmado en el mismo instante es un filtro
                    # tan estricto que casi nunca da resultados. "Top 5" es para
                    # descubrir setups vivos, no solo los ya perfectamente alineados.
                    if result and result.cascade_status in ("AWAITING_CONFIRMATION", "AWAITING_EXECUTION", "READY"):
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
