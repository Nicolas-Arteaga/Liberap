"""
ROUND 35 — AUDITORIA FORENSE DE TRADES REALES (SimulatedTrades, Postgres).

Fuente: tabla "SimulatedTrades" (Postgres, Host=localhost:5433/Verge) --
3315 trades reales del sistema de produccion (17 perfiles de estrategia
distintos, no solo Nexus), 2026-05-16 a 2026-09-22. Los campos ricos
(Ma7DistancePctAtEntry, MaxAdversePrice, MaxFavorablePrice,
AgentDecisionJson, ExitAuditJson) estan TODOS NULOS -- se perdieron en el
incidente de reset de Docker documentado en memoria; se reconstruyen
desde cero usando klines_clean (15m) de binance_vision_clean.db.

NO se inventa nada: si un simbolo/trade no tiene cobertura de klines
suficiente antes de la entrada, se descarta explicitamente (se cuenta y
reporta, no se rellena).
"""
import os, sys, math, numpy as np, sqlite3, collections, json
import psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_smartmoney import pctile_causal

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
ROLL = 2880   # 30 dias en barras de 15m, para percentiles causales


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","ClosePrice","SlPrice","TpPrice",
                   "OpenedAt","ClosedAt","ExitReason","RealizedPnl","StrategyProfileId"
                   FROM "SimulatedTrades" WHERE "ExitReason" IN ('tp_hit','sl_hit')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < ROLL + 100:
        return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float); v = np.array([r[5] for r in k], float)
    return dict(t=t, o=o, h=h, l=l, c=c, v=v)


def sma(arr, w):
    n = len(arr); out = np.full(n, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(arr)])
    for i in range(w - 1, n):
        out[i] = (cs[i + 1] - cs[i + 1 - w]) / w
    return out


def find_bar_index(t_arr, ts_ms):
    """indice de la ultima barra CERRADA antes o en ts_ms (causal)."""
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def context_at(d, i):
    """features causales en la barra i (usa solo datos hasta i inclusive)."""
    c, h, l, o, v = d["c"], d["h"], d["l"], d["o"], d["v"]
    if i < 105:
        return None
    ma7 = np.mean(c[i - 6:i + 1]); ma25 = np.mean(c[i - 24:i + 1])
    ma50 = np.mean(c[i - 49:i + 1]); ma99 = np.mean(c[i - 98:i + 1])
    ma7_prev3 = np.mean(c[i - 9:i - 2]) if i >= 9 else np.nan
    ma7_slope = ma7 - ma7_prev3
    prevc = c[i - 1] if i >= 1 else c[i]
    tr = max(h[i] - l[i], abs(h[i] - prevc), abs(l[i] - prevc))
    trs = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(max(1, i - 13), i + 1)]
    atr14 = np.mean(trs) if trs else np.nan
    hi20 = h[max(0, i - 20):i + 1].max(); lo20 = l[max(0, i - 20):i + 1].min()
    hi50 = h[max(0, i - 50):i + 1].max(); lo50 = l[max(0, i - 50):i + 1].min()
    dist_hi20 = (c[i] - hi20) / c[i] if c[i] > 0 else np.nan
    dist_lo20 = (c[i] - lo20) / c[i] if c[i] > 0 else np.nan
    up_count = sum(1 for j in range(i - 9, i + 1) if c[j] > o[j]) if i >= 9 else np.nan
    vol30 = v[max(0, i - ROLL):i + 1]
    vol_pct = float((vol30 < v[i]).mean()) if len(vol30) > 50 else np.nan
    rng_now = h[i] - l[i]
    rng30 = (h[max(0, i - ROLL):i + 1] - l[max(0, i - ROLL):i + 1])
    rng_pct = float((rng30 < rng_now).mean()) if len(rng30) > 50 else np.nan
    return dict(ma7=ma7, ma25=ma25, ma50=ma50, ma99=ma99, ma7_slope=ma7_slope,
                ma7_above_ma25=ma7 > ma25, ma7_above_ma99=ma7 > ma99, ma25_above_ma99=ma25 > ma99,
                price_vs_ma25=(c[i] - ma25) / c[i], price_vs_ma99=(c[i] - ma99) / c[i],
                atr14=atr14, atr_rel=atr14 / c[i] if c[i] > 0 else np.nan,
                dist_hi20=dist_hi20, dist_lo20=dist_lo20, up_count_10=up_count,
                vol_pct=vol_pct, rng_pct=rng_pct, close=c[i])


def mae_mfe(d, i_entry, ts_close_ms, side, entry_px):
    t, h, l = d["t"], d["h"], d["l"]
    j_end = np.searchsorted(t, ts_close_ms, side="right")
    j_start = i_entry + 1
    if j_end <= j_start or j_end >= len(h):
        return None
    hi = h[j_start:j_end].max(); lo = l[j_start:j_end].min()
    if side == 1:
        mfe = (hi - entry_px) / entry_px; mae = (lo - entry_px) / entry_px
    else:
        mfe = (entry_px - lo) / entry_px; mae = (entry_px - hi) / entry_px
    return mfe * 1e4, mae * 1e4   # bp


def main():
    print("=== ROUND 35 — AUDITORIA FORENSE DE TRADES REALES ===\n")
    trades = load_trades()
    print(f"FASE 1 — trades cargados (tp_hit + sl_hit, excluye timeout): {len(trades)}")
    tp_n = sum(1 for t in trades if t[8] == "tp_hit")
    sl_n = sum(1 for t in trades if t[8] == "sl_hit")
    print(f"  TP: {tp_n}   SL: {sl_n}   win_rate={tp_n/(tp_n+sl_n):.1%}")
    side_n = collections.Counter(t[1] for t in trades)
    print(f"  Side (0/1): {dict(side_n)}")
    syms = sorted(set(t[0] for t in trades))
    print(f"  simbolos distintos: {len(syms)}")
    profiles = collections.Counter(str(t[10]) for t in trades)
    print(f"  perfiles de estrategia distintos: {len(profiles)}")
    pnl = [float(t[9]) if t[9] is not None else 0.0 for t in trades]
    print(f"  PnL total={sum(pnl):.2f}  medio={np.mean(pnl):.2f}  mediana={np.median(pnl):.2f}\n")

    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    kdata = {}
    print("Cargando klines por simbolo (esto puede tardar)...")
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
    con.close()
    print(f"simbolos con cobertura de klines suficiente: {len(kdata)}/{len(syms)}\n")

    rows = []
    skipped_no_kline = 0; skipped_no_context = 0; skipped_no_mae = 0
    for (sym, side_raw, entry_px, close_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof) in trades:
        if sym not in kdata:
            skipped_no_kline += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None:
            skipped_no_kline += 1
            continue
        ctx = context_at(d, i)
        if ctx is None:
            skipped_no_context += 1
            continue
        side = 1 if side_raw == 0 else -1   # asumido: Side=0 LONG, 1 SHORT (consistente con conteos)
        ts_close = int(closed.timestamp() * 1000)
        mm = mae_mfe(d, i, ts_close, side, float(entry_px))
        if mm is None:
            skipped_no_mae += 1
            mfe, mae = np.nan, np.nan
        else:
            mfe, mae = mm
        rows.append(dict(symbol=sym, side=side, reason=reason, pnl=float(pnl_v) if pnl_v else 0.0,
                          profile=str(prof), mfe=mfe, mae=mae, **ctx))

    print(f"trades reconstruidos con contexto: {len(rows)}  (descartados: sin_kline={skipped_no_kline}, "
          f"sin_contexto={skipped_no_context}, sin_mae_mfe={skipped_no_mae})\n")

    tp_rows = [r for r in rows if r["reason"] == "tp_hit"]
    sl_rows = [r for r in rows if r["reason"] == "sl_hit"]
    print(f"con contexto reconstruido: TP={len(tp_rows)}  SL={len(sl_rows)}\n")

    print("#" * 70 + "\n FASE 3 — COMPARACION DE CONTEXTO PRE-ENTRADA: TP vs SL\n" + "#" * 70)
    feats_to_compare = ["ma7_slope", "price_vs_ma25", "price_vs_ma99", "atr_rel", "dist_hi20", "dist_lo20",
                         "up_count_10", "vol_pct", "rng_pct"]
    for f in feats_to_compare:
        tpv = np.array([r[f] for r in tp_rows if np.isfinite(r[f])])
        slv = np.array([r[f] for r in sl_rows if np.isfinite(r[f])])
        if len(tpv) < 20 or len(slv) < 20:
            continue
        print(f"  {f:16s}: TP mean={tpv.mean():+.5f} median={np.median(tpv):+.5f} (n={len(tpv)})  |  "
              f"SL mean={slv.mean():+.5f} median={np.median(slv):+.5f} (n={len(slv)})")

    for boolf in ("ma7_above_ma25", "ma7_above_ma99", "ma25_above_ma99"):
        tp_frac = np.mean([r[boolf] for r in tp_rows])
        sl_frac = np.mean([r[boolf] for r in sl_rows])
        print(f"  {boolf:16s}: TP frac={tp_frac:.2%}  SL frac={sl_frac:.2%}")

    print("\n" + "#" * 70 + "\n FASE 6 — MFE/MAE observados\n" + "#" * 70)
    for label, pop in (("TP", tp_rows), ("SL", sl_rows)):
        mfe_v = np.array([r["mfe"] for r in pop if np.isfinite(r["mfe"])])
        mae_v = np.array([r["mae"] for r in pop if np.isfinite(r["mae"])])
        if len(mfe_v) < 10:
            continue
        print(f"  {label}: MFE mean={mfe_v.mean():.1f}bp median={np.median(mfe_v):.1f}bp  "
              f"MAE mean={mae_v.mean():.1f}bp median={np.median(mae_v):.1f}bp  n={len(mfe_v)}")
    # trades que fueron SL pero tuvieron MFE grande antes de caer (¿el TP estaba mal puesto, o el SL muy ajustado?)
    sl_with_big_mfe = [r for r in sl_rows if np.isfinite(r["mfe"]) and r["mfe"] > 100]
    print(f"\n  Trades SL con MFE>100bp ANTES de terminar en SL (posible TP mal puesto o salida temprana perdida): "
          f"{len(sl_with_big_mfe)}/{len(sl_rows)} ({len(sl_with_big_mfe)/max(1,len(sl_rows)):.1%})")

    print("\n" + "#" * 70 + "\n FASE 5 — PRESENCIA DE LOS 3 SETUPS DEL USUARIO EN TRADES REALES\n" + "#" * 70)
    # Setup 1: MA7<MA25 y MA7<MA99, ma7_slope>0 (giro reciente) -- LONG
    s1 = [r for r in rows if r["side"] == 1 and r["ma7"] < r["ma25"] and r["ma7"] < r["ma99"] and r["ma7_slope"] > 0]
    s1_tp = sum(1 for r in s1 if r["reason"] == "tp_hit")
    print(f"  Setup 1 (MA7<MA25,MA99 + giro pendiente positiva, LONG): {len(s1)} trades reales coinciden, "
          f"TP={s1_tp} ({s1_tp/len(s1):.1%} win)" if s1 else "  Setup 1: 0 trades reales coinciden con el estado descrito")
    # Setup 2: MA7>MA99, MA7<MA25 -- LONG
    s2 = [r for r in rows if r["side"] == 1 and r["ma7"] > r["ma99"] and r["ma7"] < r["ma25"]]
    s2_tp = sum(1 for r in s2 if r["reason"] == "tp_hit")
    print(f"  Setup 2 (MA7>MA99, MA7<MA25, LONG): {len(s2)} trades reales coinciden, "
          f"TP={s2_tp} ({s2_tp/len(s2):.1%} win)" if s2 else "  Setup 2: 0 coincidencias")
    # Setup 3: MA7>MA25>MA99, ma7_slope<0 -- SHORT
    s3 = [r for r in rows if r["side"] == -1 and r["ma7"] > r["ma25"] > r["ma99"] and r["ma7_slope"] < 0]
    s3_tp = sum(1 for r in s3 if r["reason"] == "tp_hit")
    print(f"  Setup 3 (MA7>MA25>MA99 + pendiente MA7 negativa, SHORT): {len(s3)} trades reales coinciden, "
          f"TP={s3_tp} ({s3_tp/len(s3):.1%} win)" if s3 else "  Setup 3: 0 coincidencias")

    # guardar dataset completo para inspeccion posterior / ejemplos concretos
    out_path = os.path.join(HERE, "..", "..", "scratch_r35_forensic_dataset.json")
    with open(out_path, "w") as fo:
        json.dump(rows, fo, default=str)
    print(f"\nGuardado dataset completo en {out_path} ({len(rows)} trades) para extraer ejemplos concretos.")
    print("\nfin FASE 1-6 de R35")


if __name__ == "__main__":
    main()
