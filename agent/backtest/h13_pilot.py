"""
H13 PILOT — OI / PRICE DIVERGENCE EVENT STUDY (piloto, NO concluyente)

Objetivo: ¿hay un efecto temporal consistente y económicamente relevante
alrededor de eventos de divergencia/convergencia OI-precio, que justifique
seguir cuando haya >=70 dias de OI? NO demuestra rentabilidad.

======================= PARAMETROS PRE-DECLARADOS =======================
(congelados ANTES de mirar cualquier resultado; sin grid search)

  BAR            = 1h   (OI nativo 5m -> se resamplea a 1h tomando el ULTIMO
                        valor de cada hora; klines.db 1h cubre 99% de los 45
                        simbolos en la ventana de OI)
  LOOKBACK       = 4h   (4 barras) para definir el evento
  Z_WIN          = 7d   (168 barras) ventana rolling CAUSAL (solo hacia atras)
                        para estandarizar dOI% y ret_prior
  Z_THRESH       = 1.0  el evento requiere |z(dOI%)| >= 1.0 AND
                        |z(ret_prior)| >= 1.0  (mov de precio Y de
                        posicionamiento, ambos no triviales)
  COOLDOWN       = 4h   tras un evento en un simbolo, se suprimen nuevos
                        eventos de ese simbolo por 4 barras
  QUADRANTS      = A(ret+,dOI+)  B(ret+,dOI-)  C(ret-,dOI+)  D(ret-,dOI-)
  HORIZONS       = 1h, 4h, 12h, 24h forward (log-return desde close[T])
  ENTRY_DELAY    = 0 barras (desde close[T]); se reporta tambien delay=1 como
                  sensibilidad
  PLACEBO_SHIFT  = +48h (fijo)
  MATCHED_CTRL   = por evento, hasta 3 barras del MISMO simbolo sin evento,
                  con realized_vol_24h dentro de +-25% y |ret_prior| dentro
                  de +-25% del evento, y a >=24h de cualquier evento
  COSTS          = fee RT 8 bp  +  slippage/lado {0, 2, 5} bp (RT extra {0,4,10})
  BOOTSTRAP      = 2000 resamples sobre EVENTOS y, aparte, sobre SIMBOLOS
  MULTIPLE_TEST  = 16 tests primarios (4 quadrants x 4 horizons) -> BH q-values

======================= REGLA DE VEREDICTO (pre-declarada) =======================
  CONTINUE : algun cuadrante muestra, en >=2 horizontes, efecto INCREMENTAL
             (evento - matched) con IC bootstrap 90% que excluye 0, MISMO signo
             en las dos mitades del periodo, MISMO signo en >=60% de los
             simbolos con >=5 eventos, y magnitud BRUTA >= 20 bp.
  PARK     : signo consistente pero magnitud < 20 bp o IC marginal.
  FAILED   : ningun cuadrante sobrevive el matched control, o el placebo
             reproduce el efecto, o el signo se da vuelta entre mitades/simbolos.
"""
import os, sys, json, sqlite3, math, statistics, random, collections
from datetime import datetime, timezone

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..", "..")
KLDB = os.path.join(HERE, "..", "data", "klines.db")
BVDB = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
H = 3600_000
BAR = H
LOOKBACK = 4
Z_WIN = 168
Z_THRESH = 1.0
COOLDOWN = 4
HORIZONS = [1, 4, 12, 24]
PLACEBO_SHIFT = 48
FEE_RT_BP = 8.0
SLIP_BP = [0.0, 2.0, 5.0]
random.seed(20260906)


def load_1h(con, sym, a, b):
    rows = con.execute(
        "SELECT open_time,open,high,low,close,volume FROM klines WHERE symbol=? AND interval='1h' "
        "AND is_final=1 AND open_time BETWEEN ? AND ? ORDER BY open_time", (sym, a, b)).fetchall()
    return rows


def load_oi_1h(con, sym, a, b):
    """OI 5m -> 1h: ultimo valor de cada hora (<= cierre de esa hora)."""
    rows = con.execute(
        "SELECT timestamp,open_interest FROM open_interest WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
        (sym, a, b)).fetchall()
    by_h = {}
    for ts, oi in rows:
        hkey = (ts // H) * H
        by_h[hkey] = oi          # el ultimo gana (rows ya ordenadas)
    return by_h


def zscore_causal(series, i, win):
    lo = max(0, i - win)
    hist = [x for x in series[lo:i] if x is not None]
    if len(hist) < 20:
        return None
    m = statistics.mean(hist); s = statistics.pstdev(hist)
    if s == 0:
        return None
    return (series[i] - m) / s


def realized_vol(logrets, i, win=24):
    lo = max(0, i - win)
    seg = [x for x in logrets[lo:i] if x is not None]
    if len(seg) < 6:
        return None
    return statistics.pstdev(seg)


def main():
    kl = sqlite3.connect(f"file:{KLDB}?mode=ro", uri=True)
    bv = sqlite3.connect(f"file:{BVDB}?mode=ro", uri=True)

    syms = [r[0] for r in kl.execute(
        "SELECT symbol FROM open_interest GROUP BY symbol HAVING COUNT(*)*1.0/9601 >= 0.90")]
    win_lo = kl.execute("SELECT MIN(timestamp) FROM open_interest").fetchone()[0]
    win_hi = kl.execute("SELECT MAX(timestamp) FROM open_interest").fetchone()[0]
    mid = (win_lo + win_hi) // 2

    # BTC 1h para regimen
    btc = {r[0]: r[4] for r in load_1h(kl, "BTCUSDT", win_lo - 30 * 24 * H, win_hi + H)}
    btc_times = sorted(btc)

    def btc_regime(t):
        # retorno BTC de las ultimas 24h a la hora t
        t0 = (t // H) * H
        import bisect
        j = bisect.bisect_right(btc_times, t0) - 1
        if j < 24:
            return "na"
        r = math.log(btc[btc_times[j]] / btc[btc_times[j - 24]]) if btc[btc_times[j - 24]] else 0
        if r > 0.02: return "btc_up"
        if r < -0.02: return "btc_down"
        return "btc_flat"

    events = []          # dicts
    per_sym_counts = collections.Counter()
    total_bars = 0

    for sym in syms:
        kr = load_1h(kl, sym, win_lo - Z_WIN * H - 10 * H, win_hi + 30 * H)
        if len(kr) < Z_WIN + LOOKBACK + max(HORIZONS) + 10:
            continue
        oi = load_oi_1h(kl, sym, win_lo - Z_WIN * H - 10 * H, win_hi + H)
        times = [r[0] for r in kr]
        close = [r[1 + 3] for r in kr]
        vol = [r[1 + 4] for r in kr]
        oiv = [oi.get(t) for t in times]
        logret = [None] + [math.log(close[k] / close[k - 1]) if close[k - 1] else None for k in range(1, len(kr))]

        # series de cambios a LOOKBACK
        dOI = [None] * len(kr)
        rprior = [None] * len(kr)
        for k in range(LOOKBACK, len(kr)):
            if oiv[k] is not None and oiv[k - LOOKBACK]:
                dOI[k] = (oiv[k] - oiv[k - LOOKBACK]) / oiv[k - LOOKBACK]
            if close[k - LOOKBACK]:
                rprior[k] = math.log(close[k] / close[k - LOOKBACK])

        last_evt = -10 ** 9
        for k in range(LOOKBACK + Z_WIN, len(kr) - max(HORIZONS)):
            t = times[k]
            if t < win_lo or t > win_hi:
                continue
            total_bars += 1
            if dOI[k] is None or rprior[k] is None:
                continue
            zo = zscore_causal(dOI, k, Z_WIN)
            zp = zscore_causal(rprior, k, Z_WIN)
            if zo is None or zp is None:
                continue
            if abs(zo) < Z_THRESH or abs(zp) < Z_THRESH:
                continue
            if k - last_evt < COOLDOWN:
                continue
            last_evt = k
            q = ("A" if rprior[k] > 0 else "C") if dOI[k] > 0 else ("B" if rprior[k] > 0 else "D")
            rv = realized_vol(logret, k, 24)
            fwd = {}
            for hh in HORIZONS:
                if close[k] and close[k + hh]:
                    fwd[hh] = math.log(close[k + hh] / close[k])
            fwd1 = {}   # entry delay = 1 bar
            for hh in HORIZONS:
                if k + 1 + hh < len(close) and close[k + 1] and close[k + 1 + hh]:
                    fwd1[hh] = math.log(close[k + 1 + hh] / close[k + 1])
            # placebo
            kp = k + PLACEBO_SHIFT
            fwdp = {}
            if kp + max(HORIZONS) < len(close):
                for hh in HORIZONS:
                    if close[kp] and close[kp + hh]:
                        fwdp[hh] = math.log(close[kp + hh] / close[kp])
            vz = zscore_causal(vol, k, Z_WIN)
            events.append(dict(sym=sym, t=t, k=k, half=(0 if t < mid else 1), quad=q,
                               dOI=dOI[k], rprior=rprior[k], zo=zo, zp=zp, rv=rv, volz=vz,
                               btc=btc_regime(t), fwd=fwd, fwd1=fwd1, fwdp=fwdp,
                               close_k=close[k]))
            per_sym_counts[sym] += 1

        # matched controls: guardamos las series para muestrear despues
        events_syms = [e for e in events if e["sym"] == sym]
        if events_syms:
            # candidatos: barras sin evento, a >=24h de cualquier evento
            evk = set()
            for e in events_syms:
                for dd in range(-24, 25):
                    evk.add(e["k"] + dd)
            cand = []
            for k in range(LOOKBACK + Z_WIN, len(kr) - max(HORIZONS)):
                if times[k] < win_lo or times[k] > win_hi or k in evk:
                    continue
                if rprior[k] is None:
                    continue
                rv = realized_vol(logret, k, 24)
                if rv is None:
                    continue
                fwd = {}
                for hh in HORIZONS:
                    if close[k] and close[k + hh]:
                        fwd[hh] = math.log(close[k + hh] / close[k])
                cand.append(dict(k=k, rprior=rprior[k], rv=rv, fwd=fwd))
            for e in events_syms:
                pool = [c for c in cand
                        if e["rv"] and abs(c["rv"] - e["rv"]) <= 0.25 * e["rv"]
                        and abs(c["rprior"] - e["rprior"]) <= 0.25 * abs(e["rprior"]) + 1e-9]
                random.shuffle(pool)
                e["matched"] = pool[:3]

    # ---------- agregacion ----------
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else None

    def boot_ci(xs, n=2000):
        xs = [x for x in xs if x is not None]
        if len(xs) < 8:
            return (None, None, None)
        ms = []
        for _ in range(n):
            s = [xs[random.randrange(len(xs))] for _ in xs]
            ms.append(statistics.mean(s))
        ms.sort()
        return (ms[int(.05 * n)], ms[int(.50 * n)], ms[int(.95 * n)])

    def boot_ci_bysym(pairs, n=2000):
        # pairs = list of (sym, value); resample simbolos
        bys = collections.defaultdict(list)
        for s, v in pairs:
            if v is not None:
                bys[s].append(v)
        keys = list(bys)
        if len(keys) < 4:
            return (None, None, None)
        ms = []
        for _ in range(n):
            acc = []
            for _ in keys:
                acc += bys[keys[random.randrange(len(keys))]]
            ms.append(statistics.mean(acc))
        ms.sort()
        return (ms[int(.05 * n)], ms[int(.50 * n)], ms[int(.95 * n)])

    out = {"params": dict(BAR="1h", LOOKBACK=LOOKBACK, Z_WIN=Z_WIN, Z_THRESH=Z_THRESH,
                          COOLDOWN=COOLDOWN, HORIZONS=HORIZONS, PLACEBO_SHIFT=PLACEBO_SHIFT,
                          FEE_RT_BP=FEE_RT_BP, SLIP_BP=SLIP_BP),
           "window": [win_lo, win_hi], "n_symbols": len(syms), "n_events": len(events),
           "total_bars_scanned": total_bars,
           "events_per_quadrant": dict(collections.Counter(e["quad"] for e in events)),
           "events_per_btc_regime": dict(collections.Counter(e["btc"] for e in events)),
           "events_per_symbol_top": per_sym_counts.most_common(12),
           "quadrants": {}}

    print("=" * 78)
    print(f"H13 PILOT — {len(events)} eventos / {len(syms)} simbolos / "
          f"{(win_hi-win_lo)/86400000:.1f} dias  [PILOTO, NO CONCLUYENTE]")
    print("=" * 78)
    print("eventos/cuadrante:", out["events_per_quadrant"])
    print("eventos/regimen BTC:", out["events_per_btc_regime"])
    print()

    pvals = []
    for q in ["A", "B", "C", "D"]:
        ev = [e for e in events if e["quad"] == q]
        qd = {"n": len(ev), "horizons": {}}
        print(f"--- Quadrant {q}  (n={len(ev)})  "
              f"{'ret+ OI+' if q=='A' else 'ret+ OI-' if q=='B' else 'ret- OI+' if q=='C' else 'ret- OI-'}")
        for hh in HORIZONS:
            raw = [e["fwd"].get(hh) for e in ev]
            raw1 = [e["fwd1"].get(hh) for e in ev]
            plac = [e["fwdp"].get(hh) for e in ev]
            # matched: por evento, media de sus matched - propio fwd
            incr = []
            for e in ev:
                m = mean([c["fwd"].get(hh) for c in e.get("matched", [])])
                if e["fwd"].get(hh) is not None and m is not None:
                    incr.append(e["fwd"][hh] - m)
            mr = mean(raw); mr_bp = mr * 1e4 if mr is not None else None
            ci = boot_ci([x for x in raw])
            ci_bp = tuple(round(c * 1e4, 1) if c is not None else None for c in ci)
            ci_sym = boot_ci_bysym([(e["sym"], e["fwd"].get(hh)) for e in ev])
            ci_sym_bp = tuple(round(c * 1e4, 1) if c is not None else None for c in ci_sym)
            mi = mean(incr); mi_bp = mi * 1e4 if mi is not None else None
            ci_i = boot_ci(incr); ci_i_bp = tuple(round(c * 1e4, 1) if c is not None else None for c in ci_i)
            mp = mean(plac); mp_bp = mp * 1e4 if mp is not None else None
            # estabilidad por mitad y por simbolo
            h0 = mean([e["fwd"].get(hh) for e in ev if e["half"] == 0])
            h1 = mean([e["fwd"].get(hh) for e in ev if e["half"] == 1])
            bysym = collections.defaultdict(list)
            for e in ev:
                v = e["fwd"].get(hh)
                if v is not None:
                    bysym[e["sym"]].append(v)
            symmeans = {s: statistics.mean(v) for s, v in bysym.items() if len(v) >= 5}
            frac_same = (sum(1 for v in symmeans.values() if (v > 0) == (mr > 0)) / len(symmeans)) if symmeans and mr is not None else None
            # costo
            after = {}
            for sl in SLIP_BP:
                cost_bp = FEE_RT_BP + 2 * sl
                after[sl] = round((abs(mr_bp) - cost_bp), 1) if mr_bp is not None else None
            qd["horizons"][hh] = dict(
                raw_bp=round(mr_bp, 1) if mr_bp is not None else None,
                raw_ci_bp=ci_bp, raw_ci_bysym_bp=ci_sym_bp,
                raw_delay1_bp=round(mean([x for x in raw1]) * 1e4, 1) if mean([x for x in raw1]) is not None else None,
                incr_bp=round(mi_bp, 1) if mi_bp is not None else None, incr_ci_bp=ci_i_bp,
                placebo_bp=round(mp_bp, 1) if mp_bp is not None else None,
                half0_bp=round(h0 * 1e4, 1) if h0 is not None else None,
                half1_bp=round(h1 * 1e4, 1) if h1 is not None else None,
                n_symbols_ge5=len(symmeans), frac_symbols_same_sign=round(frac_same, 2) if frac_same is not None else None,
                after_costs_bp=after)
            print(f"  h={hh:>2}h  raw={qd['horizons'][hh]['raw_bp']:>7} bp  CI90=[{ci_bp[0]},{ci_bp[2]}]  "
                  f"incr(vs matched)={qd['horizons'][hh]['incr_bp']} bp CI=[{ci_i_bp[0]},{ci_i_bp[2]}]  "
                  f"placebo={qd['horizons'][hh]['placebo_bp']} bp  half0/1={qd['horizons'][hh]['half0_bp']}/{qd['horizons'][hh]['half1_bp']}  "
                  f"sym_same={qd['horizons'][hh]['frac_symbols_same_sign']} (n={len(symmeans)})  "
                  f"after5bp={after[5.0]}")
        out["quadrants"][q] = qd
        print()

    json.dump(out, open(os.path.join(ROOT, "scratch_h13_pilot.json"), "w"), indent=1, default=str)
    print("guardado scratch_h13_pilot.json")


if __name__ == "__main__":
    main()
