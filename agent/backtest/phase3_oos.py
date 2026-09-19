"""
PHASE 3 §H — estabilidad Out-of-Sample. Consume scratch_gate_v4_results.json
(baseline_trades + real_trades por estrategia). Parte cada ventana por TIEMPO:
Discovery 40% / Validation 30% / Final OOS 30%. Sin tuning, sin threshold hunting.
"""
import os, sys, json, statistics as st
HERE = os.path.dirname(__file__)
RES = os.path.join(HERE, "..", "..", "scratch_gate_v4_results.json")


def pf(pnls):
    pos = sum(p for p in pnls if p > 0); neg = -sum(p for p in pnls if p < 0)
    return (pos / neg) if neg else (float("inf") if pos else float("nan"))


def cls(p):
    if p != p:
        return "?"
    return "W" if p > 1.05 else ("L" if p < 0.95 else "N")


def main():
    R = json.load(open(RES))
    print("=" * 96)
    print("PHASE 3 §H — OOS  (Discovery 40% / Validation 30% / Final OOS 30%, por tiempo)")
    print("=" * 96)
    print(f"{'estrategia':26} {'fuente':7} | {'Discovery':>18} | {'Validation':>18} | {'Final OOS':>18} | consistente?")
    rows = []
    for name, d in R.items():
        if name.startswith("_") or "window" not in d:
            continue
        wa, wb = d["window"]
        c1, c2 = wa + 0.40 * (wb - wa), wa + 0.70 * (wb - wa)
        for src, key, tkey in (("REAL", "real_trades", "open"), ("REPLAY", "baseline_trades", "open_time")):
            trs = d.get(key, [])
            seg = [[], [], []]
            for t in trs:
                ot = t[tkey]
                seg[0 if ot < c1 else (1 if ot < c2 else 2)].append(t["pnl"])
            pfs = [pf(s) for s in seg]
            ns = [len(s) for s in seg]
            clss = [cls(p) for p in pfs]
            consistent = len(set(x for x in clss if x != "?")) <= 1
            print(f"{name:26} {src:7} | "
                  + " | ".join(f"PF {p:5.2f} n{n:<3} {c}" for p, n, c in zip(pfs, ns, clss))
                  + f" | {'sí' if consistent else 'NO'}")
            rows.append((name, src, clss))
        print()

    # ── gate H ──
    print("=" * 96)
    agree_final = 0
    consistent_all = 0
    disagree_wl = []
    strategies = [n for n in R if not n.startswith("_") and "window" in R[n]]
    for name in strategies:
        real = next(r for r in rows if r[0] == name and r[1] == "REAL")[2]
        rep = next(r for r in rows if r[0] == name and r[1] == "REPLAY")[2]
        rf, bf = real[2], rep[2]   # Final OOS class
        if rf == bf and rf != "?":
            agree_final += 1
        if {rf, bf} == {"W", "L"}:
            disagree_wl.append(name)
        rc = len(set(x for x in real if x != "?")) <= 1
        bc = len(set(x for x in rep if x != "?")) <= 1
        if rc and bc:
            consistent_all += 1
    n = len(strategies)
    print(f"H — coinciden REAL/REPLAY en Final OOS: {agree_final}/{n}")
    print(f"H — clase consistente en los 3 segmentos (ambas fuentes): {consistent_all}/{n}")
    print(f"H — discrepancias loser<->winner en Final OOS: {disagree_wl}")
    H = "FAILED" if (agree_final <= n - 2 or disagree_wl) else ("PASS" if (agree_final == n and consistent_all >= n - 1) else "LIMITED")
    print(f"\nGATE H = {H}")


if __name__ == "__main__":
    main()
