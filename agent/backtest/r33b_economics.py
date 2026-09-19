"""
ROUND 33, PARTE B — convertir R-multiplo a bp REAL (el costo es fijo en
bp, pero R varia con la volatilidad -- rv_hi selecciona mecanicamente
barras de R mas grande, lo cual puede inflar el R-multiplo sin que haya
edge economico real). Se calcula bp = mean_R * R_bp_promedio - costo, y
se compara cada candidato contra el baseline SHORT incondicional al MISMO
TP -- exactamente el test de informacion incremental que faltaba en la
Fase 1-2, y el que R25 ya enseño que es obligatorio antes de creer
cualquier cosa del lado SHORT en este dataset.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST_RT_BP = 24.0
HORIZON = 96
STEP = 16
MIN_R = 0.0005


def load_all():
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    return P, F


def first_touch(hi, lo, tp_px, sl_px, side):
    if side > 0:
        tp_hits = hi >= tp_px; sl_hits = lo <= sl_px
    else:
        tp_hits = lo <= tp_px; sl_hits = hi >= sl_px
    tp_i = np.argmax(tp_hits) if tp_hits.any() else None
    sl_i = np.argmax(sl_hits) if sl_hits.any() else None
    if tp_i is None and sl_i is None:
        return "time", None
    if tp_i is None:
        return "sl", sl_i
    if sl_i is None:
        return "tp", tp_i
    if tp_i < sl_i:
        return "tp", tp_i
    if sl_i < tp_i:
        return "sl", sl_i
    return "tie", tp_i


def scan(P, F, seg, side, tp_mult, mask_by_sym=None):
    """devuelve list of (r_mult, r_bp_del_R_esa_entrada, seg, dy, symbol)."""
    out = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; h_ = d["h"]; lo_ = d["l"]; o = d["o"]; t = d["t"]; n = len(c)
        rv = f["rv"]
        idxs = np.where(mask_by_sym[s])[0] if mask_by_sym is not None else np.arange(ROLL, n - HORIZON - 2, STEP)
        for i in idxs:
            if i < ROLL or i + 1 + HORIZON >= n:
                continue
            R = rv[i]
            if not np.isfinite(R) or R < MIN_R:
                continue
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            e = i + 1
            entry_px = o[e]
            hi_w = h_[e:e + HORIZON]; lo_w = lo_[e:e + HORIZON]
            sl_px = entry_px * (1 - side * 1.0 * R)
            tp_px = entry_px * (1 + side * tp_mult * R)
            res, idx = first_touch(hi_w, lo_w, tp_px, sl_px, side)
            if res == "tp":
                r_mult = tp_mult
            elif res == "sl":
                r_mult = -1.0
            elif res == "tie":
                r_mult = (tp_mult - 1.0) / 2
            else:
                exit_px = o[e + HORIZON] if e + HORIZON < len(o) else c[min(e + HORIZON - 1, n - 1)]
                r_mult = side * math.log(exit_px / entry_px) / R
            out.append((r_mult, R * 1e4, seg(dy), dy, s))
    return out


def bp_econ(trades, segf):
    rows = [(r, rbp) for (r, rbp, sgv, dy, s) in trades if sgv == segf]
    if len(rows) < 30:
        return None
    arr = np.array(rows)
    bp_per_trade = arr[:, 0] * arr[:, 1]   # r_mult * R_en_bp = pnl en bp
    net_bp = bp_per_trade - COST_RT_BP
    return dict(n=len(arr), gross_mean_bp=bp_per_trade.mean(), net_mean_bp=net_bp.mean(),
                r_bp_avg=arr[:, 1].mean(), win_rate=(net_bp > 0).mean())


def main():
    print("=== ROUND 33B — CONVERSION A BP REAL + TEST DE INFORMACION INCREMENTAL vs BASELINE SHORT ===\n")
    P, F = load_all()
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")

    states = {}
    for s, f in F.items():
        states[s] = dict(
            rv_hi=np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= 0.90),
            ret1_hi=np.isfinite(f["ret1_pct"]) & (f["ret1_pct"] >= 0.90),
        )

    print("#" * 70 + "\n BASELINE SHORT incondicional (referencia obligatoria, mismo TP)\n" + "#" * 70)
    baseline_econ = {}
    for tp in (1.0, 2.0, 3.0):
        trades = scan(P, F, seg, -1, tp)
        for sgv in ("train", "val", "oos"):
            e = bp_econ(trades, sgv)
            if e:
                print(f"  BASELINE SHORT TP={tp:.0f}R {sgv:5s}: n={e['n']:6d} gross={e['gross_mean_bp']:+.2f}bp "
                      f"net={e['net_mean_bp']:+.2f}bp R_avg={e['r_bp_avg']:.1f}bp WR={e['win_rate']:.2f}")
            if sgv == "oos":
                baseline_econ[tp] = e

    print("\n" + "#" * 70 + "\n CONDICIONADOS (rv_hi, ret1_hi) — bp real y comparacion vs baseline\n" + "#" * 70)
    for state_name in ("rv_hi", "ret1_hi"):
        mask_by_sym = {s: states[s][state_name] for s in states}
        for tp in (1.0, 2.0, 3.0):
            trades = scan(P, F, seg, -1, tp, mask_by_sym=mask_by_sym)
            print(f"\n  -- {state_name}+SHORT TP={tp:.0f}R --")
            for sgv in ("train", "val", "oos"):
                e = bp_econ(trades, sgv)
                if not e:
                    continue
                print(f"    {sgv:5s}: n={e['n']:6d} gross={e['gross_mean_bp']:+.2f}bp net={e['net_mean_bp']:+.2f}bp "
                      f"R_avg={e['r_bp_avg']:.1f}bp WR={e['win_rate']:.2f}")
                if sgv == "oos" and tp in baseline_econ and baseline_econ[tp]:
                    base = baseline_econ[tp]
                    delta = e['net_mean_bp'] - base['net_mean_bp']
                    print(f"    >>> DELTA vs baseline SHORT incondicional (mismo TP, OOS): {delta:+.2f}bp neto "
                          f"({'aporta info incremental' if delta > 5 else 'NO aporta info incremental -- indistinguible de solo estar SHORT'})")

    print("\nfin R33B")


if __name__ == "__main__":
    main()
