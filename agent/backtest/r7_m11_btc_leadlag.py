"""
ROUND 7 — EXPERIMENTO 2 — M11: BTC 5-MIN SHOCK -> ALT LEAD-LAG SNAP (sub-15m).

H9.1 (lead-lag sub-segundo) fue declarada UNTESTABLE a 15m. H18 (shock BTC 1h ->
catch-up de alts 1-4h) fue FAILED. Este experimento cubre el hueco intermedio:
shock de BTC en la barra de 5m, reaccion del alt en las siguientes 1-6 barras de
5m (5-30 min). Es la escala donde vive la latencia MECANICA real (motor de
liquidaciones, MMs recotizando, bots de arbitraje perp-perp): del orden de
segundos a minutos, no de horas.

MECANISMO: BTC pega un salto brusco. Los alts que por microestructura (libro
fino, MM lento, sin flujo propio) NO se movieron con BTC en esa misma barra
tienen una reaccion pendiente. Si es lag mecanico -> catch-up en la direccion de
BTC en los proximos minutos. Si el alt "eligio" no moverse (fuerza
idiosincratica) -> no hay catch-up. La prediccion NETA depende de cual domina.

EVENTO (grid de 5m, universo = BTCUSDT + top-N alts liquidos de klines_5m):
  bret[T]  = log(btc_close[T]/btc_close[T-1])           (retorno 5m de BTC)
  z_bret   = zscore_causal(bret, ROLL)  (ROLL=8640 ~ 30d de 5m)
  shock    = |z_bret| >= ZK  (ZK=3.0)   -> ~top 0.3% de barras
  para cada alt en la barra T del shock:
    aret[T]     = log(alt_close[T]/alt_close[T-1])
    beta7d      = cov(aret,bret)/var(bret) rolling causal 7d (2016 barras)
    resid       = aret[T] - beta7d*bret[T]
    underreact  = sign(resid) == -sign(bret[T])  AND  |resid| >= URK*rolling_std(aret) (URK=1.0)
                  (el alt se movio MENOS que su beta manda, en contra de BTC)

ENTRADA: open[T+1] del alt. Horizontes 1/2/3/6 barras (5/10/15/30 min), open->open.
Direccion evaluada = sign(bret[T])  (apostamos catch-up del alt hacia BTC).

CONTROLES:
  placebo   : mismos indices, ventana forward +PLACEBO barras (+288 = +24h).
  matched   : alts que SI se movieron con BTC (|resid| <= 0.3*rolling_std) ->
              si tienen el mismo drift forward, es beta de mercado continuando,
              no lead-lag.
  uncond    : TODAS los alts en la barra del shock (sin filtro underreact) ->
              aisla "todo driftea tras un shock de BTC".
  late_spike (secundario, solo overlap con btc_klines_1m 2026-06..08):
              subset donde el salto de BTC ocurrio en los ultimos 2 min de la
              barra T -> el alt tuvo ~0 tiempo de reaccionar -> prediccion mas
              fuerte de catch-up.

VEREDICTO PROMISING (algun horizonte): |after_cost| >= 4bp ; CI excl 0 ;
halves_same_sign ; frac_sym_pos >= 0.55 ; top5_conc <= 0.6 ;
|placebo| < 0.4*|efecto| ; el efecto SUPERA a 'uncond' y a 'matched' en magnitud.
Supera costo pero falla un criterio -> PARK. Nada supera costo -> FAILED.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone
from r7_common import zscore_causal, agg_pairs

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
TOP_N = 120
ROLL = 8640          # 30 d de 5m
BETAWIN = 2016       # 7 d de 5m
ZK = 3.0
URK = 1.0
PLACEBO = 288        # +24 h
HORIZONS = [1, 2, 3, 6]
COST_RT_BP = 16.0


def load_5m(con, sym):
    r = con.execute(
        "SELECT open_time,open,close FROM klines_5m WHERE symbol=? AND interval='5m' ORDER BY open_time",
        (sym,)).fetchall()
    if len(r) < ROLL + 800:
        return None
    a = np.array(r, float)
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2]


def roll_std_causal(a, win):
    n = len(a); x = np.nan_to_num(a)
    cs = np.concatenate([[0.0], np.cumsum(x)]); cq = np.concatenate([[0.0], np.cumsum(x * x)])
    i = np.arange(n); lo = np.clip(i - win, 0, None); k = (i - lo).astype(float)
    m = np.where(k > 0, (cs[i] - cs[lo]) / np.where(k > 0, k, 1), np.nan)
    v = np.where(k > 0, (cq[i] - cq[lo]) / np.where(k > 0, k, 1) - m * m, np.nan)
    s = np.sqrt(np.clip(v, 0, None)); s[i < win] = np.nan
    return s


def roll_beta_causal(aret, bret, win):
    """beta = E[a*b]/E[b*b] rolling causal [t-win,t)."""
    n = len(aret)
    ab = np.nan_to_num(aret * bret); bb = np.nan_to_num(bret * bret)
    cab = np.concatenate([[0.0], np.cumsum(ab)]); cbb = np.concatenate([[0.0], np.cumsum(bb)])
    i = np.arange(n); lo = np.clip(i - win, 0, None)
    num = cab[i] - cab[lo]; den = cbb[i] - cbb[lo]
    out = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    out[i < win] = np.nan
    return out


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    b = load_5m(con, "BTCUSDT")
    bt, bo, bc = b
    bret = np.concatenate([[np.nan], np.log(bc[1:] / bc[:-1])])
    z_bret = zscore_causal(bret, ROLL)
    shock_mask = np.abs(z_bret) >= ZK
    tpos = {int(v): i for i, v in enumerate(bt)}

    rows = con.execute(
        "SELECT symbol, COUNT(*) n, AVG(open*volume) av FROM klines_5m WHERE interval='5m' "
        "GROUP BY symbol HAVING n > ? ORDER BY av DESC LIMIT ?", (ROLL + 800, TOP_N + 5)).fetchall()
    syms = [r[0] for r in rows if r[0] != "BTCUSDT"][:TOP_N]

    B = {k: {h: [] for h in HORIZONS} for k in ("real", "plac", "match", "uncond")}
    n_ev = 0; n_shock_bars = int(shock_mask.sum()); used = 0
    tmin = tmax = None
    for sym in syms:
        d = load_5m(con, sym)
        if d is None:
            continue
        at, ao, ac = d
        # alinear al índice de BTC
        common = np.array([tpos[int(v)] for v in at if int(v) in tpos], dtype=np.int64)
        if len(common) < ROLL + 800:
            continue
        # mapa inverso: para cada bar del alt, su índice en BTC
        amask = np.array([int(v) in tpos for v in at])
        aidx_btc = np.array([tpos.get(int(v), -1) for v in at])
        used += 1
        if tmin is None:
            tmin, tmax = at[0], at[-1]
        else:
            tmin, tmax = min(tmin, at[0]), max(tmax, at[-1])
        n = len(ac)
        aret = np.concatenate([[np.nan], np.log(ac[1:] / ac[:-1])])
        bret_al = np.where(aidx_btc >= 0, bret[np.clip(aidx_btc, 0, len(bret) - 1)], np.nan)
        zb_al = np.where(aidx_btc >= 0, z_bret[np.clip(aidx_btc, 0, len(z_bret) - 1)], np.nan)
        beta = roll_beta_causal(aret, bret_al, BETAWIN)
        resid = aret - beta * bret_al
        rs = roll_std_causal(aret, BETAWIN)
        is_shock = np.abs(zb_al) >= ZK
        sgn_b = np.sign(bret_al)
        under = is_shock & (np.sign(resid) == -sgn_b) & (np.abs(resid) >= URK * rs)
        matched = is_shock & (np.abs(resid) <= 0.3 * rs)
        maxh = max(HORIZONS)
        for tag, mask in (("real", under), ("match", matched), ("uncond", is_shock)):
            idx = np.where(mask)[0]
            idx = idx[(idx >= BETAWIN) & (idx + 1 + maxh + PLACEBO < n)]
            keep = []; last = -999
            for i in idx:
                if i - last >= 1:
                    keep.append(i); last = i
            idx = np.array(keep, int)
            if tag == "real":
                n_ev += len(idx)
            e = idx + 1
            s_ = sgn_b[idx]
            for h in HORIZONS:
                rr = s_ * np.log(ao[e + h] / ao[e])
                for v_ in rr:
                    B[tag][h].append((sym, v_))
                if tag == "real":
                    rp = s_ * np.log(ao[e + PLACEBO + h] / ao[e + PLACEBO])
                    for v_ in rp:
                        B["plac"][h].append((sym, v_))
    con.close()

    months = (int(tmax) - int(tmin)) / (30 * 86400000)
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "symbols_used": used, "span_months": round(months, 1),
           "btc_shock_bars": n_shock_bars, "alt_underreact_events": n_ev,
           "params": dict(TOP_N=TOP_N, ROLL=ROLL, BETAWIN=BETAWIN, ZK=ZK, URK=URK,
                          PLACEBO=PLACEBO, HORIZONS=HORIZONS, COST_RT_BP=COST_RT_BP),
           "horizons": {}}
    print(f"universo {used} alts · ~{months:.1f} meses · BTC shock bars={n_shock_bars} · alt underreact events={n_ev}")
    for h in HORIZONS:
        R = agg_pairs(B["real"][h]); P = agg_pairs(B["plac"][h])
        M = agg_pairs(B["match"][h]); U = agg_pairs(B["uncond"][h])
        after = round(R["mean_bp"] - np.sign(R["mean_bp"]) * COST_RT_BP, 2) if "mean_bp" in R else None
        out["horizons"][h] = {"real": R, "placebo": P, "matched": M, "uncond": U, "after_cost_bp": after}
        print(f"\n h={h*5:>3}m  real={R.get('mean_bp')} bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} "
              f"halves=({R.get('half1_bp')},{R.get('half2_bp')}) symPos={R.get('frac_sym_pos')} conc={R.get('top5_conc')} n={R.get('n')}")
        print(f"        placebo={P.get('mean_bp')}  matched(se movió c/BTC)={M.get('mean_bp')}  uncond(todos)={U.get('mean_bp')}  after_cost={after}")

    path = os.path.join(ROOT, "scratch_r7_m11_btc_leadlag.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
