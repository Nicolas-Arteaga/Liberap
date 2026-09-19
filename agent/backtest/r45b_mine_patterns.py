"""
ROUND 45b -- mineria de combinaciones ganador-vs-perdedor sobre el dataset
de r45_cross_profile_mining.py (2611 trades, contexto 100% causal).

Split temporal por OpenedAt: TRAIN (primer 60%) / VAL (siguiente 20%) /
OOS (ultimo 20%). Las reglas se MINAN solo en TRAIN (maximizando lift de
win-rate con soporte minimo), se miden (sin retocar) en VAL y OOS.
"""
import os, json, itertools
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r45_dataset.json")

CONT_FEATS = ["ret_1", "ret_3", "ret_5", "ret_10", "ret_20", "ma7_slope", "ma25_slope",
              "price_vs_ma7", "price_vs_ma25", "price_vs_ma50", "price_vs_ma99", "atr_rel",
              "dist_hi5", "dist_lo5", "dist_hi10", "dist_lo10", "dist_hi20", "dist_lo20",
              "dist_hi50", "dist_lo50", "vol_rel", "vol_pct", "body_ratio", "upper_wick_ratio",
              "lower_wick_ratio", "rsi14", "oi_chg_1h", "toptrader_ls", "global_ls", "funding"]
BOOL_FEATS = ["ma7_above_ma25", "ma7_above_ma99", "ma25_above_ma99"]


def load():
    with open(DATA) as f:
        rows = json.load(f)
    rows.sort(key=lambda r: r["ts"])
    return rows


def split(rows):
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    return rows[:i1], rows[i1:i2], rows[i2:]


def binarize_conditions(rows, feat):
    vals = np.array([r[feat] for r in rows if r.get(feat) is not None and np.isfinite(r[feat])])
    if len(vals) < 100:
        return []
    qs = np.nanpercentile(vals, [20, 40, 60, 80])
    conds = []
    for q, label in zip(qs, ["p20", "p40", "p60", "p80"]):
        conds.append((feat, ">=", q, f"{feat}>={label}"))
        conds.append((feat, "<", q, f"{feat}<{label}"))
    return conds


def match(r, cond):
    feat, op, thr, _ = cond
    v = r.get(feat)
    if v is None or not np.isfinite(v):
        return False
    return v >= thr if op == ">=" else v < thr


def eval_rule(rows, conds, side_filter=None):
    pop = [r for r in rows if (side_filter is None or r["side"] == side_filter)
           and all(match(r, c) for c in conds)]
    if not pop:
        return 0, 0.0, 0.0
    wins = sum(1 for r in pop if r["win"])
    pnl = sum(r["pnl"] for r in pop)
    return len(pop), wins / len(pop), pnl


def mine_single_and_pairs(train, base_rate, min_support=40):
    all_conds = []
    for f in CONT_FEATS:
        all_conds.extend(binarize_conditions(train, f))
    for f in BOOL_FEATS:
        all_conds.append((f, ">=", 0.5, f"{f}=True"))
        all_conds.append((f, "<", 0.5, f"{f}=False"))

    results = []
    for side in (1, -1):
        # singles
        for c in all_conds:
            n, wr, pnl = eval_rule(train, [c], side)
            if n >= min_support:
                results.append(dict(conds=[c], side=side, n=n, wr=wr, pnl=pnl, lift=wr - base_rate))
        # pairs (sample to keep it tractable)
        for c1, c2 in itertools.combinations(all_conds, 2):
            if c1[0] == c2[0]:
                continue
            n, wr, pnl = eval_rule(train, [c1, c2], side)
            if n >= min_support:
                results.append(dict(conds=[c1, c2], side=side, n=n, wr=wr, pnl=pnl, lift=wr - base_rate))
    results.sort(key=lambda r: (-r["lift"], -r["n"]))
    return results


def describe(rule):
    side = "LONG" if rule["side"] == 1 else "SHORT"
    conds = " & ".join(c[3] for c in rule["conds"])
    return f"{side} | {conds}"


def main():
    rows = load()
    train, val, oos = split(rows)
    base_rate = sum(1 for r in train if r["win"]) / len(train)
    print(f"TRAIN={len(train)} ({train[0]['opened'][:10]}..{train[-1]['opened'][:10]})  "
          f"VAL={len(val)} ({val[0]['opened'][:10]}..{val[-1]['opened'][:10]})  "
          f"OOS={len(oos)} ({oos[0]['opened'][:10]}..{oos[-1]['opened'][:10]})")
    print(f"Base win-rate TRAIN: {base_rate:.1%}\n")

    results = mine_single_and_pairs(train, base_rate, min_support=40)
    print(f"Reglas candidatas con soporte>=40 en TRAIN: {len(results)}\n")
    print("TOP 25 por lift de win-rate (TRAIN):")
    seen_desc = set()
    top = []
    for r in results:
        d = describe(r)
        if d in seen_desc:
            continue
        seen_desc.add(d)
        top.append(r)
        if len(top) >= 25:
            break
    for r in top:
        n_val, wr_val, pnl_val = eval_rule(val, r["conds"], r["side"])
        n_oos, wr_oos, pnl_oos = eval_rule(oos, r["conds"], r["side"])
        print(f"  {describe(r):70s} TRAIN n={r['n']:4d} wr={r['wr']:.1%} pnl={r['pnl']:8.1f} | "
              f"VAL n={n_val:4d} wr={wr_val:.1%} pnl={pnl_val:8.1f} | "
              f"OOS n={n_oos:4d} wr={wr_oos:.1%} pnl={pnl_oos:8.1f}")

    out = os.path.join(HERE, "..", "..", "scratch_r45_top_rules.json")
    with open(out, "w") as fo:
        json.dump([dict(conds=r["conds"], side=r["side"], n=r["n"], wr=r["wr"], pnl=r["pnl"]) for r in top], fo)
    print(f"\nGuardado top 25 en {out}")

    # Re-ranking: exigir soporte OOS minimo (evita que "sobrevive OOS" sea
    # un accidente de 2-3 trades) y ordenar por lift COMBINADO val+oos, no
    # por el lift de TRAIN (que es el que sufre data-dredging).
    print("\n" + "#" * 70)
    print("RE-RANKING: exigiendo soporte real en VAL y OOS (>=15 cada uno)")
    print("#" * 70)
    robust = []
    for r in results:
        n_val, wr_val, pnl_val = eval_rule(val, r["conds"], r["side"])
        n_oos, wr_oos, pnl_oos = eval_rule(oos, r["conds"], r["side"])
        if n_val >= 15 and n_oos >= 15:
            combined_lift = (wr_val - base_rate) + (wr_oos - base_rate)
            robust.append(dict(rule=r, n_val=n_val, wr_val=wr_val, pnl_val=pnl_val,
                                n_oos=n_oos, wr_oos=wr_oos, pnl_oos=pnl_oos, combined_lift=combined_lift))
    robust.sort(key=lambda x: -x["combined_lift"])
    print(f"Reglas con soporte>=15 en VAL Y OOS simultaneamente: {len(robust)}\n")
    seen = set()
    shown = 0
    for x in robust:
        d = describe(x["rule"])
        if d in seen:
            continue
        seen.add(d)
        r = x["rule"]
        print(f"  {d:60s} TRAIN n={r['n']:4d} wr={r['wr']:.1%} | "
              f"VAL n={x['n_val']:4d} wr={x['wr_val']:.1%} pnl={x['pnl_val']:7.1f} | "
              f"OOS n={x['n_oos']:4d} wr={x['wr_oos']:.1%} pnl={x['pnl_oos']:7.1f}")
        shown += 1
        if shown >= 20:
            break
    if shown == 0:
        print("  NINGUNA regla mantiene soporte>=15 simultaneo en VAL y OOS con lift positivo.")


if __name__ == "__main__":
    main()
