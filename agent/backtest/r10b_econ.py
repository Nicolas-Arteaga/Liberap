"""
ROUND 10b — follow-up: el signal dOI (A/D SHORT) NO vive en DOWN sino en UP/FLAT.
Falta: (1) placebo de barras aleatorias por régimen, (2) per-symbol / leave-top-k,
(3) sim económica entrada open[t+1], para UP, FLAT y UP∪FLAT.
Definición congelada idéntica a r10. Costo RT conservador = 24 bp (fee 10 + spread 6
+ slip 8); funding aparte cuando el holding cruza settlement.
"""
import os, sys, json, math, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r9_oi_alpha import load_panel
from r10_doi_regime import build_feats, regime, HOR, hlabel, ROLL, W, REG_THR
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
RT_BP = 24.0
MARGIN = 300.0
rng = np.random.default_rng(20260913)


def main():
    P, bret, btpos = load_panel()
    F, btc_tr, mkt_cum = build_feats(P, bret, btpos)
    bc = P["BTCUSDT"]["c"]; btms = {int(t): i for i, t in enumerate(P["BTCUSDT"]["t"])}

    # eventos
    ev = []          # (sym, regime, day, i, entry_open_idx)
    randbars = {r: [] for r in ("UP", "FLAT", "DOWN")}
    for s, d in P.items():
        f = F[s]; c = d["c"]; o = d["o"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        last = {"A": -999, "D": -999}
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + 2 >= n:
                continue
            sr = np.sign(f["retW"][i]); so = np.sign(f["dOI"][i])
            q = "A" if (sr < 0 and so > 0) else ("D" if (sr > 0 and so < 0) else None)
            if q is None or i - last[q] < W:
                continue
            last[q] = i
            tms = int(d["t"][i]); reg = regime(btc_tr.get(tms))
            if reg is None:
                continue
            ev.append((s, reg, datetime.utcfromtimestamp(tms/1000).date(), i))
        # random bars por regimen (para placebo): 1 de cada 40
        for i in range(ROLL, n - max(HOR) - 2, 40):
            tms = int(d["t"][i]); reg = regime(btc_tr.get(tms))
            if reg is not None:
                randbars[reg].append((s, i))

    days = sorted(set(e[2] for e in ev))
    tcut, vcut = days[int(len(days)*0.5)], days[int(len(days)*0.75)]
    def seg(day): return "train" if day <= tcut else ("val" if day <= vcut else "oos")

    GROUPS = {"UP": ("UP",), "FLAT": ("FLAT",), "UPFLAT": ("UP", "FLAT")}
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "RT_BP": RT_BP}

    for gname, regs in GROUPS.items():
        sub = [e for e in ev if e[1] in regs]
        print(f"\n{'='*66}\nGRUPO {gname}  ·  n_eventos={len(sub)}\n{'='*66}")
        # --- placebo: random bars mismo(s) regimen(es) ---
        print("  PLACEBO random-bars (SHORT, mismo régimen):")
        for h in (8, 16, 32):
            rb = []
            for reg in regs:
                for (s, i) in randbars[reg]:
                    d = P[s]
                    if i + h < len(d["c"]):
                        rb.append((s, -math.log(d["c"][i+h]/d["c"][i])))
            R = agg_pairs(rb)
            print(f"    {hlabel(h):>3}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")
        # --- real por horizonte + TRAIN/VAL/OOS ---
        print("  REAL close-to-close (SHORT):")
        for h in HOR:
            allp = [(s, -math.log(P[s]["c"][i+h]/P[s]["c"][i])) for (s, r, dd, i) in sub if i+h < len(P[s]["c"])]
            R = agg_pairs(allp)
            segd = {}
            for sg in ("train", "val", "oos"):
                pp = [(s, -math.log(P[s]["c"][i+h]/P[s]["c"][i])) for (s, r, dd, i) in sub if seg(dd) == sg and i+h < len(P[s]["c"])]
                Rs = agg_pairs(pp)
                segd[sg] = Rs.get("mean_bp")
            print(f"    {hlabel(h):>3}: {R.get('mean_bp'):>7}bp CI[{R['ci_bp'][0]:.0f},{R['ci_bp'][1]:.0f}] excl0={R.get('ci_excl_0')} "
                  f"symPos={R.get('frac_sym_pos')} conc={R.get('top5_conc')} | TR={segd['train']} VAL={segd['val']} OOS={segd['oos']}")
        # --- per-symbol / leave-top-k @4h ---
        h = 16
        by = {}
        for (s, r, dd, i) in sub:
            if i + h < len(P[s]["c"]):
                by.setdefault(s, []).append(-math.log(P[s]["c"][i+h]/P[s]["c"][i]))
        sym_sum = {s: float(np.sum(v)) for s, v in by.items()}
        sym_mean = {s: float(np.mean(v)) for s, v in by.items()}
        order = sorted(sym_sum, key=lambda s: sym_sum[s], reverse=True)
        allv = np.concatenate([np.array(by[s]) for s in by])
        pos = sum(1 for s in sym_mean if sym_mean[s] > 0)
        print(f"  PER-SYMBOL @4h: nSym={len(by)} symPos={pos/len(by):.2f} media={allv.mean()*1e4:.1f}bp mediana_sym={np.median(list(sym_mean.values()))*1e4:.1f}bp")
        for k in range(1, 8):
            drop = set(order[:k])
            v = np.concatenate([np.array(by[s]) for s in by if s not in drop])
            print(f"    -top{k} ({','.join(list(drop)[:2])}..): {v.mean()*1e4:+.1f}bp n={len(v)}")
        # --- sim económica entrada open[t+1] ---
        print(f"  SIM ECON (entrada open[t+1], SHORT, RT={RT_BP}bp, margin=${MARGIN}):")
        span_days = (max(int(P[s]["t"][i+1]) for (s, r, dd, i) in sub) - min(int(P[s]["t"][i+1]) for (s, r, dd, i) in sub)) / 86400000
        for h in (8, 16, 32):
            g = []
            for (s, r, dd, i) in sub:
                e = i + 1
                if e + h < len(P[s]["o"]):
                    g.append(-math.log(P[s]["o"][e+h]/P[s]["o"][e]) * 1e4)
            g = np.array(g)
            fund = 1.5 * (h*15/480)     # ~1.5bp por 8h de holding (aprox medio funding)
            net = g - RT_BP - fund
            tr_mo = len(g) / (span_days/30)
            print(f"    {hlabel(h):>3} hold~{h*15/60:.1f}h: trades/mo={tr_mo:.0f} avg_g={g.mean():+.1f} avg_net={net.mean():+.1f}bp "
                  f"med_net={np.median(net):+.1f} WR={(net>0).mean():.2f} "
                  f"PF={net[net>0].sum()/max(1e-9,-net[net<0].sum()):.2f} NET/mo=${net.mean()*MARGIN/1e4*tr_mo:.0f}")
        out[gname] = {"n": len(sub)}

    json.dump(out, open(os.path.join(ROOT, "scratch_r10b_econ.json"), "w"), indent=1, default=str)
    print("\nok")


if __name__ == "__main__":
    main()
