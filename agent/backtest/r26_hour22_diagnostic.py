"""
ROUND 26, PIVOTE — liquidation cascade quedo bloqueada por cobertura de
datos (ver informe). Diagnostico causal de la hora 22:00 UTC (R19/R20: el
efecto horario mas fuerte del proyecto, -12.3bp @22:00xcompresion, nunca
explicado). Objetivo: caracterizar ESTRUCTURALMENTE que distingue a esa
hora de sus vecinas -- volumen, rango realizado, dispersion cross-sectional,
frecuencia de eventos extremos -- usando SOLO TRAIN (diagnostico
descriptivo, no una prueba de estrategia).
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")


def main():
    print("=== ROUND 26 PIVOTE — DIAGNOSTICO ESTRUCTURAL DE LA HORA 22:00 UTC ===\n")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d
    con.close()
    print(f"universo: {len(P)} simbolos")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut = days_all[int(len(days_all) * 0.5)]
    print(f"TRAIN <= {tcut} (solo TRAIN, diagnostico, sin mirar VAL/OOS)\n")

    by_hour = {h: dict(vol=[], rng=[], absret=[], extreme=0, n=0) for h in range(24)}
    hourly_rets = collections.defaultdict(list)   # hora -> lista de listas de retornos por timestamp (para dispersion cross-sectional)
    ts_group = collections.defaultdict(list)      # (hour) -> dict timestamp-> [rets]

    for s, d in P.items():
        c = d["c"]; h_ = d["h"]; l = d["l"]; o = d["o"]; v = d["v"]; t = d["t"]; n = len(c)
        r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
        rng_bar = (h_ - l) / np.where(c > 0, c, np.nan)
        qv = o * v
        for i in range(1, n):
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            if dy > tcut:
                continue
            hr = datetime.utcfromtimestamp(int(t[i]) / 1000).hour
            rec = by_hour[hr]
            if np.isfinite(qv[i]):
                rec["vol"].append(qv[i])
            if np.isfinite(rng_bar[i]):
                rec["rng"].append(rng_bar[i])
            if np.isfinite(r1[i]):
                rec["absret"].append(abs(r1[i]))
                rec["n"] += 1
                if abs(r1[i]) > 0.01:   # movimiento >1% en 15m, umbral fijo (no fiteado)
                    rec["extreme"] += 1
                ts_group[(hr, int(t[i]))].append(r1[i])

    print("#" * 80)
    print(f"{'hora':>4s} {'n':>8s} {'vol_med($)':>14s} {'rango_med(%)':>13s} {'|ret1|_med(%)':>14s} {'%extremos(>1%)':>15s} {'disp_XS_med(%)':>15s}")
    print("#" * 80)
    disp_by_hour = {}
    for hr in range(24):
        key_ts = [k for k in ts_group if k[0] == hr]
        disp_vals = []
        for k in key_ts:
            rets = [r for r in ts_group[k] if np.isfinite(r)]
            if len(rets) >= 30:
                disp_vals.append(np.std(rets))
        disp_by_hour[hr] = np.median(disp_vals) if disp_vals else np.nan
        rec = by_hour[hr]
        vol_med = np.median(rec["vol"]) if rec["vol"] else np.nan
        rng_med = np.median(rec["rng"]) * 100 if rec["rng"] else np.nan
        absret_med = np.median(rec["absret"]) * 100 if rec["absret"] else np.nan
        pct_extreme = rec["extreme"] / rec["n"] * 100 if rec["n"] else np.nan
        marker = "  <== 22:00" if hr == 22 else ("  (21/23 vecinas)" if hr in (21, 23) else "")
        print(f"{hr:4d} {rec['n']:8d} {vol_med:14,.0f} {rng_med:13.4f} {absret_med:14.4f} {pct_extreme:14.2f}% "
              f"{disp_by_hour[hr]*100:14.4f}%{marker}")

    print("\n" + "#" * 80)
    print(" COMPARACION 22:00 vs promedio de sus 2 horas vecinas (21:00 y 23:00) vs promedio del dia")
    print("#" * 80)
    all_vol = np.median([v for hr in range(24) for v in by_hour[hr]["vol"]])
    all_rng = np.median([v for hr in range(24) for v in by_hour[hr]["rng"]]) * 100
    all_disp = np.nanmedian(list(disp_by_hour.values())) * 100
    v22 = np.median(by_hour[22]["vol"]); vneigh = np.median(by_hour[21]["vol"] + by_hour[23]["vol"])
    r22 = np.median(by_hour[22]["rng"]) * 100; rneigh = np.median(by_hour[21]["rng"] + by_hour[23]["rng"]) * 100
    d22 = disp_by_hour[22] * 100; dneigh = np.nanmean([disp_by_hour[21], disp_by_hour[23]]) * 100
    print(f"  Volumen mediano:      22:00=${v22:,.0f}   vecinas(21/23)=${vneigh:,.0f}   promedio_dia=${all_vol:,.0f}   "
          f"ratio 22:00/dia = {v22/all_vol:.2f}x")
    print(f"  Rango intrabar (%):   22:00={r22:.4f}%   vecinas={rneigh:.4f}%   promedio_dia={all_rng:.4f}%   "
          f"ratio = {r22/all_rng:.2f}x")
    print(f"  Dispersion cross-sec: 22:00={d22:.4f}%   vecinas={dneigh:.4f}%   promedio_dia={all_disp:.4f}%   "
          f"ratio = {d22/all_disp:.2f}x")

    print("\nfin diagnostico horario -- ver informe para interpretacion causal")


if __name__ == "__main__":
    main()
