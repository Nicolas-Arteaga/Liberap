"""Write a read-only daily coverage/gap report for append-only liquidation research."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


FIVE_MINUTES_MS = 300_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(__file__).with_name("data") / "klines.db")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = conn.execute("""
        SELECT symbol, COUNT(*), MIN(timestamp), MAX(timestamp), MAX(ingested_at)
        FROM liquidations_research GROUP BY symbol ORDER BY symbol
    """).fetchall()
    health = conn.execute("""
        SELECT ts, event, symbols_subscribed, events_since_last, note
        FROM liq_collector_health ORDER BY ts DESC LIMIT 288
    """).fetchall()
    conn.close()

    symbols = {}
    for symbol, count, first, last, ingested in rows:
        symbols[symbol] = {
            "events": count,
            "first_event_ms": first,
            "last_event_ms": last,
            "last_ingested_ms": ingested,
            "span_hours": round((last - first) / 3_600_000, 3) if first is not None else 0.0,
        }
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_db": str(args.db),
        "summary": {
            "symbols": len(symbols),
            "events": sum(item["events"] for item in symbols.values()),
            "last_event_age_minutes": min(
                ((now_ms - item["last_event_ms"]) / 60_000 for item in symbols.values() if item["last_event_ms"]),
                default=None,
            ),
        },
        "symbols": symbols,
        "recent_health": [
            {"ts": row[0], "event": row[1], "symbols_subscribed": row[2], "events_since_last": row[3], "note": row[4]}
            for row in health
        ],
        "monitoring_rule": "Investigate if no heartbeat is present for >10 minutes; do not infer outage from quiet markets alone.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
