"""
ROUND 45c -- version vectorizada (numpy) de la mineria de r45b, mucho mas
rapida: construye matrices booleanas de condiciones por split y combina
con operaciones de array en vez de listas de comprehension por regla.
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


def build_matrix(rows):
    n = len(rows)
    side = np.array([r["side"] for r in rows], float)
    win = np.array([r["win"] for r in rows], bool)
    pnl = np.array([r["pnl"] for r in rows], float)
    feats = {}
    for f in CONT_FEATS + BOOL_FEATS:
        feats[f] = np.array([r[f] if r.get(f) is not None else np.nan for r in rows], float)
    return dict(side=side, win=win, pnl=pnl, feats=feats, n=n)


def build_conditions(train_mat):
    conds = []  # each: (name, mask_fn(mat)->bool array)
    for f in CONT_FEATS:
        v = train_mat["feats"][f]
        finite = v[np.isfinite(v)]
        if len(finite) < 100:
            continue
        qs = np.nanpercentile(finite, [20, 40, 60, 80])
        for q, label in zip(qs, ["p20", "p40", "p60", "p80"]):
            conds.append((f"{f}>={label}", f, ">=", q))
            conds.append((f"{f}<{label}", f, "<", q))
    for f in BOOL_FEATS:
        conds.append((f"{f}=True", f, ">=", 0.5))
        conds.append((f"{f}=False", f, "<", 0.5))
    return conds


def mask_for(mat, cond, side_val):
    _, feat, op, thr = cond
    v = mat["feats"][feat]
    valid = np.isfinite(v)
    m = (v >= thr) if op == ">=" else (v < thr)
    return valid & m & (mat["side"] == side_val)


def stats(mat, mask):
    n = int(mask.sum())
    if n == 0:
        return 0, 0.0, 0.0
    wr = float(mat["win"][mask].mean())
    pnl = float(mat["pnl"][mask].sum())
    return n, wr, pnl


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    train_rows, val_rows, oos_rows = rows[:i1], rows[i1:i2], rows[i2:]
    train, val, oos = build_matrix(train_rows), build_matrix(val_rows), build_matrix(oos_rows)
    base_rate = float(train["win"].mean())
    print(f"TRAIN={len(train_rows)} ({train_rows[0]['opened'][:10]}..{train_rows[-1]['opened'][:10]})  "
          f"VAL={len(val_rows)} ({val_rows[0]['opened'][:10]}..{val_rows[-1]['opened'][:10]})  "
          f"OOS={len(oos_rows)} ({oos_rows[0]['opened'][:10]}..{oos_rows[-1]['opened'][:10]})")
    print(f"Base win-rate TRAIN: {base_rate:.1%}\n")

    conds = build_conditions(train)
    print(f"Condiciones base: {len(conds)}")

    min_support = 40
    results = []
    for side_val in (1, -1):
        masks_train = {c[0]: mask_for(train, c, side_val) for c in conds}
        # singles
        for c in conds:
            m = masks_train[c[0]]
            n_, wr, pnl = stats(train, m)
            if n_ >= min_support:
                results.append(dict(names=[c[0]], conds=[c], side=side_val, n=n_, wr=wr, pnl=pnl))
        # pairs
        names = list(masks_train.keys())
        feat_of = {c[0]: c[1] for c in conds}
        cond_of = {c[0]: c for c in conds}
        for a, b in itertools.combinations(names, 2):
            if feat_of[a] == feat_of[b]:
                continue
            m = masks_train[a] & masks_train[b]
            n_ = int(m.sum())
            if n_ >= min_support:
                wr = float(train["win"][m].mean()); pnl = float(train["pnl"][m].sum())
                results.append(dict(names=[a, b], conds=[cond_of[a], cond_of[b]], side=side_val, n=n_, wr=wr, pnl=pnl))
    print(f"Reglas con soporte>=40 en TRAIN: {len(results)}\n")

    def eval_on(mat, side_val, conds_):
        m = np.ones(mat["n"], bool) & (mat["side"] == side_val)
        for c in conds_:
            m = m & mask_for(mat, c, side_val)
        return stats(mat, m)

    for r in results:
        r["lift"] = r["wr"] - base_rate
    results.sort(key=lambda r: (-r["lift"], -r["n"]))

    print("TOP 25 por lift TRAIN (referencia, sujeto a overfitting):")
    seen = set(); shown = []
    for r in results:
        key = tuple(r["names"]) + (r["side"],)
        if key in seen:
            continue
        seen.add(key); shown.append(r)
        if len(shown) >= 25:
            break
    for r in shown:
        n_val, wr_val, pnl_val = eval_on(val, r["side"], r["conds"])
        n_oos, wr_oos, pnl_oos = eval_on(oos, r["side"], r["conds"])
        side_lbl = "LONG" if r["side"] == 1 else "SHORT"
        desc = f"{side_lbl} | " + " & ".join(r["names"])
        print(f"  {desc:65s} TRAIN n={r['n']:4d} wr={r['wr']:.1%} | "
              f"VAL n={n_val:4d} wr={wr_val:.1%} pnl={pnl_val:7.1f} | "
              f"OOS n={n_oos:4d} wr={wr_oos:.1%} pnl={pnl_oos:7.1f}")

    print("\n" + "#" * 70)
    print("RE-RANKING ROBUSTO: exigiendo soporte>=15 en VAL Y OOS simultaneo,")
    print("ordenado por lift COMBINADO val+oos (no por el lift de TRAIN)")
    print("#" * 70)
    robust = []
    for r in results:
        n_val, wr_val, pnl_val = eval_on(val, r["side"], r["conds"])
        n_oos, wr_oos, pnl_oos = eval_on(oos, r["side"], r["conds"])
        if n_val >= 15 and n_oos >= 15:
            combined = (wr_val - base_rate) + (wr_oos - base_rate)
            robust.append(dict(r=r, n_val=n_val, wr_val=wr_val, pnl_val=pnl_val,
                                n_oos=n_oos, wr_oos=wr_oos, pnl_oos=pnl_oos, combined=combined))
    robust.sort(key=lambda x: -x["combined"])
    print(f"Reglas con soporte>=15 en VAL y OOS a la vez: {len(robust)}\n")
    seen2 = set(); shown2 = 0
    for x in robust:
        key = tuple(x["r"]["names"]) + (x["r"]["side"],)
        if key in seen2:
            continue
        seen2.add(key)
        side_lbl = "LONG" if x["r"]["side"] == 1 else "SHORT"
        desc = f"{side_lbl} | " + " & ".join(x["r"]["names"])
        print(f"  {desc:60s} TRAIN n={x['r']['n']:4d} wr={x['r']['wr']:.1%} | "
              f"VAL n={x['n_val']:4d} wr={x['wr_val']:.1%} pnl={x['pnl_val']:7.1f} | "
              f"OOS n={x['n_oos']:4d} wr={x['wr_oos']:.1%} pnl={x['pnl_oos']:7.1f}")
        shown2 += 1
        if shown2 >= 20:
            break
    if shown2 == 0:
        print("  NINGUNA regla con soporte serio en VAL+OOS simultaneo.")

    with open(os.path.join(HERE, "..", "..", "scratch_r45_robust_rules.json"), "w") as fo:
        json.dump([dict(names=x["r"]["names"], conds=x["r"]["conds"], side=x["r"]["side"],
                         n_train=x["r"]["n"], wr_train=x["r"]["wr"],
                         n_val=x["n_val"], wr_val=x["wr_val"], pnl_val=x["pnl_val"],
                         n_oos=x["n_oos"], wr_oos=x["wr_oos"], pnl_oos=x["pnl_oos"])
                    for x in robust[:20]], fo)


if __name__ == "__main__":
    main()
