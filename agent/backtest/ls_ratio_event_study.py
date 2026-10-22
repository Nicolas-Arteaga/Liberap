"""Frozen long/short ratio event family (research/preregistration/LS_RATIO_EVENT_FAMILY_V1.md).

Read-only: finalized 5m OHLCV + isolated OI-metrics store; emits a JSON report.
Implementation choices the preregistration leaves open are fixed here BEFORE
any result was seen and recorded in the report under ``implementation_notes``.
No parameter may be changed after running; there are no variants.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

T0 = 1_764_547_200_000          # 2025-12-01 00:00 UTC, first 5m bucket of the OI store
STEP = 300_000
RATIOS = ("toptrader_ls_pos", "global_ls_acct", "taker_ls_vol")
WINDOW = 672                    # 7d of 15m observations
MIN_VALID = 600                 # no imputation: z uses available obs, needs >=600 of 672
Z_EVENT, Z_CONTROL = 2.0, 0.3
COOLDOWN = 16                   # 4h in 15m steps
HORIZONS = {"1h": 4, "4h": 16, "8h": 32}   # 15m steps
PLACEBO = 192                   # +48h in 15m steps
COSTS = (10, 26, 36)
NBOOT = 4000
SEED = 20261021


def load_symbol(price_conn, oi_conn, symbol, n):
    rows = price_conn.execute("SELECT open_time, close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? ORDER BY open_time", (symbol, T0)).fetchall()
    if not rows:
        return None
    close = np.full(n, np.nan)
    for t, c in rows:
        k = (t - T0) // STEP
        if 0 <= k < n:
            close[k] = c
    oi = {r: np.full(n, np.nan) for r in RATIOS}
    q = f"SELECT open_time, {', '.join(RATIOS)} FROM oi_metrics WHERE symbol=? AND open_time>=? ORDER BY open_time"
    for row in oi_conn.execute(q, (symbol, T0)):
        k = (row[0] - T0) // STEP
        if 0 <= k < n:
            for j, r in enumerate(RATIOS):
                oi[r][k] = row[1 + j]
    return close, oi


def features(close, oi, n):
    """Return per-15m-decision arrays. Decision j closes at 5m index i=3j+2.
    Ratio visible at i is the 5m bucket i-1 (same conservative lag as the panel)."""
    m = (n - 2) // 3
    idx = 3 * np.arange(m) + 2
    px = close[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        ret1h = np.log(close[idx] / close[np.maximum(idx - 12, 0)])
        r5 = np.log(close[1:] / close[:-1]); r5 = np.concatenate(([np.nan], r5))
    rv = pd.Series(r5).rolling(48, min_periods=40).std().to_numpy()[idx]
    rvs = pd.Series(rv)
    qs = np.column_stack([rvs.rolling(WINDOW, min_periods=MIN_VALID).quantile(p).shift(1).to_numpy() for p in (.2, .4, .6, .8)])
    quint = np.where(np.isfinite(qs).all(axis=1), (rv[:, None] > qs).sum(axis=1), -1)
    z = {}
    for r in RATIOS:
        x = pd.Series(oi[r][idx - 1])
        mu = x.rolling(WINDOW, min_periods=MIN_VALID).mean().shift(1)
        sd = x.rolling(WINDOW, min_periods=MIN_VALID).std().shift(1)
        z[r] = ((x - mu) / sd.replace(0, np.nan)).to_numpy()
    fwd = {}
    for h, s in HORIZONS.items():
        f = np.full(m, np.nan)
        f[:m - s] = np.log(px[s:] / px[:m - s])
        fwd[h] = f
    return idx, px, ret1h, np.where(np.isfinite(rv), quint, -1), z, fwd


def shifted(a, s):
    out = np.full(len(a), np.nan)
    out[:len(a) - s] = a[s:]
    return out


def boot_mean(sym_sum, sym_cnt, rng):
    k = len(sym_sum)
    ix = rng.integers(0, k, size=(NBOOT, k))
    return sym_sum[ix].sum(axis=1) / sym_cnt[ix].sum(axis=1)


def stats(pairs, rng):
    """pairs: list of (symbol, value). Symbol-cluster bootstrap of the mean (bp)."""
    if len(pairs) < 2:
        return {"n": len(pairs)}
    by = {}
    for s, v in pairs:
        by.setdefault(s, []).append(v)
    syms = list(by)
    ss = np.array([sum(by[s]) for s in syms]); sc = np.array([len(by[s]) for s in syms], float)
    b = boot_mean(ss, sc, rng) * 1e4
    mean = ss.sum() / sc.sum() * 1e4
    p = min(1.0, 2 * (min((b <= 0).sum(), (b >= 0).sum()) + 1) / (NBOOT + 1))
    return {"n": int(sc.sum()), "n_sym": len(syms), "mean_bp": round(float(mean), 2),
            "ci95_bp": [round(float(np.percentile(b, 2.5)), 2), round(float(np.percentile(b, 97.5)), 2)],
            "ci_excl_0": bool(np.percentile(b, 2.5) > 0 or np.percentile(b, 97.5) < 0), "p": float(p)}


def bh(ps, q=.05):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); m = len(ps); thr = -1
    for rank, i in enumerate(order, 1):
        if ps[i] <= q * rank / m:
            thr = rank
    out = [False] * m
    for rank, i in enumerate(order, 1):
        if rank <= thr:
            out[i] = True
    return out


def run(price_db, oi_db, universe, end_ms):
    n = (end_ms - T0) // STEP
    symbols = json.loads(Path(universe).read_text(encoding="utf8"))["symbols"]
    pc = sqlite3.connect(f"file:{Path(price_db).resolve()}?mode=ro", uri=True)
    oc = sqlite3.connect(f"file:{Path(oi_db).resolve()}?mode=ro", uri=True)
    cells = {(r, tail, h): [] for r in RATIOS for tail in ("hi", "lo") for h in HORIZONS}
    used = 0
    for sym in symbols:
        d = load_symbol(pc, oc, sym, n)
        if d is None:
            continue
        idx, px, ret1h, quint, z, fwd = features(*d, n)
        if not np.isfinite(px).any():
            continue
        used += 1
        for r in RATIOS:
            zr = z[r]
            valid = np.isfinite(zr) & np.isfinite(ret1h) & (quint >= 0)
            for tail, mask in (("hi", valid & (zr >= Z_EVENT)), ("lo", valid & (zr <= -Z_EVENT))):
                ev, last = [], -10**9
                for j in np.flatnonzero(mask):
                    if j - last >= COOLDOWN:
                        ev.append(j); last = j
                if not ev:
                    continue
                ev = np.array(ev)
                ctrl = valid & (np.abs(zr) < Z_CONTROL)
                for h, s in HORIZONS.items():
                    f = fwd[h]; pf = shifted(f, PLACEBO)
                    # matched pool mean per (sign of prior 1h return, vol quintile), same symbol,
                    # control candidates sampled every 4h to avoid serial overlap
                    pool = {}
                    cj = np.flatnonzero(ctrl & np.isfinite(f) & (np.arange(len(f)) % COOLDOWN == 0))
                    for key in {(int(np.sign(ret1h[j])), int(quint[j])) for j in cj}:
                        sel = [j for j in cj if (int(np.sign(ret1h[j])), int(quint[j])) == key]
                        pool[key] = float(np.mean(f[sel]))
                    for j in ev:
                        if not np.isfinite(f[j]):
                            continue
                        key = (int(np.sign(ret1h[j])), int(quint[j]))
                        cells[(r, tail, h)].append({
                            "sym": sym, "t": int(T0 + STEP * idx[j]), "ret": float(f[j]),
                            "ctrl": pool.get(key), "plc": None if not np.isfinite(pf[j]) else float(pf[j])})
    return cells, used, n


def evaluate(cells, n, used):
    rng = np.random.default_rng(SEED)
    span_ms = n * STEP
    t_half, t_q1, t_q2 = T0 + span_ms // 2, T0 + span_ms // 2, T0 + span_ms * 3 // 4
    report, ps, keys = {}, [], []
    for key, ev in cells.items():
        name = "|".join(key)
        m = [e for e in ev if e["ctrl"] is not None]
        nsym = len({e["sym"] for e in m})
        entry = {"events_total": len(ev), "events_matched": len(m), "symbols": nsym}
        keys.append(name)
        if len(m) < 300 or nsym < 30:
            entry["status"] = "INSUFFICIENT_SAMPLE"; ps.append(1.0); report[name] = entry; continue
        inc = [(e["sym"], e["ret"] - e["ctrl"]) for e in m]
        entry["raw_event"] = stats([(e["sym"], e["ret"]) for e in m], rng)
        entry["incremental_vs_matched"] = stats(inc, rng)
        entry["placebo_raw"] = stats([(e["sym"], e["plc"]) for e in m if e["plc"] is not None], rng)
        h1 = [(e["sym"], e["ret"] - e["ctrl"]) for e in m if e["t"] < t_half]
        h2 = [(e["sym"], e["ret"] - e["ctrl"]) for e in m if e["t"] >= t_half]
        entry["half1"], entry["half2"] = stats(h1, rng), stats(h2, rng)
        entry["splits"] = {"TRAIN": stats([(e["sym"], e["ret"] - e["ctrl"]) for e in m if e["t"] < t_q1], rng),
                           "VALIDATION": stats([(e["sym"], e["ret"] - e["ctrl"]) for e in m if t_q1 <= e["t"] < t_q2], rng),
                           "OOS": stats([(e["sym"], e["ret"] - e["ctrl"]) for e in m if e["t"] >= t_q2], rng)}
        cnt = {}
        for e in m:
            cnt[e["sym"]] = cnt.get(e["sym"], 0) + 1
        frac = sorted((c / len(m) for c in cnt.values()), reverse=True)
        entry["max_symbol_share"], entry["top5_share"] = round(frac[0], 3), round(sum(frac[:5]), 3)
        entry["concentration_ok"] = bool(frac[0] <= .20 and sum(frac[:5]) <= .50)
        # economic view: direction implied by the sign of the incremental effect (post-hoc direction, flagged)
        sgn = 1 if entry["incremental_vs_matched"]["mean_bp"] >= 0 else -1
        rets = np.array(sorted(sgn * e["ret"] for e in m))
        trim = rets[:len(rets) - int(len(rets) * .05)]   # drop top 5% best event returns
        gross = float(rets.mean() * 1e4)
        entry["implied_direction"] = "long" if sgn > 0 else "short"
        entry["gross_bp_implied_dir"] = round(gross, 2)
        entry["gross_bp_trim_top5pct"] = round(float(trim.mean() * 1e4), 2)
        entry["net_bp_by_cost"] = {str(c): round(gross - c, 2) for c in COSTS}
        signs = {np.sign(gross - c) for c in COSTS}
        entry["economic"] = "PENDIENTE_cost_v2" if len(signs) > 1 else ("NET_POSITIVE_ALL_BANDS" if gross - COSTS[0] > 0 else "NET_NEGATIVE_ALL_BANDS")
        ps.append(entry["incremental_vs_matched"]["p"]); report[name] = entry
    sig = bh(ps)
    for name, s, p in zip(keys, sig, ps):
        e = report[name]; e["bh_p"] = p; e["bh_pass"] = bool(s)
        if e.get("status") == "INSUFFICIENT_SAMPLE":
            e["mechanism"] = "INSUFFICIENT_SAMPLE"; continue
        i = e["incremental_vs_matched"]; a, b = e["half1"], e["half2"]
        same = (a.get("mean_bp", 0) > 0) == (b.get("mean_bp", 0) > 0) == (i["mean_bp"] > 0)
        ok = i["ci_excl_0"] and a.get("ci_excl_0") and b.get("ci_excl_0") and same and e["bh_pass"] and e["concentration_ok"]
        e["mechanism"] = "PASS" if ok else "FAILED"
    return {"protocol": "LS_RATIO_EVENT_FAMILY_V1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbols_used": used, "cells": report,
            "implementation_notes": [
                "decision clock 15m; ratio taken from 5m bucket closing-1 (conservative lag as in microstructure_panel)",
                "z = (x - mean)/std over previous 672 15m obs, needs >=600 valid (no imputation)",
                "realized vol = std of last 48 5m log returns; quintile vs previous 672 obs",
                "matched control = mean forward return of same-symbol non-event points (|z|<0.3) with same prior-1h-return sign and vol quintile, sampled every 4h; events w/o pool dropped",
                "placebo = raw forward return starting +48h after the event, same horizon",
                "halves split at the midpoint of the study span; splits 50/25/25 by time over the span",
                "mechanism test is two-sided on the incremental effect; economic view uses the direction implied by its sign (post-hoc, therefore only descriptive)",
                "PASS needs incremental CI95 excl 0 in full and both halves with same sign, BH q=.05 over 18 cells (insufficient cells count as p=1), >=300 events/30 symbols, max symbol <=20%, top5 <=50%",
                "economic net PASS bar (>=15bp net, >=10bp after trimming top 5%) reported separately via net_bp_by_cost and gross_bp_trim_top5pct"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-db", required=True); ap.add_argument("--oi-db", required=True)
    ap.add_argument("--universe", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--end-ms", type=int, default=1_787_010_900_000)   # last 5m bucket of the price store
    a = ap.parse_args()
    cells, used, n = run(a.price_db, a.oi_db, a.universe, a.end_ms)
    res = evaluate(cells, n, used)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({k: v["mechanism"] for k, v in res["cells"].items()}, indent=1))


if __name__ == "__main__":
    main()
