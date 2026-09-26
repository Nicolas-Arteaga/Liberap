"""Read-only schema and time-coverage inspection for local research SQLite DBs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
import argparse
import pickle
from pathlib import Path


PATHS = (
    "/app/research-canonical/binance_vision_clean.db",
    "/app/live-research/klines.db",
)
CUTOFF_MS = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
CACHE = Path("/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--ma3-symbols", action="store_true")
    parser.add_argument("--probe-symbol")
    args = parser.parse_args()
    ma3_symbols: list[str] = []
    if args.ma3_symbols:
        with CACHE.open("rb") as handle:
            stream = pickle.load(handle)["stream"]
        ma3_symbols = sorted({row[1] for row in stream})
    for path in PATHS:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
            print(f"{path}: {[name for (name,) in tables]}")
            for (table,) in tables:
                columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
                print(f"  {table}: {[column[1] for column in columns]}")
            if not args.ma3_symbols and path.endswith("binance_vision_clean.db"):
                print(
                    "  klines_5m_indexes: "
                    f"{connection.execute('PRAGMA index_list(klines_5m)').fetchall()}"
                )
            if args.schema_only:
                continue
            if args.probe_symbol:
                table = "klines_5m" if path.endswith("binance_vision_clean.db") else "klines"
                extra = "" if table == "klines_5m" else " AND is_final = 1"
                row = connection.execute(
                    f"SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM {table} "
                    f"WHERE symbol = ? AND interval = '5m'{extra} AND open_time >= ?",
                    (args.probe_symbol, CUTOFF_MS),
                ).fetchone()
                print(f"  probe_post_cutoff[{args.probe_symbol}]: {row}")
                continue
            if path.endswith("binance_vision_clean.db"):
                summary = connection.execute(
                    """
                    SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(open_time), MAX(open_time)
                    FROM klines_5m
                    WHERE interval = '5m' AND open_time >= ?
                    """,
                    (CUTOFF_MS,),
                ).fetchone()
                print(f"  post_cutoff_5m: {summary}")
            elif not args.ma3_symbols:
                summary = connection.execute(
                    """
                    SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(open_time), MAX(open_time)
                    FROM klines
                    WHERE interval = '5m' AND is_final = 1 AND open_time >= ?
                    """,
                    (CUTOFF_MS,),
                ).fetchone()
                print(f"  post_cutoff_5m_final: {summary}")
            if ma3_symbols:
                table = "klines_5m" if path.endswith("binance_vision_clean.db") else "klines"
                final_clause = "" if table == "klines_5m" else " AND is_final = 1"
                interval_clause = "interval = '5m'"
                placeholders = ",".join("?" for _ in ma3_symbols)
                rows = connection.execute(
                    f"SELECT symbol, COUNT(*), MIN(open_time), MAX(open_time) FROM {table} "
                    f"WHERE symbol IN ({placeholders}) AND {interval_clause}{final_clause} "
                    "AND open_time >= ? GROUP BY symbol",
                    (*ma3_symbols, CUTOFF_MS),
                ).fetchall()
                covered = [row for row in rows if row[1] > 0]
                print(
                    f"  post_cutoff_ma3_symbols: universe={len(ma3_symbols)} "
                    f"covered={len(covered)} rows={sum(row[1] for row in covered)} "
                    f"max_open_time={max((row[3] for row in covered), default=None)}"
                )
        finally:
            connection.close()


if __name__ == "__main__":
    main()
