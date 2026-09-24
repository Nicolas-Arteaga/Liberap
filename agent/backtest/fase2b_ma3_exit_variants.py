"""Fase 2b: ATR stop-loss and time-based exits on the frozen MA3 raw-signal population.

Preregistered in MISION_LOG.md (commit 841a4f0) before this script was run.
Diagnostic-only: no production selection, no sizing, no dollar PnL.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sqlite3
from collections import defaultdict

import fase2_ma3_broad_matrix as m
import phase_slot_causal as causal

HOUR, BAR = m.HOUR, m.BAR
ATR_PERIOD = 14
COST = m.BASE_ROUND_TRIP_COST_PCT
NEW_VARIANTS = ("sl_atr_1.0", "sl_atr_1.5", "sl_atr_2.0", "time_exit_12h", "time_exit_24h",
                "time_exit_36h", "time_stop_24h_if_losing")
VARIANTS = ("baseline",) + NEW_VARIANTS
SCENARIOS = (("unconditional", -2.0), ("unconditional", 2.0), ("conditional", -2.0), ("conditional", 2.0))
PRIOR_BASELINE_OOS_UNCOND_M2 = 0.30710306548436167  # result.json of Fase 2, unconditional|tp_bias_-2


def hourly_series(rows):
    """Aggregate 5m rows -> closed 1h candles: (bucket_start, high, low, close)."""
    out, cur = [], None
    for ot, high, low, close in rows:
        bucket = ot - (ot % HOUR)
        if cur is None or cur[0] != bucket:
            if cur is not None:
                out.append(tuple(cur))
            cur = [bucket, high, low, close]
        else:
            cur[1] = max(cur[1], high)
            cur[2] = min(cur[2], low)
            cur[3] = close
    if cur is not None:
        out.append(tuple(cur))
    return out


def atr_before(hours, hour_starts, open_ms):
    """Simple mean of the last ATR_PERIOD true ranges over 1h candles closed before open_ms."""
    end = bisect.bisect_right(hour_starts, open_ms - HOUR)  # candle fully closed by open_ms
    if end < ATR_PERIOD + 1:
        return None
    trs = []
    for i in range(end - ATR_PERIOD, end):
        _, high, low, _ = hours[i]
        prev_close = hours[i - 1][3]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / ATR_PERIOD


def exit_new(rows, opens, trade, variant, timeout_mode, tp_bias_pp, atr):
    entry, side, sl0, tp = trade["entry"], trade["side"], trade["sl"], trade["tp"]
    sl = sl0
    if variant.startswith("sl_atr_") and atr:
        k = float(variant.split("_")[2])
        dist = min(abs(entry - sl0), k * atr)
        sl = entry + dist if side == 1 else entry - dist
    time_hours = {"time_exit_12h": 12, "time_exit_24h": 24, "time_exit_36h": 36}.get(variant)
    start = bisect.bisect_right(opens, trade["open_ms"])
    ceiling, timeout = 720 * HOUR, 48 * HOUR
    for ot, high, low, close in rows[start:]:
        age = ot + BAR - trade["open_ms"]
        if age > ceiling:
            return close, "timeout_hard_720"
        if side == 1:  # short: SL above, TP below
            if high >= sl:
                return sl, "SL"
            if low <= tp:
                return tp * (1 - tp_bias_pp / 100.0), "TP"
        else:
            if low <= sl:
                return sl, "SL"
            if high >= tp:
                return tp * (1 + tp_bias_pp / 100.0), "TP"
        if time_hours and age >= time_hours * HOUR:
            return close, "time_exit"
        if variant == "time_stop_24h_if_losing" and age >= 24 * HOUR and m.pct(side, entry, close) < 0:
            return close, "time_stop"
        if age >= timeout:
            if timeout_mode == "unconditional" or m.pct(side, entry, close) < 0:
                return close, "timeout_48"
    return rows[-1][3], "nodata"


def aggregate(values):
    if not values:
        return {"n": 0, "mean": None, "median": None}
    s = sorted(values)
    return {"n": len(s), "mean": sum(s) / len(s), "median": s[len(s) // 2]}


def diff(a, b):
    return None if a is None or b is None else a - b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", required=True, help="raw_ma3_243d.pkl from Fase 2")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--selftest", action="store_true",
                        help="compare exit_new(baseline) against fase2 exit_trade(baseline) on 400 trades, all scenarios")
    args = parser.parse_args()
    causal.WIN_A, causal.WIN_B, causal.KL_END = m.START, m.END, m.END + 720 * HOUR
    causal.CACHE = args.cache
    stream = causal.build_candstream()["stream"]
    trades = [{"open_ms": b, "symbol": s, "entry": e, "sl": sl, "tp": tp, "side": side} for b, s, e, sl, tp, side, _ in stream]
    if args.smoke:
        trades = trades[:40]
    conn = sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro", uri=True)
    if args.selftest:
        bad, total, rc = 0, 0, {}
        for trade in trades[::max(1, len(trades) // 400)][:400]:
            rows = m.rows_for(conn, trade["symbol"], rc)
            opens = [r[0] for r in rows]
            for mode, bias in SCENARIOS:
                old_px, old_reason, _ = m.exit_trade(rows, trade, "baseline", mode, bias)
                new_px, new_reason = exit_new(rows, opens, trade, "baseline", mode, bias, None)
                total += 1
                if abs(old_px - new_px) > 1e-12 or old_reason != new_reason:
                    bad += 1
        print(json.dumps({"selftest_total": total, "selftest_mismatch": bad}))
        return
    results = defaultdict(lambda: defaultdict(list))  # scenario -> variant -> [(split, net)]
    no_atr, cache = 0, {}
    for trade in trades:
        sym = trade["symbol"]
        if sym not in cache:
            rows = m.rows_for(conn, sym, {})
            hours = hourly_series(rows)
            cache[sym] = (rows, [r[0] for r in rows], hours, [h[0] for h in hours])
        rows, opens, hours, hour_starts = cache[sym]
        atr = atr_before(hours, hour_starts, trade["open_ms"])
        if atr is None:
            no_atr += 1
        split = m.split_for(trade["open_ms"])
        for variant in VARIANTS:
            for mode, bias in SCENARIOS:
                px, _ = exit_new(rows, opens, trade, variant, mode, bias, atr)
                net = m.pct(trade["side"], trade["entry"], px) - COST
                results[f"{mode}|tp_bias_{bias:+.0f}"][variant].append((split, net))
    conn.close()

    out = {"label": "HIPOTESIS; raw population is not production selection; preregistered in commit 841a4f0",
           "population": {"raw_signals": len(trades), "trades_without_atr_fallback_to_original_sl": no_atr},
           "families_tested_total_nonbaseline": 6 + len(NEW_VARIANTS), "scenarios": {}}
    for scen, byv in results.items():
        base = byv["baseline"]
        base_split = {sp: [v for s, v in base if s == sp] for sp in ("TRAIN", "VALIDATION", "OOS")}
        base_oos_top = sorted(base_split["OOS"], reverse=True)[3:]
        out["scenarios"][scen] = {}
        for variant, vals in byv.items():
            per = {sp: [v for s, v in vals if s == sp] for sp in ("TRAIN", "VALIDATION", "OOS")}
            deltas = {sp: diff(aggregate(per[sp])["mean"], aggregate(base_split[sp])["mean"]) for sp in per}
            top = sorted(per["OOS"], reverse=True)[3:]
            out["scenarios"][scen][variant] = {
                "oos": aggregate(per["OOS"]), "delta_vs_baseline_pp": deltas,
                "oos_without_top3_delta_pp": diff(aggregate(top)["mean"], aggregate(base_oos_top)["mean"]),
                "oos_cost_plus_50_mean": diff(aggregate(per["OOS"])["mean"], COST * 0.5),
            }
    # preregistered verdict per new variant
    verdicts = {}
    for variant in NEW_VARIANTS:
        ok_all = True
        for scen in out["scenarios"]:
            r = out["scenarios"][scen][variant]
            d = r["delta_vs_baseline_pp"]
            a = (d["OOS"] or 0) > 0
            b = (r["oos_without_top3_delta_pp"] or 0) > 0
            c = sum(1 for sp in d.values() if (sp or 0) > 0) >= 2
            if not (a and b and c):
                ok_all = False
        verdicts[variant] = "PASA criterio preregistrado (HIPOTESIS)" if ok_all else "NO pasa"
    out["verdict_preregistered"] = verdicts
    # regression check vs Fase 2 baseline
    chk = out["scenarios"]["unconditional|tp_bias_-2"]["baseline"]["oos"]["mean"]
    out["regression_check"] = {"expected": PRIOR_BASELINE_OOS_UNCOND_M2, "got": chk,
                               "ok": (abs(chk - PRIOR_BASELINE_OOS_UNCOND_M2) < 1e-9) if not args.smoke else None}
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "signals": len(trades), "no_atr": no_atr,
                      "regression_ok": out["regression_check"]["ok"], "verdicts": verdicts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
