"""Read-only readiness report for forward quote-spread collection."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_day(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()


def coverage_report(db_path: str, universe: set[str], *, min_days: int = 15) -> dict:
    """Summarise only recorded observations; never infer absent spread data."""
    if min_days < 1:
        raise ValueError("min_days must be positive")
    path = Path(db_path)
    if not path.exists():
        return {"status": "COST_V2_COVERAGE_MISSING", "symbols": {}, "ready": False,
                "required_days": min_days, "universe_size": len(universe)}
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        rows = conn.execute("""
            SELECT symbol, MIN(observed_ms), MAX(observed_ms), COUNT(*), COUNT(DISTINCT observed_ms / 86400000)
            FROM quote_spreads WHERE venue='binance_usdm' GROUP BY symbol
        """).fetchall()
    finally:
        conn.close()
    by_symbol = {
        symbol: {"first_observed_utc": _utc_day(first), "last_observed_utc": _utc_day(last),
                 "observations": int(count), "distinct_utc_days": int(days),
                 "meets_required_days": int(days) >= min_days}
        for symbol, first, last, count, days in rows if symbol in universe
    }
    covered = sum(1 for item in by_symbol.values() if item["meets_required_days"])
    return {"status": "COST_V2_COVERAGE_READY" if covered == len(universe) else "COST_V2_COVERAGE_PENDING",
            "ready": covered == len(universe) and bool(universe), "required_days": min_days,
            "universe_size": len(universe), "symbols_meeting_required_days": covered,
            "symbols": by_symbol}


def _load_universe(path: str) -> set[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    values = payload.get("symbols") or payload.get("universe")
    if not isinstance(values, list) or not values:
        raise ValueError("universe must contain a non-empty symbols/universe array")
    return {str(value).upper() for value in values}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--min-days", type=int, default=15)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = coverage_report(args.db, _load_universe(args.universe), min_days=args.min_days)
    output = json.dumps(report, sort_keys=True, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
