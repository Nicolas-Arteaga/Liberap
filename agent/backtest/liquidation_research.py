"""Liquidation-event eligibility gate for VIRE.

No event hypothesis may be backtested unless liquidation events overlap the
canonical OHLCV history for enough symbols and enough calendar time.
"""
from __future__ import annotations

import sqlite3


def assess(conn: sqlite3.Connection, liquidation_db_path: str, canonical_db_path: str | None = None, min_days: int = 30, min_symbols: int = 20) -> dict:
    # The primary key is exchange/symbol/interval/time, which is excellent for
    # one symbol but expensive for a venue-wide coverage check. This additive
    # index keeps the dashboard endpoint bounded as the multi-exchange archive
    # grows; it neither changes nor replaces market data.
    price_conn = conn
    if canonical_db_path:
        try:
            price_conn = sqlite3.connect(f"file:{canonical_db_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return {"mode": "liquidation_event_v1", "status": "REJECTED_DATA_UNAVAILABLE", "reason": str(exc)}
    if price_conn is conn:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_km_exchange_interval_time ON klines_multi_exchange(exchange, interval, open_time)")
        conn.commit()
    try:
        live = sqlite3.connect(f"file:{liquidation_db_path}?mode=ro", uri=True)
        rows, symbols, first, last = live.execute("SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(timestamp), MAX(timestamp) FROM liquidations_research").fetchone()
        live.close()
    except sqlite3.Error as exc:
        return {"mode": "liquidation_event_v1", "status": "REJECTED_DATA_UNAVAILABLE", "reason": str(exc)}
    # This venue-matched backfill is small (only liquidation symbols), so
    # precise MIN/MAX is safe and avoids assuming response insertion order.
    pfirst, plast = price_conn.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_multi_exchange WHERE exchange='bybit' AND interval='5m'").fetchone()
    overlap_start, overlap_end = max(int(first or 0), int(pfirst or 0)), min(int(last or 0), int(plast or 0))
    overlap_days = max(0.0, (overlap_end - overlap_start) / 86400000)
    price_symbols = price_conn.execute("SELECT COUNT(DISTINCT symbol) FROM klines_multi_exchange WHERE exchange='bybit' AND interval='5m'").fetchone()[0]
    if price_conn is not conn:
        price_conn.close()
    eligible = bool(rows and symbols >= min_symbols and price_symbols >= min_symbols and overlap_days >= min_days)
    return {"mode":"liquidation_event_v1","events":int(rows),"symbols":int(symbols),"price_symbols":int(price_symbols),"first_ms":first,"last_ms":last,"price_first_ms":pfirst,"price_last_ms":plast,"overlap_days":round(overlap_days,2),"status":"ELIGIBLE_FOR_HYPOTHESIS" if eligible else "REJECTED_INSUFFICIENT_HISTORICAL_OVERLAP","required_days":min_days,"required_symbols":min_symbols}
