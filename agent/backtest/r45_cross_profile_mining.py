"""
ROUND 45 -- MINERIA TRANSVERSAL DE LOS ~16 PERFILES.

Fuente: "SimulatedTrades" (Postgres), TODOS los perfiles, ExitReason en
(tp_hit, sl_hit) -- el nombre del perfil NO se usa para nada mas que
reportar de donde salio cada trade despues de encontrar un patron. Se
excluyen ONUSDT/BBUSDT (corrupcion de precio ya documentada, R37/R43).

Los trades son en su enorme mayoria "reconstructed" (incidente Docker,
ver R44) -- se usan igual para DESCUBRIMIENTO segun instruccion explicita
de R45, dejando marcada la limitacion de validacion.

Contexto pre-entrada reconstruido 100% causal desde klines_clean (15m) +
oi_metrics + funding_hist de binance_vision_clean.db, igual metodologia
que R35 (indice de barra = ultima barra CERRADA antes de OpenedAt).
"""
import os, sys, math, json, sqlite3, collections, itertools
import numpy as np
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
EXCLUDE_SYMS = {"ONUSDT", "BBUSDT"}


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""
        SELECT t."Symbol", t."Side", t."EntryPrice", t."ClosePrice", t."SlPrice", t."TpPrice",
               t."OpenedAt", t."ClosedAt", t."ExitReason", t."RealizedPnl", t."StrategyProfileId",
               p."Name", t."Margin"
        FROM "SimulatedTrades" t
        LEFT JOIN "StrategyProfiles" p ON p."Id" = t."StrategyProfileId"
        WHERE t."ExitReason" IN ('tp_hit','sl_hit') AND t."Status" IN (1,2)
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < 200:
        return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float); v = np.array([r[5] for r in k], float)
    return dict(t=t, o=o, h=h, l=l, c=c, v=v)


def load_oi(con, symbol):
    rows = con.execute("SELECT open_time,sum_oi,toptrader_ls_pos,global_ls_acct,taker_ls_vol "
                        "FROM oi_metrics WHERE symbol=? ORDER BY open_time", (symbol,)).fetchall()
    if len(rows) < 50:
        return None
    return dict(t=np.array([r[0] for r in rows], np.int64),
                oi=np.array([r[1] for r in rows], float),
                tl=np.array([r[2] if r[2] is not None else np.nan for r in rows], float),
                gl=np.array([r[3] if r[3] is not None else np.nan for r in rows], float),
                tk=np.array([r[4] if r[4] is not None else np.nan for r in rows], float))


def load_funding(con, symbol):
    rows = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (symbol,)).fetchall()
    if len(rows) < 5:
        return None
    return dict(t=np.array([r[0] for r in rows], np.int64), r=np.array([r[1] for r in rows], float))


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def last_value_before(d, ts_ms, key):
    idx = np.searchsorted(d["t"], ts_ms, side="right") - 1
    if idx < 0:
        return np.nan
    return d[key][idx]


def context_at(d, i, oi=None, fh=None, ts_ms=None):
    c, h, l, o, v = d["c"], d["h"], d["l"], d["o"], d["v"]
    if i < 105:
        return None
    def ret(n):
        return (c[i] - c[i - n]) / c[i - n] if i >= n and c[i - n] != 0 else np.nan
    ma7 = np.mean(c[i - 6:i + 1]); ma25 = np.mean(c[i - 24:i + 1])
    ma50 = np.mean(c[i - 49:i + 1]); ma99 = np.mean(c[i - 98:i + 1])
    ma7_prev3 = np.mean(c[i - 9:i - 2]) if i >= 9 else np.nan
    ma25_prev3 = np.mean(c[i - 27:i - 20]) if i >= 27 else np.nan
    ma7_slope = (ma7 - ma7_prev3) / c[i]
    ma25_slope = (ma25 - ma25_prev3) / c[i]
    prevc = c[i - 1] if i >= 1 else c[i]
    trs = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(max(1, i - 13), i + 1)]
    atr14 = np.mean(trs) if trs else np.nan
    hi5 = h[max(0, i - 5):i + 1].max(); lo5 = l[max(0, i - 5):i + 1].min()
    hi10 = h[max(0, i - 10):i + 1].max(); lo10 = l[max(0, i - 10):i + 1].min()
    hi20 = h[max(0, i - 20):i + 1].max(); lo20 = l[max(0, i - 20):i + 1].min()
    hi50 = h[max(0, i - 50):i + 1].max(); lo50 = l[max(0, i - 50):i + 1].min()
    vol30 = v[max(0, i - 500):i + 1]
    vol_pct = float((vol30 < v[i]).mean()) if len(vol30) > 50 else np.nan
    body = abs(c[i] - o[i]); rng = max(h[i] - l[i], 1e-12)
    upper_wick = h[i] - max(c[i], o[i]); lower_wick = min(c[i], o[i]) - l[i]
    gains = [max(c[j] - c[j - 1], 0) for j in range(max(1, i - 13), i + 1)]
    losses = [max(c[j - 1] - c[j], 0) for j in range(max(1, i - 13), i + 1)]
    avg_g = np.mean(gains) if gains else np.nan; avg_l = np.mean(losses) if losses else np.nan
    rsi14 = 100 - 100 / (1 + avg_g / avg_l) if avg_l and avg_l > 0 else (100.0 if avg_g and avg_g > 0 else 50.0)

    feats = dict(
        ret_1=ret(1), ret_3=ret(3), ret_5=ret(5), ret_10=ret(10), ret_20=ret(20),
        ma7_slope=ma7_slope, ma25_slope=ma25_slope,
        ma7_above_ma25=float(ma7 > ma25), ma7_above_ma99=float(ma7 > ma99), ma25_above_ma99=float(ma25 > ma99),
        price_vs_ma7=(c[i] - ma7) / c[i], price_vs_ma25=(c[i] - ma25) / c[i],
        price_vs_ma50=(c[i] - ma50) / c[i], price_vs_ma99=(c[i] - ma99) / c[i],
        atr_rel=atr14 / c[i] if c[i] > 0 else np.nan,
        dist_hi5=(c[i] - hi5) / c[i], dist_lo5=(c[i] - lo5) / c[i],
        dist_hi10=(c[i] - hi10) / c[i], dist_lo10=(c[i] - lo10) / c[i],
        dist_hi20=(c[i] - hi20) / c[i], dist_lo20=(c[i] - lo20) / c[i],
        dist_hi50=(c[i] - hi50) / c[i], dist_lo50=(c[i] - lo50) / c[i],
        vol_rel=v[i] / (np.mean(v[max(0, i - 20):i]) + 1e-9), vol_pct=vol_pct,
        body_ratio=body / rng, upper_wick_ratio=upper_wick / rng, lower_wick_ratio=lower_wick / rng,
        rsi14=rsi14, close=c[i],
    )
    if oi is not None and ts_ms is not None:
        oi_now = last_value_before(oi, ts_ms, "oi")
        idx_oi = np.searchsorted(oi["t"], ts_ms, side="right") - 1
        oi_chg = np.nan
        if idx_oi is not None and idx_oi >= 4 and np.isfinite(oi_now) and oi["oi"][idx_oi - 4] not in (0, np.nan):
            oi_chg = (oi_now - oi["oi"][idx_oi - 4]) / oi["oi"][idx_oi - 4] if oi["oi"][idx_oi - 4] else np.nan
        feats["oi_chg_1h"] = oi_chg
        feats["toptrader_ls"] = last_value_before(oi, ts_ms, "tl")
        feats["global_ls"] = last_value_before(oi, ts_ms, "gl")
    else:
        feats["oi_chg_1h"] = np.nan; feats["toptrader_ls"] = np.nan; feats["global_ls"] = np.nan
    if fh is not None and ts_ms is not None:
        feats["funding"] = last_value_before(fh, ts_ms, "r")
    else:
        feats["funding"] = np.nan
    return feats


def main():
    print("=== ROUND 45 -- MINERIA TRANSVERSAL DE LOS PERFILES (todos, sin distincion) ===\n")
    trades = load_trades()
    trades = [t for t in trades if t[0] not in EXCLUDE_SYMS]
    print(f"Trades limpios (excl ON/BB, tp_hit+sl_hit, todos los perfiles): {len(trades)}")
    syms = sorted(set(t[0] for t in trades))
    print(f"Simbolos distintos: {len(syms)}")

    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    kdata, oidata, fhdata = {}, {}, {}
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
        oi = load_oi(con, s)
        if oi is not None:
            oidata[s] = oi
        fh = load_funding(con, s)
        if fh is not None:
            fhdata[s] = fh
    con.close()
    print(f"Simbolos con klines: {len(kdata)}/{len(syms)}  |  con OI: {len(oidata)}  |  con funding: {len(fhdata)}\n")

    rows = []
    skipped = 0
    for (sym, side_raw, entry_px, close_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof_id, prof_name, margin) in trades:
        if sym not in kdata:
            skipped += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None:
            skipped += 1
            continue
        ctx = context_at(d, i, oidata.get(sym), fhdata.get(sym), ts_open)
        if ctx is None:
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        rows.append(dict(symbol=sym, side=side, reason=reason, win=(reason == "tp_hit"),
                          pnl=float(pnl_v) if pnl_v else 0.0, profile=str(prof_name),
                          margin=float(margin) if margin else 150.0,
                          ts=ts_open, opened=opened, closed=closed,
                          entry_px=float(entry_px), close_px=float(close_px) if close_px else None,
                          **ctx))
    print(f"Trades con contexto reconstruido: {len(rows)}  (descartados por falta de cobertura: {skipped})\n")

    win_n = sum(1 for r in rows if r["win"])
    print(f"Win rate global (base rate): {win_n}/{len(rows)} = {win_n/len(rows):.1%}\n")

    out_path = os.path.join(HERE, "..", "..", "scratch_r45_dataset.json")
    with open(out_path, "w") as fo:
        json.dump(rows, fo, default=str)
    print(f"Dataset guardado: {out_path} ({len(rows)} filas)\n")
    return rows


if __name__ == "__main__":
    main()
