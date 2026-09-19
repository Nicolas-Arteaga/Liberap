"""
ROUND 6 — H22 DEEP VALIDATION (el único survivor del screen).
Escepticismo escalado: el screen dio +24 bp @15m / +72 bp @60m — hay que
verificar que no sea lookahead/artefacto antes de declararlo PROMISING.

Cambios vs el screen (todos MÁS conservadores):
  - Entrada REALISTA: al OPEN de la barra t+1 (el evento se conoce recién al
    close de t; no se puede fillear en close[t]).
  - Slippage explícito: {0, 2, 5} bp por lado, ADEMÁS de 8 bp de fee RT.
  - Bull y Bear por SEPARADO (no pooled) — si solo un lado funciona, es más débil.
  - Split temporal en TERCIOS (params ya congelados; no se re-fitea nada).
  - Exit a horizonte fijo (1/2/4 barras = 15/30/60 min) desde el open de t+1.
  - Matched control estricto: mismo |z_ret|, taker NEUTRO (|z_tbr|<=0.3).
  - Placebo +96 barras.
  - Monetización: PnL por trade con $150 nocional, y estimación mensual con la
    frecuencia real.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
TOP_N = 150
ROLL = 2880
W = 4
PLACEBO = 96
HORIZONS = [1, 2, 4]     # barras de 15m desde el open de t+1
FEE_RT_BP = 8.0
SLIP_SIDE = [0.0, 2.0, 5.0]
MARGIN = 150.0
rng = np.random.default_rng(20260909)


def zc(a, win):
    n = len(a); x = np.nan_to_num(a); ok = (~np.isnan(a)).astype(float)
    cs = np.concatenate([[0.0], np.cumsum(x)]); cq = np.concatenate([[0.0], np.cumsum(x * x)])
    ck = np.concatenate([[0.0], np.cumsum(ok)])
    i = np.arange(n); lo = i - win; v = lo >= 0
    lc = np.clip(lo, 0, None)
    k = np.where(v, ck[i] - ck[lc], 0.0)
    m = np.where(k > 0, (cs[i] - cs[lc]) / np.where(k > 0, k, 1), np.nan)
    var = np.where(k > 0, (cq[i] - cq[lc]) / np.where(k > 0, k, 1) - m * m, np.nan)
    s = np.sqrt(np.clip(var, 0, None))
    out = np.full(n, np.nan); g = v & (k >= win * 0.5) & (s > 0)
    out[g] = (a[g] - m[g]) / s[g]
    return out


def load(con, sym):
    r = con.execute(
        "SELECT k.open_time,k.open,k.close,t.quote_volume,t.taker_buy_quote "
        "FROM klines_clean k JOIN taker_flow t ON k.symbol=t.symbol AND k.interval=t.interval AND k.open_time=t.open_time "
        "WHERE k.symbol=? AND k.interval='15m' ORDER BY k.open_time", (sym,)).fetchall()
    if len(r) < ROLL + 400:
        return None
    a = np.array(r, float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]


def collect():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    liq = con.execute(
        "SELECT symbol FROM taker_flow t WHERE interval='15m' GROUP BY symbol "
        "HAVING COUNT(*)>? ORDER BY (SELECT AVG(quote_volume) FROM taker_flow t2 WHERE t2.symbol=t.symbol AND t2.interval='15m') DESC LIMIT ?",
        (ROLL + 400, TOP_N)).fetchall()
    syms = [s for (s,) in liq]
    tmin_all = con.execute("SELECT MIN(open_time) FROM klines_clean WHERE interval='15m'").fetchone()[0]
    tmax_all = con.execute("SELECT MAX(open_time) FROM klines_clean WHERE interval='15m'").fetchone()[0]
    third = (tmax_all - tmin_all) / 3

    ev = []   # (sym, kind, t_open_ms, entry_open, [c at open_of(t+1+h) for h], [placebo c], seg_third)
    for sym in syms:
        r = load(con, sym)
        if r is None:
            continue
        tms, o, c, qv, tbq = r
        n = len(c)
        retW = np.concatenate([np.full(W, np.nan), np.log(c[W:] / c[:-W])])
        qvW = np.convolve(np.nan_to_num(qv), np.ones(W))[:n]  # BACKWARD (causal)
        tbqW = np.convolve(np.nan_to_num(tbq), np.ones(W))[:n]  # BACKWARD (causal)
        tbrW = np.divide(tbqW, qvW, out=np.full(n, np.nan), where=qvW > 0)
        zret = zc(retW, ROLL); ztbr = zc(tbrW, ROLL)
        bull = (zret <= -1.0) & (ztbr >= 1.0)
        bear = (zret >= 1.0) & (ztbr <= -1.0)
        ctrlm = (np.abs(zret) >= 1.0) & (np.abs(ztbr) <= 0.3)
        for kind, mask in (("bull", bull), ("bear", bear), ("ctrl_bull", ctrlm & (zret < 0)), ("ctrl_bear", ctrlm & (zret > 0))):
            last = -999
            for t in np.where(mask)[0]:
                if t < ROLL or t + 1 + max(HORIZONS) + PLACEBO >= n or t - last < W:
                    continue
                last = t
                e = t + 1                      # entrada al OPEN de t+1
                seg = int((tms[t] - tms[0]) // third) if third > 0 else 0
                ret_h = []
                for h in HORIZONS:
                    ret_h.append(np.log(o[e + h] / o[e]))       # open->open, horizonte fijo
                plac_h = [np.log(o[e + PLACEBO + h] / o[e + PLACEBO]) for h in HORIZONS]
                ev.append((sym, kind, int(tms[t]), seg, ret_h, plac_h))
    return syms, ev, third, tmin_all


def side_sign(kind):
    return 1 if "bull" in kind else -1   # bull: esperamos precio SUBE -> long ; bear: baja -> short


def stats(rows, hi):
    """rows: list de (sym, seg, dir_adj_ret). Devuelve dict."""
    if len(rows) < 40:
        return {"n": len(rows)}
    by = {}
    for s, seg, v in rows:
        by.setdefault(s, []).append(v)
    us = list(by)
    sym_sum = np.array([np.sum(by[s]) for s in us])
    sym_cnt = np.array([len(by[s]) for s in us], float)
    allv = np.concatenate([np.asarray(by[s]) for s in us])
    mean_bp = allv.mean() * 1e4
    idx = np.arange(len(us))
    bs = np.array([sym_sum[p].sum() / sym_cnt[p].sum() for p in (rng.choice(idx, len(idx)) for _ in range(3000))]) * 1e4
    bs.sort()
    # por tercio
    seg_means = {}
    for k in (0, 1, 2):
        sv = [v for s, seg, v in rows if seg == k]
        seg_means[k] = round(float(np.mean(sv)) * 1e4, 1) if len(sv) >= 20 else None
    return dict(n=len(allv), n_sym=len(us), mean_bp=round(float(mean_bp), 1),
               ci_bp=[round(float(bs[150]), 1), round(float(bs[2849]), 1)],
               frac_sym_pos=round(float((sym_sum > 0).mean()), 2),
               top5_conc=round(float(np.sort(sym_sum)[::-1][:5].clip(0).sum() / (sym_sum.clip(0).sum() or 1)), 2),
               by_third=seg_means)


def main():
    syms, ev, third, t0 = collect()
    months = (max(e[2] for e in ev) - min(e[2] for e in ev)) / (30 * 86400000)
    print(f"universo {len(syms)} · eventos totales {len(ev)} · ~{months:.1f} meses")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(syms),
           "span_months": round(months, 1), "sides": {}}

    for kind in ("bull", "bear"):
        base = [e for e in ev if e[1] == kind]
        ctrl = [e for e in ev if e[1] == f"ctrl_{kind}"]
        sg = side_sign(kind)
        print(f"\n===== {kind.upper()}  n={len(base)}  (ctrl n={len(ctrl)}) =====")
        blk = {"n": len(base), "n_ctrl": len(ctrl), "horizons": {}}
        for hi, h in enumerate(HORIZONS):
            real_rows = [(s, seg, sg * rh[hi]) for (s, k, ts, seg, rh, ph) in base]
            plac_rows = [(s, seg, sg * ph[hi]) for (s, k, ts, seg, rh, ph) in base]
            ctrl_rows = [(s, seg, sg * rh[hi]) for (s, k, ts, seg, rh, ph) in ctrl]
            R = stats(real_rows, hi); P = stats(plac_rows, hi); C = stats(ctrl_rows, hi)
            # costos: fee RT + 2*slip
            after = {}
            for sl in SLIP_SIDE:
                after[sl] = round(R["mean_bp"] - (FEE_RT_BP + 2 * sl), 1)
            # PnL $ por trade a slippage 2bp/lado
            net_bp_2 = R["mean_bp"] - (FEE_RT_BP + 4)
            pnl_usd = round(MARGIN * net_bp_2 / 1e4, 3)
            blk["horizons"][h] = {"real": R, "placebo_mean_bp": P.get("mean_bp"),
                                  "ctrl_mean_bp": C.get("mean_bp"),
                                  "after_cost_bp": after, "net_bp_at_2bp_slip": round(net_bp_2, 1),
                                  "pnl_usd_per_trade_at_2bp": pnl_usd}
            print(f"  h={h*15:>3}m  real={R['mean_bp']:>7} bp CI{R['ci_bp']}  placebo={P.get('mean_bp')}  ctrl={C.get('mean_bp')}  "
                  f"thirds={R['by_third']}  symPos={R['frac_sym_pos']}  conc={R['top5_conc']}  "
                  f"| after0/2/5bp={after[0.0]}/{after[2.0]}/{after[5.0]}  $/trade@2bp={pnl_usd}")
        out["sides"][kind] = blk

    # monetización: eventos por mes por lado, y PnL mensual a slippage 2bp, horizonte 2 (30m)
    for kind in ("bull", "bear"):
        n = out["sides"][kind]["n"]
        ev_per_month = n / months
        h = 2  # 30 min
        net_bp = out["sides"][kind]["horizons"][h]["net_bp_at_2bp_slip"]
        # capital: si el holding es 30m y hay ev_per_month eventos repartidos en ~150 símbolos,
        # 3 slots de $150 alcanzan de sobra (solapamiento bajo). Nocional efectivo ~ $150/trade.
        monthly_usd = ev_per_month * MARGIN * net_bp / 1e4
        out["sides"][kind]["monetization_30m_2bp"] = {
            "events_per_month": round(ev_per_month, 1),
            "net_bp_per_trade": net_bp,
            "monthly_pnl_usd_est": round(monthly_usd, 1),
            "note": "$150 nocional/trade, holding 30m, 3 slots de $150 sobran (solapamiento bajo)"
        }
        print(f"\n{kind}: {ev_per_month:.0f} ev/mes · net {net_bp} bp/trade @30m · PnL mensual estimado ≈ ${monthly_usd:.0f} (con $150/trade)")

    json.dump(out, open(os.path.join(ROOT, "scratch_r6_h22_validate.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r6_h22_validate.json")


if __name__ == "__main__":
    main()
