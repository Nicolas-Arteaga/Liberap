"""
ROUND 14 — ALTCOIN CROSS-SECTIONAL ALPHA DISCOVERY.

Universo: 45 símbolos ex-ante (mismo de R11-R13; es el subconjunto con OI+L/S+
funding+taker completos desde antes de TRAIN; los otros ~380 pares del venue no
tienen OI/funding/L-S history -> se documenta como límite de datos, no se oculta).
Datos: klines_clean 15m, taker_flow 15m, oi_metrics 5m->15m, funding_hist 8h.
14.5 meses (2025-06-01..2026-08-17), sin descargas nuevas.

METODOLOGÍA:
  1) Features causales por símbolo (15m grid).
  2) A cada timestamp del grid de rebalanceo (cada 16 barras = 4h), se
     estandarizan CROSS-SECCIONALMENTE (z-score entre los símbolos con dato
     válido ESE bar) -> separa señal idiosincrática de drift común del universo
     (la lección de R13).
  3) 9 scores candidatos PREDECLARADOS (combinaciones/interacciones de 2+
     features) + 1 oracle de control (retorno futuro real, NUNCA usado como
     estrategia, solo para verificar que el motor de ranking separa cuando la
     señal es perfecta).
  4) Para cada score: LONG top-decile, SHORT bottom-decile, LONG-SHORT — sin
     asumir dirección.
  5) Screening en TRAIN @24h vs random-ranking y vs momentum-only/vol-only.
  6) Sobrevivientes -> TRAIN/VAL/OOS completo, todos los horizontes, N=1/2/3/5/10,
     placebo, sim económica causal con capital <=450.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r9_oi_alpha import load_panel
from r12_smartmoney import restrict_universe, pctile_causal
from datetime import datetime, timezone, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
ROLL = 2880          # 30d causal, 15m grid
REBAL = 16           # 4h
HOR_BARS = {"1h": 4, "4h": 16, "12h": 48, "24h": 96, "72h": 288}
RT_BP = 2 * (5.0 + 3.0 + 4.0)   # 24bp, mismo criterio que R10-R13
rng = np.random.default_rng(20260917)


def build_features(P, bret, btpos):
    F = {}
    for s, d in P.items():
        c = d["c"]; o = d["o"]; v = d["v"]; n = len(c)
        ret1h = np.concatenate([np.full(4, np.nan), np.log(c[4:] / c[:-4])])
        ret4h = np.concatenate([np.full(16, np.nan), np.log(c[16:] / c[:-16])])
        ret24h = np.concatenate([np.full(96, np.nan), np.log(c[96:] / c[:-96])])
        r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
        rv = np.full(n, np.nan)
        cs2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r1) ** 2)])
        for i in range(96, n):
            rv[i] = math.sqrt((cs2[i] - cs2[i - 96]) / 96)
        vol_pct = pctile_causal(rv, ROLL)
        volume_z = zscore_causal(v, ROLL)
        oi = d["oi"]
        dOI1h = np.concatenate([np.full(4, np.nan), np.log(np.where(oi[4:] > 0, oi[4:], np.nan) / np.where(oi[:-4] > 0, oi[:-4], np.nan))])
        dOI4h = np.concatenate([np.full(16, np.nan), np.log(np.where(oi[16:] > 0, oi[16:], np.nan) / np.where(oi[:-16] > 0, oi[:-16], np.nan))])
        fund_z = zscore_causal(d["fund"], ROLL)
        tbr = d["tbr"]
        taker_z = zscore_causal(tbr - 0.5, ROLL)
        F[s] = dict(ret1h=ret1h, ret4h=ret4h, ret24h=ret24h, rv=rv, vol_pct=vol_pct,
                    volume_z=volume_z, dOI1h=dOI1h, dOI4h=dOI4h, fund_z=fund_z, taker_z=taker_z)
    return F


def xsec_z(vals):
    """vals: dict sym->valor (ya filtrado a validos). devuelve dict sym->z cross-sectional."""
    arr = np.array(list(vals.values()))
    m, s = arr.mean(), arr.std()
    if s <= 0 or not np.isfinite(s):
        return {k: 0.0 for k in vals}
    return {k: (v - m) / s for k, v in vals.items()}


def main():
    print("=== ROUND 14 — ALTCOIN CROSS-SECTIONAL ALPHA DISCOVERY ===")
    P, bret, btpos = load_panel()
    P = restrict_universe(P)
    print(f"universo feature-completo (OI+L/S+funding+taker+precio): {len(P)} símbolos")
    print("NOTA DE COBERTURA: el venue tiene ~400+ perps; taker_flow cubre ~429 con precio+flujo,")
    print("pero OI/funding/L-S histórico solo existe para el universo ex-ante de 63 (45 con historia completa).")
    print("Este round usa ese universo feature-completo -- es el límite de datos real, documentado, no oculto.")
    F = build_features(P, bret, btpos)
    syms = list(P.keys())

    # calendario de rebalanceo: usar timestamps de BTC como grid maestro
    bt = P["BTCUSDT"]["t"]; n_bt = len(bt)
    rebal_idx_master = list(range(ROLL, n_bt - HOR_BARS["72h"] - 1, REBAL))
    print(f"grid de rebalanceo: {len(rebal_idx_master)} timestamps cada 4h")

    # posiciones de cada simbolo alineadas al ms de BTC
    pos_by_sym = {s: P[s]["pos"] for s in syms}

    def get_val(s, key, i_btc_ms):
        j = pos_by_sym[s].get(i_btc_ms)
        if j is None:
            return None, None
        v = F[s][key][j]
        return (v, j) if np.isfinite(v) else (None, j)

    # ---- construir, para cada rebalanceo, los scores cross-seccionales ----
    records = []   # dict con symbol->(scores...), timestamp, indices para fwd returns
    for i_bt in rebal_idx_master:
        tms = int(bt[i_bt])
        raw = {}
        for s in syms:
            if s == "BTCUSDT":
                continue
            j = pos_by_sym[s].get(tms)
            if j is None or j < ROLL:
                continue
            feat = F[s]
            vals = (feat["ret24h"][j], feat["ret4h"][j], feat["rv"][j], feat["vol_pct"][j],
                    feat["volume_z"][j], feat["dOI1h"][j], feat["dOI4h"][j], feat["fund_z"][j], feat["taker_z"][j])
            if all(np.isfinite(v) for v in vals) and j + HOR_BARS["72h"] < len(P[s]["c"]):
                raw[s] = dict(ret24h=vals[0], ret4h=vals[1], rv=vals[2], vol_pct=vals[3],
                              volume_z=vals[4], dOI1h=vals[5], dOI4h=vals[6], fund_z=vals[7], taker_z=vals[8], j=j)
        if len(raw) < 20:
            continue
        xret24 = xsec_z({s: v["ret24h"] for s, v in raw.items()})
        xret4 = xsec_z({s: v["ret4h"] for s, v in raw.items()})
        xrv = xsec_z({s: v["rv"] for s, v in raw.items()})
        xcompress = xsec_z({s: -v["vol_pct"] for s, v in raw.items()})   # alto = muy comprimido
        xvol = xsec_z({s: v["volume_z"] for s, v in raw.items()})
        xdoi1 = xsec_z({s: v["dOI1h"] for s, v in raw.items()})
        xdoi4 = xsec_z({s: v["dOI4h"] for s, v in raw.items()})
        xfund = xsec_z({s: v["fund_z"] for s, v in raw.items()})
        xtaker = xsec_z({s: v["taker_z"] for s, v in raw.items()})

        scores = {}
        for s in raw:
            scores.setdefault(s, {})
            scores[s]["momentum_only"] = xret24[s]
            scores[s]["vol_only"] = xrv[s]
            scores[s]["S1_expansion_OI"] = xrv[s] + xdoi4[s]
            scores[s]["S2_compression_pending"] = xcompress[s] + xdoi4[s]
            scores[s]["S3_price_OI_divergence"] = xdoi4[s] * (-np.sign(xret4[s]) if xret4[s] != 0 else 0)
            scores[s]["S4_funding_taker_disagree"] = xtaker[s] - xfund[s]
            scores[s]["S5_relmom_OI_confirm"] = xret24[s] + xdoi4[s]
            scores[s]["S6_volume_OI_breakout"] = xvol[s] + xdoi4[s]
            scores[s]["S7_outlier_convexity"] = abs(xret24[s]) + abs(xdoi4[s]) + abs(xfund[s]) + abs(xtaker[s]) + abs(xvol[s])
            scores[s]["S8_funding_extreme_fade"] = -xfund[s]
        records.append(dict(tms=tms, raw=raw, scores=scores))

    print(f"rebalanceos usables (>=20 símbolos válidos): {len(records)}")
    days_all = sorted(set(datetime.utcfromtimestamp(r["tms"] / 1000).date() for r in records))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")

    def fwd_ret(s, j, hbars):
        c = P[s]["c"]
        return math.log(c[j + hbars] / c[j]) if j + hbars < len(c) else None

    SCORE_NAMES = ["momentum_only", "vol_only", "S1_expansion_OI", "S2_compression_pending",
                   "S3_price_OI_divergence", "S4_funding_taker_disagree", "S5_relmom_OI_confirm",
                   "S6_volume_OI_breakout", "S7_outlier_convexity", "S8_funding_extreme_fade"]

    def portfolio_fwd(score_name, n_legs, variant, hbars, segfilter=None, oracle_h=None):
        """variant: 'long_top','short_bottom','long_short'. Devuelve list (sym,ret)."""
        out = []
        for rec in records:
            day = datetime.utcfromtimestamp(rec["tms"] / 1000).date()
            if segfilter is not None and seg(day) != segfilter:
                continue
            sc = rec["scores"]
            if oracle_h is not None:
                # oracle: rankear por el retorno futuro REAL a ese horizonte (solo sanity)
                tmp = {}
                for s, v in rec["raw"].items():
                    r = fwd_ret(s, v["j"], HOR_BARS[oracle_h])
                    if r is not None:
                        tmp[s] = r
                order = sorted(tmp, key=lambda s: tmp[s], reverse=True)
            else:
                order = sorted(sc, key=lambda s: sc[s][score_name], reverse=True)
            if len(order) < 2 * n_legs:
                continue
            top = order[:n_legs]; bot = order[-n_legs:]
            for s in top:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None:
                    if variant in ("long_top", "long_short"):
                        out.append((s, r))
            for s in bot:
                j = rec["raw"][s]["j"]; r = fwd_ret(s, j, hbars)
                if r is not None:
                    if variant == "short_bottom":
                        out.append((s, -r))
                    elif variant == "long_short":
                        out.append((s, -r))
        return out

    def random_bench(n_legs, hbars, segfilter, seed=0, variant="long_short"):
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

    # ===== SCREENING EN TRAIN @24h, N=5, long_short =====
    print("\n" + "#" * 70 + "\n# FASE 1-3 — SCREENING (TRAIN, @24h, N=5, long_short) vs random/momentum/vol/oracle\n" + "#" * 70)
    N0 = 5; H0 = "24h"
    screen = {}
    for name in SCORE_NAMES:
        pairs = portfolio_fwd(name, N0, "long_short", HOR_BARS[H0], segfilter="train")
        R = agg_pairs(pairs)
        screen[name] = R
        print(f"  {name:28s}: {R.get('mean_bp')} bp  CI{R.get('ci_bp')}  excl0={R.get('ci_excl_0')}  n={R.get('n')}  symPos={R.get('frac_sym_pos')}")
    rnd = agg_pairs(random_bench(N0, HOR_BARS[H0], "train", seed=7))
    print(f"  {'RANDOM (control)':28s}: {rnd.get('mean_bp')} bp  CI{rnd.get('ci_bp')}  n={rnd.get('n')}")
    orc = agg_pairs(portfolio_fwd(None, N0, "long_short", HOR_BARS[H0], segfilter="train", oracle_h=H0))
    print(f"  {'ORACLE (sanity, NO estrategia)':28s}: {orc.get('mean_bp')} bp  CI{orc.get('ci_bp')}  n={orc.get('n')}")

    # sobrevivientes de screening: CI excl 0 en TRAIN, supera random claramente, supera costo (24bp) en magnitud bruta
    survivors = []
    for name, R in screen.items():
        if "mean_bp" in R and R["ci_excl_0"] and abs(R["mean_bp"]) > abs(rnd.get("mean_bp", 0)) + 5 and abs(R["mean_bp"]) > RT_BP:
            survivors.append(name)
    print(f"\n  SOBREVIVIENTES del screening (CI excl 0, > random+5bp, > costo bruto): {survivors if survivors else 'NINGUNO'}")

    detailed = {}
    for name in (survivors if survivors else SCORE_NAMES[:3]):   # si no hay sobrevivientes, igual reportamos las 3 mejores en TRAIN para transparencia
        print(f"\n{'='*66}\nDETALLE: {name}\n{'='*66}")
        det = {"by_h": {}, "by_variant": {}, "by_N": {}}
        for h in HOR_BARS:
            row = {}
            for sgv in ("train", "val", "oos"):
                pairs = portfolio_fwd(name, N0, "long_short", HOR_BARS[h], segfilter=sgv)
                R = agg_pairs(pairs); row[sgv] = R.get("mean_bp")
            det["by_h"][h] = row
            print(f"  h={h:>4}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        for variant in ("long_top", "short_bottom", "long_short"):
            row = {}
            for sgv in ("train", "val", "oos"):
                pairs = portfolio_fwd(name, N0, variant, HOR_BARS["24h"], segfilter=sgv)
                R = agg_pairs(pairs); row[sgv] = (R.get("mean_bp"), R.get("n"))
            det["by_variant"][variant] = row
            print(f"  variant={variant:14s}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        for Nn in (1, 2, 3, 5, 10):
            row = {}
            for sgv in ("train", "val", "oos"):
                pairs = portfolio_fwd(name, Nn, "long_short", HOR_BARS["24h"], segfilter=sgv)
                R = agg_pairs(pairs); row[sgv] = (R.get("mean_bp"), R.get("n"))
            det["by_N"][Nn] = row
            print(f"  N={Nn:<2}: train={row['train']}  val={row['val']}  oos={row['oos']}")
        detailed[name] = det

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(P),
           "n_rebalances": len(records), "tcut": str(tcut), "vcut": str(vcut),
           "screening": screen, "random_bench": rnd, "oracle": orc,
           "survivors": survivors, "detailed": detailed}
    json.dump(out, open(os.path.join(ROOT, "scratch_r14_discovery.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r14_discovery.json")


if __name__ == "__main__":
    main()
