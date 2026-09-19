"""
ROUND 46b -- comparar contexto pre-entrada entre los extremos de
excursion (grandes ganadores vs perdidas inmediatas vs perdidas con
reversion) para encontrar el MECANISMO, no solo un feature aislado.
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r46_dataset.json")

FEATS = ["ret_1", "ret_3", "ret_5", "ret_10", "ret_20", "ma7_slope", "ma25_slope",
         "price_vs_ma7", "price_vs_ma25", "price_vs_ma50", "price_vs_ma99", "atr_rel",
         "dist_hi5", "dist_lo5", "dist_hi10", "dist_lo10", "dist_hi20", "dist_lo20",
         "dist_hi50", "dist_lo50", "vol_rel", "vol_pct", "body_ratio", "upper_wick_ratio",
         "lower_wick_ratio", "rsi14", "oi_chg_1h", "toptrader_ls", "global_ls", "funding",
         "accel_3_10", "compression_ratio", "vol_surge", "pos_in_range50", "pullback_vs_trend"]


def load():
    with open(DATA) as f:
        return json.load(f)


def summarize(pop, name):
    print(f"\n--- {name} (n={len(pop)}) ---")
    out = {}
    for f in FEATS:
        vals = np.array([r[f] for r in pop if r.get(f) is not None and np.isfinite(r[f])])
        if len(vals) < 10:
            continue
        out[f] = (float(np.median(vals)), float(np.mean(vals)), len(vals))
    return out


def main():
    rows = load()
    big_win = [r for r in rows if r["win"] and r["mfe"] >= 300]
    normal_win = [r for r in rows if r["win"] and r["mfe"] < 300]
    reversal_loss = [r for r in rows if not r["win"] and r["mfe"] >= 100]
    small_mfe_loss = [r for r in rows if not r["win"] and 30 <= r["mfe"] < 100]
    immediate_loss = [r for r in rows if not r["win"] and r["mfe"] < 30]

    groups = {"BIG_WIN(mfe>=300)": big_win, "NORMAL_WIN(<300)": normal_win,
              "REVERSAL_LOSS(mfe>=100)": reversal_loss, "SMALL_MFE_LOSS": small_mfe_loss,
              "IMMEDIATE_LOSS(mfe<30)": immediate_loss}
    summaries = {name: summarize(pop, name) for name, pop in groups.items()}

    print("\n" + "=" * 100)
    print("COMPARACION: BIG_WIN vs IMMEDIATE_LOSS (los dos extremos -- que separa un movimiento real de uno que muere ya)")
    print("=" * 100)
    bw, il = summaries["BIG_WIN(mfe>=300)"], summaries["IMMEDIATE_LOSS(mfe<30)"]
    diffs = []
    for f in FEATS:
        if f in bw and f in il:
            med_bw, mean_bw, n_bw = bw[f]
            med_il, mean_il, n_il = il[f]
            spread = abs(mean_bw) + abs(mean_il) + 1e-9
            rel_diff = abs(mean_bw - mean_il) / spread
            diffs.append((rel_diff, f, mean_bw, mean_il, n_bw, n_il))
    diffs.sort(reverse=True)
    for rel_diff, f, mean_bw, mean_il, n_bw, n_il in diffs[:15]:
        print(f"  {f:20s}: BIG_WIN mean={mean_bw:+.5f} (n={n_bw})  |  IMMEDIATE_LOSS mean={mean_il:+.5f} (n={n_il})  reldiff={rel_diff:.2f}")

    print("\n" + "=" * 100)
    print("COMPARACION: BIG_WIN vs REVERSAL_LOSS (mismo tipo de arranque, pero uno aguanta y el otro revierte)")
    print("=" * 100)
    rl = summaries["REVERSAL_LOSS(mfe>=100)"]
    diffs2 = []
    for f in FEATS:
        if f in bw and f in rl:
            med_bw, mean_bw, n_bw = bw[f]
            med_rl, mean_rl, n_rl = rl[f]
            spread = abs(mean_bw) + abs(mean_rl) + 1e-9
            rel_diff = abs(mean_bw - mean_rl) / spread
            diffs2.append((rel_diff, f, mean_bw, mean_rl, n_bw, n_rl))
    diffs2.sort(reverse=True)
    for rel_diff, f, mean_bw, mean_rl, n_bw, n_rl in diffs2[:15]:
        print(f"  {f:20s}: BIG_WIN mean={mean_bw:+.5f} (n={n_bw})  |  REVERSAL_LOSS mean={mean_rl:+.5f} (n={n_rl})  reldiff={rel_diff:.2f}")

    # side split (LONG vs SHORT) para cada grupo -- ¿el mecanismo es direccional?
    print("\n" + "=" * 100)
    print("DISTRIBUCION LONG/SHORT por grupo")
    print("=" * 100)
    for name, pop in groups.items():
        longs = sum(1 for r in pop if r["side"] == 1)
        print(f"  {name:26s}: LONG={longs}/{len(pop)} ({longs/max(1,len(pop)):.1%})")

    # perfil de origen por grupo (transversalidad)
    print("\n" + "=" * 100)
    print("PERFILES DE ORIGEN por grupo (evidencia de transversalidad)")
    print("=" * 100)
    import collections
    for name, pop in groups.items():
        c = collections.Counter(r["profile"] for r in pop)
        top = c.most_common(5)
        print(f"  {name:26s}: {top}")


if __name__ == "__main__":
    main()
