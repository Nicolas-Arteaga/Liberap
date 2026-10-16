"""Read-only QA for the isolated historical OI backfill."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path


BUCKET_MS = 300_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{Path(args.db).resolve()}?mode=ro", uri=True)
    try:
        duplicates = conn.execute("""
            SELECT COUNT(*) FROM (SELECT symbol, open_time, COUNT(*) n FROM oi_metrics
            GROUP BY symbol, open_time HAVING n > 1)
        """).fetchone()[0]
        off_grid = conn.execute("SELECT COUNT(*) FROM oi_metrics WHERE open_time % ? != 0", (BUCKET_MS,)).fetchone()[0]
        per_symbol = []
        for symbol, count, first, last in conn.execute("""
            SELECT symbol, COUNT(*), MIN(open_time), MAX(open_time)
            FROM oi_metrics GROUP BY symbol ORDER BY symbol
        """):
            expected = (last - first) // BUCKET_MS + 1
            per_symbol.append({"symbol": symbol, "rows": count, "first_open_time": first,
                               "last_open_time": last, "expected_buckets": expected,
                               "missing_buckets": expected - count,
                               "coverage_pct": round(100 * count / expected, 6) if expected else 0.0})
    finally:
        conn.close()
    payload = {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "db": str(Path(args.db).resolve()),
        "checks": {
            "duplicates": {"value": duplicates, "pass": duplicates == 0},
            "timestamps_aligned_5m": {"off_grid_rows": off_grid, "pass": off_grid == 0},
            # Vision's create_time labeling is not proven from this CSV alone.
            # Consumers must lag one full bucket rather than choose a favorable
            # interpretation of open vs close semantics.
            "create_time_semantics": {"status": "AMBIGUOUS", "required_lag_ms": BUCKET_MS,
                                      "pass": True},
        },
        "summary": {"symbols": len(per_symbol), "symbols_90pct": sum(x["coverage_pct"] >= 90 for x in per_symbol)},
        "symbols": per_symbol,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if all(check["pass"] for check in payload["checks"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
