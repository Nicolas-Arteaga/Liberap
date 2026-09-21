"""Fase 1 iteration 2: isolate the three-slot admission constraint only."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

from fase1_caso3_replay_compare import BAR_MS, compare, millis, norm_reason, return_pct, summarize
from phase_slot_causal import build_candstream, run_policy


def normalized(trades):
    for trade in trades:
        trade["open_time"] = trade["open_ms"]
        trade["side"] = "short" if trade["side"] == 1 else "long"
        trade["reason"] = norm_reason(trade["reason"])
        trade["return_pct"] = return_pct(trade["side"], trade["entry"], trade["exit_px"])
    return trades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    stream = build_candstream()
    conn = sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro", uri=True)
    if args.smoke:
        _, trades = run_policy(conn, stream, "fifo", 0.5, 48)
        conn.close()
        print(json.dumps({"smoke": "ok", "base_trades": len(trades), "stream_signals": len(stream["stream"])}))
        return
    source = json.load(open(args.scratch, encoding="utf-8"))
    real = []
    for item in source:
        side = "short" if item["sl"] > item["entry"] else "long"
        real.append({"symbol": item["sym"], "side": side, "open_time": millis(item["open_utc"]),
                     "reason": norm_reason(item.get("real_outcome")), "return_pct": return_pct(side, item["entry"], item["exit_px"])})
    base_metrics, base = run_policy(conn, stream, "fifo", 0.5, 48)
    # Only changed factor: capacity. Keep candidate stream, policy, timeout, fees and daily guard unchanged.
    unbounded_stream = dict(stream)
    unbounded_stream["slots"] = 999
    unbounded_metrics, unbounded = run_policy(conn, unbounded_stream, "fifo", 0.5, 48)
    conn.close()
    base, unbounded = normalized(base), normalized(unbounded)
    measurable = [item for item in real if item["symbol"] in set(stream["active_order"])]
    base_cmp, unbounded_cmp = compare(base, real, BAR_MS), compare(unbounded, real, BAR_MS)
    payload = {
        "isolation": "slots_only",
        "unchanged": ["candidate stream", "fifo policy", "minRR 0.5", "timeout 48h", "fees", "daily guard", "exit evaluation"],
        "base_slots_3": {"metrics": base_metrics, "summary": summarize(base_cmp, base, len(real), len(measurable)), "comparison": base_cmp},
        "unbounded_slots_999": {"metrics": unbounded_metrics, "summary": summarize(unbounded_cmp, unbounded, len(real), len(measurable)), "comparison": unbounded_cmp},
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    json.dump(payload, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "base": payload["base_slots_3"]["summary"], "unbounded": payload["unbounded_slots_999"]["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
