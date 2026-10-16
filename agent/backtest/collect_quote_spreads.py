"""Append-only public Binance USD-M best-bid/best-ask collector for research.

This is deliberately independent of the live agent.  It reads the public
``/fapi/v1/ticker/bookTicker`` endpoint and writes only an isolated SQLite
file supplied with ``--db``.  It never creates orders, profile writes, ledger
writes, or a production endpoint.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import time
from pathlib import Path
from urllib.request import urlopen


ENDPOINT = "https://fapi.binance.com/fapi/v1/ticker/bookTicker"
VENUE = "binance_usdm"


def now_ms() -> int:
    return int(time.time() * 1000)


def load_universe(path: str) -> set[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    values = payload.get("symbols") or payload.get("universe")
    if not isinstance(values, list) or not values:
        raise ValueError("universe must contain a non-empty symbols/universe array")
    return {str(value).upper() for value in values}


def fetch_book_ticker():
    with urlopen(ENDPOINT, timeout=20) as response:  # nosec B310: fixed public read-only endpoint
        return json.loads(response.read().decode("utf-8"))


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quote_spreads (
          venue TEXT NOT NULL,
          symbol TEXT NOT NULL,
          observed_ms INTEGER NOT NULL,
          bid REAL NOT NULL,
          ask REAL NOT NULL,
          bid_qty REAL,
          ask_qty REAL,
          source TEXT NOT NULL,
          PRIMARY KEY (venue, symbol, observed_ms)
        );
        CREATE INDEX IF NOT EXISTS idx_quote_spreads_symbol_time
          ON quote_spreads(venue, symbol, observed_ms);
        CREATE TABLE IF NOT EXISTS spread_stats (
          venue TEXT NOT NULL,
          symbol TEXT NOT NULL,
          utc_hour INTEGER NOT NULL,
          sample_count INTEGER NOT NULL,
          median_spread_bps REAL NOT NULL,
          p90_spread_bps REAL NOT NULL,
          median_top_notional_usdt REAL NOT NULL,
          refreshed_at_ms INTEGER NOT NULL,
          PRIMARY KEY (venue, symbol, utc_hour)
        );
    """)


def collect_once(db_path: str, universe: set[str], fetch=fetch_book_ticker, observed_ms: int | None = None) -> dict:
    observed_ms = now_ms() if observed_ms is None else int(observed_ms)
    raw = fetch()
    rows = []
    rejected = 0
    for item in raw:
        symbol = str(item.get("symbol", "")).upper()
        if symbol not in universe:
            continue
        try:
            bid, ask = float(item["bidPrice"]), float(item["askPrice"])
            bid_qty, ask_qty = float(item.get("bidQty", 0)), float(item.get("askQty", 0))
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        if bid <= 0 or ask < bid:
            rejected += 1
            continue
        rows.append((VENUE, symbol, observed_ms, bid, ask, bid_qty, ask_qty, "binance_fapi_bookTicker"))
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        ensure_schema(conn)
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO quote_spreads VALUES (?,?,?,?,?,?,?,?)", rows)
        inserted = conn.total_changes - before
        conn.commit()
    finally:
        conn.close()
    return {"venue": VENUE, "observed_ms": observed_ms, "eligible": len(rows),
            "inserted": inserted, "rejected": rejected, "universe_size": len(universe)}


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("empty sample")
    index = min(len(sorted_values) - 1, round((len(sorted_values) - 1) * q))
    return sorted_values[index]


def refresh_hourly_stats(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        groups: dict[tuple[str, str, int], list[tuple[float, float]]] = {}
        for venue, symbol, observed_ms, bid, ask, bid_qty, ask_qty in conn.execute(
            "SELECT venue,symbol,observed_ms,bid,ask,bid_qty,ask_qty FROM quote_spreads"
        ):
            mid = (bid + ask) / 2.0
            if mid <= 0:
                continue
            hour = int(observed_ms) // 3_600_000
            groups.setdefault((venue, symbol, hour), []).append(((ask - bid) / mid * 10_000, min(bid * bid_qty, ask * ask_qty)))
        updated = 0
        for (venue, symbol, hour), values in groups.items():
            spreads = sorted(value[0] for value in values)
            depth = sorted(value[1] for value in values)
            conn.execute("""
                INSERT INTO spread_stats VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(venue,symbol,utc_hour) DO UPDATE SET
                  sample_count=excluded.sample_count, median_spread_bps=excluded.median_spread_bps,
                  p90_spread_bps=excluded.p90_spread_bps,
                  median_top_notional_usdt=excluded.median_top_notional_usdt,
                  refreshed_at_ms=excluded.refreshed_at_ms
            """, (venue, symbol, hour, len(values), _percentile(spreads, .5), _percentile(spreads, .9),
                  _percentile(depth, .5), now_ms()))
            updated += 1
        conn.commit()
        return {"hourly_groups": updated}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--refresh-stats", action="store_true")
    args = parser.parse_args()
    if not args.once and not args.refresh_stats:
        parser.error("use --once and/or --refresh-stats")
    result = {}
    if args.once:
        result["collection"] = collect_once(args.db, load_universe(args.universe))
    if args.refresh_stats:
        result["stats"] = refresh_hourly_stats(args.db)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
