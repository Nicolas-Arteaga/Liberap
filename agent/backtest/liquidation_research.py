"""Liquidation-event eligibility gate for VIRE.

No event hypothesis may be backtested unless liquidation events overlap the
canonical OHLCV history for enough symbols and enough calendar time.
"""
from __future__ import annotations

import sqlite3
import statistics
import time


_CACHE: dict[tuple[str, str | None, int, int], tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 300


def assess(conn: sqlite3.Connection, liquidation_db_path: str, canonical_db_path: str | None = None, min_days: int = 30, min_symbols: int = 20) -> dict:
    key = (liquidation_db_path, canonical_db_path, min_days, min_symbols)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return {**cached[1], "cache_age_seconds": round(time.monotonic() - cached[0], 2)}
    # The primary key is exchange/symbol/interval/time, which is excellent for
    # one symbol but expensive for a venue-wide coverage check. This additive
    # index keeps the dashboard endpoint bounded as the multi-exchange archive
    # grows; it neither changes nor replaces market data.
    price_conn = conn
    if canonical_db_path:
        try:
            price_conn = sqlite3.connect(f"file:{canonical_db_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            result = {"mode": "liquidation_event_v1", "status": "REJECTED_DATA_UNAVAILABLE", "reason": str(exc)}
            _CACHE[key] = (time.monotonic(), result); return result
    if price_conn is conn:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_km_exchange_interval_time ON klines_multi_exchange(exchange, interval, open_time)")
        conn.commit()
    try:
        live = sqlite3.connect(f"file:{liquidation_db_path}?mode=ro", uri=True)
        rows, symbols, first, last = live.execute("SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(timestamp), MAX(timestamp) FROM liquidations_research").fetchone()
        live.close()
    except sqlite3.Error as exc:
        result = {"mode": "liquidation_event_v1", "status": "REJECTED_DATA_UNAVAILABLE", "reason": str(exc)}
        _CACHE[key] = (time.monotonic(), result); return result
    # Do not use a venue-wide MIN/MAX here.  That would let price candles for
    # BTC prove coverage for a liquidation event in an unrelated altcoin.  A
    # liquidation hypothesis is only causal when its *own* symbol has enough
    # matched venue candles before and after its events.
    pfirst, plast = price_conn.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_multi_exchange WHERE exchange='bybit' AND interval='5m'").fetchone()
    liquidation_ranges = []
    try:
        live = sqlite3.connect(f"file:{liquidation_db_path}?mode=ro", uri=True)
        liquidation_ranges = live.execute(
            "SELECT symbol, MIN(timestamp), MAX(timestamp) FROM liquidations_research GROUP BY symbol"
        ).fetchall()
        live.close()
    except sqlite3.Error:
        liquidation_ranges = []
    overlaps: list[float] = []
    matched_symbols = 0
    for symbol, event_first, event_last in liquidation_ranges:
        candle_first, candle_last = price_conn.execute(
            "SELECT MIN(open_time), MAX(open_time) FROM klines_multi_exchange "
            "WHERE exchange='bybit' AND symbol=? AND interval='5m'", (symbol,)
        ).fetchone()
        if candle_first is None or candle_last is None:
            continue
        matched_symbols += 1
        overlap_start, overlap_end = max(int(event_first), int(candle_first)), min(int(event_last), int(candle_last))
        overlaps.append(max(0.0, (overlap_end - overlap_start) / 86400000))
    # Median is representative of the actual common-symbol coverage; the
    # eligibility decision itself is stricter and requires enough individual
    # symbols to meet the full history requirement.
    overlap_days = statistics.median(overlaps) if overlaps else 0.0
    eligible_symbols = sum(days >= min_days for days in overlaps)
    price_symbols = matched_symbols
    if price_conn is not conn:
        price_conn.close()
    eligible = bool(rows and eligible_symbols >= min_symbols)
    result = {"mode":"liquidation_event_v1","events":int(rows),"symbols":int(symbols),"price_symbols":int(price_symbols),"eligible_symbols":int(eligible_symbols),"first_ms":first,"last_ms":last,"price_first_ms":pfirst,"price_last_ms":plast,"overlap_days":round(overlap_days,2),"status":"ELIGIBLE_FOR_HYPOTHESIS" if eligible else "REJECTED_INSUFFICIENT_HISTORICAL_OVERLAP","required_days":min_days,"required_symbols":min_symbols}
    _CACHE[key] = (time.monotonic(), result)
    return result
