"""
ROUND 9 — OI HISTORICAL ALPHA HUNT.
Panel 15m (universo EX-ANTE congelado research/universe/oi_universe.json, 63 sym)
sobre binance_vision_clean.db:  klines_clean(15m) + taker_flow(15m) +
oi_metrics(5m->15m) + funding_hist(8h) + BTC/market return.

Experimentos (todo PRE-REGISTRADO, sin elegir horizonte/bucket post-hoc):
  H13C : cuadrantes price x dOI  (A: p- oi+ ; B: p- oi- ; C: p+ oi+ ; D: p+ oi-)
  H15  : 8 estados price x dOI x taker-aggression  (continuación vs exhaustion)
  H16  : funding extremo x dOI x price-trend  (¿OI aporta incremental sobre funding?)
  M15  : reaction-beta persistente ante shocks de BTC  (TRAIN->OOS, portfolio congelado)

Ventana W (lookback) = 4 barras (1h). z causal ROLL = 2880 (30d de 15m).
Horizontes = [1,2,4,8,16,32,96] barras = 15m/30m/1h/2h/4h/8h/24h.
Retorno forward = log(c[t+h]/c[t]) crudo (screen close-to-close) + variante
residualizada BTC. Costo screen (conservador) = 20 bp round-trip.
TRAIN/VAL/OOS = 50/25/25 por fecha de evento. Bootstrap por símbolo (cluster) y
por evento. Placebo temporal + matched control en cada experimento.
"""
import os, sqlite3, json, math, numpy as np
from datetime import datetime, timezone
from r7_common import zscore_causal, agg_pairs, rng

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
UNIV = os.path.join(HERE, "..", "..", "research", "universe", "oi_universe.json")
BAR = 15 * 60 * 1000
W = 4
ROLL = 2880
HOR = [1, 2, 4, 8, 16, 32, 96]
COST_RT_BP = 20.0
PLACEBO = 96
rng2 = np.random.default_rng(20260911)


def load_panel():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    syms = json.load(open(UNIV))["universe"]
    have_oi = set(s for (s,) in con.execute("SELECT DISTINCT symbol FROM oi_metrics"))
    have_tk = set(s for (s,) in con.execute("SELECT DISTINCT symbol FROM taker_flow WHERE interval='15m'"))
    P = {}
    for s in syms:
        if s not in have_oi:
            continue
        k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                        "WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
        if len(k) < ROLL + 400:
            continue
        kt = np.array([r[0] for r in k], np.int64)
        o = np.array([r[1] for r in k], float); h = np.array([r[2] for r in k], float)
        lo = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
        v = np.array([r[5] for r in k], float)
        pos = {int(t): i for i, t in enumerate(kt)}
        # taker (15m)
        tbr = np.full(len(kt), np.nan); qv = np.full(len(kt), np.nan)
        for ot, q, tbq in con.execute("SELECT open_time,quote_volume,taker_buy_quote FROM taker_flow "
                                      "WHERE symbol=? AND interval='15m'", (s,)):
            i = pos.get(int(ot))
            if i is not None and q and q > 0:
                tbr[i] = tbq / q; qv[i] = q
        # oi (5m -> tomar los múltiplos de 15m)
        oi = np.full(len(kt), np.nan); oiv = np.full(len(kt), np.nan)
        gls = np.full(len(kt), np.nan); ttls = np.full(len(kt), np.nan); tkls = np.full(len(kt), np.nan)
        for ot, so, sov, gl, tt, tk in con.execute(
                "SELECT open_time,sum_oi,sum_oi_value,global_ls_acct,toptrader_ls_pos,taker_ls_vol "
                "FROM oi_metrics WHERE symbol=? ORDER BY open_time", (s,)):
            if int(ot) % 900000 != 0:
                continue
            i = pos.get(int(ot))
            if i is not None:
                oi[i] = so; oiv[i] = sov; gls[i] = gl; ttls[i] = tt; tkls[i] = tk
        # funding (8h) -> step causal
        fr = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (s,)).fetchall()
        fund = np.full(len(kt), np.nan)
        if fr:
            fct = np.array([x[0] for x in fr], np.int64); frr = np.array([x[1] for x in fr], float)
            j = np.searchsorted(fct, kt, side="right") - 1
            good = j >= 0
            fund[good] = frr[j[good]]
        P[s] = dict(t=kt, o=o, h=h, l=lo, c=c, v=v, tbr=tbr, qv=qv, oi=oi, oiv=oiv,
                    gls=gls, ttls=ttls, tkls=tkls, fund=fund, pos=pos)
    con.close()
    # BTC series + market median return
    if "BTCUSDT" in P:
        b = P["BTCUSDT"]
        bret = np.concatenate([[np.nan], np.log(b["c"][1:] / b["c"][:-1])])
        btpos = {int(t): i for i, t in enumerate(b["t"])}
    else:
        bret = None; btpos = {}
    return P, bret, btpos


def fwd_raw(c, i, h):
    j = i + h
    return math.log(c[j] / c[i]) if j < len(c) else None


def seg_of(ev_days_sorted, day):
    n = len(ev_days_sorted)
    t_cut = ev_days_sorted[int(n * 0.5)]; v_cut = ev_days_sorted[int(n * 0.75)]
    return "train" if day <= t_cut else ("val" if day <= v_cut else "oos")


def report(bucket, label, cost=COST_RT_BP):
    print(f"\n--- {label} ---")
    res = {}
    for h in HOR:
        R = agg_pairs(bucket.get(h, []))
        res[h] = R
        if "mean_bp" not in R:
            print(f"  {h*15:>4}m: n={R.get('n')}"); continue
        net = R["mean_bp"] - math.copysign(cost, R["mean_bp"])
        print(f"  {h*15:>4}m: {R['mean_bp']:>7.2f}bp CI[{R['ci_bp'][0]:>6.1f},{R['ci_bp'][1]:>6.1f}] excl0={R['ci_excl_0']} "
              f"h1/h2=({R['half1_bp']:.1f},{R['half2_bp']:.1f}) symPos={R['frac_sym_pos']} conc={R['top5_conc']} "
              f"n={R['n']} nS={R['n_sym']} | net={net:.1f}")
    return res


def main():
    print("=== ROUND 9 — OI HISTORICAL ALPHA HUNT ===")
    P, bret, btpos = load_panel()
    print(f"panel: {len(P)} símbolos con OI+klines")
    span = None
    for s, d in P.items():
        a, b = d["t"][0], d["t"][-1]
        span = (a, b) if span is None else (min(span[0], a), max(span[1], b))
    def dd(ms): return datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d")
    print(f"span: {dd(span[0])} .. {dd(span[1])}")

    # precompute per symbol
    feats = {}
    for s, d in P.items():
        c = d["c"]; n = len(c)
        retW = np.concatenate([np.full(W, np.nan), np.log(c[W:] / c[:-W])])
        oi = d["oi"]
        dOI = np.concatenate([np.full(W, np.nan), np.log(np.where(oi[W:] > 0, oi[W:], np.nan) / np.where(oi[:-W] > 0, oi[:-W], np.nan))])
        tbrW = np.concatenate([np.full(W, np.nan), np.array([np.nanmean(d["tbr"][i-W:i]) if i >= W else np.nan for i in range(W, n)])]) if False else None
        # tbr window mean (vectorizado simple)
        tb = np.nan_to_num(d["tbr"]); ok = (~np.isnan(d["tbr"])).astype(float)
        csb = np.concatenate([[0.0], np.cumsum(tb)]); csk = np.concatenate([[0.0], np.cumsum(ok)])
        idx = np.arange(n); loi = np.clip(idx - W, 0, None)
        kk = csk[idx] - csk[loi]
        tbrW = np.where(kk > 0, (csb[idx] - csb[loi]) / np.where(kk > 0, kk, 1), np.nan)
        tbrW[idx < W] = np.nan
        retlong = np.concatenate([np.full(96, np.nan), np.log(c[96:] / c[:-96])])
        z_ret = zscore_causal(retW, ROLL)
        z_doi = zscore_causal(dOI, ROLL)
        z_tbr = zscore_causal(tbrW - 0.5, ROLL)
        z_fund = zscore_causal(d["fund"], ROLL)   # 30d de barras 15m (~90 settlements distintos dentro)
        # beta a BTC causal 30d
        beta = np.full(n, np.nan)
        if bret is not None:
            bal = np.array([bret[btpos[int(t)]] if int(t) in btpos else np.nan for t in d["t"]])
            r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
            ab = np.nan_to_num(r1 * bal); bb = np.nan_to_num(bal * bal)
            cab = np.concatenate([[0.0], np.cumsum(ab)]); cbb = np.concatenate([[0.0], np.cumsum(bb)])
            lb = np.clip(idx - ROLL, 0, None)
            num = cab[idx] - cab[lb]; den = cbb[idx] - cbb[lb]
            beta = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
            beta[idx < ROLL] = np.nan
        else:
            bal = np.full(n, np.nan)
        feats[s] = dict(retW=retW, dOI=dOI, tbrW=tbrW, retlong=retlong, z_ret=z_ret, z_doi=z_doi,
                        z_tbr=z_tbr, z_fund=z_fund, beta=beta, bal=bal)

    # ---------- H13C ----------
    print("\n" + "=" * 70 + "\nH13C — CUADRANTES price x dOI\n" + "=" * 70)
    QUAD = {"A": (-1, +1), "B": (-1, -1), "C": (+1, +1), "D": (+1, -1)}
    q_raw = {q: {h: [] for h in HOR} for q in QUAD}
    q_plac = {q: {h: [] for h in HOR} for q in QUAD}
    q_match = {q: {h: [] for h in HOR} for q in QUAD}      # price move, OI flat
    q_resid = {q: {h: [] for h in HOR} for q in QUAD}
    q_seg = {q: {seg: {h: [] for h in HOR} for seg in ("train", "val", "oos")} for q in QUAD}
    alldays = []
    for s, d in P.items():
        f = feats[s]; c = d["c"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        matchsig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) <= 0.3)
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + PLACEBO >= n:
                continue
            sr = int(np.sign(f["retW"][i])); so = int(np.sign(f["dOI"][i]))
            q = next((k for k, (a, b) in QUAD.items() if a == sr and b == so), None)
            if q is None:
                continue
            day = datetime.utcfromtimestamp(d["t"][i]/1000).date()
            alldays.append(day)
        # 2nd pass with seg needs global cut; do after
    alldays_sorted = sorted(set(alldays))
    for s, d in P.items():
        f = feats[s]; c = d["c"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        matchsig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) <= 0.3)
        last = {q: -999 for q in QUAD}
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + PLACEBO >= n:
                continue
            sr = int(np.sign(f["retW"][i])); so = int(np.sign(f["dOI"][i]))
            q = next((k for k, (a, b) in QUAD.items() if a == sr and b == so), None)
            if q is None or i - last[q] < W:
                continue
            last[q] = i
            day = datetime.utcfromtimestamp(d["t"][i]/1000).date()
            seg = seg_of(alldays_sorted, day)
            for h in HOR:
                r = fwd_raw(c, i, h)
                if r is None:
                    continue
                q_raw[q][h].append((s, r))
                q_seg[q][seg][h].append((s, r))
                rp = fwd_raw(c, i + PLACEBO, h)
                if rp is not None:
                    q_plac[q][h].append((s, rp))
                # residual BTC
                bfh = 0.0
                if bret is not None and int(d["t"][i]) in btpos:
                    bi = btpos[int(d["t"][i])]
                    if bi + h < len(bret):
                        # suma de bret sobre h barras
                        pass
                if not math.isnan(f["beta"][i]) and int(d["t"][i]) in btpos:
                    bi = btpos[int(d["t"][i])]
                    bc = P["BTCUSDT"]["c"]
                    if bi + h < len(bc):
                        br = math.log(bc[bi + h] / bc[bi])
                        q_resid[q][h].append((s, r - f["beta"][i] * br))
        last = {q: -999 for q in QUAD}
        for i in np.where(matchsig)[0]:
            if i < ROLL or i + max(HOR) >= n:
                continue
            sr = int(np.sign(f["retW"][i]))
            q = "A" if sr < 0 else "C"    # match: sólo por signo de price (OI flat)
            q2 = "B" if sr < 0 else "D"
            for h in HOR:
                r = fwd_raw(c, i, h)
                if r is None:
                    continue
                q_match[q][h].append((s, r)); q_match[q2][h].append((s, r))

    H13 = {}
    for q in QUAD:
        H13[q] = {"raw": report(q_raw[q], f"H13C {q}  ({'p-' if QUAD[q][0]<0 else 'p+'} {'oi+' if QUAD[q][1]>0 else 'oi-'})  RAW fwd (+ = precio sube)"),
                  "placebo": report(q_plac[q], f"H13C {q} placebo +24h"),
                  "matched_OIflat": report(q_match[q], f"H13C {q} matched (mismo signo de precio, OI PLANO)"),
                  "resid_btc": report(q_resid[q], f"H13C {q} residual-BTC"),
                  "train": report(q_seg[q]["train"], f"H13C {q} TRAIN"),
                  "val": report(q_seg[q]["val"], f"H13C {q} VAL"),
                  "oos": report(q_seg[q]["oos"], f"H13C {q} OOS")}

    # ---------- H15 ----------
    print("\n" + "=" * 70 + "\nH15 — ESTADOS price x dOI x taker-aggression\n" + "=" * 70)
    STATES = {}
    for pr in ("dn", "up"):
        for o_ in ("oiUp", "oiDn"):
            for tk in ("tkBuy", "tkSell"):
                STATES[f"{pr}_{o_}_{tk}"] = (pr, o_, tk)
    s_raw = {k: {h: [] for h in HOR} for k in STATES}
    s_plac = {k: {h: [] for h in HOR} for k in STATES}
    s_oos = {k: {h: [] for h in HOR} for k in STATES}
    reg = {h: [] for h in HOR}     # (retW, dOI, z_tbr, |ret| , btc_r) -> fwd  para OLS incremental
    for s, d in P.items():
        f = feats[s]; c = d["c"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 0.5) & (np.abs(f["z_tbr"]) >= 0.5)
        last = {k: -999 for k in STATES}
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + PLACEBO >= n:
                continue
            pr = "dn" if f["retW"][i] < 0 else "up"
            o_ = "oiUp" if f["dOI"][i] > 0 else "oiDn"
            tk = "tkBuy" if f["z_tbr"][i] > 0 else "tkSell"
            k = f"{pr}_{o_}_{tk}"
            if i - last[k] < W:
                continue
            last[k] = i
            day = datetime.utcfromtimestamp(d["t"][i]/1000).date()
            seg = seg_of(alldays_sorted, day)
            br = 0.0
            if bret is not None and int(d["t"][i]) in btpos:
                bi = btpos[int(d["t"][i])]
                br = bret[bi] if bi < len(bret) else 0.0
            for h in HOR:
                r = fwd_raw(c, i, h)
                if r is None:
                    continue
                s_raw[k][h].append((s, r))
                if seg == "oos":
                    s_oos[k][h].append((s, r))
                rp = fwd_raw(c, i + PLACEBO, h)
                if rp is not None:
                    s_plac[k][h].append((s, rp))
                reg[h].append((f["retW"][i], f["dOI"][i], f["z_tbr"][i], abs(f["retW"][i]), br, r))
    H15 = {}
    for k in STATES:
        H15[k] = {"raw": report(s_raw[k], f"H15 {k}"),
                  "placebo": report(s_plac[k], f"H15 {k} placebo +24h"),
                  "oos": report(s_oos[k], f"H15 {k} OOS")}

    print("\n--- H15 OLS incremental: fwd ~ 1 + retW + dOI + z_tbr + |retW| + btc_ret ---")
    ols_out = {}
    for h in HOR:
        rows = [r for r in reg[h] if all(np.isfinite(x) for x in r)]
        if len(rows) < 400:
            ols_out[h] = {"n": len(rows)}; continue
        A = np.array([[1, a, b, cc, dd_, ee] for (a, b, cc, dd_, ee, y) in rows])
        y = np.array([r[5] for r in rows])
        try:
            beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        except np.linalg.LinAlgError:
            ols_out[h] = {"n": len(rows), "err": "SVD"}; continue
        res = y - A @ beta
        s2 = (res @ res) / (len(y) - A.shape[1])
        se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
        names = ["const", "retW", "dOI", "z_tbr", "absRetW", "btc_ret"]
        row = {names[j]: (round(float(beta[j]), 5), round(float(beta[j]/se[j]), 2)) for j in range(6)}
        ols_out[h] = row
        print(f"  {h*15:>4}m n={len(rows)}: " + "  ".join(f"{k}={v[0]}(t{v[1]})" for k, v in row.items() if k in ("dOI", "z_tbr", "retW")))

    # ---------- H16 ----------
    print("\n" + "=" * 70 + "\nH16 — FUNDING extremo x dOI x price-trend\n" + "=" * 70)
    H16B = {}
    for fg in ("fPos", "fNeg"):
        for o_ in ("oiUp", "oiDn"):
            H16B[f"{fg}_{o_}"] = {h: [] for h in HOR}
    h16_fund_only = {h: [] for h in HOR}
    reg16 = {h: [] for h in HOR}
    for s, d in P.items():
        f = feats[s]; c = d["c"]; n = len(c)
        ext = np.abs(f["z_fund"]) >= 1.5
        last = -999; lastk = {k: -999 for k in H16B}
        for i in np.where(ext)[0]:
            if i < ROLL or i + max(HOR) >= n:
                continue
            fg = "fPos" if f["z_fund"][i] > 0 else "fNeg"
            o_ = "oiUp" if f["dOI"][i] > 0 else "oiDn"
            k = f"{fg}_{o_}"
            if i - lastk[k] < W:
                continue
            lastk[k] = i
            # signo: funding+ (longs pagan, crowd long) -> apostamos DOWN -> sgn=-1
            sgn = -1.0 if fg == "fPos" else 1.0
            for h in HOR:
                r = fwd_raw(c, i, h)
                if r is None:
                    continue
                H16B[k][h].append((s, sgn * r))
                h16_fund_only[h].append((s, sgn * r))
                reg16[h].append((f["z_fund"][i], f["dOI"][i], f["retlong"][i], r))
    H16 = {"fund_only": report(h16_fund_only, "H16 funding extremo SOLO (sgn contra el lado que paga)")}
    for k in H16B:
        H16[k] = report(H16B[k], f"H16 {k} (sgn contra el lado que paga)")
    print("\n--- H16 OLS: fwd ~ 1 + z_fund + dOI + retlong ---")
    h16ols = {}
    for h in HOR:
        rows = [r for r in reg16[h] if all(np.isfinite(x) for x in r)]
        if len(rows) < 200:
            h16ols[h] = {"n": len(rows)}; continue
        A = np.array([[1, a, b, cc] for (a, b, cc, y) in rows]); y = np.array([r[3] for r in rows])
        try:
            beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        except np.linalg.LinAlgError:
            h16ols[h] = {"n": len(rows), "err": "SVD"}; continue
        res = y - A @ beta; s2 = (res @ res) / (len(y) - 4)
        se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
        h16ols[h] = {"z_fund": (round(float(beta[1]), 5), round(float(beta[1]/se[1]), 2)),
                     "dOI": (round(float(beta[2]), 5), round(float(beta[2]/se[2]), 2)),
                     "retlong": (round(float(beta[3]), 5), round(float(beta[3]/se[3]), 2))}
        print(f"  {h*15:>4}m n={len(rows)}: z_fund={h16ols[h]['z_fund']}  dOI={h16ols[h]['dOI']}  retlong={h16ols[h]['retlong']}")

    # ---------- M15 ----------
    print("\n" + "=" * 70 + "\nM15 — REACTION-BETA PERSISTENTE (shocks BTC)\n" + "=" * 70)
    M15 = {}
    if bret is None:
        print("  sin BTC -> skip")
    else:
        bc = P["BTCUSDT"]["c"]; bt = P["BTCUSDT"]["t"]
        z_b = zscore_causal(np.concatenate([[np.nan], np.log(bc[1:] / bc[:-1])]), ROLL)
        shock_idx = [i for i in np.where(np.abs(z_b) >= 3.0)[0] if i > ROLL and i + 96 + 1 < len(bc)]
        # de-overlap 8 barras
        keep = []; lasts = -999
        for i in shock_idx:
            if i - lasts >= 8:
                keep.append(i); lasts = i
        shock_idx = keep
        shock_days = sorted(datetime.utcfromtimestamp(bt[i]/1000).date() for i in shock_idx)
        print(f"  shocks BTC |z|>=3 (de-overlap 8): {len(shock_idx)}")
        # por evento: norm_resid por símbolo
        per_sym_train = {}; per_sym_all = {}
        ev_records = []   # (day, i_btc, {sym: (norm_resid, i_sym)})
        for i in shock_idx:
            tb_ms = int(bt[i])
            br2 = math.log(bc[i + 1] / bc[i - 1])
            sgn = math.copysign(1.0, br2)
            day = datetime.utcfromtimestamp(tb_ms/1000).date()
            rec = {}
            for s, d in P.items():
                if s == "BTCUSDT":
                    continue
                j = d["pos"].get(tb_ms)
                if j is None or j - 1 < 0 or j + 1 >= len(d["c"]) or j < ROLL:
                    continue
                f = feats[s]
                if math.isnan(f["beta"][j]):
                    continue
                ar = math.log(d["c"][j + 1] / d["c"][j - 1])
                exp = f["beta"][j] * br2
                resid = (ar - exp) * sgn      # + = sobre-reaccionó en la dirección del shock
                rec[s] = (resid, j)
            if len(rec) >= 10:
                ev_records.append((day, i, sgn, rec))
        # split temporal por día de evento
        edays = sorted(set(r[0] for r in ev_records))
        tcut = edays[int(len(edays) * 0.5)]; vcut = edays[int(len(edays) * 0.75)]
        train_resid = {};
        for day, i, sgn, rec in ev_records:
            if day <= tcut:
                for s, (r, j) in rec.items():
                    train_resid.setdefault(s, []).append(r)
        chronic = {s: float(np.mean(v)) for s, v in train_resid.items() if len(v) >= 3}
        if len(chronic) >= 12:
            vals = np.array(sorted(chronic.values()))
            lo_t, hi_t = np.quantile(vals, [1/3, 2/3])
            under = set(s for s, v in chronic.items() if v <= lo_t)   # crónico sub-reacciona
            over = set(s for s, v in chronic.items() if v >= hi_t)    # crónico sobre-reacciona
            print(f"  TRAIN chronic: {len(chronic)} sym · under={len(under)} over={len(over)}")
            # persistencia: corr train-mean vs val/oos-mean
            for segname, dcut0, dcut1 in (("VAL", tcut, vcut), ("OOS", vcut, edays[-1])):
                seg_resid = {}
                for day, i, sgn, rec in ev_records:
                    if dcut0 < day <= dcut1:
                        for s, (r, j) in rec.items():
                            seg_resid.setdefault(s, []).append(r)
                common = [s for s in chronic if s in seg_resid and len(seg_resid[s]) >= 3]
                if len(common) >= 8:
                    xt = np.array([chronic[s] for s in common])
                    yt = np.array([np.mean(seg_resid[s]) for s in common])
                    cc = float(np.corrcoef(xt, yt)[0, 1])
                    print(f"  persistencia corr(TRAIN, {segname}) = {cc:.3f}  (n_sym={len(common)})")
                    M15[f"persist_{segname}"] = {"corr": cc, "n_sym": len(common)}
            # portfolio congelado: en VAL+OOS, post-shock signed fwd de under vs over
            for segname, dcut0, dcut1 in (("VAL", tcut, vcut), ("OOS", vcut, edays[-1])):
                pf = {"under": {h: [] for h in [4, 8, 16, 24]}, "over": {h: [] for h in [4, 8, 16, 24]}}
                for day, i, sgn, rec in ev_records:
                    if not (dcut0 < day <= dcut1):
                        continue
                    for s, (r, j) in rec.items():
                        grp = "under" if s in under else ("over" if s in over else None)
                        if grp is None:
                            continue
                        d = P[s]
                        for h in [4, 8, 16, 24]:
                            if j + 1 + h < len(d["c"]):
                                fr = sgn * math.log(d["c"][j + 1 + h] / d["c"][j + 1])
                                pf[grp][h].append((s, fr))
                print(f"\n  [{segname}] portfolio congelado (signo = dirección del shock):")
                seg_pf = {}
                for grp in ("under", "over"):
                    seg_pf[grp] = {}
                    for h in [4, 8, 16, 24]:
                        R = agg_pairs(pf[grp][h])
                        seg_pf[grp][h] = R
                        if "mean_bp" in R:
                            print(f"    {grp:5s} h={h*15:>4}m: {R['mean_bp']:>7.2f}bp CI[{R['ci_bp'][0]:.1f},{R['ci_bp'][1]:.1f}] "
                                  f"symPos={R['frac_sym_pos']} conc={R['top5_conc']} n={R['n']}")
                # spread under - over
                for h in [4, 8, 16, 24]:
                    ru = agg_pairs(pf["under"][h]); ro = agg_pairs(pf["over"][h])
                    if "mean_bp" in ru and "mean_bp" in ro:
                        print(f"    SPREAD under-over h={h*15:>4}m: {ru['mean_bp']-ro['mean_bp']:>7.2f} bp")
                M15[f"pf_{segname}"] = seg_pf
            # control: ranking aleatorio
            rndkeys = list(chronic.keys())
            rng2.shuffle(rndkeys)
            r_under = set(rndkeys[:len(under)]); r_over = set(rndkeys[-len(over):])
            pf = {"under": {h: [] for h in [8, 16]}, "over": {h: [] for h in [8, 16]}}
            for day, i, sgn, rec in ev_records:
                if day <= vcut:
                    continue
                for s, (r, j) in rec.items():
                    grp = "under" if s in r_under else ("over" if s in r_over else None)
                    if grp is None:
                        continue
                    d = P[s]
                    for h in [8, 16]:
                        if j + 1 + h < len(d["c"]):
                            pf[grp][h].append((s, sgn * math.log(d["c"][j + 1 + h] / d["c"][j + 1])))
            print("\n  [OOS] control RANKING ALEATORIO:")
            for h in [8, 16]:
                ru = agg_pairs(pf["under"][h]); ro = agg_pairs(pf["over"][h])
                if "mean_bp" in ru and "mean_bp" in ro:
                    print(f"    rnd spread under-over h={h*15}m: {ru['mean_bp']-ro['mean_bp']:.2f} bp")
        else:
            print("  chronic insuficiente")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "panel_symbols": len(P), "span": [dd(span[0]), dd(span[1])],
           "H13C": H13, "H15": H15, "H15_ols": ols_out, "H16": H16, "H16_ols": h16ols, "M15": M15}
    path = os.path.join(ROOT, "scratch_r9_oi_alpha.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
