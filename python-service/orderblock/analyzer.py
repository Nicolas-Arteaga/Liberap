import pandas as pd
import requests
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .schemas import (
    ObAnalyzeRequest, ObAnalyzeResponse, ObZone,
    ObScanRequest, ObScanResponse, ObScanItem,
)
from .detector import find_live_pending_blocks
from fvg.volume_profile import build_volume_profile, poc_distance_pct
from shared_kline_cache import get_or_fetch

logger = logging.getLogger("ORDERBLOCK")

# Mismos pesos/criterios que FVG (mismo mecanismo de confluencia, ver
# python-service/fvg/analyzer.py) -- entrar HOY pesa mas que cualquier otra
# cosa, el resto son desempates.
W_ENTRY = 0.5
W_POC = 0.3
W_FRESHNESS = 0.2

ENTRY_APPROACH_PCT = 0.5
POC_DIST_PCT_ZERO_AT = 0.5
MAX_ZONE_AGE_CANDLES = 60  # mismo MAX_CANDLES_TO_MITIGATION que el detector

# TP de liquidez real (identico en espiritu a FvgAnalyzer._liquidity_target
# y a agent/backtest/level_sweep_liquidity_tp.py -- validado con backtest
# real: SHORT+este TP+filtro POC = $92.26/mes, estable).
RECENT_IMPULSE_LOOKBACK = 40
DISPROPORTION_RATIO = 1.2
FADING_IMPULSE_TARGET_RATIO = 0.5
TP_HAIRCUT_RATIO = 0.9
SL_BUFFER_RATIO = 0.15
HVN_MAX_DIST_PCT = 0.5


class OrderBlockAnalyzer:
    def __init__(self):
        self.timeout = 8

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
                logger.warning(f"[OB] Binance Futures falló para {symbol}, intento spot: {e}")
                try:
                    r = requests.get(
                        "https://api.binance.com/api/v3/klines",
                        params={"symbol": clean_symbol, "interval": interval, "limit": limit},
                        timeout=self.timeout,
                    )
                    r.raise_for_status()
                    return r.json()
                except Exception as e2:
                    logger.error(f"[OB] Binance Spot también falló para {symbol}: {e2}")
                    return None

        return get_or_fetch(clean_symbol, interval, limit, _do_fetch)

    def _klines_to_df(self, raw: list) -> pd.DataFrame:
        df = pd.DataFrame(raw).iloc[:, :6]
        df.columns = ["open_time", "open", "high", "low", "close", "volume"]
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
        return df

    def _entry_status(self, top: float, bottom: float, current_price: float) -> tuple:
        if bottom <= current_price <= top:
            return "IN_ZONE", 0.0
        dist = (current_price - top) if current_price > top else (bottom - current_price)
        dist_pct = abs(dist) / current_price * 100.0 if current_price else 999.0
        status = "APPROACHING" if dist_pct <= ENTRY_APPROACH_PCT else "FAR"
        return status, round(dist_pct, 4)

    def _liquidity_tp(self, direction: str, entry: float, highs: list, lows: list, idx: int) -> Optional[float]:
        """Identico en espiritu a FvgAnalyzer._liquidity_target -- nivel de
        liquidez real (swing), con deteccion de impulso viejo desproporcionado
        y haircut del 10%. direction: 'bullish' (LONG, objetivo arriba) o
        'bearish' (SHORT, objetivo abajo)."""
        start = max(0, idx - 200)
        window_highs = highs[start:idx + 1]
        window_lows = lows[start:idx + 1]
        recent_start = max(start, idx - RECENT_IMPULSE_LOOKBACK)
        recent_highs = highs[recent_start:idx + 1]
        recent_lows = lows[recent_start:idx + 1]

        if direction == "bullish":
            swing_high, local_high = max(window_highs), max(recent_highs)
            if swing_high <= entry or local_high <= entry:
                return None
            local_reach, full_reach = local_high - entry, swing_high - entry
            raw_target = entry + full_reach * FADING_IMPULSE_TARGET_RATIO if full_reach > local_reach * DISPROPORTION_RATIO else swing_high
            return entry + (raw_target - entry) * TP_HAIRCUT_RATIO
        else:
            swing_low, local_low = min(window_lows), min(recent_lows)
            if swing_low >= entry or local_low >= entry:
                return None
            local_reach, full_reach = entry - local_low, entry - swing_low
            raw_target = entry - full_reach * FADING_IMPULSE_TARGET_RATIO if full_reach > local_reach * DISPROPORTION_RATIO else swing_low
            return entry - (entry - raw_target) * TP_HAIRCUT_RATIO

    def _build_zone(self, ob: dict, df: pd.DataFrame, bins: list, current_price: float,
                     highs: list, lows: list) -> ObZone:
        direction = ob["direction"]
        top, bottom = ob["ob_top"], ob["ob_bottom"]
        entry_status, dist_to_entry_pct = self._entry_status(top, bottom, current_price)

        dist_pct, overlapping = poc_distance_pct(top, bottom, bins)
        entry_price = top if direction == "bearish" else bottom  # borde de mitigacion real
        tp_price = self._liquidity_tp(direction, entry_price, highs, lows, len(df) - 1)
        tp_price = tp_price if tp_price is not None else entry_price

        gap_size = top - bottom
        sl_price = (bottom - gap_size * SL_BUFFER_RATIO) if direction == "bullish" else (top + gap_size * SL_BUFFER_RATIO)

        entry_score = 100.0 if entry_status == "IN_ZONE" else (
            max(0.0, 1.0 - dist_to_entry_pct / ENTRY_APPROACH_PCT) * 100.0 if entry_status == "APPROACHING" else 0.0
        )
        poc_score = max(0.0, 1.0 - dist_pct / POC_DIST_PCT_ZERO_AT) * 100.0
        age = len(df) - 1 - ob["bos_idx"]
        freshness_score = max(0.0, 100.0 - (age / MAX_ZONE_AGE_CANDLES) * 100.0)
        confluence_score = round(min(W_ENTRY * entry_score + W_POC * poc_score + W_FRESHNESS * freshness_score, 100.0), 1)

        tp_distance_pct = abs(tp_price - current_price) / current_price * 100.0 if current_price else 0.0

        return ObZone(
            id=f"ob_{direction}_{ob['ob_idx']}",
            direction=direction, top=top, bottom=bottom, bos_price=df["close"].iloc[ob["bos_idx"]],
            formed_at=datetime.fromtimestamp(ob["formed_at_ms"] / 1000, tz=timezone.utc).isoformat(),
            formed_at_ms=ob["formed_at_ms"], candle_index=ob["ob_idx"],
            entry_status=entry_status, dist_to_entry_pct=dist_to_entry_pct,
            poc_confluence=overlapping, poc_distance_pct=dist_pct,
            confluence_score=confluence_score, sl_price=round(sl_price, 8), tp_price=round(tp_price, 8),
            tp_distance_pct=round(tp_distance_pct, 4),
            validated_stable=(direction == "bearish"),  # ver nota en schemas.py -- SHORT es lo validado
        )

    def analyze_symbol(self, req: ObAnalyzeRequest) -> Optional[ObAnalyzeResponse]:
        raw = self._fetch_klines(req.symbol, req.interval, req.limit)
        if not raw or len(raw) < 100:
            return None
        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        highs, lows = df["high"].tolist(), df["low"].tolist()
        opens, closes, open_times = df["open"].tolist(), df["close"].tolist(), df["open_time"].tolist()

        pending = find_live_pending_blocks(opens, highs, lows, closes, open_times)
        bins_raw, _ = build_volume_profile(df)

        zones: List[ObZone] = []
        for ob in pending.values():
            if ob is not None:
                zones.append(self._build_zone(ob, df, bins_raw, current_price, highs, lows))
        zones.sort(key=lambda z: z.confluence_score, reverse=True)

        return ObAnalyzeResponse(
            symbol=req.symbol, interval=req.interval,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            current_price=current_price, zones=zones,
        )

    def scan(self, req: ObScanRequest) -> ObScanResponse:
        logger.info(f"[OB-SCAN] Escaneando {len(req.symbols)} símbolos en {req.interval}...")
        items: List[ObScanItem] = []

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._scan_symbol, s, req.interval, req.only_validated): s for s in req.symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item = future.result()
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning(f"[OB-SCAN] Error analizando {symbol}: {e}")

        if req.sort_by == "range":
            items.sort(key=lambda x: x.tp_distance_pct, reverse=True)
        else:
            items.sort(key=lambda x: x.confluence_score, reverse=True)
        top_5 = items[:5]
        logger.info(f"[OB-SCAN] Completo: {len(items)} accionables | top-5 devuelto")

        return ObScanResponse(
            top_5=top_5, scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat(), actionable_count=len(items),
        )

    def _scan_symbol(self, symbol: str, interval: str, only_validated: bool) -> Optional[ObScanItem]:
        raw = self._fetch_klines(symbol, interval, 300)
        if not raw or len(raw) < 100:
            return None
        df = self._klines_to_df(raw)
        current_price = float(df["close"].iloc[-1])
        highs, lows = df["high"].tolist(), df["low"].tolist()
        opens, closes, open_times = df["open"].tolist(), df["close"].tolist(), df["open_time"].tolist()

        pending = find_live_pending_blocks(opens, highs, lows, closes, open_times)
        candidates = [ob for ob in pending.values() if ob is not None]
        if only_validated:
            candidates = [ob for ob in candidates if ob["direction"] == "bearish"]  # SHORT-only validado
        if not candidates:
            return None

        bins_raw, _ = build_volume_profile(df)
        built = [self._build_zone(ob, df, bins_raw, current_price, highs, lows) for ob in candidates]
        actionable = [z for z in built if z.entry_status in ("IN_ZONE", "APPROACHING")]
        if not actionable:
            return None
        best = max(actionable, key=lambda z: z.confluence_score)

        return ObScanItem(
            symbol=symbol, direction=best.direction, top=best.top, bottom=best.bottom,
            current_price=current_price, poc_confluence=best.poc_confluence,
            poc_distance_pct=best.poc_distance_pct, entry_status=best.entry_status,
            dist_to_entry_pct=best.dist_to_entry_pct, sl_price=best.sl_price, tp_price=best.tp_price,
            tp_distance_pct=best.tp_distance_pct, confluence_score=best.confluence_score,
            formed_at=best.formed_at, validated_stable=best.validated_stable,
        )
