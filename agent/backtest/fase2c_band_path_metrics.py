"""Fase 2c: descriptive path metrics for real Band Touch trades using 15m candles
from the live agent cache (klines.db). Read-only; no downloads; no dollar PnL.
N is small: everything here is a HYPOTHESIS, not evidence of edge.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3

BAR = 15 * 60 * 1000
HOUR = 3_600_000


def pct(side, entry, price):
    # side 1 = short (gain when price falls), same convention as Fase 2.
    return (entry - price) / entry * 100.0 if side == 1 else (price - entry) / entry * 100.0


def boot_ci(values, n=2000, seed=7):
    if len(values) < 3:
        return None
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(values) for _ in values) / len(values) for _ in range(n))
    return [means[int(n * .025)], means[int(n * .975)]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--db", default="/app/live-research/klines.db")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=10)
    rows_out, skipped = [], []
    for t in csv.DictReader(open(args.trades, encoding="utf8")):
        try:
            side, entry = int(t["side"]), float(t["entry"])
            open_ms, close_ms = int(float(t["open_ms"])), int(float(t["close_ms"]))
        except ValueError:
            skipped.append((t.get("symbol"), "bad_row"))
            continue
        candles = conn.execute(
            "SELECT open_time, high, low, close FROM klines WHERE symbol=? AND interval='15m' "
            "AND open_time>=? AND open_time+?<=? ORDER BY open_time",
            (t["symbol"], open_ms, BAR, close_ms)).fetchall()
        # Only candles fully inside [open, close]: the entry/exit candles contain
        # prices from before entry / after exit and would inflate MFE (lower-bound method).
        expected = max(1, (close_ms - open_ms) // BAR - 1)
        coverage = len(candles) / expected
        if len(candles) < 2 or coverage < 0.8:
            skipped.append((t["symbol"], "life_lt_2_full_candles" if expected < 2 else f"coverage_{coverage:.2f}"))
            continue
        fav = [pct(side, entry, c[2] if side == 1 else c[1]) for c in candles]
        adv = [pct(side, entry, c[1] if side == 1 else c[2]) for c in candles]
        peak = max(range(len(fav)), key=fav.__getitem__)
        mfe = max(0.0, fav[peak])
        final = pct(side, entry, float(t["close_price"])) if t.get("close_price") else pct(side, entry, candles[-1][3])
        life_h = (close_ms - open_ms) / HOUR
        t_mfe_h = (candles[peak][0] + BAR - open_ms) / HOUR
        rows_out.append({"symbol": t["symbol"], "life_h": life_h, "mfe_pct": mfe, "mae_pct": min(adv),
                         "final_return_pct": final, "giveback_pct": mfe - final, "time_to_mfe_h": t_mfe_h,
                         "censored_last10pct": t_mfe_h >= 0.9 * life_h, "exit_reason": t.get("exit_reason") or "unknown",
                         "coverage": coverage})
    summary = {"n_input": len(rows_out) + len(skipped), "n_measured": len(rows_out), "skipped": skipped,
               "label": "HIPOTESIS descriptiva, N chico, sin PnL USD, velas 15m completas dentro de la vida del trade (cota inferior de MFE)"}
    if rows_out:
        def mean(k): return sum(r[k] for r in rows_out) / len(rows_out)
        summary["mean"] = {k: mean(k) for k in ("life_h", "mfe_pct", "mae_pct", "final_return_pct", "giveback_pct", "time_to_mfe_h")}
        summary["boot95_mean_mfe"] = boot_ci([r["mfe_pct"] for r in rows_out])
        summary["boot95_mean_giveback"] = boot_ci([r["giveback_pct"] for r in rows_out])
        summary["censored_last10pct"] = sum(1 for r in rows_out if r["censored_last10pct"])
        thr = {}
        for th in (2, 5, 10):
            reached = [r for r in rows_out if r["mfe_pct"] >= th]
            thr[f"mfe>={th}%"] = {"n_reached": len(reached),
                                  "gave_back_ge50pct": sum(1 for r in reached if r["giveback_pct"] >= 0.5 * r["mfe_pct"]),
                                  "of_which_censored": sum(1 for r in reached if r["censored_last10pct"])}
        summary["thresholds"] = thr
        by = {}
        for r in rows_out:
            by.setdefault(r["exit_reason"], []).append(r)
        summary["by_exit_reason"] = {k: {"n": len(v), "mean_mfe": sum(x["mfe_pct"] for x in v) / len(v),
                                         "mean_final": sum(x["final_return_pct"] for x in v) / len(v)} for k, v in by.items()}
    with open(args.output, "w", encoding="utf-8") as h:
        json.dump({"summary": summary, "trades": rows_out}, h, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False)[:1800])


if __name__ == "__main__":
    main()
