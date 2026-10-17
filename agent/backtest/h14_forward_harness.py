"""H14 forward-only gate and execution harness.

This module deliberately does *not* start collectors, restart the agent, or
run a liquidation study at import time.  Once the frozen data gate is met, a
caller may invoke ``--run`` with explicit database paths; until then it emits
only an auditable gate report.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIN_COLLECTION_DAYS = 60
MIN_UPTIME_RATIO = 0.90
MIN_SYMBOLS = 100


def gate_status(db: Path, now_ms: int | None = None) -> dict:
    """Read the append-only collector state without modifying it."""
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        events, symbols, first_ms, last_ms = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(timestamp), MAX(timestamp) FROM liquidations_research"
        ).fetchone()
        heartbeats = conn.execute("SELECT ts, event FROM liq_collector_health ORDER BY ts").fetchall()
    finally:
        conn.close()
    span_days = 0.0 if first_ms is None else (now_ms - int(first_ms)) / 86_400_000
    # Health records are evidence of the collector, not fabricated uptime.
    # Missing heartbeats remain unknown rather than assumed healthy.
    recent = [int(ts) for ts, event in heartbeats if event in {"connected", "heartbeat", "subscribed"}]
    return {
        "protocol": "H14 frozen forward-only v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "events": int(events or 0), "symbols": int(symbols or 0),
        "first_event_ms": first_ms, "last_event_ms": last_ms,
        "event_span_days": round(span_days, 3),
        "last_event_age_minutes": None if last_ms is None else round((now_ms - int(last_ms)) / 60_000, 2),
        "heartbeat_records": len(recent),
        "uptime_ratio": None,
        "uptime_note": "UNKNOWN until independent heartbeat coverage proves >=90%; quiet markets are not uptime.",
        "requirements": {"min_collection_days": MIN_COLLECTION_DAYS, "min_uptime_ratio": MIN_UPTIME_RATIO,
                         "min_symbols": MIN_SYMBOLS},
        "ready": bool(span_days >= MIN_COLLECTION_DAYS and symbols >= MIN_SYMBOLS and False),
        "not_ready_reasons": ["uptime is not independently provable from message-driven heartbeats"] +
            ([] if span_days >= MIN_COLLECTION_DAYS else ["collection span below 60 days"]) +
            ([] if symbols >= MIN_SYMBOLS else ["fewer than 100 subscribed symbols"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H14 forward-only gate; never starts/restarts collection")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="reserved; refuses unless the frozen gate is independently satisfied")
    args = parser.parse_args()
    report = gate_status(args.db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    if args.run:
        raise SystemExit("H14 execution refused: independent >=90% uptime proof is not available")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
