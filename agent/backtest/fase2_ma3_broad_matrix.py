"""Conditional Fase 2: frozen MA3 raw-signal population, path metrics and exit matrix.

This is diagnostic-only.  It intentionally does not model production selection,
position sizing, dollar PnL, or a claim of profitability.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

import phase_slot_causal as causal

HOUR = 3_600_000
BAR = 300_000
START = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
SPLITS = (("TRAIN", START, int(datetime(2026, 4, 26, tzinfo=timezone.utc).timestamp() * 1000)),
          ("VALIDATION", int(datetime(2026, 4, 26, tzinfo=timezone.utc).timestamp() * 1000), int(datetime(2026, 6, 14, tzinfo=timezone.utc).timestamp() * 1000)),
          ("OOS", int(datetime(2026, 6, 14, tzinfo=timezone.utc).timestamp() * 1000), END))
BASE_ROUND_TRIP_COST_PCT = 0.08  # phase_slot_causal.FEE: 0.04% each side


def pct(side, entry, price):
    return ((entry - price) / entry * 100.0) if side == 1 else ((price - entry) / entry * 100.0)


def split_for(ts):
    # Boundary fix (not a re-registered cutoff change): ma_precompute can
    # return a bucket exactly at END due to inclusive internal bucketing.
    # Only ts == END is treated as inclusive of the last split; TRAIN/VALIDATION/OOS
    # cutoffs themselves are untouched. See MISION_LOG.md.
    if ts == END:
        return SPLITS[-1][0]
    return next(name for name, left, right in SPLITS if left <= ts < right)


def rows_for(conn, symbol, cache):
    if symbol not in cache:
        cache[symbol] = conn.execute(
            "SELECT open_time, high, low, close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<? ORDER BY open_time",
            (symbol, START, END + 720 * HOUR),
        ).fetchall()
    return cache[symbol]


def exit_trade(rows, trade, variant, timeout_mode, tp_fill_bias_pp):
    """Causal OHLC exit: SL is evaluated before TP for same-bar ambiguity."""
    start = bisect.bisect_right([r[0] for r in rows], trade["open_ms"])
    timeout = 48 * HOUR
    ceiling = 720 * HOUR
    entry, side, original_sl, original_tp = trade["entry"], trade["side"], trade["sl"], trade["tp"]
    risk = abs(entry - original_sl)
    tp = original_tp if variant != "tp_short_50" else entry + (original_tp - entry) * 0.5
    sl = original_sl if variant != "sl_atr_1r" else entry + (original_sl - entry) * 1.0
    max_fav = 0.0
    breakeven = False
    for ot, high, low, close in rows[start:]:
        age = ot + BAR - trade["open_ms"]
        if age > ceiling:
            return close, "timeout_hard_720", ot + BAR
        favourable = pct(side, entry, low if side == 1 else high)
        max_fav = max(max_fav, favourable)
        if variant == "break_even_1r" and max_fav >= risk / entry * 100:
            breakeven = True
        effective_sl = entry if breakeven else sl
        if side == 1:
            if high >= effective_sl:
                return effective_sl, "break_even" if breakeven else "SL", ot + BAR
            if low <= tp:
                return tp * (1 - tp_fill_bias_pp / 100.0), "TP", ot + BAR
        else:
            if low <= effective_sl:
                return effective_sl, "break_even" if breakeven else "SL", ot + BAR
            if high >= tp:
                return tp * (1 + tp_fill_bias_pp / 100.0), "TP", ot + BAR
        if variant.startswith("giveback_") and max_fav > 0:
            giveback = float(variant.split("_")[1])
            observed = pct(side, entry, close)
            if max_fav - observed >= max_fav * giveback / 100.0:
                return close, "giveback", ot + BAR
        if variant == "trailing_2r" and max_fav >= 2 * risk / entry * 100:
            observed = pct(side, entry, close)
            if max_fav - observed >= 2 * risk / entry * 100:
                return close, "trailing", ot + BAR
        if age >= timeout:
            observed = pct(side, entry, close)
            if timeout_mode == "unconditional" or observed < 0:
                return close, "timeout_48", ot + BAR
    return rows[-1][3], "nodata", rows[-1][0] + BAR


def path_metrics(rows, trade):
    start = bisect.bisect_right([r[0] for r in rows], trade["open_ms"])
    window = [r for r in rows[start:] if r[0] + BAR <= trade["open_ms"] + 48 * HOUR]
    if not window:
        return None
    fav = [pct(trade["side"], trade["entry"], r[2] if trade["side"] == 1 else r[1]) for r in window]
    adverse = [pct(trade["side"], trade["entry"], r[1] if trade["side"] == 1 else r[2]) for r in window]
    peak = max(range(len(fav)), key=fav.__getitem__)
    return {"mfe_pct": fav[peak], "mae_pct": min(adverse), "giveback_pct": fav[peak] - pct(trade["side"], trade["entry"], window[-1][3]),
            "time_to_mfe_h": (window[peak][0] + BAR - trade["open_ms"]) / HOUR,
            "return_6h": _return_at(window, trade, 6), "return_12h": _return_at(window, trade, 12),
            "return_24h": _return_at(window, trade, 24), "return_48h": pct(trade["side"], trade["entry"], window[-1][3])}


def _return_at(rows, trade, hours):
    target = trade["open_ms"] + hours * HOUR
    eligible = [r for r in rows if r[0] + BAR <= target]
    return pct(trade["side"], trade["entry"], eligible[-1][3]) if eligible else None


def aggregate(rows):
    values = [r["net_return_pct"] for r in rows]
    return {"n": len(rows), "mean_net_return_pct": sum(values) / len(values) if values else None,
            "median_net_return_pct": sorted(values)[len(values) // 2] if values else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        print(json.dumps({"smoke": "ok", "population": "raw_ma3_signals", "start": START, "end": END, "splits": SPLITS}))
        return
    causal.WIN_A, causal.WIN_B, causal.KL_END = START, END, END + 720 * HOUR
    causal.CACHE = os.path.join(os.path.dirname(args.output), "raw_ma3_243d.pkl")
    stream = causal.build_candstream()["stream"]
    trades = [{"open_ms": b, "symbol": s, "entry": e, "sl": sl, "tp": tp, "side": side} for b, s, e, sl, tp, side, _ in stream]
    conn = sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro", uri=True)
    cache, paths = {}, []
    # sl_atr_1r excluded: its formula (entry + (original_sl - entry) * 1.0) is a
    # no-op identical to the original SL, discovered when its OOS numbers matched
    # baseline exactly in every scenario. Not silently redefined post-hoc (would be
    # an untested variant introduced after seeing results); left for a separate,
    # pre-registered iteration with a real ATR series. See MISION_LOG.md.
    variants = ("baseline", "tp_short_50", "giveback_10", "giveback_25", "giveback_50", "break_even_1r", "trailing_2r")
    scenarios = (("unconditional", -2.0), ("unconditional", 2.0), ("conditional", -2.0), ("conditional", 2.0))
    matrix = defaultdict(lambda: defaultdict(list))
    for trade in trades:
        rows = rows_for(conn, trade["symbol"], cache)
        metric = path_metrics(rows, trade)
        if metric:
            paths.append({"split": split_for(trade["open_ms"]), "symbol": trade["symbol"], **metric})
        for variant in variants:
            for timeout_mode, fill_bias in scenarios:
                exit_px, reason, close_ms = exit_trade(rows, trade, variant, timeout_mode, fill_bias)
                gross = pct(trade["side"], trade["entry"], exit_px)
                matrix[f"{timeout_mode}|tp_bias_{fill_bias:+.0f}"][variant].append({"split": split_for(trade["open_ms"]), "net_return_pct": gross - BASE_ROUND_TRIP_COST_PCT, "reason": reason, "close_ms": close_ms})
    conn.close()
    def path_summary(part):
        rows = [r for r in paths if r["split"] == part]
        if not rows:
            return {"n": 0}
        def m(key):
            vals = sorted(r[key] for r in rows if r.get(key) is not None)
            if not vals:
                return None
            return {"mean": sum(vals) / len(vals), "median": vals[len(vals) // 2], "n": len(vals)}
        return {"n": len(rows), "mfe_pct": m("mfe_pct"), "mae_pct": m("mae_pct"),
                "giveback_pct": m("giveback_pct"), "time_to_mfe_h": m("time_to_mfe_h"),
                "return_6h": m("return_6h"), "return_12h": m("return_12h"),
                "return_24h": m("return_24h"), "return_48h": m("return_48h")}

    output = {"label": "HIPOTESIS; raw population is not production selection", "population": {"raw_signals": len(trades), "window": [START, END], "splits": SPLITS},
              "path_metrics_48h": {part: path_summary(part) for part, _, _ in SPLITS},
              "variants_tested": len(variants), "scenarios": len(scenarios), "base_round_trip_cost_pct": BASE_ROUND_TRIP_COST_PCT, "matrix": {}}
    for scenario, by_variant in matrix.items():
        base = [r for r in by_variant["baseline"] if r["split"] == "OOS"]
        base_all = aggregate(base)
        output["matrix"][scenario] = {}
        for variant, values in by_variant.items():
            oos = [r for r in values if r["split"] == "OOS"]
            top3 = sorted(oos, key=lambda r: r["net_return_pct"], reverse=True)[3:]
            costly = [{**r, "net_return_pct": r["net_return_pct"] - BASE_ROUND_TRIP_COST_PCT * .5} for r in oos]
            row = {"oos": aggregate(oos), "oos_without_top3": aggregate(top3), "oos_cost_plus_50": aggregate(costly),
                   "delta_oos_vs_baseline_pp": (aggregate(oos)["mean_net_return_pct"] - base_all["mean_net_return_pct"]) if oos and base_all["n"] else None}
            output["matrix"][scenario][variant] = row
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "raw_signals": len(trades), "variants": len(variants), "scenarios": len(scenarios)}))


if __name__ == "__main__":
    main()
