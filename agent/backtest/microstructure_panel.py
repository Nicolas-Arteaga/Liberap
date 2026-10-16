"""Causal, read-only 5m panel builder for microstructure research.

The builder intentionally accepts explicit SQLite paths.  It never opens the
live agent cache for writing and it does not fabricate a value when a source is
missing.  OI and taker inputs are lagged one completed five-minute bucket;
funding is only exposed after its settlement timestamp.
"""
from __future__ import annotations

import bisect
import sqlite3
from dataclasses import dataclass
from pathlib import Path


FIVE_MIN_MS = 300_000


@dataclass(frozen=True)
class PanelPaths:
    price_db: str
    oi_db: str | None = None
    funding_db: str | None = None


def _rows(conn: sqlite3.Connection, query: str, args: tuple) -> list[tuple]:
    return conn.execute(query, args).fetchall()


def _latest_before(times: list[int], values: list[tuple], cutoff: int):
    index = bisect.bisect_right(times, cutoff) - 1
    return values[index] if index >= 0 else None


def _load_oi(path: str | None, symbol: str, start_ms: int, end_ms: int):
    if not path or not Path(path).exists():
        return [], []
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        rows = _rows(conn, """
            SELECT open_time, sum_oi, sum_oi_value, toptrader_ls_acct,
                   toptrader_ls_pos, global_ls_acct, taker_ls_vol
            FROM oi_metrics WHERE symbol=? AND open_time<=? ORDER BY open_time
        """, (symbol, end_ms))
    finally:
        conn.close()
    return [int(row[0]) for row in rows], rows


def _load_funding(path: str | None, symbol: str, end_ms: int):
    if not path or not Path(path).exists():
        return [], []
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        # FundingStore v1 uses funding_events; the legacy cache uses funding_hist.
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "funding_events" in names:
            rows = _rows(conn, """
                SELECT funding_time_ms, funding_rate FROM funding_events
                WHERE venue='binance_usdm' AND symbol=? AND rate_type='settlement_rate'
                  AND funding_time_ms<=? ORDER BY funding_time_ms
            """, (symbol, end_ms))
        elif "funding_hist" in names:
            rows = _rows(conn, "SELECT calc_time, funding_rate FROM funding_hist WHERE symbol=? AND calc_time<=? ORDER BY calc_time",
                         (symbol, end_ms))
        else:
            rows = []
    finally:
        conn.close()
    return [int(row[0]) for row in rows], rows


def build_5m_panel(symbol: str, start_ms: int, end_ms: int, paths: PanelPaths) -> list[dict]:
    """Return causal rows ordered by completed 5m bar open.

    At ``open_time=t``, price OHLC belongs to the bar that just closed at
    ``t+5m``.  External 5m inputs use only observations at or before ``t-5m``;
    this conservative lag avoids claiming knowledge of a bucket whose exact
    `create_time` semantics are still under audit.
    """
    price_path = Path(paths.price_db).resolve()
    conn = sqlite3.connect(f"file:{price_path}?mode=ro", uri=True)
    try:
        candles = _rows(conn, """
            SELECT open_time, open, high, low, close, volume
            FROM klines_clean WHERE symbol=? AND interval='5m'
              AND open_time>=? AND open_time<=? ORDER BY open_time
        """, (symbol, start_ms, end_ms))
        taker = _rows(conn, """
            SELECT open_time, volume, quote_volume, trade_count,
                   taker_buy_volume, taker_buy_quote
            FROM taker_flow WHERE symbol=? AND interval='5m'
              AND open_time<=? ORDER BY open_time
        """, (symbol, end_ms))
    finally:
        conn.close()
    oi_times, oi = _load_oi(paths.oi_db, symbol, start_ms, end_ms)
    funding_times, funding = _load_funding(paths.funding_db, symbol, end_ms)
    taker_times = [int(row[0]) for row in taker]
    output = []
    for open_time, op, high, low, close, volume in candles:
        cutoff = int(open_time) - FIVE_MIN_MS
        oi_row = _latest_before(oi_times, oi, cutoff)
        taker_row = _latest_before(taker_times, taker, cutoff)
        funding_row = _latest_before(funding_times, funding, int(open_time))
        output.append({
            "symbol": symbol, "open_time": int(open_time), "open": op, "high": high,
            "low": low, "close": close, "volume": volume,
            "oi": None if oi_row is None else {"observed_at": int(oi_row[0]), "sum_oi": oi_row[1],
                "sum_oi_value": oi_row[2], "toptrader_ls_acct": oi_row[3],
                "toptrader_ls_pos": oi_row[4], "global_ls_acct": oi_row[5], "taker_ls_vol": oi_row[6]},
            "taker_flow": None if taker_row is None else {"observed_at": int(taker_row[0]),
                "volume": taker_row[1], "quote_volume": taker_row[2], "trade_count": taker_row[3],
                "taker_buy_volume": taker_row[4], "taker_buy_quote": taker_row[5]},
            "funding": None if funding_row is None else {"settled_at": int(funding_row[0]), "rate": funding_row[1]},
        })
    return output
