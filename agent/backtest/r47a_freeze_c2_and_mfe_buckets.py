"""
ROUND 47a -- congela la formula exacta de C2 (R46) y analiza que
diferencia, DENTRO de la poblacion que ya cumple C2, un movimiento
mediocre (MFE<50bp) de uno grande (MFE>=300bp). Tambien evalua el
espejo LONG con la MISMA formula congelada (sin re-buscar thresholds).
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r46_dataset.json")


def f(r, feat):
    v = r.get(feat)
    return v if (v is not None and np.isfinite(v)) else None


def load():
    with open(DATA) as fh:
        rows = json.load(fh)
    rows.sort(key=lambda r: r["ts"])
    return rows


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6)
    train_rows = rows[:i1]

    # ---- FORMULA CONGELADA DE C2 (identica a R46c, no se retoca) ----
    train_trend_short = [r for r in train_rows if r["side"] == -1 and f(r, "price_vs_ma50") is not None
                          and f(r, "price_vs_ma50") < 0 and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                          and f(r, "accel_3_10") is not None]
    accel_median_short = float(np.median([r["accel_3_10"] for r in train_trend_short]))
    train_trend_long = [r for r in train_rows if r["side"] == 1 and f(r, "price_vs_ma50") is not None
                         and f(r, "price_vs_ma50") > 0 and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                         and f(r, "accel_3_10") is not None]
    accel_median_long = float(np.median([r["accel_3_10"] for r in train_trend_long]))

    print("=== FORMULA CONGELADA (idéntica a R46, umbrales SOLO de TRAIN) ===")
    print(f"C2 SHORT: side=-1 AND price_vs_ma50<0 AND ret_20<0 AND accel_3_10 >= {accel_median_short:.6f}")
    print(f"C1 LONG : side=1  AND price_vs_ma50>0 AND ret_20>0 AND accel_3_10 <= {accel_median_long:.6f}")
    print("SL/TP/exit: el que ya traia cada trade real (sin re-optimizar). Timeframe: 15m.")
    print("Entrada: al cierre de la vela que cumple la condicion (misma barra usada para calcular las features).\n")

    def c2(r):
        return (r["side"] == -1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") < 0
                and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") >= accel_median_short)

    def c1(r):
        return (r["side"] == 1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") > 0
                and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") <= accel_median_long)

    pop_c2 = [r for r in rows if c2(r)]
    pop_c1 = [r for r in rows if c1(r)]
    print(f"Poblacion TOTAL que cumple C2 (todo may-sep): {len(pop_c2)} trades")
    print(f"Poblacion TOTAL que cumple C1 (mirror LONG, misma formula congelada): {len(pop_c1)} trades\n")

    # ---- bucketizacion por MFE, DENTRO de la poblacion C2 ----
    buckets = [("<50bp", 0, 50), ("50-100bp", 50, 100), ("100-200bp", 100, 200),
               ("200-300bp", 200, 300), ("300-500bp", 300, 500), (">=500bp", 500, 1e9)]
    print("=== BUCKETIZACION POR MFE, dentro de C2 (SHORT) ===")
    bucketed = {}
    for label, lo, hi in buckets:
        pop = [r for r in pop_c2 if lo <= r["mfe"] < hi]
        bucketed[label] = pop
        wins = sum(1 for r in pop if r["win"])
        print(f"  {label:10s}: n={len(pop):3d}  win_rate={wins/max(1,len(pop)):.1%}  pnl_total={sum(r['pnl'] for r in pop):8.1f}")

    FEATS = ["ret_1", "ret_3", "ret_5", "ret_10", "ret_20", "ma7_slope", "ma25_slope",
              "price_vs_ma7", "price_vs_ma25", "price_vs_ma50", "price_vs_ma99", "atr_rel",
              "dist_hi5", "dist_lo5", "dist_hi10", "dist_lo10", "dist_hi20", "dist_lo20",
              "dist_hi50", "dist_lo50", "vol_rel", "vol_pct", "body_ratio", "upper_wick_ratio",
              "lower_wick_ratio", "rsi14", "oi_chg_1h", "toptrader_ls", "global_ls", "funding",
              "accel_3_10", "compression_ratio", "vol_surge", "pos_in_range50", "bars_to_mfe"]

    low = bucketed["<50bp"] + bucketed["50-100bp"]
    high = bucketed["300-500bp"] + bucketed[">=500bp"]
    print(f"\n=== COMPARACION: C2 mediocre (MFE<100bp, n={len(low)}) vs C2 grande (MFE>=300bp, n={len(high)}) ===")
    diffs = []
    for feat in FEATS:
        lo_v = np.array([r[feat] for r in low if r.get(feat) is not None and np.isfinite(r[feat])])
        hi_v = np.array([r[feat] for r in high if r.get(feat) is not None and np.isfinite(r[feat])])
        if len(lo_v) < 5 or len(hi_v) < 5:
            continue
        spread = abs(np.mean(lo_v)) + abs(np.mean(hi_v)) + 1e-9
        rel = abs(np.mean(lo_v) - np.mean(hi_v)) / spread
        diffs.append((rel, feat, np.mean(lo_v), np.mean(hi_v), len(lo_v), len(hi_v)))
    diffs.sort(reverse=True)
    for rel, feat, m_lo, m_hi, n_lo, n_hi in diffs[:15]:
        print(f"  {feat:20s}: mediocre mean={m_lo:+.5f}(n={n_lo})  |  grande mean={m_hi:+.5f}(n={n_hi})  reldiff={rel:.2f}")

    with open(os.path.join(HERE, "..", "..", "scratch_r47_c2_pop.json"), "w") as fo:
        json.dump(pop_c2, fo, default=str)
    with open(os.path.join(HERE, "..", "..", "scratch_r47_c1_pop.json"), "w") as fo:
        json.dump(pop_c1, fo, default=str)


if __name__ == "__main__":
    main()
