"""
ROUND 10 — dOI REGIME BREAK TEST.

Pregunta: ¿el poder predictivo de dOI (H13-C A/D, PARK en R9) existe
independiente del régimen de BTC, o solo captura beta/régimen bajista?

Definición CONGELADA de H13-C A/D (idéntica a R9):
  W = 4 barras (1h), z causal ROLL = 2880 (30d).
  evento = |z(retW)| >= 1  AND  |z(dOI)| >= 1
  quadrant A: retW < 0 & dOI > 0   ;  D: retW > 0 & dOI < 0
  dirección operada = SHORT en ambos  ->  signed_fwd = -log(c[t+h]/c[t])  (+ = ganó)

RÉGIMEN (thresholds CONGELADOS antes de ver resultados):
  btc_tr = log(btc_close[t] / btc_close[t-96])   (retorno trailing 24h de BTC, causal)
  UP   : btc_tr > +0.015
  DOWN : btc_tr < -0.015
  FLAT : entre medias
  (robustez: se reporta también con pendiente de SMA7d de BTC; diagnóstico ±1.0/±2.5%)

Horizontes PREDECLARADOS: 15m/30m/1h/2h/4h/8h/24h.  Costo screen: 20 bp RT.
TRAIN/VAL/OOS 50/25/25 por fecha de evento (global, mismo corte para todos).
Cluster bootstrap por símbolo. Matched control (OI plano) por régimen.
"""
import os, sys, json, math, numpy as np
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs, rng
from r9_oi_alpha import load_panel

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
W = 4
ROLL = 2880
HOR = [1, 2, 4, 8, 16, 32, 96]           # 15m..24h en barras de 15m
COST_RT_BP = 20.0
REG_THR = 0.015
rng10 = np.random.default_rng(20260912)


def hlabel(h):
    return {1: "15m", 2: "30m", 4: "1h", 8: "2h", 16: "4h", 32: "8h", 96: "24h"}[h]


def build_feats(P, bret, btpos):
    bc = P["BTCUSDT"]["c"]; bt = P["BTCUSDT"]["t"]
    btc_tr_by_ms = {}
    for i in range(96, len(bc)):
        btc_tr_by_ms[int(bt[i])] = math.log(bc[i] / bc[i - 96])
    # cumret BTC para forward btc-return
    # market return 15m: mediana cross-sectional por barra (alineado por ms)
    ms_all = sorted(set(int(t) for d in P.values() for t in d["t"]))
    idx_of = {m: k for k, m in enumerate(ms_all)}
    ret_mat = np.full((len(ms_all), len(P)), np.nan)
    for si, (s, d) in enumerate(P.items()):
        r1 = np.concatenate([[np.nan], np.log(d["c"][1:] / d["c"][:-1])])
        for k, t in enumerate(d["t"]):
            ret_mat[idx_of[int(t)], si] = r1[k]
    mkt_ret = np.nanmedian(ret_mat, axis=1)          # 15m market median return por ms
    mkt_cum = np.nancumsum(np.nan_to_num(mkt_ret))
    mkt_cum_by_ms = {m: mkt_cum[idx_of[m]] for m in ms_all}

    F = {}
    for s, d in P.items():
        c = d["c"]; n = len(c)
        retW = np.concatenate([np.full(W, np.nan), np.log(c[W:] / c[:-W])])
        oi = d["oi"]
        dOI = np.concatenate([np.full(W, np.nan),
                              np.log(np.where(oi[W:] > 0, oi[W:], np.nan) / np.where(oi[:-W] > 0, oi[:-W], np.nan))])
        z_ret = zscore_causal(retW, ROLL)
        z_doi = zscore_causal(dOI, ROLL)
        retlong = np.concatenate([np.full(96, np.nan), np.log(c[96:] / c[:-96])])
        r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
        # realized vol causal 96
        rv = np.full(n, np.nan)
        cs2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r1) ** 2)])
        for i in range(96, n):
            rv[i] = math.sqrt((cs2[i] - cs2[i - 96]) / 96)
        # beta causal a BTC
        bal = np.array([bret[btpos[int(t)]] if int(t) in btpos else np.nan for t in d["t"]])
        ab = np.nan_to_num(r1 * bal); bb = np.nan_to_num(bal * bal)
        cab = np.concatenate([[0.0], np.cumsum(ab)]); cbb = np.concatenate([[0.0], np.cumsum(bb)])
        ii = np.arange(n); lb = np.clip(ii - ROLL, 0, None)
        num = cab[ii] - cab[lb]; den = cbb[ii] - cbb[lb]
        beta = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
        beta[ii < ROLL] = np.nan
        F[s] = dict(retW=retW, dOI=dOI, z_ret=z_ret, z_doi=z_doi, retlong=retlong,
                    rv=rv, beta=beta)
    return F, btc_tr_by_ms, mkt_cum_by_ms


def regime(btc_tr, thr=REG_THR):
    if btc_tr is None or math.isnan(btc_tr):
        return None
    if btc_tr > thr:
        return "UP"
    if btc_tr < -thr:
        return "DOWN"
    return "FLAT"


def report(bucket, label):
    R = {h: agg_pairs(bucket.get(h, [])) for h in HOR}
    print(f"\n--- {label} ---")
    for h in HOR:
        r = R[h]
        if "mean_bp" not in r:
            print(f"  {hlabel(h):>4}: n={r.get('n')}"); continue
        net = abs(r["mean_bp"]) - COST_RT_BP
        print(f"  {hlabel(h):>4}: {r['mean_bp']:>7.2f}bp CI[{r['ci_bp'][0]:>6.1f},{r['ci_bp'][1]:>6.1f}] "
              f"excl0={str(r['ci_excl_0']):5s} h1/h2=({r['half1_bp']:.0f},{r['half2_bp']:.0f}) "
              f"symPos={r['frac_sym_pos']} conc={r['top5_conc']} n={r['n']} nS={r['n_sym']} | net~{net:+.0f}")
    return R


def ols_beta_control(rows):
    """rows: (dOI, btc_fwd, mkt_fwd, retlong, rv, y).  y = signed_fwd (SHORT convention)."""
    rows = [r for r in rows if all(np.isfinite(x) for x in r)]
    if len(rows) < 300:
        return {"n": len(rows)}
    X = np.array([[1, a, b, c, d, e] for (a, b, c, d, e, y) in rows])
    y = np.array([r[5] for r in rows])
    # full
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2_full = 1 - resid.var() / y.var()
    se = np.sqrt(np.diag((resid @ resid) / (len(y) - X.shape[1]) * np.linalg.inv(X.T @ X)))
    # sin dOI
    X0 = X[:, [0, 2, 3, 4, 5]]
    b0, *_ = np.linalg.lstsq(X0, y, rcond=None)
    r2_0 = 1 - (y - X0 @ b0).var() / y.var()
    return {"n": len(rows), "beta_dOI": round(float(beta[1]), 5), "t_dOI": round(float(beta[1] / se[1]), 2),
            "beta_btc": round(float(beta[2]), 3), "t_btc": round(float(beta[2] / se[2]), 1),
            "R2_full": round(float(r2_full), 4), "R2_no_dOI": round(float(r2_0), 4),
            "dR2": round(float(r2_full - r2_0), 5)}


def main():
    print("=== ROUND 10 — dOI REGIME BREAK TEST ===")
    P, bret, btpos = load_panel()
    F, btc_tr, mkt_cum = build_feats(P, bret, btpos)
    bc = P["BTCUSDT"]["c"]; btms = {int(t): i for i, t in enumerate(P["BTCUSDT"]["t"])}
    print(f"panel {len(P)} símbolos")

    # 1er pase: recolectar días de evento para el corte temporal global
    evdays = []
    for s, d in P.items():
        f = F[s]; n = len(d["c"])
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) >= n:
                continue
            sr = np.sign(f["retW"][i]); so = np.sign(f["dOI"][i])
            if (sr < 0 and so > 0) or (sr > 0 and so < 0):
                evdays.append(datetime.utcfromtimestamp(d["t"][i] / 1000).date())
    evd = sorted(set(evdays))
    tcut, vcut = evd[int(len(evd) * 0.5)], evd[int(len(evd) * 0.75)]
    print(f"eventos A/D totales≈{len(evdays)} · corte TRAIN<= {tcut} · VAL<= {vcut}")

    REGS = ("UP", "FLAT", "DOWN")
    # acumuladores
    def nb():
        return {h: [] for h in HOR}
    by_rq = {(r, q): nb() for r in REGS for q in ("A", "D", "AD")}
    by_rq_inv = {(r, q): nb() for r in REGS for q in ("A", "D", "AD")}       # placebo dirección invertida
    by_rq_match = {r: nb() for r in REGS}
    by_rq_resid = {(r, q): nb() for r in REGS for q in ("AD",)}
    by_rseg = {(r, seg): nb() for r in REGS for seg in ("train", "val", "oos")}   # A+D pooled, signed SHORT
    reg_rows = {(r, h): [] for r in REGS for h in HOR}       # para OLS beta-control (h fijo 8=2h y 16=4h)
    econ_rows = []      # (sym, regime, seg, entry_ms, {h: signed_open_fwd})  para sim económica A+D
    # thresholds diagnósticos
    zthr_diag = {z: {r: nb() for r in REGS} for z in (0.7, 1.0, 1.5)}

    for s, d in P.items():
        f = F[s]; c = d["c"]; o = d["o"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        matchsig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) <= 0.3)
        lastq = {"A": -999, "D": -999}
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + 2 >= n:
                continue
            sr = np.sign(f["retW"][i]); so = np.sign(f["dOI"][i])
            if sr < 0 and so > 0:
                q = "A"
            elif sr > 0 and so < 0:
                q = "D"
            else:
                continue
            if i - lastq[q] < W:
                continue
            lastq[q] = i
            tms = int(d["t"][i])
            reg = regime(btc_tr.get(tms))
            if reg is None:
                continue
            day = datetime.utcfromtimestamp(tms / 1000).date()
            seg = "train" if day <= tcut else ("val" if day <= vcut else "oos")
            bi = btms.get(tms)
            for h in HOR:
                fwd = math.log(c[i + h] / c[i])
                sgn_fwd = -fwd                                   # SHORT
                for qq in (q, "AD"):
                    by_rq[(reg, qq)][h].append((s, sgn_fwd))
                    by_rq_inv[(reg, qq)][h].append((s, fwd))     # dirección invertida (LONG) placebo
                by_rseg[(reg, seg)][h].append((s, sgn_fwd))
                if h in (8, 16):
                    btc_fwd = math.log(bc[bi + h] / bc[bi]) if (bi is not None and bi + h < len(bc)) else np.nan
                    mkt_fwd = (mkt_cum.get(int(d["t"][i + h])) - mkt_cum.get(tms)) if (int(d["t"][i + h]) in mkt_cum and tms in mkt_cum) else np.nan
                    reg_rows[(reg, h)].append((f["dOI"][i], btc_fwd, mkt_fwd, f["retlong"][i], f["rv"][i], sgn_fwd))
            # residual BTC (A+D)
            if bi is not None:
                for h in HOR:
                    if bi + h < len(bc):
                        br = math.log(bc[bi + h] / bc[bi])
                        by_rq_resid[(reg, "AD")][h].append((s, -(math.log(c[i + h] / c[i]) - f["beta"][i] * br)))
            # económico: entrada open[i+1]
            e = i + 1
            rec = {}
            for h in HOR:
                if e + h < len(o):
                    rec[h] = -math.log(o[e + h] / o[e])          # SHORT desde open[i+1]
            econ_rows.append((s, reg, seg, int(d["t"][e]), rec))
            # diagnóstico thresholds
            for z in (0.7, 1.0, 1.5):
                if abs(f["z_ret"][i]) >= z and abs(f["z_doi"][i]) >= z:
                    for h in HOR:
                        zthr_diag[z][reg][h].append((s, -math.log(c[i + h] / c[i])))
        # matched (OI plano) por régimen
        lastm = -999
        for i in np.where(matchsig)[0]:
            if i < ROLL or i + max(HOR) >= n or i - lastm < W:
                continue
            lastm = i
            tms = int(d["t"][i]); reg = regime(btc_tr.get(tms))
            if reg is None:
                continue
            sr = np.sign(f["retW"][i])
            for h in HOR:
                # matched se opera en la MISMA dirección que A/D daría: A(sr<0)->short, D(sr>0)->short => siempre short
                by_rq_match[reg][h].append((s, -math.log(c[i + h] / c[i])))

    # ---------- SALIDA ----------
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "regime_threshold": REG_THR, "tcut": str(tcut), "vcut": str(vcut), "results": {}}

    print("\n" + "=" * 70 + "\n(1-2) dOI POR RÉGIMEN — A+D pooled, SHORT (+ = ganó), net~ = |mean|-20bp\n" + "=" * 70)
    for reg in REGS:
        out["results"][f"AD_{reg}"] = {h: agg_pairs(by_rq[(reg, "AD")][h]) for h in HOR}
        report(by_rq[(reg, "AD")], f"REGIME {reg}  ·  A+D  ·  SHORT")
    print("\n--- matched control (OI plano) por régimen, misma dirección SHORT ---")
    for reg in REGS:
        out["results"][f"match_{reg}"] = {h: agg_pairs(by_rq_match[reg][h]) for h in HOR}
        report(by_rq_match[reg], f"REGIME {reg} · matched OI-flat")
    print("\n--- residual-BTC (A+D) por régimen ---")
    for reg in REGS:
        report(by_rq_resid[(reg, "AD")], f"REGIME {reg} · A+D residual-BTC")

    print("\n" + "=" * 70 + "\n(9) DIRECCIÓN: A sola / D sola / invertida(LONG placebo) por régimen\n" + "=" * 70)
    for reg in REGS:
        report(by_rq[(reg, "A")], f"REGIME {reg} · A only · SHORT")
        report(by_rq[(reg, "D")], f"REGIME {reg} · D only · SHORT")
        report(by_rq_inv[(reg, "AD")], f"REGIME {reg} · A+D · INVERTED (LONG) placebo")

    print("\n" + "=" * 70 + "\n(5) MATRIZ RÉGIMEN × TRAIN/VAL/OOS  (A+D SHORT, bp por horizonte)\n" + "=" * 70)
    mat = {}
    for reg in REGS:
        mat[reg] = {}
        for seg in ("train", "val", "oos"):
            R = {h: agg_pairs(by_rseg[(reg, seg)][h]) for h in HOR}
            mat[reg][seg] = {hlabel(h): (R[h].get("mean_bp"), R[h].get("n"), R[h].get("ci_excl_0")) for h in HOR}
    out["results"]["matrix"] = mat
    for reg in REGS:
        print(f"\n  [{reg}]")
        for seg in ("train", "val", "oos"):
            cells = "  ".join(f"{hlabel(h)}={ (lambda x: f'{x:+.0f}' if x is not None else 'na')(mat[reg][seg][hlabel(h)][0]) }"
                              f"{'*' if mat[reg][seg][hlabel(h)][2] else ' '}" for h in HOR)
            nn = mat[reg][seg][hlabel(HOR[0])][1]
            print(f"    {seg:5s} (n~{nn}): {cells}")

    print("\n" + "=" * 70 + "\n(4) CONTROL DE BETA — OLS: signed_fwd ~ 1 + dOI + btc_fwd + mkt_fwd + retlong + rv\n" + "=" * 70)
    out["results"]["beta_control"] = {}
    for reg in REGS:
        for h in (8, 16):
            r = ols_beta_control(reg_rows[(reg, h)])
            out["results"]["beta_control"][f"{reg}_{hlabel(h)}"] = r
            print(f"  {reg:5s} {hlabel(h):>3}: {r}")

    print("\n" + "=" * 70 + "\n(8) SENSIBILIDAD DE THRESHOLD (diagnóstico) — A+D SHORT @2h y @4h\n" + "=" * 70)
    for z in (0.7, 1.0, 1.5):
        for reg in REGS:
            R2 = agg_pairs(zthr_diag[z][reg][8]); R4 = agg_pairs(zthr_diag[z][reg][16])
            print(f"  z>={z} {reg:5s}: 2h={R2.get('mean_bp')}bp(n={R2.get('n')},excl0={R2.get('ci_excl_0')})  "
                  f"4h={R4.get('mean_bp')}bp(n={R4.get('n')},excl0={R4.get('ci_excl_0')})")

    # ---------- ¿SOBREVIVE? decidir per-símbolo + económico ----------
    # criterio de "sobrevive el test de régimen para seguir": DOWN con net>0 y CI excl 0 en val Y oos a algún h>=2h,
    # y beta_control t_dOI significativo (<=-2) en DOWN.
    def net_ok(reg, seg, h):
        r = agg_pairs(by_rseg[(reg, seg)][h])
        return ("mean_bp" in r and r["ci_excl_0"] and abs(r["mean_bp"]) - COST_RT_BP > 0 and r["mean_bp"] > 0)
    down_val_oos = any(net_ok("DOWN", "val", h) and net_ok("DOWN", "oos", h) for h in (8, 16, 32))
    bc_down = out["results"]["beta_control"].get("DOWN_4h", {})
    beta_ok = isinstance(bc_down.get("t_dOI"), (int, float)) and bc_down["t_dOI"] <= -2
    survives_any = down_val_oos and beta_ok
    up_ok = any(net_ok("UP", "val", h) and net_ok("UP", "oos", h) for h in (8, 16, 32))
    flat_ok = any(net_ok("FLAT", "val", h) and net_ok("FLAT", "oos", h) for h in (8, 16, 32))
    print(f"\n>>> survive check: DOWN(val&oos net>0)={down_val_oos}  beta_ctrl_DOWN_t<=-2={beta_ok}  UP_ok={up_ok}  FLAT_ok={flat_ok}")
    out["survive"] = dict(down=down_val_oos, beta_ok=bool(beta_ok), up=up_ok, flat=flat_ok)

    if survives_any:
        print("\n" + "=" * 70 + "\n(6) PER-SYMBOL — leave-one-out / leave-top-k (régimen DOWN, A+D, h=4h SHORT)\n" + "=" * 70)
        pairs = by_rq[("DOWN", "AD")][16]
        by = {}
        for s, v in pairs:
            by.setdefault(s, []).append(v)
        sym_mean = {s: float(np.mean(v)) for s, v in by.items()}
        sym_sum = {s: float(np.sum(v)) for s, v in by.items()}
        order = sorted(sym_sum, key=lambda s: sym_sum[s], reverse=True)
        allv = np.concatenate([np.array(by[s]) for s in by])
        base = allv.mean() * 1e4
        pos = sum(1 for s in sym_mean if sym_mean[s] > 0)
        print(f"  símbolos={len(by)}  symPos={pos/len(by):.2f}  media global={base:.1f}bp  mediana por símbolo={np.median(list(sym_mean.values()))*1e4:.1f}bp")
        for k in range(1, 6):
            drop = set(order[:k])
            v = np.concatenate([np.array(by[s]) for s in by if s not in drop])
            print(f"  quitando top-{k} ({','.join(list(drop)[:3])}...): media={v.mean()*1e4:+.1f}bp  n={len(v)}")
        # leave-one-out peor caso
        worst = None
        for s in order[:10]:
            v = np.concatenate([np.array(by[x]) for x in by if x != s])
            m = v.mean() * 1e4
            if worst is None or m < worst[1]:
                worst = (s, m)
        print(f"  LOO peor: quitar {worst[0]} -> {worst[1]:+.1f}bp (base {base:.1f})")
        out["results"]["per_symbol_DOWN_4h"] = {"n_sym": len(by), "symPos": pos / len(by), "base_bp": base,
                                                "loo_worst": worst}

        print("\n" + "=" * 70 + "\n(7) SIM ECONÓMICA — DOWN, A+D, entrada open[t+1], SHORT\n" + "=" * 70)
        FEE = 5.0; SPREAD = 6.0; SLIP = 4.0   # bp/lado fee? -> RT: fee 10 + spread 6 + slip 8 = 24; + funding aparte
        RT_BP = 2 * FEE + SPREAD + 2 * SLIP    # 24 bp conservador
        MARGIN = 300.0
        span_days = (max(r[3] for r in econ_rows) - min(r[3] for r in econ_rows)) / 86400000
        for h in (8, 16, 32):
            rr = [rec[h] for (s, reg, seg, ems, rec) in econ_rows if reg == "DOWN" and h in rec]
            if len(rr) < 30:
                print(f"  h={hlabel(h)}: n={len(rr)}"); continue
            g = np.array(rr) * 1e4
            hold_h = h * 15 / 60.0
            fund_cost = 0.0
            net = g - RT_BP - fund_cost
            trades_mo = len(rr) / (span_days / 30.0)
            gross_mo = g.mean() * MARGIN / 1e4 * trades_mo
            net_mo = net.mean() * MARGIN / 1e4 * trades_mo
            wr = (net > 0).mean()
            pf = net[net > 0].sum() / (-net[net < 0].sum()) if (net < 0).any() else np.inf
            eq = np.cumsum(net); dd = (np.maximum.accumulate(eq) - eq).max()
            print(f"  h={hlabel(h):>3} hold~{hold_h:.1f}h: trades/mo={trades_mo:.0f}  gross/mo=${gross_mo:.0f}  "
                  f"NET/mo=${net_mo:.0f}  avg_net={net.mean():+.1f}bp  med_net={np.median(net):+.1f}bp  "
                  f"WR={wr:.2f}  PF={pf:.2f}  maxDD={dd:.0f}bp  (RT_cost={RT_BP}bp, margin=${MARGIN})")
            out["results"].setdefault("econ_DOWN", {})[hlabel(h)] = dict(
                trades_mo=round(trades_mo, 1), net_mo_usd=round(net_mo, 1), avg_net_bp=round(float(net.mean()), 1),
                med_net_bp=round(float(np.median(net)), 1), wr=round(float(wr), 2),
                pf=round(float(pf), 2) if np.isfinite(pf) else None, maxdd_bp=round(float(dd), 0))
    else:
        print("\n>>> dOI NO sobrevive el test de régimen para pasar a per-símbolo/económico.")

    path = os.path.join(ROOT, "scratch_r10_doi_regime.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
