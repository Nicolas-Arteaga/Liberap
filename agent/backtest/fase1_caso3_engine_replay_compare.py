"""Fase 1 iteration 1: replay using the production MA evaluator, then compare."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

from fase1_caso3_replay_compare import BAR_MS, compare, millis, norm_reason, return_pct, summarize
from phase_slot_causal import build_candstream, run_policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", action="store_true", help="Sólo valida imports y cache existente; no mide Gate 1.")
    args = parser.parse_args()
    if args.smoke:
        stream = build_candstream()
        conn = sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro", uri=True)
        metrics, trades = run_policy(conn, stream, "fifo", 0.5, 48)
        conn.close()
        print(json.dumps({"smoke": "ok", "stream_signals": len(stream["stream"]), "symbols": stream["n_syms"],
                          "executed_trades": len(trades), "metrics": metrics}))
        return

    source = json.load(open(args.scratch, encoding="utf-8"))
    real = []
    for item in source:
        side = "short" if item["sl"] > item["entry"] else "long"
        real.append({"symbol": item["sym"], "side": side, "open_time": millis(item["open_utc"]),
                     "reason": norm_reason(item.get("real_outcome")),
                     "return_pct": return_pct(side, item["entry"], item["exit_px"])})
    stream = build_candstream()
    conn = sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro", uri=True)
    metrics, trades = run_policy(conn, stream, "fifo", 0.5, 48)
    conn.close()
    for trade in trades:
        trade["open_time"] = trade["open_ms"]
        trade["side"] = "short" if trade["side"] == 1 else "long"
        trade["reason"] = norm_reason(trade["reason"])
        trade["return_pct"] = return_pct(trade["side"], trade["entry"], trade["exit_px"])
    measurable = [item for item in real if item["symbol"] in set(stream["active_order"])]
    comparison = compare(trades, real, BAR_MS)
    payload = {
        "run_mode": "production_ma_evaluator_autonomous_replay_then_compare",
        "baseline": {"slots": 3, "margin": 150.0, "timeout": "48h unconditional", "policy": "fifo", "bar_ms": BAR_MS},
        "stream": {"signals": len(stream["stream"]), "symbols": stream["n_syms"]},
        "coverage": {"real_total": len(real), "measurable": len(measurable), "missing": len(real)-len(measurable)},
        "metrics": metrics,
        "trades": trades,
        "comparison": comparison,
        "summary": summarize(comparison, trades, len(real), len(measurable)),
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    json.dump(payload, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "summary": payload["summary"], "stream": payload["stream"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
