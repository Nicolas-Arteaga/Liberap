"""
ROUND 13 — DRIFT ALTS vs BTC: ¿prima de riesgo sistemática explotable, market-
neutral, o solo beta/drift disfrazado?

Datos: los mismos 14.5 meses ya ingeridos (klines_clean 15m -> resampleado a
DIARIO, causal). Universo: mismos 45 símbolos ex-ante de R11/R12 (existían
<= 2025-07-01). Sin descargas nuevas.

Construcción (todo congelado ANTES de mirar resultados):
  - beta[t] = beta causal 30d (OLS ret_diario vs ret_diario BTC), trailing.
  - resid_mom[t] = suma causal de residuales (ret - beta*btc_ret) de los
    últimos 14 días (momentum idiosincrático, ortogonal a beta por construcción).
  - Rebalanceo SEMANAL (cada 7 días, día fijo). N=5 por pata (predeclarado;
    N=8 como sensibilidad diagnóstica, no elegido post-hoc).

Test A/B — BETTING-AGAINST-BETA (market-neutral):
  LONG los N de menor beta trailing, SHORT los N de mayor beta trailing.
  Se calcula el book SIN cubrir (raw, dollar-neutral pero no beta-neutral) y
  CUBIERTO con una pata de BTC dimensionada para llevar el beta neto del libro
  a 0: hedged_ret = raw_ret - port_beta_prev * btc_week_ret.
  Esto separa EXPLÍCITAMENTE: (1) retorno crudo long-short (puede esconder
  exposición short de mercado), (2) la contribución de la pata de cobertura de
  BTC, (3) el residual beta-neutral = la prima "real" si existe.

Test C — CROSS-SECTIONAL RESIDUAL MOMENTUM:
  LONG los N con mayor resid_mom, SHORT los N con menor. Mismo hedge.

Test D — estabilidad temporal: TRAIN/VAL/OOS (50/25/25 por fecha de rebalanceo)
  + por trimestre.

Test E — placebos: bucket aleatorio (mismo N por lado, símbolos al azar en vez
  de por beta/resid_mom) con el MISMO procedimiento de hedge.

Test F — sim económica: capital <=450 USDT, N legs + 1 leg de hedge BTC, costo
  RT conservador (24bp) sobre TODO el libro cada semana (turnover completo,
  cota superior de costo), funding real agregado, sin apalancamiento y con
  apalancamiento explícito 2x/3x (nocional = capital*lev/legs, margen sigue
  siendo <=450).
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r9_oi_alpha import load_panel
from r12_smartmoney import restrict_universe
from datetime import datetime, timezone, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
BETA_WIN = 30       # dias
MOM_WIN = 14         # dias
REBAL_DAYS = 7
N_LEGS = 5            # primario, predeclarado
N_LEGS_SENS = 8       # sensibilidad diagnostica
FEE_SIDE = 5.0; SPREAD_SIDE = 3.0; SLIP_SIDE = 4.0
RT_BP = 2 * (FEE_SIDE + SPREAD_SIDE + SLIP_SIDE)   # 24 bp, mismo criterio que R10-R12
rng = np.random.default_rng(20260916)


def daily_series(d):
    """resample 15m -> diario (close del ultimo bar del dia UTC, volumen $ sumado)."""
    t = d["t"]; c = d["c"]; o = d["o"]; v = d["v"]
    day = (t // 86400000).astype(np.int64)
    udays, idx_last = np.unique(day, return_index=False), None
    # ultimo indice de cada dia
    order = np.argsort(t)
    day_o = day[order]
    last_idx = {}
    for pos, dv in zip(order, day_o):
        last_idx[int(dv)] = pos   # como esta ordenado por t creciente, el ultimo pos por dia queda
    days_sorted = sorted(last_idx)
    close = np.array([c[last_idx[dd]] for dd in days_sorted])
    dollar_vol = np.zeros(len(days_sorted))
    dvmap = collections.defaultdict(float)
    for i, dv in enumerate(day):
        dvmap[int(dv)] += o[i] * v[i]
    dollar_vol = np.array([dvmap[dd] for dd in days_sorted])
    return np.array(days_sorted, np.int64), close, dollar_vol


def main():
    print("=== ROUND 13 — DRIFT ALTS vs BTC (betting-against-beta / market-neutral) ===")
    P, bret, btpos = load_panel()
    P = restrict_universe(P)
    print(f"universo: {len(P)} símbolos")

    daily = {}
    for s, d in P.items():
        days, close, dv = daily_series(d)
        daily[s] = dict(days=days, close=close, dv=dv)
    btc = daily["BTCUSDT"]
    btc_day_idx = {int(dv): i for i, dv in enumerate(btc["days"])}

    # panel alineado al calendario de BTC (dias donde BTC tiene dato)
    cal = btc["days"]
    n_cal = len(cal)
    print(f"calendario diario: {n_cal} días ({datetime.utcfromtimestamp(int(cal[0])*86400).date()} .. {datetime.utcfromtimestamp(int(cal[-1])*86400).date()})")

    btc_ret = np.concatenate([[np.nan], np.log(btc["close"][1:] / btc["close"][:-1])])

    # alinear cada simbolo al calendario BTC (relleno con NaN si falta el dia)
    ALGN = {}
    for s, dd in daily.items():
        idxmap = {int(dv): i for i, dv in enumerate(dd["days"])}
        px = np.full(n_cal, np.nan); dvv = np.full(n_cal, np.nan)
        for i, dv in enumerate(cal):
            j = idxmap.get(int(dv))
            if j is not None:
                px[i] = dd["close"][j]; dvv[i] = dd["dv"][j]
        ret = np.concatenate([[np.nan], np.log(px[1:] / px[:-1])])
        ALGN[s] = dict(px=px, ret=ret, dv=dvv)

    # beta causal 30d y resid-momentum causal 14d
    for s, d in ALGN.items():
        r = d["ret"]; n = n_cal
        beta = np.full(n, np.nan)
        for i in range(BETA_WIN, n):
            rb = btc_ret[i - BETA_WIN:i]; ra = r[i - BETA_WIN:i]
            ok = np.isfinite(rb) & np.isfinite(ra)
            if ok.sum() >= BETA_WIN * 0.7:
                vb = rb[ok]; va = ra[ok]
                denom = np.dot(vb, vb)
                beta[i] = float(np.dot(va, vb) / denom) if denom > 0 else np.nan
        resid = r - beta * btc_ret
        mom = np.full(n, np.nan)
        cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(resid))])
        ok = (~np.isnan(resid)).astype(float); csk = np.concatenate([[0.0], np.cumsum(ok)])
        for i in range(BETA_WIN + MOM_WIN, n):
            k = csk[i] - csk[i - MOM_WIN]
            if k >= MOM_WIN * 0.7:
                mom[i] = cs[i] - cs[i - MOM_WIN]
        d["beta"] = beta; d["resid_mom"] = mom

    # fechas de rebalanceo (cada REBAL_DAYS, empezando cuando ya hay beta valido para >= N_LEGS_SENS simbolos)
    start_i = BETA_WIN + MOM_WIN + 1
    rebal_idx = list(range(start_i, n_cal - REBAL_DAYS, REBAL_DAYS))
    print(f"rebalanceos semanales: {len(rebal_idx)}")

    def universe_at(i, key):
        vals = {}
        for s, d in ALGN.items():
            if s == "BTCUSDT":
                continue
            v = d[key][i]
            if np.isfinite(v) and np.isfinite(d["px"][i]) and np.isfinite(d["px"][i + REBAL_DAYS]):
                vals[s] = v
        return vals

    def week_ret(s, i):
        px = ALGN[s]["px"]
        if not (np.isfinite(px[i]) and np.isfinite(px[i + REBAL_DAYS])):
            return None
        return math.log(px[i + REBAL_DAYS] / px[i])

    def btc_week_ret(i):
        return math.log(btc["close"][btc_day_idx.get(int(cal[i + REBAL_DAYS]), -1)] / btc["close"][btc_day_idx.get(int(cal[i]), -1)]) \
            if int(cal[i]) in btc_day_idx and int(cal[i + REBAL_DAYS]) in btc_day_idx else \
            math.log(btc["close"][i + REBAL_DAYS] / btc["close"][i])

    def run_portfolio(rank_key, n_legs, reverse, randomize=False, seed=0):
        """rank_key: 'beta' o 'resid_mom'. reverse=True -> long = mayor valor.
        Devuelve dict h->records (usa solo un horizonte=1 semana) + series semanal."""
        raw_bp = []; hedged_bp = []; hedge_leg_bp = []; port_beta_l = []; days_l = []
        rr = np.random.default_rng(seed)
        for i in rebal_idx:
            uni = universe_at(i, rank_key)
            uni_beta = universe_at(i, "beta")
            if len(uni) < 2 * n_legs:
                continue
            syms = list(uni)
            if randomize:
                rr.shuffle(syms)
                longs, shorts = syms[:n_legs], syms[-n_legs:]
            else:
                order = sorted(syms, key=lambda s: uni[s], reverse=reverse)
                longs, shorts = order[:n_legs], order[-n_legs:]
            rl = [week_ret(s, i) for s in longs]; rs = [week_ret(s, i) for s in shorts]
            bl = [uni_beta.get(s, np.nan) for s in longs]; bs = [uni_beta.get(s, np.nan) for s in shorts]
            if any(v is None for v in rl + rs) or any(not np.isfinite(v) for v in bl + bs):
                continue
            raw = float(np.mean(rl) - np.mean(rs))
            port_beta = float(np.mean(bl) - np.mean(bs))
            bwr = btc_week_ret(i)
            hedge_leg = -port_beta * bwr
            hedged = raw + hedge_leg
            raw_bp.append((cal[i], raw * 1e4)); hedged_bp.append((cal[i], hedged * 1e4))
            hedge_leg_bp.append((cal[i], hedge_leg * 1e4)); port_beta_l.append(port_beta)
            days_l.append(int(cal[i]))
        return dict(raw=raw_bp, hedged=hedged_bp, hedge_leg=hedge_leg_bp, port_beta=port_beta_l, days=days_l)

    def daysplit(days):
        ds = sorted(days); n = len(ds)
        tcut, vcut = ds[int(n * 0.5)], ds[int(n * 0.75)]
        return tcut, vcut

    def summarize(res, label):
        days = res["days"]
        if len(days) < 10:
            print(f"  {label}: n insuficiente ({len(days)})"); return None
        tcut, vcut = daysplit(days)
        def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
        raw = np.array([x[1] for x in res["raw"]]); hed = np.array([x[1] for x in res["hedged"]])
        hleg = np.array([x[1] for x in res["hedge_leg"]])
        segs = np.array([seg(dv) for dv in days])
        print(f"\n  {label}  (n_semanas={len(days)}, port_beta medio={np.mean(res['port_beta']):+.2f})")
        print(f"    RAW      : mean={raw.mean():+7.1f}bp  train={raw[segs=='train'].mean() if (segs=='train').any() else float('nan'):+7.1f}  "
              f"val={raw[segs=='val'].mean() if (segs=='val').any() else float('nan'):+7.1f}  oos={raw[segs=='oos'].mean() if (segs=='oos').any() else float('nan'):+7.1f}")
        print(f"    HEDGE-LEG: mean={hleg.mean():+7.1f}bp  (contribución pura de la cobertura BTC)")
        print(f"    HEDGED   : mean={hed.mean():+7.1f}bp  train={hed[segs=='train'].mean() if (segs=='train').any() else float('nan'):+7.1f}  "
              f"val={hed[segs=='val'].mean() if (segs=='val').any() else float('nan'):+7.1f}  oos={hed[segs=='oos'].mean() if (segs=='oos').any() else float('nan'):+7.1f}  "
              f"WR={float((hed>0).mean()):.2f}  PF={hed[hed>0].sum()/max(1e-9,-hed[hed<0].sum()):.2f}")
        # por trimestre
        qtr = collections.defaultdict(list)
        for dv, v in zip(days, hed):
            dt_ = date(1970, 1, 1) + timedelta(days=int(dv))
            qtr[f"{dt_.year}Q{(dt_.month-1)//3+1}"].append(v)
        print("    por trimestre (hedged bp): " + "  ".join(f"{k}={np.mean(v):+.0f}[{len(v)}]" for k, v in sorted(qtr.items())))
        return dict(days=days, raw=raw, hedged=hed, hedge_leg=hleg, seg=segs, tcut=str(tcut), vcut=str(vcut))

    print("\n" + "#" * 70 + "\n# TEST A/B — BETTING-AGAINST-BETA (long low-beta / short high-beta)\n" + "#" * 70)
    bab = run_portfolio("beta", N_LEGS, reverse=False)
    S_bab = summarize(bab, f"N={N_LEGS} LONG low-beta / SHORT high-beta")
    bab8 = run_portfolio("beta", N_LEGS_SENS, reverse=False)
    summarize(bab8, f"N={N_LEGS_SENS} (sensibilidad) LONG low-beta / SHORT high-beta")
    bab_inv = run_portfolio("beta", N_LEGS, reverse=True)
    S_bab_inv = summarize(bab_inv, f"N={N_LEGS} INVERTIDO: LONG high-beta / SHORT low-beta")

    print("\n" + "#" * 70 + "\n# TEST C — CROSS-SECTIONAL RESIDUAL MOMENTUM\n" + "#" * 70)
    rm = run_portfolio("resid_mom", N_LEGS, reverse=True)
    S_rm = summarize(rm, f"N={N_LEGS} LONG mayor resid-momentum / SHORT menor")
    rm_inv = run_portfolio("resid_mom", N_LEGS, reverse=False)
    S_rm_inv = summarize(rm_inv, f"N={N_LEGS} INVERTIDO: LONG menor resid-mom / SHORT mayor")

    print("\n" + "#" * 70 + "\n# TEST E — PLACEBO (bucket aleatorio, mismo N, mismo hedge)\n" + "#" * 70)
    plac = run_portfolio("beta", N_LEGS, reverse=False, randomize=True, seed=1)
    S_plac = summarize(plac, "PLACEBO random-bucket (N=5)")

    # ===== TEST F: sim economica =====
    print("\n" + "#" * 70 + "\n# TEST F — SIM ECONOMICA (capital<=450, RT=24bp full-turnover/semana + funding)\n" + "#" * 70)
    fh = {}
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    for s in list(P) + ["BTCUSDT"]:
        rows = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (s,)).fetchall()
        if rows:
            fh[s] = (np.array([r[0] for r in rows], np.int64), np.array([r[1] for r in rows], float))
    con.close()

    def funding_week(sym, day0, side):
        if sym not in fh:
            return 0.0
        ct, fr = fh[sym]
        t0 = int(day0) * 86400000; t1 = t0 + REBAL_DAYS * 86400000
        m = (ct >= t0) & (ct < t1)
        return side * float(fr[m].sum()) * 1e4   # long paga funding+, short lo recibe

    def econ(res_key, n_legs, reverse, cap, lev, label):
        legs_total = 2 * n_legs + 1     # longs+shorts+hedge
        notional_leg = cap * lev / legs_total
        pnl_weeks = []
        for i in rebal_idx:
            uni = universe_at(i, res_key); uni_beta = universe_at(i, "beta")
            if len(uni) < 2 * n_legs:
                continue
            order = sorted(uni, key=lambda s: uni[s], reverse=reverse)
            longs, shorts = order[:n_legs], order[-n_legs:]
            rl = [week_ret(s, i) for s in longs]; rs = [week_ret(s, i) for s in shorts]
            bl = [uni_beta.get(s, np.nan) for s in longs]; bs = [uni_beta.get(s, np.nan) for s in shorts]
            if any(v is None for v in rl + rs) or any(not np.isfinite(v) for v in bl + bs):
                continue
            port_beta = float(np.mean(bl) - np.mean(bs))
            bwr = btc_week_ret(i)
            pnl = 0.0; fund = 0.0
            for s, r in zip(longs, rl):
                pnl += r * notional_leg; fund += funding_week(s, cal[i], +1) / 1e4 * notional_leg
            for s, r in zip(shorts, rs):
                pnl -= r * notional_leg; fund += funding_week(s, cal[i], -1) / 1e4 * notional_leg
            hedge_notional = -port_beta * notional_leg * n_legs   # tamaño de la pata BTC
            pnl += hedge_notional * bwr
            fund += funding_week("BTCUSDT", cal[i], 1 if hedge_notional > 0 else -1) / 1e4 * abs(hedge_notional)
            gross_bp = pnl / (notional_leg * legs_total) * 1e4
            cost = RT_BP   # bp sobre el libro, turnover completo semanal (cota superior)
            net = pnl - cost / 1e4 * (notional_leg * legs_total) - fund
            pnl_weeks.append((int(cal[i]), net))
        if len(pnl_weeks) < 10:
            print(f"    {label}: n insuficiente"); return None
        arr = np.array([x[1] for x in pnl_weeks])
        span_w = len(pnl_weeks)
        net_mo = arr.sum() / (span_w / (30 / REBAL_DAYS))
        eq = np.cumsum(arr); dd = (np.maximum.accumulate(eq) - eq).max()
        bym = collections.defaultdict(float)
        for (dv, v) in pnl_weeks:
            mk = (date(1970, 1, 1) + timedelta(days=dv)).strftime("%Y-%m")
            bym[mk] += v
        months = np.array(sorted(bym.values()))
        flag = "  <<< SUPERA 150" if net_mo >= 150 else ""
        print(f"    {label}: semanas={span_w} NET/mes=${net_mo:.0f} notional/leg=${notional_leg:.0f} "
              f"maxDD=${dd:.0f} WR={float((arr>0).mean()):.2f} "
              f"m[P5/50/95]=[{np.percentile(months,5):.0f}/{np.median(months):.0f}/{np.percentile(months,95):.0f}] "
              f"meses+/-={int((months>0).sum())}/{int((months<0).sum())}{flag}")
        return net_mo

    results_econ = {}
    for name, key, rev in (("betting-against-beta", "beta", False), ("residual-momentum", "resid_mom", True)):
        for lev in (1, 2, 3):
            r = econ(key, N_LEGS, rev, 450, lev, f"{name} N={N_LEGS} lev={lev}x")
            results_econ[f"{name}_lev{lev}"] = r

    best = max([v for v in results_econ.values() if v is not None], default=-1e9)
    print(f"\n>>> MEJOR NET/mes (todas las variantes de sim económica): ${best:.0f}  (target $150)")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(P),
           "n_rebalances": len(rebal_idx), "results_econ": results_econ, "best_usd_mo": best}
    json.dump(out, open(os.path.join(ROOT, "scratch_r13_altbeta.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r13_altbeta.json")


if __name__ == "__main__":
    main()
