"""Delta neto de funding para una revisión formal e inmutable del research loop.

Lee candidate.json/entries.jsonl en modo sólo lectura.  No materializa una
revisión, no toca el agente y no cambia StrategyProfiles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def _mean(values):
    return sum(values) / len(values) if values else None


def _duration_bucket(hours: float) -> str:
    if hours <= 1:
        return "<=1h"
    if hours <= 4:
        return "(1h,4h]"
    if hours <= 12:
        return "(4h,12h]"
    if hours <= 24:
        return "(12h,24h]"
    return ">24h"


def _event_bucket(n: int) -> str:
    return str(n) if n < 3 else "3+"


def _summarize(rows, key):
    buckets = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(row)
    out = {}
    for name, group in sorted(buckets.items()):
        before = _mean([r["ret_before_funding_pct"] for r in group])
        after = _mean([r["ret"] for r in group])
        out[name] = {"n": len(group), "net_before_funding_pct": before,
                     "net_after_funding_pct": after,
                     "delta_net_funding_pct": after - before,
                     "funding_events_total": sum(r["funding_event_count"] for r in group)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-dir", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--canonical-db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    os.environ["LAB_CANONICAL_DB"] = args.canonical_db
    sys.path.insert(0, str(Path(__file__).parent))
    import lab_audit as A
    from funding_history import FundingStore
    from lab_adapters import get_adapter
    from research_loop import FrozenAdapter

    revision = Path(args.revision_dir)
    candidate = json.loads((revision / "candidate.json").read_text(encoding="utf-8"))
    entries_path = revision / "entries.jsonl"
    actual_hash = hashlib.sha256(entries_path.read_bytes()).hexdigest()
    if actual_hash != candidate["entries_artifact"]["sha256"]:
        raise SystemExit("entries.jsonl no coincide con el hash del manifiesto")
    entries = [json.loads(line) for line in entries_path.read_text(encoding="utf-8").splitlines() if line]
    base = get_adapter(candidate["adapter_definition"]["name"])
    adapter = FrozenAdapter(base, entries)
    store = FundingStore(args.db)
    result, _report, rows = A.audit_adapter(adapter, entries=entries, funding_store=store, return_rows=True)
    if not result["valid"]:
        raise SystemExit(result.get("error", "auditoría funding inválida"))
    before = _mean([row["ret_before_funding_pct"] for row in rows])
    after = _mean([row["ret"] for row in rows])
    output = {
        "candidate_id": candidate["candidate_id"], "revision": candidate["revision"],
        "entries_sha256": actual_hash, "n": len(rows),
        "funding_validation": store.sign_validation_result(),
        "overall": {"net_before_funding_pct": before, "net_after_funding_pct": after,
                    "delta_net_funding_pct": after - before,
                    "funding_events_total": sum(r["funding_event_count"] for r in rows),
                    "trades_crossing_funding": sum(r["funding_event_count"] > 0 for r in rows)},
        "by_holding_duration": _summarize(rows, lambda r: _duration_bucket(r["age_h"])),
        "by_funding_windows": _summarize(rows, lambda r: _event_bucket(r["funding_event_count"])),
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
