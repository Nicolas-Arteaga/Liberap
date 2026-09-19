"""
ROUND 6 — ADVERSARIAL ALPHA HUNT — screening económico barato (numpy).
3 hipótesis NUEVAS de estructura CONDICIONAL (A + B confirma + C dirección),
sobre datos que YA tenemos: taker_flow 15m + klines_clean 15m de
binance_vision_clean.db (8.5 meses, 2025-12-01 .. 2026-08-17).

TODO PRE-DECLARADO (sin grid). Universo = top-N por liquidez (mediana de
quote_volume 15m). Costo total asumido: 16 bp round-trip (fees+funding+slip+lat).

────────────────────────────────────────────────────────────────────────────
H21 — VOLUME-CLIMAX EXHAUSTION (fill-count climax + one-sided taker + NO follow-through)
  Participante obligado: retail hitting market en pánico/FOMO + stop-runs.
  Catalizador: trade_count z>=2 (rolling 30d) AND taker_buy_ratio >=0.70 o <=0.30.
  Confirmación C: la barra t+1 NO continúa ( |ret[t+1]| < 0.5*|ret[t]| ).
  Predicción: entrada al close[t+1] EN CONTRA de la dirección del climax -> reversión.
  Falsificación: reversión <= costos / placebo igual / signo inestable.

H22 — TAKER/PRICE DIVERGENCE (participantes distintos: agresión taker vs precio realizado)
  Participante obligado: la contraparte pasiva (MM / vendedor grande) que absorbe.
  Catalizador: sobre ventana W=4 barras, z(ret_W)<=-1 AND z(taker_buy_frac_W)>=+1
               (precio cae fuerte mientras los takers COMPRAN agresivo) -> bounce.
               Simétrico para el lado bearish.
  Predicción: retorno forward revierte la caída (bounce) / la subida (drop).
  Falsificación: sin bounce / placebo igual / no supera a un matched control
                 (misma caída, taker neutro).

H26 — VOL-EXPANSION + TAKER CONFIRMATION (expansión + flujo que la respalda continúa)
  Participante obligado: dinero informado (flujo) vs stop-run sin demanda real.
  Catalizador: rv_pct cruza de <0.30 a >0.70 en <=2 barras (expansión de vol).
  Confirmación B/C: taker_imbalance de las 2 barras del cruce coincide con la
               dirección del cruce -> "confirmado"; opuesto -> "divergente".
  Predicción: confirmado -> continuación ; divergente -> reversión.
  Falsificación: el flujo no discrimina continuación de reversión.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
BAR = 15 * 60 * 1000
TOP_N = 150
ROLL = 2880          # 30 d de barras 15m para z-scores / percentiles
PLACEBO = 96         # +24 h
COST_RT_BP = 16.0
HORIZONS = [1, 2, 4, 8]
rng = np.random.default_rng(20260909)


def zscore_causal(a, win):
    """z-score rolling causal (solo pasado), vectorizado con cumsum."""
    n = len(a)
    x = np.nan_to_num(a, nan=0.0)
    ok = (~np.isnan(a)).astype(float)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    cq = np.concatenate([[0.0], np.cumsum(x * x)])
    ck = np.concatenate([[0.0], np.cumsum(ok)])
    i = np.arange(n)
    lo = i - win
    valid = lo >= 0
    out = np.full(n, np.nan)
    k = np.where(valid, ck[i] - ck[np.clip(lo, 0, None)], 0.0)
    m = np.where(k > 0, (cs[i] - cs[np.clip(lo, 0, None)]) / np.where(k > 0, k, 1), np.nan)
    v = np.where(k > 0, (cq[i] - cq[np.clip(lo, 0, None)]) / np.where(k > 0, k, 1) - m * m, np.nan)
    s = np.sqrt(np.clip(v, 0, None))
    good = valid & (k >= win * 0.5) & (s > 0)
    out[good] = (a[good] - m[good]) / s[good]
    return out


def pctile_causal(a, win):
    """percentil rolling causal (fracción del pasado < valor actual), con sliding_window_view."""
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(a)
    out = np.full(n, np.nan)
    if n <= win:
        return out
    sw = sliding_window_view(a, win)          # shape (n-win+1, win); fila i = a[i:i+win]
    # para el bar t (t>=win) la ventana pasada es a[t-win:t] = sw[t-win]
    cur = a[win:n]
    past = sw[0:n - win]
    with np.errstate(invalid="ignore"):
        frac = np.nanmean(past < cur[:, None], axis=1)
    out[win:n] = frac
    return out


def load(con, sym):
    r = con.execute(
        "SELECT k.open_time,k.open,k.high,k.low,k.close,t.quote_volume,t.trade_count,t.taker_buy_quote "
        "FROM klines_clean k JOIN taker_flow t "
        "ON k.symbol=t.symbol AND k.interval=t.interval AND k.open_time=t.open_time "
        "WHERE k.symbol=? AND k.interval='15m' ORDER BY k.open_time", (sym,)).fetchall()
    if len(r) < ROLL + 400:
        return None
    a = np.array(r, dtype=float)
    return dict(t=a[:, 0], o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4],
               qv=a[:, 5], tc=a[:, 6], tbq=a[:, 7])


def fwd_ret(c, idx, h):
    """log return c[idx+h]/c[idx]; nan si fuera de rango."""
    j = idx + h
    out = np.full(len(idx), np.nan)
    ok = j < len(c)
    out[ok] = np.log(c[j[ok]] / c[idx[ok]])
    return out


def agg(pairs_by_h):
    """pairs_by_h: dict h -> list of (sym, value). Cluster-bootstrap sobre símbolos, rápido."""
    res = {}
    for h, pairs in pairs_by_h.items():
        if len(pairs) < 40:
            res[h] = {"n": len(pairs), "note": "muestra chica"}
            continue
        by = {}
        for s, v in pairs:
            by.setdefault(s, []).append(v)
        sym_arr = {s: np.asarray(vs, float) for s, vs in by.items()}
        us = list(sym_arr)
        allv = np.concatenate([sym_arr[s] for s in us])
        mean_bp = allv.mean() * 1e4
        sym_sum = np.array([sym_arr[s].sum() for s in us])
        sym_cnt = np.array([len(sym_arr[s]) for s in us], float)
        sym_mean = sym_sum / sym_cnt
        # cluster bootstrap: resample símbolos, media ponderada por nº de eventos
        idx = np.arange(len(us))
        bs = np.empty(3000)
        for b in range(3000):
            pick = rng.choice(idx, len(idx))
            bs[b] = (sym_sum[pick].sum()) / (sym_cnt[pick].sum())
        bs = np.sort(bs) * 1e4
        pos = sym_sum[sym_sum > 0].sum() or 1e-9
        top5 = np.sort(sym_sum)[::-1][:5]
        conc = top5[top5 > 0].sum() / pos
        half = len(allv) // 2
        h0 = allv[:half].mean() * 1e4; h1 = allv[half:].mean() * 1e4
        res[h] = dict(n=len(allv), n_sym=len(us),
                      mean_bp=round(float(mean_bp), 1),
                      ci_bp=[round(float(bs[150]), 1), round(float(bs[2849]), 1)],
                      after_cost_bp=round(abs(float(mean_bp)) - COST_RT_BP, 1),
                      half0_bp=round(float(h0), 1), half1_bp=round(float(h1), 1),
                      halves_same_sign=bool((h0 > 0) == (h1 > 0)),
                      frac_symbols_positive=round(float((sym_sum > 0).mean()), 2),
                      top5_pnl_concentration=round(float(conc), 2))
    return res


def verdict(name, real, placebo, ctrl=None):
    """Regla PROMISING pre-declarada: algún horizonte con
       |mean|>=COST+4 ∧ CI excluye 0 ∧ mismo signo en las 2 mitades ∧
       frac_symbols_positive>=0.55 ∧ top5_conc<=0.6 ∧ placebo <40% del efecto
       ∧ (si hay ctrl) el real supera al ctrl en magnitud."""
    for h in HORIZONS:
        r = real.get(h, {})
        if r.get("n", 0) < 100 or "mean_bp" not in r:
            continue
        m = r["mean_bp"]; ci = r["ci_bp"]
        ci_excl0 = (ci[0] > 0 and ci[1] > 0) or (ci[0] < 0 and ci[1] < 0)
        pb = placebo.get(h, {}).get("mean_bp", 0.0)
        cond = (abs(m) >= COST_RT_BP + 4 and ci_excl0 and r["halves_same_sign"]
                and r["frac_symbols_positive"] >= 0.55 and r["top5_pnl_concentration"] <= 0.6
                and abs(pb) < 0.4 * abs(m))
        if ctrl is not None:
            cr = ctrl.get(h, {}).get("mean_bp", None)
            if cr is not None and abs(m) <= abs(cr):
                cond = False
        if cond:
            return "PROMISING", h
    # PARK vs FAILED: si algún horizonte tiene |mean|>costo y CI excluye 0 pero
    # falla otro criterio -> PARK. Si nada supera costos -> FAILED.
    for h in HORIZONS:
        r = real.get(h, {})
        if "mean_bp" in r and abs(r["mean_bp"]) >= COST_RT_BP and \
           ((r["ci_bp"][0] > 0 and r["ci_bp"][1] > 0) or (r["ci_bp"][0] < 0 and r["ci_bp"][1] < 0)):
            return "PARK", h
    return "FAILED", None


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    liq = con.execute(
        "SELECT symbol, COUNT(*) n, "
        "  (SELECT AVG(quote_volume) FROM taker_flow t2 WHERE t2.symbol=t.symbol AND t2.interval='15m') av "
        "FROM taker_flow t WHERE interval='15m' GROUP BY symbol HAVING n > ? ORDER BY av DESC LIMIT ?",
        (ROLL + 400, TOP_N)).fetchall()
    syms = [s for s, _, _ in liq]
    print(f"universo: {len(syms)} símbolos líquidos (15m taker_flow)")

    H21 = {h: [] for h in HORIZONS}; H21p = {h: [] for h in HORIZONS}; H21c = {h: [] for h in HORIZONS}
    H22 = {h: [] for h in HORIZONS}; H22p = {h: [] for h in HORIZONS}; H22c = {h: [] for h in HORIZONS}
    H26 = {h: [] for h in HORIZONS}; H26p = {h: [] for h in HORIZONS}; H26div = {h: [] for h in HORIZONS}
    counts = dict(h21=0, h21c=0, h22=0, h22c=0, h26conf=0, h26div=0)

    for si, sym in enumerate(syms):
        d = load(con, sym)
        if d is None:
            continue
        c = d["c"]; n = len(c)
        lr = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
        tbr = np.divide(d["tbq"], d["qv"], out=np.full(n, np.nan), where=d["qv"] > 0)   # frac buy $
        timb = 2 * tbr - 1

        # ---------- H21 ----------
        tc_z = zscore_causal(d["tc"], ROLL)
        bar_ret = np.log(c / d["o"])
        climax = (tc_z >= 2.0) & ((tbr >= 0.70) | (tbr <= 0.30))
        idxs = np.where(climax)[0]
        last = -999
        for t in idxs:
            if t < ROLL or t + 1 + max(HORIZONS) + PLACEBO >= n or t - last < 4:
                continue
            dirn = 1 if bar_ret[t] > 0 else -1
            r1 = lr[t + 1]
            if np.isnan(r1):
                continue
            noft = abs(r1) < 0.5 * abs(bar_ret[t])
            last = t
            base = t + 1
            for h in HORIZONS:
                if base + h < n:
                    fr = -dirn * np.log(c[base + h] / c[base])   # entrada en contra del climax
                    (H21 if noft else H21c)[h].append((sym, fr))
                    if base + PLACEBO + h < n:
                        frp = -dirn * np.log(c[base + PLACEBO + h] / c[base + PLACEBO])
                        (H21p if noft else H21c)[h].append((sym, frp)) if noft else None
            counts["h21" if noft else "h21c"] += 1

        # ---------- H22 ----------
        W = 4
        retW = np.concatenate([np.full(W, np.nan), np.log(c[W:] / c[:-W])])
        qvW = np.convolve(np.nan_to_num(d["qv"]), np.ones(W))[:n]  # BACKWARD (causal): sum(qv[t-W+1:t+1])
        tbqW = np.convolve(np.nan_to_num(d["tbq"]), np.ones(W))[:n]  # BACKWARD (causal)
        tbrW = np.divide(tbqW, qvW, out=np.full(n, np.nan), where=qvW > 0)
        z_ret = zscore_causal(retW, ROLL)
        z_tbr = zscore_causal(tbrW, ROLL)
        bull = (z_ret <= -1.0) & (z_tbr >= 1.0)
        bear = (z_ret >= 1.0) & (z_tbr <= -1.0)
        ctrl = (np.abs(z_ret) >= 1.0) & (np.abs(z_tbr) <= 0.3)
        for kind, mask, sgn in (("bull", bull, 1), ("bear", bear, -1), ("ctrl", ctrl, 0)):
            ii = np.where(mask)[0]
            lastc = -999
            for t in ii:
                if t < ROLL or t + max(HORIZONS) + PLACEBO >= n or t - lastc < W:
                    continue
                lastc = t
                s = sgn if sgn != 0 else (1 if z_ret[t] < 0 else -1)   # ctrl: dir = signo de la caída/subida, esperando reversión
                for h in HORIZONS:
                    fr = s * np.log(c[t + h] / c[t])
                    if kind == "ctrl":
                        H22c[h].append((sym, fr))
                    else:
                        H22[h].append((sym, fr))
                        frp = s * np.log(c[t + PLACEBO + h] / c[t + PLACEBO])
                        H22p[h].append((sym, frp))
                counts["h22c" if kind == "ctrl" else "h22"] += 1

        # ---------- H26 ----------
        from numpy.lib.stride_tricks import sliding_window_view
        rv = np.full(n, np.nan)
        if n > 9:
            rv[9:] = np.nanstd(sliding_window_view(lr, 8)[1:n - 8], axis=1)
        rvp = pctile_causal(rv, 1344)   # 14 d
        cross = np.zeros(n, bool)
        cross[3:] = (rvp[3:] > 0.70) & (np.roll(rvp, 2)[3:] < 0.30)
        cross[np.isnan(rvp)] = False
        ii = np.where(cross)[0]
        lastx = -999
        for t in ii:
            if t < 1344 or t + max(HORIZONS) + PLACEBO >= n or t - lastx < 4:
                continue
            lastx = t
            dirn = 1 if (c[t] > c[t - 2]) else -1
            imb2 = np.nanmean(timb[t - 1:t + 1])
            confirmed = np.sign(imb2) == dirn
            for h in HORIZONS:
                if confirmed:
                    fr = dirn * np.log(c[t + h] / c[t])          # continuación
                    H26[h].append((sym, fr))
                    frp = dirn * np.log(c[t + PLACEBO + h] / c[t + PLACEBO])
                    H26p[h].append((sym, frp))
                else:
                    fr = -dirn * np.log(c[t + h] / c[t])         # reversión (esperada)
                    H26div[h].append((sym, fr))
            counts["h26conf" if confirmed else "h26div"] += 1

        if si % 40 == 0:
            print(f"  {si}/{len(syms)}  counts={counts}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "universe": len(syms), "counts": counts, "cost_rt_bp": COST_RT_BP, "results": {}}

    def block(name, real, placebo, ctrl):
        r = agg(real); p = agg(placebo); c_ = agg(ctrl) if ctrl else None
        v, hh = verdict(name, r, p, c_)
        out["results"][name] = {"real": r, "placebo": p, "control": c_, "verdict": v, "verdict_horizon": hh}
        print(f"\n===== {name}  ->  {v} (h={hh}) =====")
        for h in HORIZONS:
            rr = r.get(h, {})
            if "mean_bp" not in rr:
                print(f"  h={h}: {rr}"); continue
            pb = p.get(h, {}).get("mean_bp", "?")
            cc = c_.get(h, {}).get("mean_bp", "-") if c_ else "-"
            print(f"  h={h*15:>3}m  mean={rr['mean_bp']:>7} bp  CI{rr['ci_bp']}  afterCost={rr['after_cost_bp']}  "
                  f"placebo={pb}  ctrl={cc}  halves={rr['half0_bp']}/{rr['half1_bp']} same={rr['halves_same_sign']}  "
                  f"symPos={rr['frac_symbols_positive']}  top5conc={rr['top5_pnl_concentration']}  n={rr['n']}")

    block("H21_climax_exhaustion", H21, H21p, H21c)
    block("H22_taker_price_divergence", H22, H22p, H22c)
    block("H26_volexp_taker_confirm", H26, H26p, H26div)

    json.dump(out, open(os.path.join(ROOT, "scratch_r6_screen.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r6_screen.json")
    surv = [k for k, v in out["results"].items() if v["verdict"] == "PROMISING"]
    print("SURVIVORS (PROMISING):", surv or "NINGUNO — NO ALPHA FOUND en este screen")


if __name__ == "__main__":
    main()
