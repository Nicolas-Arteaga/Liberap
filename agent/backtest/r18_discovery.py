"""
ROUND 18 — ALPHA HUNT: BREAK THE FRAME.

Cambio de modo: no "factor -> backtest -> falsar" sino "comportamiento de
mercado -> secuencia -> reacción -> payoff asimétrico". Universo ANCHO (357
símbolos, solo OHLCV+taker, igual R15 -- no se exige OI/funding).

Listing events (pedido evaluar rápido, no casarse): ya evaluado por WebFetch
-- Binance publica anuncios reales y fechados, pero requiere paginar ~10+
meses de historial mixto (spot/futuros/otros servicios) para construir un
calendario limpio, Y en R7/R8 ya se determinó que incluso con fechas
perfectas el universo de listings crypto-nativos "limpios" en esta ventana es
de ~20-38 eventos -- insuficiente para un backtest robusto pase lo que pase
con la calidad del dato. Se descarta en minutos, tal como pide el brief, y se
pasa a las familias A/B/D/E (prioritarias).

SECUENCIA 1 — COMPRESIÓN -> EXPANSIÓN (Familias A+B+D+E):
  Estado: rv_pctile(t) causal en decil bajo sostenido >= K barras (mercado
  quieto). Evento: la PRIMERA barra que rompe con |ret| en decil alto.
  Dirección = signo de la barra de ruptura (continuación, hipótesis simple).
  Se mide la distribución COMPLETA de MFE/MAE (no solo el retorno medio) a
  varios horizontes -- eso es la Familia D (asimetría de payoff).
  Control: mismo evento SIN la compresión previa (rompe "en frío").

SECUENCIA 2 — CAPITULACIÓN/CLIMAX -> REACCIÓN (Familias A+D+I):
  Evento: caída en decil bajo + volumen en decil alto en 1-2 barras.
  Se mide la reacción (MFE/MAE, ambos sentidos, sin asumir reversión ni
  continuación) -- Familia I: reacción, no predicción.
  Control: caída de igual magnitud SIN volumen anómalo.

DIAGNÓSTICOS LIGEROS (no sim económica completa, solo para mapa de alpha):
  - Familia H: retorno medio por hora UTC (¿hay ventanas horarias con sesgo?).
  - Familia C: reacción de "rezagados" tras un movimiento amplio del universo
    (más liviano que H18 -- solo diagnóstico, no otra ronda de cross-sectional).
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r12_smartmoney import pctile_causal
from r15_wide_discovery import universe, load_symbol, MIN_ROWS
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
ROLL = 2880
RT_BP = 2 * (5.0 + 3.0 + 4.0)   # 24bp, mismo criterio de todo el proyecto
HOR = {"1h": 4, "4h": 16, "12h": 48, "24h": 96}
rng = np.random.default_rng(20260921)


def build_feats(d):
    c = d["c"]; h = d["h"]; l = d["l"]; o = d["o"]; v = d["v"]; n = len(c)
    r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    rv = np.full(n, np.nan)
    cs2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r1) ** 2)])
    for i in range(96, n):
        rv[i] = math.sqrt((cs2[i] - cs2[i - 96]) / 96)
    rv_pct = pctile_causal(rv, ROLL)
    ret1_pct = pctile_causal(r1, ROLL)
    volz = zscore_causal(d["o"] * d["v"], ROLL)
    vol_pct = pctile_causal(d["o"] * d["v"], ROLL)
    return dict(r1=r1, rv=rv, rv_pct=rv_pct, ret1_pct=ret1_pct, volz=volz, vol_pct=vol_pct)


def mfe_mae(o, h, l, i_entry, hbars, side):
    """MFE/MAE (log-return) desde open[i_entry] usando high/low intrabar."""
    j1 = i_entry + hbars
    if j1 >= len(o):
        return None
    hi = h[i_entry:j1 + 1].max(); lo = l[i_entry:j1 + 1].min()
    entry = o[i_entry]
    final_ret = side * math.log(o[j1] / entry)
    if side > 0:
        mfe = math.log(hi / entry); mae = math.log(lo / entry)
    else:
        mfe = -math.log(lo / entry); mae = -math.log(hi / entry)
    return final_ret, mfe, mae


def summarize_mfemae(rows, label):
    """rows: list de (sym, final, mfe, mae) en LOG-return. Reporta en bp."""
    if len(rows) < 20:
        print(f"    {label}: n insuficiente ({len(rows)})"); return None
    fin = np.array([r[1] for r in rows]) * 1e4
    mfe = np.array([r[2] for r in rows]) * 1e4
    mae = np.array([r[3] for r in rows]) * 1e4
    wr = float((fin > 0).mean())
    print(f"    {label}: n={len(rows)}  final_mean={fin.mean():+.1f}bp  final_med={np.median(fin):+.1f}bp  "
          f"WR={wr:.2f}  MFE[p50/p75/p90]=({np.percentile(mfe,50):.0f}/{np.percentile(mfe,75):.0f}/{np.percentile(mfe,90):.0f})  "
          f"MAE[p50/p25/p10]=({np.percentile(mae,50):.0f}/{np.percentile(mae,25):.0f}/{np.percentile(mae,10):.0f})")
    return dict(n=len(rows), final_mean=float(fin.mean()), final_med=float(np.median(fin)), wr=wr,
                mfe_p50=float(np.percentile(mfe, 50)), mfe_p75=float(np.percentile(mfe, 75)), mfe_p90=float(np.percentile(mfe, 90)),
                mae_p50=float(np.percentile(mae, 50)), mae_p25=float(np.percentile(mae, 25)), mae_p10=float(np.percentile(mae, 10)))


def main():
    print("=== ROUND 18 — ALPHA HUNT: BREAK THE FRAME ===")
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

    # ================= SECUENCIA 1: COMPRESIÓN -> EXPANSIÓN =================
    print("\n" + "#" * 70 + "\n# SECUENCIA 1 — COMPRESIÓN -> EXPANSIÓN (MFE/MAE, con y sin compresión previa)\n" + "#" * 70)
    K_COMPRESS = 8       # barras de 15m (~2h) en compresión sostenida
    COMPRESS_PCT = 0.25
    BREAKOUT_PCT = 0.85
    ev_with, ev_without, ctrl_placebo, ev_randbars = [], [], [], []
    for s, d in P.items():
        f = F[s]; c = d["c"]; o = d["o"]; h = d["h"]; l = d["l"]; n = len(c)
        rvp = f["rv_pct"]; r1p = f["ret1_pct"]
        compressed = np.zeros(n, bool)
        for i in range(K_COMPRESS, n):
            seg_ = rvp[i - K_COMPRESS:i]
            compressed[i] = np.all(np.isfinite(seg_)) and np.all(seg_ < COMPRESS_PCT)
        breakout = np.isfinite(r1p) & ((r1p >= BREAKOUT_PCT) | (r1p <= 1 - BREAKOUT_PCT))
        last_w = -999; last_wo = -999
        for i in np.where(breakout)[0]:
            if i < ROLL or i + 1 + max(HOR.values()) >= n:
                continue
            side = 1 if f["r1"][i] > 0 else -1
            with_compress = compressed[i - 1] if i >= 1 else False
            e = i + 1
            for h_lbl, hb in HOR.items():
                r = mfe_mae(o, h, l, e, hb, side)
                if r is None:
                    continue
                dy = datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date()
                if with_compress and i - last_w >= 4:
                    ev_with.append((s, h_lbl, seg(dy), r[0], r[1], r[2]))
                elif (not with_compress) and i - last_wo >= 4:
                    ev_without.append((s, h_lbl, seg(dy), r[0], r[1], r[2]))
            if with_compress:
                last_w = i
            else:
                last_wo = i
    print("\n -- CON compresión previa (Familia A+B) --")
    for h_lbl in HOR:
        rows = [(s, fi, mf, ma) for (s, hl, sg, fi, mf, ma) in ev_with if hl == h_lbl]
        summarize_mfemae(rows, f"h={h_lbl} ALL")
        for sgv in ("train", "val", "oos"):
            rows_s = [(s, fi, mf, ma) for (s, hl, sg, fi, mf, ma) in ev_with if hl == h_lbl and sg == sgv]
            summarize_mfemae(rows_s, f"h={h_lbl} {sgv}")
    print("\n -- SIN compresión previa (control -- ruptura 'en frío') --")
    for h_lbl in HOR:
        rows = [(s, fi, mf, ma) for (s, hl, sg, fi, mf, ma) in ev_without if hl == h_lbl]
        summarize_mfemae(rows, f"h={h_lbl} ALL")

    # ================= SECUENCIA 2: CAPITULACIÓN -> REACCIÓN =================
    print("\n" + "#" * 70 + "\n# SECUENCIA 2 — CAPITULACIÓN/CLIMAX -> REACCIÓN (ambos sentidos, MFE/MAE)\n" + "#" * 70)
    DROP_PCT = 0.03; VOL_PCT_THR = 0.90
    ev_cap_down_long, ev_cap_down_short = [], []
    ev_cap_matched_long, ev_cap_matched_short = [], []
    for s, d in P.items():
        f = F[s]; c = d["c"]; o = d["o"]; h = d["h"]; l = d["l"]; n = len(c)
        r1p = f["ret1_pct"]; volp = f["vol_pct"]
        climax = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp >= VOL_PCT_THR)
        matched = np.isfinite(r1p) & (r1p <= DROP_PCT) & (~np.isfinite(volp) | (volp < 0.5))
        last = -999
        for i in np.where(climax)[0]:
            if i < ROLL or i - last < 4 or i + 1 + max(HOR.values()) >= n:
                continue
            last = i; e = i + 1
            for h_lbl, hb in HOR.items():
                rL = mfe_mae(o, h, l, e, hb, +1); rS = mfe_mae(o, h, l, e, hb, -1)
                if rL:
                    ev_cap_down_long.append((s, h_lbl, rL[0], rL[1], rL[2]))
                if rS:
                    ev_cap_down_short.append((s, h_lbl, rS[0], rS[1], rS[2]))
        last = -999
        for i in np.where(matched)[0][::3]:
            if i < ROLL or i - last < 4 or i + 1 + max(HOR.values()) >= n:
                continue
            last = i; e = i + 1
            for h_lbl, hb in HOR.items():
                rL = mfe_mae(o, h, l, e, hb, +1)
                if rL:
                    ev_cap_matched_long.append((s, h_lbl, rL[0], rL[1], rL[2]))
    print("\n -- tras CAPITULACIÓN (drop + volumen climax): LONG (bet rebote) --")
    for h_lbl in HOR:
        rows = [(s, fi, mf, ma) for (s, hl, fi, mf, ma) in ev_cap_down_long if hl == h_lbl]
        summarize_mfemae(rows, f"h={h_lbl}")
    print("\n -- tras CAPITULACIÓN: SHORT (bet continuación) --")
    for h_lbl in HOR:
        rows = [(s, fi, mf, ma) for (s, hl, fi, mf, ma) in ev_cap_down_short if hl == h_lbl]
        summarize_mfemae(rows, f"h={h_lbl}")
    print("\n -- CONTROL: mismo drop SIN volumen climax, LONG --")
    for h_lbl in HOR:
        rows = [(s, fi, mf, ma) for (s, hl, fi, mf, ma) in ev_cap_matched_long if hl == h_lbl]
        summarize_mfemae(rows, f"h={h_lbl}")

    # ================= DIAGNÓSTICOS LIGEROS =================
    print("\n" + "#" * 70 + "\n# DIAGNÓSTICO — Familia H: retorno medio 1h por hora UTC (universo ancho)\n" + "#" * 70)
    byhour = {hh: [] for hh in range(24)}
    for s, d in P.items():
        c = d["c"]; t = d["t"]; n = len(c)
        for i in range(0, n - 4, 4):
            hh = datetime.utcfromtimestamp(int(t[i]) / 1000).hour
            if i + 4 < n:
                byhour[hh].append((s, math.log(c[i + 4] / c[i])))
    for hh in range(24):
        R = agg_pairs(byhour[hh])
        flag = "*" if R.get("ci_excl_0") else " "
        print(f"    {hh:02d}:00 UTC  {R.get('mean_bp'):>7.2f}bp{flag}  n={R.get('n')}")

    print("\n" + "#" * 70 + "\n# DIAGNÓSTICO — Familia C: reacción de rezagados tras movimiento amplio del universo\n" + "#" * 70)
    # movimiento amplio = bar donde la mediana cross-sectional de |ret_1h| esta en decil alto
    common_ms = sorted(set(int(t) for d in P.values() for t in d["t"]))
    idx_of = {m: k for k, m in enumerate(common_ms)}
    med_ret = np.full(len(common_ms), np.nan)
    mat = np.full((len(common_ms), len(P)), np.nan)
    for si, (s, d) in enumerate(P.items()):
        f = F[s]
        for k, t in enumerate(d["t"]):
            j = idx_of.get(int(t))
            if j is not None:
                mat[j, si] = f["r1"][k]
    med_ret = np.nanmedian(mat, axis=1)
    thr = np.nanpercentile(np.abs(med_ret), 90)
    wide_moves = np.where(np.abs(med_ret) >= thr)[0]
    print(f"  movimientos amplios detectados (|mediana 15m| top decil): {len(wide_moves)}")
    lag_reaction = []
    for widx in wide_moves[::5]:
        tms = common_ms[widx]
        mv = med_ret[widx]
        for s, d in P.items():
            j = d["pos"].get(tms)
            if j is None or j + 16 >= len(d["c"]) or j < 4:
                continue
            r_here = F[s]["r1"][j]
            if not np.isfinite(r_here):
                continue
            if np.sign(r_here) != np.sign(mv) or abs(r_here) > 0.3 * abs(mv):
                continue   # solo "rezagados" (no siguieron el movimiento amplio)
            fwd = math.log(d["c"][j + 16] / d["c"][j]) * np.sign(mv)   # catch-up esperado
            lag_reaction.append((s, fwd))
    R = agg_pairs(lag_reaction)
    print(f"  reacción de rezagados (catch-up esperado, @4h): {R.get('mean_bp')}bp CI{R.get('ci_bp')} n={R.get('n')}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(P)}
    json.dump(out, open(os.path.join(ROOT, "scratch_r18_discovery.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r18_discovery.json")


if __name__ == "__main__":
    main()
