"""
H12 — TAKER ORDER FLOW / CVD · FASE 1 (existencia de alpha source).
Protocolo CONGELADO: agent/H12_TAKER_FLOW_TEST.md. NO modificar params. Sin grid-search.
No es una estrategia. Un solo veredicto: PASS / FAILED / UNTESTABLE.

Corrida:
  python h12_taker_flow.py --universe   # imprime el universo final del audit (no corre el test)
  python h12_taker_flow.py              # corre el test congelado -> h12_results.json
"""
import os, sys, json, math, sqlite3, datetime as dt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
FUND_DB = os.path.join(HERE, "..", "data", "klines.db")
OUT = os.path.join(HERE, "h12_results.json")

# ================= PARÁMETROS CONGELADOS (H12_TAKER_FLOW_TEST.md) =================
BAR_MS            = 900_000
WINDOWS_BARS      = [4, 16, 48, 96]        # 1h / 4h / 12h / 24h
FWD_HORIZONS_BARS = [4, 16, 48]            # 1h / 4h / 12h
Z_LOOKBACK_BARS   = 96
Z_BUCKETS         = [(0, 1), (1, 2), (2, 3), (3, 99)]
EXTREME_Z         = [2, 3]
RANGE_LOOKBACK    = 16
LIQ_FLOOR_USD_15M = 1_000_000
COV_MIN           = 0.95
FEE_PER_SIDE      = 0.0004
SLIP_LEVELS       = [0.0, 0.0002, 0.0005]
PLACEBO_SHIFT_BARS = 25
DISCOVERY  = ("2025-12-01", "2026-03-31")
VALIDATION = ("2026-04-01", "2026-05-31")
FINAL_OOS  = ("2026-06-01", "2026-08-17")
SPLITS = {"discovery": DISCOVERY, "validation": VALIDATION, "final_oos": FINAL_OOS}
FAMILIES = ["A_TI", "B_CVD", "C_accel", "D_divergence", "E_extreme"]
PARTIAL_CORR_FLOOR = 0.03
ECON_GATE_BP = 15.0
# ================================================================================


def _ms(s): return int(dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def final_universe(conn):
    """Universo BASE del test: sólo cobertura de historia (>=COV_MIN de la ventana
    completa dic-2025->17-ago-2026). La liquidez NO se filtra acá -- el protocolo
    congelado (§6, 'trailing-7d') es un piso ROLLING aplicado POR BARRA dentro del
    test (ver `F["elig"]` en run()), igual que H9/H10/H11. Filtrar el universo por
    mediana lifetime aquí sería una interpretación distinta del §6 y colapsaba el
    universo a 12 símbolos (confirmado con el usuario 2026-09-04 -- NO usar)."""
    t0, t1 = _ms("2025-12-01"), _ms("2026-08-17")
    exp = (t1 - t0) // BAR_MS
    tk = {r[0]: r[1] for r in conn.execute(
        "SELECT symbol,COUNT(*) FROM taker_flow WHERE interval='15m' AND open_time>=? AND open_time<? GROUP BY symbol", (t0, t1))}
    return sorted(s for s, n in tk.items() if n / exp >= COV_MIN)


def load(conn, syms):
    ph = ",".join("?" * len(syms))
    tf = pd.read_sql_query(
        f"SELECT symbol,open_time,volume,quote_volume,taker_buy_volume FROM taker_flow WHERE interval='15m' AND symbol IN ({ph})",
        conn, params=syms)
    kc = pd.read_sql_query(
        f"SELECT symbol,open_time,close FROM klines_clean WHERE interval='15m' AND symbol IN ({ph})",
        conn, params=syms)
    m = kc.merge(tf, on=["symbol", "open_time"], how="inner").sort_values(["symbol", "open_time"])
    fc = sqlite3.connect(FUND_DB)
    fund = pd.read_sql_query("SELECT symbol,funding_time,funding_rate FROM funding_rates WHERE funding_time>1700000000000", fc)
    fc.close()
    return m, fund.sort_values(["symbol", "funding_time"])


def czs(s, lb):
    return (s - s.rolling(lb, min_periods=lb).mean()) / s.rolling(lb, min_periods=lb).std()


def bucketize(a):
    out = np.full(len(a), -1, int)
    for i, (lo, hi) in enumerate(Z_BUCKETS):
        out[(a >= lo) & (a < hi)] = i
    return out


def pcorr(y, x, ctrls):
    X = np.column_stack([np.ones_like(x)] + ctrls)
    bx = np.linalg.lstsq(X, x, rcond=None)[0]
    by = np.linalg.lstsq(X, y, rcond=None)[0]
    rx, ry = x - X @ bx, y - X @ by
    return float("nan") if np.std(rx) == 0 or np.std(ry) == 0 else float(np.corrcoef(rx, ry)[0, 1])


def summarize(vals, sym_ids):
    vals = np.asarray(vals, float); m = np.isfinite(vals)
    vals, sym_ids = vals[m], np.asarray(sym_ids)[m]
    if len(vals) < 100:
        return None
    per = {}
    for s in np.unique(sym_ids):
        per[s] = float(np.sum(vals[sym_ids == s]))
    tot = sum(per.values())
    top5 = sorted(per.values(), key=lambda z: -abs(z))[:5]
    psm = np.array([np.median(vals[sym_ids == s]) for s in np.unique(sym_ids)])
    return dict(n=int(len(vals)), mean_bp=round(float(np.mean(vals)) * 1e4, 3),
                median_bp=round(float(np.median(vals)) * 1e4, 3),
                hit=round(float(np.mean(vals > 0)), 3), n_symbols=int(len(per)),
                n_sym_pos_median=int(np.sum(psm > 0)),
                top5_share_of_sum=(round(float(sum(top5) / tot), 3) if tot else None))


def funding_aligned(M, fund):
    out = np.full(len(M), np.nan)
    fb = {s: d for s, d in fund.groupby("symbol")}
    for sym, idx in M.groupby("symbol").groups.items():
        d = fb.get(sym)
        if d is None:
            continue
        ft, fr = d["funding_time"].values, d["funding_rate"].values
        pos = np.searchsorted(ft, M.loc[idx, "open_time"].values, side="right") - 1
        out[M.index.get_indexer(idx)] = np.where(pos >= 0, fr[np.clip(pos, 0, len(fr) - 1)], np.nan)
    return out


def build(M, placebo=False):
    parts = []
    for sym, d in M.groupby("symbol", sort=False):
        d = d.copy()
        tbv = d["taker_buy_volume"].shift(PLACEBO_SHIFT_BARS) if placebo else d["taker_buy_volume"]
        vol = d["volume"].shift(PLACEBO_SHIFT_BARS) if placebo else d["volume"]
        d["delta"] = 2 * tbv - vol                       # taker_buy - taker_sell
        d["_vol"] = vol
        d["TI"] = d["delta"] / vol                        # H12-A por barra
        d["r"] = np.log(d["close"]).diff()
        d["z_mom"] = czs(d["r"], Z_LOOKBACK_BARS)
        d["rng"] = (d["close"].rolling(RANGE_LOOKBACK).max() - d["close"].rolling(RANGE_LOOKBACK).min()) / d["close"]
        for w in WINDOWS_BARS:
            cvd = d["delta"].rolling(w).sum()
            volw = vol.rolling(w).sum()
            d[f"TIagg_{w}"] = cvd / volw                  # H12-B (CVD normalizado)
            d[f"retw_{w}"] = np.log(d["close"]) - np.log(d["close"].shift(w))
        for w in WINDOWS_BARS:
            d[f"accel_{w}"] = d[f"TIagg_{w}"] - d[f"TIagg_{w}"].shift(w)   # H12-C
        for h in FWD_HORIZONS_BARS:
            d[f"fwd_{h}"] = np.log(d["close"]).shift(-h) - np.log(d["close"])
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def run(M, fund, placebo=False):
    F = build(M, placebo=placebo)
    F["funding"] = funding_aligned(F, fund)
    F["liq"] = (F["close"] * F["_vol"]).rolling(672, min_periods=672).median()
    F["elig"] = (F["liq"] >= LIQ_FLOOR_USD_15M)
    sc = {s: i for i, s in enumerate(sorted(F["symbol"].unique()))}
    F["sc"] = F["symbol"].map(sc)
    ot = F["open_time"].values
    ctrl = ["r", "rng", "funding"]
    res = {}
    for sp, (a, b) in SPLITS.items():
        base = (ot >= _ms(a)) & (ot <= _ms(b)) & F["elig"].values
        for h in FWD_HORIZONS_BARS:
            fwd = F[f"fwd_{h}"].values
            # ---- H12-A: TI por barra ----
            _sig_bucketed(res, F, base, fwd, "A_TI", None, F["TI"].values, sp, h, ctrl)
            for w in WINDOWS_BARS:
                _sig_bucketed(res, F, base, fwd, "B_CVD", w, F[f"TIagg_{w}"].values, sp, h, ctrl)
                _sig_bucketed(res, F, base, fwd, "C_accel", w, F[f"accel_{w}"].values, sp, h, ctrl)
                # ---- H12-D: divergencia precio/flujo ----
                retw = F[f"retw_{w}"].values; tiw = F[f"TIagg_{w}"].values
                diverge = (np.sign(retw) != np.sign(tiw)) & np.isfinite(retw) & np.isfinite(tiw)
                out = np.sign(tiw) * fwd     # "seguir el flujo cuando el precio discrepa"
                mm = base & diverge & np.isfinite(out)
                s = summarize(out[mm], F["sc"].values[mm])
                if s:
                    res[f"{sp}|h{h}|D_divergence|w{w}|directional"] = s
                # ---- H12-E: extreme flow ----
                z_tiw = czs(pd.Series(tiw), Z_LOOKBACK_BARS).values
                for zt in EXTREME_Z:
                    ext = np.abs(z_tiw) >= zt
                    oute = np.sign(tiw) * fwd
                    mm = base & ext & np.isfinite(oute)
                    s = summarize(oute[mm], F["sc"].values[mm])
                    if s:
                        res[f"{sp}|h{h}|E_extreme|w{w}|z{zt}"] = s
    return res


def _sig_bucketed(res, F, base, fwd, fam, w, x, sp, h, ctrl):
    """señal de magnitud: bucket por |z(x)|, media de fwd por bucket + directional sign(x)*fwd + INCREMENTAL."""
    tag = f"{fam}|w{w}" if w else fam
    z = czs(pd.Series(x), Z_LOOKBACK_BARS).values
    bk = bucketize(np.abs(z))
    for bi in range(len(Z_BUCKETS)):
        mm = base & (bk == bi) & np.isfinite(fwd)
        s = summarize(fwd[mm], F["sc"].values[mm])
        if s:
            res[f"{sp}|h{h}|{tag}|bucket{bi}"] = s
    out = np.sign(x) * fwd
    mm = base & np.isfinite(out)
    s = summarize(out[mm], F["sc"].values[mm])
    if s:
        res[f"{sp}|h{h}|{tag}|directional"] = s
    # INCREMENTAL: partial corr de x con fwd, control [r, rng, funding]
    mm = base & np.isfinite(fwd) & np.isfinite(x)
    for c in ctrl:
        mm = mm & np.isfinite(F[c].values)
    if mm.sum() > 500:
        y = fwd[mm]; xx = x[mm]
        res[f"{sp}|h{h}|{tag}|INCREMENTAL"] = dict(
            n=int(mm.sum()),
            raw=round(float(np.corrcoef(xx, y)[0, 1]), 4),
            partial_given_mom_rng_funding=round(pcorr(y, xx, [F[c].values[mm] for c in ctrl]), 4))


def main():
    conn = sqlite3.connect(DB)
    uni = final_universe(conn)
    if "--universe" in sys.argv:
        print(json.dumps({"n": len(uni), "symbols": uni}, indent=1)); return
    if len(uni) < 20:
        json.dump({"verdict": "UNTESTABLE", "reason": f"universo final = {len(uni)} símbolos (<20)"}, open(OUT, "w"), indent=1)
        print("UNTESTABLE — universo <20"); return
    print(f"universo final: {len(uni)} símbolos", flush=True)
    M, fund = load(conn, uni)
    conn.close()
    print(f"frame: {len(M):,} filas", flush=True)
    report = {"frozen_params": {k: v for k, v in globals().items() if k.isupper()},
              "universe_n": len(uni), "universe": uni,
              "real": run(M, fund, placebo=False),
              "placebo": run(M, fund, placebo=True)}
    json.dump(report, open(OUT, "w"), indent=1, default=str)
    print("DONE -> h12_results.json", flush=True)


if __name__ == "__main__":
    main()
