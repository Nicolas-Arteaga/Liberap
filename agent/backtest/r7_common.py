"""Helpers compartidos Round 7 (causal z, causal pctile, cluster bootstrap)."""
import numpy as np

rng = np.random.default_rng(20260910)


def zscore_causal(a, win):
    n = len(a)
    x = np.nan_to_num(a, nan=0.0)
    ok = (~np.isnan(a)).astype(float)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    cq = np.concatenate([[0.0], np.cumsum(x * x)])
    ck = np.concatenate([[0.0], np.cumsum(ok)])
    i = np.arange(n)
    lo = i - win
    valid = lo >= 0
    lc = np.clip(lo, 0, None)
    out = np.full(n, np.nan)
    k = np.where(valid, ck[i] - ck[lc], 0.0)
    m = np.where(k > 0, (cs[i] - cs[lc]) / np.where(k > 0, k, 1), np.nan)
    v = np.where(k > 0, (cq[i] - cq[lc]) / np.where(k > 0, k, 1) - m * m, np.nan)
    s = np.sqrt(np.clip(v, 0, None))
    good = valid & (k >= win * 0.5) & (s > 0)
    out[good] = (a[good] - m[good]) / s[good]
    return out


def roll_mean_causal(a, win):
    """media rolling causal [t-win, t) (excluye la barra actual)."""
    n = len(a)
    x = np.nan_to_num(a, nan=0.0)
    ok = (~np.isnan(a)).astype(float)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    ck = np.concatenate([[0.0], np.cumsum(ok)])
    i = np.arange(n)
    lo = np.clip(i - win, 0, None)
    k = ck[i] - ck[lo]
    out = np.where(k > 0, (cs[i] - cs[lo]) / np.where(k > 0, k, 1), np.nan)
    out[i < win] = np.nan
    return out


def cluster_boot(sym_sum, sym_cnt, nboot=3000):
    idx = np.arange(len(sym_sum))
    bs = np.empty(nboot)
    for b in range(nboot):
        pick = rng.choice(idx, len(idx))
        d = sym_cnt[pick].sum()
        bs[b] = sym_sum[pick].sum() / d if d > 0 else 0.0
    return np.sort(bs) * 1e4


def agg_pairs(pairs, nboot=3000):
    """pairs: list[(sym, value_return_fraction)] -> dict de stats en bp."""
    if len(pairs) < 40:
        return {"n": len(pairs), "note": "muestra chica (<40)"}
    by = {}
    for s, v in pairs:
        by.setdefault(s, []).append(v)
    us = list(by)
    arr = {s: np.asarray(by[s], float) for s in us}
    allv = np.concatenate([arr[s] for s in us])
    sym_sum = np.array([arr[s].sum() for s in us])
    sym_cnt = np.array([len(arr[s]) for s in us], float)
    bs = cluster_boot(sym_sum, sym_cnt, nboot)
    pos = sym_sum[sym_sum > 0].sum() or 1e-9
    top5 = np.sort(sym_sum)[::-1][:5]
    half = len(allv) // 2
    return dict(
        n=int(len(allv)), n_sym=int(len(us)),
        mean_bp=round(float(allv.mean() * 1e4), 2),
        median_bp=round(float(np.median(allv) * 1e4), 2),
        ci_bp=[round(float(bs[int(0.05 * nboot)]), 2), round(float(bs[int(0.95 * nboot)]), 2)],
        ci_excl_0=bool(bs[int(0.05 * nboot)] > 0 or bs[int(0.95 * nboot)] < 0),
        frac_sym_pos=round(float((sym_sum > 0).mean()), 2),
        top5_conc=round(float(top5[top5 > 0].sum() / pos), 2),
        half1_bp=round(float(allv[:half].mean() * 1e4), 2),
        half2_bp=round(float(allv[half:].mean() * 1e4), 2),
        halves_same_sign=bool(np.sign(allv[:half].mean()) == np.sign(allv[half:].mean())),
    )
