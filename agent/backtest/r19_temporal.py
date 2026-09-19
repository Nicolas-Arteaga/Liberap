"""
ROUND 19 — TEMPORAL MICROSTRUCTURE + EXECUTION ALPHA HUNT.

Universo ancho (357 símbolos, OHLCV+taker, igual R15/R18). Todo con placebo
desde el inicio (la lección de R18): shuffle de etiqueta hora/ventana,
desplazamiento de hora, día anterior/siguiente.

TRACK A — Hora del día: no solo retorno medio; también volatilidad realizada,
  probabilidad de breakout, probabilidad de expansión de volumen, por hora UTC.
TRACK B — Funding settlement (00/08/16 UTC, reloj universal, no depende del
  universo con funding_hist): volatilidad y reacción en 5 ventanas alrededor
  del settlement, vs control fuera de settlement.
TRACK D — Hora x evento: la hora con mejor lectura en A, condicionada a
  compresión/expansión de volumen (interacción, no aislado).
TRACK C (ligero) — reacción de "sobre-reactores" tras shock de mercado ancho
  (reversión de la sobre-reacción, distinto de leader-laggard catch-up ya
  fallado).
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, RT_BP
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
rng = np.random.default_rng(20260923)


def main():
    print("=== ROUND 19 — TEMPORAL MICROSTRUCTURE + EXECUTION ALPHA HUNT ===")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    print(f"universo ancho: {len(P)} símbolos")

    days_all = []
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    for t in P[ref]["t"]:
        days_all.append(datetime.utcfromtimestamp(int(t) / 1000).date())
    days_all = sorted(set(days_all))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")

    # ================= TRACK A — HORA DEL DÍA =================
    print("\n" + "#" * 70 + "\n# TRACK A — HORA DEL DÍA: retorno, volatilidad, prob. breakout, prob. vol. expansión\n" + "#" * 70)
    byhour = {hh: {"ret1h": [], "ret4h": [], "rv": [], "breakout": [], "volexp": [], "n": 0} for hh in range(24)}
    seg_byhour = {hh: {sgv: [] for sgv in ("train", "val", "oos")} for hh in range(24)}
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        for i in range(0, n - 16, 1):
            hh = datetime.utcfromtimestamp(int(t[i]) / 1000).hour
            if i + 4 >= n or i + 16 >= n:
                continue
            r1h = math.log(c[i + 4] / c[i]); r4h = math.log(c[i + 16] / c[i])
            byhour[hh]["ret1h"].append((s, r1h)); byhour[hh]["ret4h"].append((s, r4h))
            if np.isfinite(f["rv"][i]):
                byhour[hh]["rv"].append(f["rv"][i])
            if np.isfinite(f["ret1_pct"][i]):
                byhour[hh]["breakout"].append(1 if (f["ret1_pct"][i] >= 0.9 or f["ret1_pct"][i] <= 0.1) else 0)
            if np.isfinite(f["vol_pct"][i]):
                byhour[hh]["volexp"].append(1 if f["vol_pct"][i] >= 0.9 else 0)
            byhour[hh]["n"] += 1
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            seg_byhour[hh][seg(dy)].append((s, r1h))

    print(f"\n{'hora':>5s} {'ret1h_bp':>9s} {'CI':>16s} {'rv_med':>8s} {'P(breakout)':>11s} {'P(vol_exp)':>10s} {'n':>8s}")
    hour_stats = {}
    for hh in range(24):
        R = agg_pairs(byhour[hh]["ret1h"])
        rv_med = float(np.median(byhour[hh]["rv"])) if byhour[hh]["rv"] else float("nan")
        pbrk = float(np.mean(byhour[hh]["breakout"])) if byhour[hh]["breakout"] else float("nan")
        pvol = float(np.mean(byhour[hh]["volexp"])) if byhour[hh]["volexp"] else float("nan")
        star = "*" if R.get("ci_excl_0") else " "
        print(f"{hh:5d} {R.get('mean_bp'):>8.2f}{star} [{R['ci_bp'][0]:>6.1f},{R['ci_bp'][1]:>6.1f}] {rv_med*1e4:>8.1f} {pbrk:>11.3f} {pvol:>10.3f} {R.get('n'):>8d}")
        hour_stats[hh] = dict(ret1h_bp=R.get("mean_bp"), ci=R.get("ci_bp"), excl0=R.get("ci_excl_0"),
                              rv_med=rv_med, p_breakout=pbrk, p_volexp=pvol, n=R.get("n"))

    real_spread = max(abs(hour_stats[hh]["ret1h_bp"]) for hh in range(24) if hour_stats[hh]["ret1h_bp"] is not None)
    best_hour = max(hour_stats, key=lambda hh: abs(hour_stats[hh]["ret1h_bp"]) if hour_stats[hh]["ret1h_bp"] else 0)
    print(f"\n  hora con mayor |efecto|: {best_hour}:00 UTC -> {hour_stats[best_hour]['ret1h_bp']:+.2f}bp")

    print("\n  PLACEBO — shuffle de etiqueta-hora (3 iteraciones), máximo |efecto| entre 24 buckets falsos:")
    all_pairs = [(s, r1h) for hh in range(24) for (s, r1h) in byhour[hh]["ret1h"]]
    for it in range(3):
        idx = rng.permutation(len(all_pairs))
        fake_hours = np.array([rng.integers(0, 24) for _ in range(len(all_pairs))])
        buckets = {hh: [] for hh in range(24)}
        for k, hh_f in enumerate(fake_hours):
            buckets[hh_f].append(all_pairs[k])
        maxeff = 0.0
        for hh in range(24):
            R = agg_pairs(buckets[hh])
            if R.get("mean_bp") is not None:
                maxeff = max(maxeff, abs(R["mean_bp"]))
        print(f"    iter {it}: max|efecto| placebo = {maxeff:.2f}bp   (real max = {real_spread:.2f}bp)")

    print(f"\n  TRAIN/VAL/OOS para la hora con mayor efecto ({best_hour}:00 UTC):")
    for sgv in ("train", "val", "oos"):
        R = agg_pairs(seg_byhour[best_hour][sgv])
        print(f"    {sgv:5s}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")

    # ================= TRACK B — FUNDING SETTLEMENT WINDOW =================
    print("\n" + "#" * 70 + "\n# TRACK B — VENTANA DE FUNDING SETTLEMENT (reloj 00/08/16 UTC, universal)\n" + "#" * 70)
    WINDOWS = {"-60to+60": (-60, 60), "-30to+30": (-30, 30), "-15to+15": (-15, 15), "-5to+15": (-5, 15), "+15to+60": (15, 60)}
    def minutes_to_settlement(t_ms):
        dt_ = datetime.utcfromtimestamp(t_ms / 1000)
        mod = (dt_.hour * 60 + dt_.minute) % 480   # 480 min = 8h
        return mod if mod <= 240 else mod - 480    # distancia con signo al settlement más cercano

    for wname, (lo, hi) in WINDOWS.items():
        in_win = {"rv": [], "ret": []}
        out_win = {"rv": [], "ret": []}
        for s, d in P.items():
            f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
            for i in range(96, n - 4, 4):
                mts = minutes_to_settlement(int(t[i]))
                r = math.log(c[i + 4] / c[i]) if i + 4 < n else None
                if r is None or not np.isfinite(f["rv"][i]):
                    continue
                if lo <= mts <= hi:
                    in_win["rv"].append(f["rv"][i]); in_win["ret"].append((s, r))
                elif abs(mts) > 120:   # control lejos de cualquier settlement
                    out_win["rv"].append(f["rv"][i]); out_win["ret"].append((s, r))
        Ri = agg_pairs(in_win["ret"]); Ro = agg_pairs(out_win["ret"])
        rvi = np.median(in_win["rv"]) * 1e4 if in_win["rv"] else float("nan")
        rvo = np.median(out_win["rv"]) * 1e4 if out_win["rv"] else float("nan")
        print(f"  {wname:>10s}: ret_1h dentro={Ri.get('mean_bp')}bp CI{Ri.get('ci_bp')} (n={Ri.get('n')})   "
              f"fuera={Ro.get('mean_bp')}bp (n={Ro.get('n')})   rv_med dentro={rvi:.1f}bp  fuera={rvo:.1f}bp")

    # ================= TRACK D — HORA x EVENTO (interacción) =================
    print("\n" + "#" * 70 + f"\n# TRACK D — hora {best_hour}:00 UTC x compresión/expansión de volumen (interacción)\n" + "#" * 70)
    inter = {"compress": [], "volexp": [], "both": [], "neither": []}
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        for i in range(ROLL, n - 4, 1):
            hh = datetime.utcfromtimestamp(int(t[i]) / 1000).hour
            if hh != best_hour or i + 4 >= n:
                continue
            r = math.log(c[i + 4] / c[i])
            cpr = np.isfinite(f["rv_pct"][i]) and f["rv_pct"][i] < 0.25
            vex = np.isfinite(f["vol_pct"][i]) and f["vol_pct"][i] >= 0.75
            if cpr and vex:
                inter["both"].append((s, r))
            elif cpr:
                inter["compress"].append((s, r))
            elif vex:
                inter["volexp"].append((s, r))
            else:
                inter["neither"].append((s, r))
    for k, v in inter.items():
        R = agg_pairs(v)
        print(f"    {k:10s}: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")

    # ================= TRACK C (ligero) — sobre-reactores tras shock ancho =================
    print("\n" + "#" * 70 + "\n# TRACK C (ligero) — reversión de sobre-reactores tras shock de mercado ancho\n" + "#" * 70)
    common_ms = sorted(set(int(t) for d in P.values() for t in d["t"]))
    idx_of = {m: k for k, m in enumerate(common_ms)}
    mat = np.full((len(common_ms), len(P)), np.nan)
    symlist = list(P.keys())
    for si, s in enumerate(symlist):
        f = F[s]; d = P[s]
        for k, t in enumerate(d["t"]):
            j = idx_of.get(int(t))
            if j is not None and k + 4 < len(d["c"]):
                mat[j, si] = f["r1"][k]
    med_ret = np.nanmedian(mat, axis=1)
    thr = np.nanpercentile(np.abs(med_ret), 90)
    shocks = np.where(np.abs(med_ret) >= thr)[0]
    over_react = []
    for widx in shocks[::4]:
        tms = common_ms[widx]; mv = med_ret[widx]
        if not np.isfinite(mv) or mv == 0:
            continue
        for s in symlist:
            d = P[s]; j = d["pos"].get(tms)
            if j is None or j + 8 >= len(d["c"]) or j < 4:
                continue
            r_here = F[s]["r1"][j]
            if not np.isfinite(r_here) or np.sign(r_here) != np.sign(mv) or abs(r_here) < 2.5 * abs(mv):
                continue   # solo sobre-reactores: 2.5x+ el movimiento del mercado, mismo signo
            fwd = -np.sign(mv) * math.log(d["c"][j + 8] / d["c"][j])   # bet reversión de la sobre-reacción
            over_react.append((s, fwd))
    R = agg_pairs(over_react)
    print(f"  reversión de sobre-reactores (2.5x+ el shock, bet contrario) @2h: {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')} symPos={R.get('frac_sym_pos')}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(P), "hour_stats": hour_stats}
    json.dump(out, open(os.path.join(ROOT, "scratch_r19_temporal.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r19_temporal.json")


if __name__ == "__main__":
    main()
