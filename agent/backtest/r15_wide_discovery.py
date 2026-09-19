"""
ROUND 15 — FIND 1-3 PROFITABLE ALTCOIN STRATEGIES (universo ANCHO, ~400 pares).

A diferencia de R9-R14 (universo restringido a 45-63 símbolos con OI/funding/L-S
completos), este round usa el universo AMPLIO: todo símbolo con klines_clean 15m
+ taker_flow 15m y >= 8000 barras de historia (~83 días) -> ~395 símbolos. Sin
OI/funding (no existen para la mayoría); solo OHLCV + taker-flow, que SÍ cubren
casi todo el venue. Excluye acciones/commodities tokenizadas (mismo criterio de
rondas anteriores) para mantener el universo cripto.

3 familias (predeclaradas, sin elegir después de ver resultados):
  A - EVENTOS/EXTREMOS: expansión de volatilidad + agresión taker extrema.
  B - CROSS-SECTIONAL SELECTION: momentum amplio (400 vs 45, comparación directa
      con R14), anomalía de volumen + confirmación de precio.
  C - ROTATION/HIGH-FREQ: reversión vs continuación de corto plazo (1h), ambas
      direcciones evaluadas explícitamente.

Grid de rebalanceo 4h (igual R14). TRAIN/VAL/OOS 50/25/25. Screening vs random
y vs oracle (sanity). N=1/2/3/5 para sobrevivientes. Sim económica causal para
cualquier candidato que pase el screening.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r12_smartmoney import pctile_causal
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
ROLL = 2880
REBAL = 16
HOR_BARS = {"1h": 4, "4h": 16, "12h": 48, "24h": 96, "72h": 288}
RT_BP = 2 * (5.0 + 3.0 + 4.0)
MIN_ROWS = 8000
EXCLUDE_BASE = {"XAU", "XAG", "SPX", "COMP", "AAPL", "AMZN", "MSFT", "GOOGL", "META", "NVDA", "TSLA", "AMD",
                "QCOM", "IBM", "UBER", "DELL", "SMCI", "AVGO", "ASTS", "AAOI", "AXTI", "HIMS", "MSTR", "COIN",
                "INTC", "MU", "ORCL", "PLTR", "BABA", "HOOD", "IREN", "CRCL", "OPEN", "ARM", "QQQ", "SPY",
                "SOXL", "SQQQ", "UVXY", "TZA", "GOOG", "BULLA", "APR", "SPCX", "SKHYNIX", "SKHY", "NBIS",
                "ONDS", "RKLB", "SNDK", "TSM", "XPD", "KOR", "EWY", "BZ", "CL"}
rng = np.random.default_rng(20260918)


def universe():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT k.symbol, COUNT(*) n FROM klines_clean k WHERE k.interval='15m' "
        "AND k.symbol IN (SELECT DISTINCT symbol FROM taker_flow WHERE interval='15m') "
        "GROUP BY k.symbol HAVING n >= ?", (MIN_ROWS,)).fetchall()
    con.close()
    syms = []
    for s, n in rows:
        base = s[:-4] if s.endswith("USDT") else s
        if base in EXCLUDE_BASE:
            continue
        syms.append(s)
    return sorted(syms)


def load_symbol(con, s):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                    "WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    if len(k) < MIN_ROWS:
        return None
    t = np.array([r[0] for r in k], np.int64)
    o = np.array([r[1] for r in k], float); h = np.array([r[2] for r in k], float)
    lo = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    v = np.array([r[5] for r in k], float)
    tf = con.execute("SELECT open_time,quote_volume,taker_buy_quote FROM taker_flow "
                     "WHERE symbol=? AND interval='15m'", (s,)).fetchall()
    pos = {int(x): i for i, x in enumerate(t)}
    qv = np.full(len(t), np.nan); tbr = np.full(len(t), np.nan)
    for ot, q, tbq in tf:
        i = pos.get(int(ot))
        if i is not None and q and q > 0:
            qv[i] = q; tbr[i] = tbq / q
    return dict(t=t, o=o, h=h, l=lo, c=c, v=v, qv=qv, tbr=tbr, pos=pos)


def build_features(d):
    c = d["c"]; n = len(c)
    r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    ret1h = np.concatenate([np.full(4, np.nan), np.log(c[4:] / c[:-4])])
    ret4h = np.concatenate([np.full(16, np.nan), np.log(c[16:] / c[:-16])])
    ret24h = np.concatenate([np.full(96, np.nan), np.log(c[96:] / c[:-96])])
    rv = np.full(n, np.nan)
    cs2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r1) ** 2)])
    for i in range(96, n, 1):
        rv[i] = math.sqrt((cs2[i] - cs2[i - 96]) / 96)
    volpct = pctile_causal(rv, ROLL)
    dollarvol = d["o"] * d["v"]
    dvol_z = zscore_causal(dollarvol, ROLL)
    taker_z = zscore_causal(d["tbr"] - 0.5, ROLL)
    return dict(ret1h=ret1h, ret4h=ret4h, ret24h=ret24h, rv=rv, volpct=volpct, dvol_z=dvol_z, taker_z=taker_z)


def xsec_z(vals):
    arr = np.array(list(vals.values()))
    m, s = arr.mean(), arr.std()
    if s <= 0 or not np.isfinite(s):
        return {k: 0.0 for k in vals}
    return {k: (v - m) / s for k, v in vals.items()}


def main():
    print("=== ROUND 15 — FIND 1-3 PROFITABLE STRATEGIES (universo ancho) ===")
    syms = universe()
    print(f"universo ancho: {len(syms)} símbolos (>= {MIN_ROWS} barras 15m, en klines_clean + taker_flow, excl. equity/commodity)")
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_features(d)
    con.close()
    print(f"cargados con features: {len(P)}")

    if "BTCUSDT" not in P:
        print("BTCUSDT no está en el universo ancho -> usar otro símbolo de referencia para el grid")
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    bt = P[ref]["t"]; n_bt = len(bt)
    rebal_idx_master = list(range(ROLL, n_bt - HOR_BARS["72h"] - 1, REBAL))
    print(f"grid de rebalanceo (ref={ref}): {len(rebal_idx_master)} timestamps cada 4h")

    records = []
    for i_bt in rebal_idx_master:
        tms = int(bt[i_bt])
        raw = {}
        for s, d in P.items():
            j = d["pos"].get(tms)
            if j is None or j < ROLL:
                continue
            feat = F[s]
            vals = (feat["ret24h"][j], feat["ret4h"][j], feat["ret1h"][j], feat["rv"][j],
                    feat["volpct"][j], feat["dvol_z"][j], feat["taker_z"][j])
            if all(np.isfinite(v) for v in vals) and j + HOR_BARS["72h"] < len(d["c"]):
                raw[s] = dict(ret24h=vals[0], ret4h=vals[1], ret1h=vals[2], rv=vals[3],
                              volpct=vals[4], dvol_z=vals[5], taker_z=vals[6], j=j)
        if len(raw) < 50:
            continue
        xret24 = xsec_z({s: v["ret24h"] for s, v in raw.items()})
        xret4 = xsec_z({s: v["ret4h"] for s, v in raw.items()})
        xret1 = xsec_z({s: v["ret1h"] for s, v in raw.items()})
        xrv = xsec_z({s: v["rv"] for s, v in raw.items()})
        xdvol = xsec_z({s: v["dvol_z"] for s, v in raw.items()})
        xtaker = xsec_z({s: v["taker_z"] for s, v in raw.items()})

        scores = {}
        for s in raw:
            scores.setdefault(s, {})
            scores[s]["A1_vol_expansion_continue"] = xrv[s] * (1 if xret4[s] >= 0 else -1)
            scores[s]["A2_taker_aggression"] = xtaker[s]
            scores[s]["B1_momentum_wide"] = xret24[s]
            scores[s]["B2_volume_anomaly_confirm"] = xdvol[s] * (1 if xret4[s] >= 0 else -1)
            scores[s]["C1_shortterm_reversal"] = -xret1[s]
            scores[s]["C2_shortterm_continuation"] = xret1[s]
        records.append(dict(tms=tms, raw=raw, scores=scores))

    print(f"rebalanceos usables (>=50 símbolos válidos): {len(records)}")
    days_all = sorted(set(datetime.utcfromtimestamp(r["tms"] / 1000).date() for r in records))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}  (n_rebal={len(records)})")
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")

    def fwd_ret(s, j, hbars):
        c = P[s]["c"]
        return math.log(c[j + hbars] / c[j]) if j + hbars < len(c) else None

    SCORE_NAMES = ["A1_vol_expansion_continue", "A2_taker_aggression", "B1_momentum_wide",
                   "B2_volume_anomaly_confirm", "C1_shortterm_reversal", "C2_shortterm_continuation"]

    def portfolio_fwd(score_name, n_legs, variant, hbars, segfilter=None, oracle_h=None):
        out = []
        for rec in records:
            day = datetime.utcfromtimestamp(rec["tms"] / 1000).date()
            if segfilter is not None and seg(day) != segfilter:
                continue
            if oracle_h is not None:
                tmp = {}
                for s, v in rec["raw"].items():
                    r = fwd_ret(s, v["j"], HOR_BARS[oracle_h])
                    if r is not None:
                        tmp[s] = r
                order = sorted(tmp, key=lambda s: tmp[s], reverse=True)
            else:
                sc = rec["scores"]
                order = sorted(sc, key=lambda s: sc[s][score_name], reverse=True)
            if len(order) < 2 * n_legs:
                continue
            top = order[:n_legs]; bot = order[-n_legs:]
            for s in top:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None and variant in ("long_top", "long_short"):
                    out.append((s, r))
            for s in bot:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None and variant in ("short_bottom", "long_short"):
                    out.append((s, -r))
        return out

    def random_bench(n_legs, hbars, segfilter, seed=0):
        rr = np.random.default_rng(seed)
        out = []
        for rec in records:
            day = datetime.utcfromtimestamp(rec["tms"] / 1000).date()
            if segfilter is not None and seg(day) != segfilter:
                continue
            syms_here = list(rec["raw"])
            if len(syms_here) < 2 * n_legs:
                continue
            rr.shuffle(syms_here)
            top, bot = syms_here[:n_legs], syms_here[-n_legs:]
            for s in top:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None:
                    out.append((s, r))
            for s in bot:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None:
                    out.append((s, -r))
        return out

    print("\n" + "#" * 70 + "\n# SCREENING (TRAIN, @24h, N=3, long_short) — universo ancho vs random/oracle\n" + "#" * 70)
    N0 = 3; H0 = "24h"
    screen = {}
    for name in SCORE_NAMES:
        pairs = portfolio_fwd(name, N0, "long_short", HOR_BARS[H0], segfilter="train")
        R = agg_pairs(pairs); screen[name] = R
        print(f"  {name:30s}: {R.get('mean_bp')} bp  CI{R.get('ci_bp')}  excl0={R.get('ci_excl_0')}  n={R.get('n')}  symPos={R.get('frac_sym_pos')}")
    rnd = agg_pairs(random_bench(N0, HOR_BARS[H0], "train", seed=11))
    print(f"  {'RANDOM (control)':30s}: {rnd.get('mean_bp')} bp  CI{rnd.get('ci_bp')}  n={rnd.get('n')}")
    orc = agg_pairs(portfolio_fwd(None, N0, "long_short", HOR_BARS[H0], segfilter="train", oracle_h=H0))
    print(f"  {'ORACLE (sanity)':30s}: {orc.get('mean_bp')} bp  CI{orc.get('ci_bp')}  n={orc.get('n')}")

    survivors = []
    for name, R in screen.items():
        if "mean_bp" in R and R["ci_excl_0"] and abs(R["mean_bp"]) > abs(rnd.get("mean_bp", 0)) + 5 and abs(R["mean_bp"]) > RT_BP:
            survivors.append(name)
    print(f"\n  SOBREVIVIENTES del screening: {survivors if survivors else 'NINGUNO'}")

    # comparación directa ANCHO(400) vs ESTRECHO(45) para momentum -- referencia a R14
    print("\n  Comparación B1_momentum_wide (universo ancho ~395) por N:")
    for Nn in (1, 2, 3, 5, 10):
        R = agg_pairs(portfolio_fwd("B1_momentum_wide", Nn, "long_short", HOR_BARS["24h"], segfilter="train"))
        print(f"    N={Nn:<2}: train={R.get('mean_bp')}bp  n={R.get('n')}  symPos={R.get('frac_sym_pos')}  conc={R.get('top5_conc')}")

    detailed = {}
    to_detail = survivors if survivors else SCORE_NAMES
    for name in to_detail:
        print(f"\n{'='*66}\nDETALLE: {name}\n{'='*66}")
        det = {"by_h": {}, "by_variant": {}, "by_N": {}}
        for h in HOR_BARS:
            row = {}
            for sgv in ("train", "val", "oos"):
                R = agg_pairs(portfolio_fwd(name, N0, "long_short", HOR_BARS[h], segfilter=sgv))
                row[sgv] = R.get("mean_bp")
            det["by_h"][h] = row
            print(f"  h={h:>4}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        for variant in ("long_top", "short_bottom", "long_short"):
            row = {}
            for sgv in ("train", "val", "oos"):
                R = agg_pairs(portfolio_fwd(name, N0, variant, HOR_BARS["24h"], segfilter=sgv))
                row[sgv] = (R.get("mean_bp"), R.get("n"))
            det["by_variant"][variant] = row
            print(f"  variant={variant:14s}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        for Nn in (1, 2, 3, 5, 10):
            row = {}
            for sgv in ("train", "val", "oos"):
                R = agg_pairs(portfolio_fwd(name, Nn, "long_short", HOR_BARS["24h"], segfilter=sgv))
                row[sgv] = (R.get("mean_bp"), R.get("n"), R.get("top5_conc"))
            det["by_N"][Nn] = row
            print(f"  N={Nn:<2}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        detailed[name] = det

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(P),
           "n_rebalances": len(records), "tcut": str(tcut), "vcut": str(vcut),
           "screening": screen, "random_bench": rnd, "oracle": orc,
           "survivors": survivors, "detailed": detailed}
    json.dump(out, open(os.path.join(ROOT, "scratch_r15_wide_discovery.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r15_wide_discovery.json")


if __name__ == "__main__":
    main()
