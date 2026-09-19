"""
H18 SCREEN — ¿un shock de BTC genera catch-up predecible en los alts rezagados?
Event study barato sobre OHLCV limpio (binance_vision_clean.db / klines_5m -> 1h),
2025-12-01 .. 2026-08-17, universo = símbolos líquidos.

PRE-DECLARADO (sin grid):
  bar = 1h (resample de 5m).
  shock BTC = |ret_BTC_1h| >= p95 de su distribución rolling 30d (720 barras), causal.
  ventana del shock = esa 1 barra.
  beta_alt = pendiente OLS de ret_alt_1h ~ ret_BTC_1h sobre las 168 barras previas (7d).
  residual = ret_alt(shock) - beta_alt * ret_BTC(shock).
  LAGGARD = residual con signo OPUESTO al shock y |residual| >= 0.5 * |beta*ret_BTC|
            (el alt "no siguió" a BTC en esa barra).
  FOLLOWER (control) = |residual| <= 0.25 * |beta*ret_BTC| (siguió).
  horizontes forward: 1h, 2h, 4h  (log-ret desde el close de la barra de shock).
  señal direccional = sign(ret_BTC(shock))  -> se predice catch-up EN ESA dirección.
  placebo: shock + 48h (misma etiqueta), recomputar forward.
  cooldown: 6h por (símbolo) tras un evento.
  costo RT asumido: 8 bp fee + slippage {0,2,5} bp/lado.

H0: retorno forward de los LAGGARD (en la dirección del shock) = el de los FOLLOWER
    y el placebo lo reproduce.
Veredicto: PROMISING / PARK / FAILED (regla al pie).
"""
import os, sys, json, sqlite3, math, statistics, random, collections, bisect
from datetime import datetime, timezone

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
H = 3600_000
Z_WIN = 720            # 30d de barras 1h para el percentil de shock
BETA_WIN = 168         # 7d
P_SHOCK = 0.95
HORIZONS = [1, 2, 4]
PLACEBO = 48
COOLDOWN = 6
FEE_RT_BP = 8.0
SLIP = [0.0, 2.0, 5.0]
MIN_DOLLAR_VOL_5M = 50_000     # liquidez mínima (mediana 5m en la ventana)
random.seed(20260909)


def load_1h(con, sym, a, b):
    rows = con.execute(
        "SELECT open_time,close,volume FROM klines_5m WHERE symbol=? AND interval='5m' "
        "AND open_time BETWEEN ? AND ? ORDER BY open_time", (sym, a, b)).fetchall()
    # resample 5m -> 1h: último close de la hora, suma de dollar-vol
    by = {}
    for ot, c, v in rows:
        hk = (ot // H) * H
        d = by.setdefault(hk, [None, 0.0])
        d[0] = c
        d[1] += c * v
    ks = sorted(by)
    return ks, [by[k][0] for k in ks], [by[k][1] for k in ks]


def ols_beta(x, y):
    n = len(x)
    if n < 20:
        return None
    mx = sum(x) / n; my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return None
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    return sxy / sxx


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    tmin = con.execute("SELECT MIN(open_time) FROM klines_5m").fetchone()[0]
    tmax = con.execute("SELECT MAX(open_time) FROM klines_5m").fetchone()[0]

    bt, bc, bv = load_1h(con, "BTCUSDT", tmin, tmax)
    blr = [None] + [math.log(bc[i] / bc[i - 1]) if bc[i - 1] else None for i in range(1, len(bc))]
    # shocks de BTC: |ret| >= p95 rolling 30d causal
    shocks = []
    for i in range(Z_WIN, len(bt) - max(HORIZONS) - PLACEBO):
        hist = [abs(x) for x in blr[i - Z_WIN:i] if x is not None]
        if len(hist) < 200 or blr[i] is None:
            continue
        thr = sorted(hist)[int(P_SHOCK * len(hist))]
        if abs(blr[i]) >= thr and abs(blr[i]) > 0.003:
            shocks.append((i, bt[i], blr[i]))
    shock_t = {t for _, t, _ in shocks}
    print(f"BTC shocks (|ret_1h|>=p95/30d): {len(shocks)}  sobre {len(bt)} barras 1h")

    syms = [r[0] for r in con.execute(
        "SELECT symbol FROM klines_5m WHERE interval='5m' GROUP BY symbol HAVING COUNT(*) > 40000")]
    syms = [s for s in syms if s != "BTCUSDT"]
    print(f"universo alts con historia: {len(syms)}")

    lag_fwd = {h: [] for h in HORIZONS}      # (sym, dir-adjusted forward return)
    fol_fwd = {h: [] for h in HORIZONS}
    lag_plac = {h: [] for h in HORIZONS}
    n_lag = n_fol = 0

    for si, sym in enumerate(syms):
        kt, kc, kdv = load_1h(con, sym, tmin, tmax)
        if len(kt) < Z_WIN + max(HORIZONS) + 10:
            continue
        # index por tiempo para alinear con BTC
        tset = {t: j for j, t in enumerate(kt)}
        lr = [None] + [math.log(kc[i] / kc[i - 1]) if kc[i - 1] else None for i in range(1, len(kc))]
        last_ev = -999
        for (bi, bts, bret) in shocks:
            j = tset.get(bts)
            if j is None or j < BETA_WIN or j + max(HORIZONS) >= len(kt):
                continue
            if j - last_ev < COOLDOWN:
                continue
            # liquidez
            seg_dv = [d for d in kdv[j - 24:j] if d]
            if not seg_dv or statistics.median(seg_dv) < MIN_DOLLAR_VOL_5M:
                continue
            # beta sobre 7d previos alineados a BTC
            xs, ys = [], []
            for k in range(j - BETA_WIN, j):
                bt_j = tset.get  # noqa
                bk = bisect.bisect_left(bt, kt[k])
                if bk < len(bt) and bt[bk] == kt[k] and blr[bk] is not None and lr[k] is not None:
                    xs.append(blr[bk]); ys.append(lr[k])
            beta = ols_beta(xs, ys)
            if beta is None or lr[j] is None:
                continue
            expected = beta * bret
            resid = lr[j] - expected
            if abs(expected) < 1e-6:
                continue
            direction = 1 if bret > 0 else -1
            # LAGGARD: no siguió (residual opuesto al shock, magnitud relevante)
            is_lag = (resid * direction < 0) and (abs(resid) >= 0.5 * abs(expected))
            is_fol = abs(resid) <= 0.25 * abs(expected)
            if not (is_lag or is_fol):
                continue
            last_ev = j
            def fwd(base_j, h):
                if base_j + h < len(kc) and kc[base_j] and kc[base_j + h]:
                    return direction * math.log(kc[base_j + h] / kc[base_j])
                return None
            if is_lag:
                n_lag += 1
                for h in HORIZONS:
                    v = fwd(j, h)
                    if v is not None: lag_fwd[h].append((sym, v))
                    pj = tset.get(bt[bi + PLACEBO]) if bi + PLACEBO < len(bt) else None
                    if pj is not None:
                        pv = fwd(pj, h)
                        if pv is not None: lag_plac[h].append((sym, pv))
            else:
                n_fol += 1
                for h in HORIZONS:
                    v = fwd(j, h)
                    if v is not None: fol_fwd[h].append((sym, v))

    def stats(pairs):
        vals = [v for _, v in pairs]
        if len(vals) < 20:
            return None
        m = statistics.mean(vals)
        # bootstrap sobre símbolos
        bys = collections.defaultdict(list)
        for s, v in pairs: bys[s].append(v)
        keys = list(bys)
        ms = []
        for _ in range(2000):
            acc = []
            for _ in keys: acc += bys[keys[random.randrange(len(keys))]]
            ms.append(statistics.mean(acc))
        ms.sort()
        return dict(n=len(vals), n_sym=len(keys), mean_bp=round(m * 1e4, 1),
                    ci_bp=[round(ms[100] * 1e4, 1), round(ms[1900] * 1e4, 1)])

    out = {"n_btc_shocks": len(shocks), "n_laggard_events": n_lag, "n_follower_events": n_fol,
           "horizons": {}}
    print(f"\nLAGGARD events: {n_lag} | FOLLOWER events: {n_fol}")
    print(f"{'h':>3} | {'laggard raw':>22} | {'follower':>16} | {'incr(lag-fol)':>14} | {'placebo':>16}")
    promising = False
    for h in HORIZONS:
        L = stats(lag_fwd[h]); F = stats(fol_fwd[h]); P = stats(lag_plac[h])
        incr = None
        if L and F:
            incr = round(L["mean_bp"] - F["mean_bp"], 1)
        out["horizons"][h] = {"laggard": L, "follower": F, "placebo": P, "incr_bp": incr}
        ls = f"{L['mean_bp']} {L['ci_bp']}" if L else "n/a"
        fs = f"{F['mean_bp']}" if F else "n/a"
        ps = f"{P['mean_bp']}" if P else "n/a"
        print(f"{h:>3} | {ls:>22} | {fs:>16} | {str(incr):>14} | {ps:>16}")
        # criterio: laggard CI excluye 0, incr>0, placebo << laggard, y raw >= 2x costo (16bp)
        if L and F and P and L["ci_bp"][0] > 0 and (incr or 0) > 0 and abs(P["mean_bp"]) < 0.4 * abs(L["mean_bp"]) and L["mean_bp"] >= 16:
            promising = True

    verdict = "PROMISING" if promising else ("PARK" if n_lag < 200 else "FAILED")
    out["verdict"] = verdict
    print(f"\nVEREDICTO H18 (screen): {verdict}")
    print("  regla: PROMISING si algún h tiene laggard CI>0, incr>0, placebo<40% del efecto, raw>=16bp.")
    json.dump(out, open(os.path.join(ROOT, "scratch_h18_screen.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
