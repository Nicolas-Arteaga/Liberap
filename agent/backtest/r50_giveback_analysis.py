"""
ROUND 50 -- correccion al analisis anterior: el usuario pregunta por
REVERSION DESDE EL PICO (cuantos trades llegaron a +$30/+40/+50 flotante
y despues se dieron vuelta), no por "estancamiento" (que fue lo que medi
mal en R49). Recorre la trayectoria real bar-a-bar y compara el maximo
flotante alcanzado vs el resultado final real (RealizedPnl de la base).
"""
import os, sys, sqlite3, collections
import numpy as np
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CAP_BARS = 2880


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","SlPrice","TpPrice",
                   "OpenedAt","ClosedAt","ExitReason","RealizedPnl","StrategyProfileId","Amount"
                   FROM "SimulatedTrades"
                   WHERE "ExitReason" IN ('tp_hit','sl_hit') AND "Symbol" NOT IN ('ONUSDT','BBUSDT')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < 500:
        return None
    t = np.array([r[0] for r in k], np.int64)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float)
    return dict(t=t, h=h, l=l, c=c)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def walk_path(h, l, i_start, n, side, entry_px, sl0_px, size):
    """Camina barra a barra hasta que el trade REAL cierra (SL o TP,
    reproducidos aqui igual que R36/R49) y devuelve el maximo flotante
    USD alcanzado durante el camino."""
    n_bars = min(CAP_BARS, n - i_start)
    max_fav_usd = 0.0
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        fav_px = hi if side > 0 else lo
        fav_usd = side * (fav_px - entry_px) * size
        if fav_usd > max_fav_usd:
            max_fav_usd = fav_usd
        sl_hit = (lo <= sl0_px) if side > 0 else (hi >= sl0_px)
        if sl_hit:
            return max_fav_usd, k
    return max_fav_usd, n_bars


def main():
    trades = load_trades()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    syms = sorted(set(t[0] for t in trades))
    kdata = {}
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
    con.close()
    print(f"trades tp/sl (excl ON/BB): {len(trades)}  simbolos con klines: {len(kdata)}/{len(syms)}\n")

    recs = []
    skipped = 0
    for (sym, side_raw, entry_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof, amount) in trades:
        if sym not in kdata or sl_px is None or amount is None:
            skipped += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None or i + 3 >= len(d["c"]):
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        entry_px = float(entry_px); sl_px = float(sl_px)
        size = float(amount) / entry_px
        real_pnl = float(pnl_v) if pnl_v else 0.0
        max_fav_usd, bars = walk_path(d["h"], d["l"], i + 1, len(d["c"]), side, entry_px, sl_px, size)
        recs.append(dict(symbol=sym, side=side, opened=opened, closed=closed, profile=str(prof),
                          reason=reason, real_pnl=real_pnl, max_fav_usd=max_fav_usd))
    print(f"trades procesados: {len(recs)}  (descartados: {skipped})\n")

    for thr in (20, 30, 40, 50):
        pop = [r for r in recs if r["max_fav_usd"] >= thr]
        gave_back_to_loss = [r for r in pop if r["real_pnl"] <= 0]
        gave_back_partial = [r for r in pop if 0 < r["real_pnl"] < r["max_fav_usd"] * 0.5]
        kept_most = [r for r in pop if r["real_pnl"] >= r["max_fav_usd"] * 0.5]
        print(f"=== Trades que llegaron a >= ${thr} flotante: {len(pop)} ===")
        print(f"  Terminaron en PERDIDA (dieron vuelta TOTAL, real_pnl<=0): {len(gave_back_to_loss)} "
              f"({len(gave_back_to_loss)/max(1,len(pop)):.1%})  -- PnL real total de estos: "
              f"${sum(r['real_pnl'] for r in gave_back_to_loss):.1f}")
        print(f"  Terminaron ganando pero se dejaron >50% del pico (giveback parcial): {len(gave_back_partial)} "
              f"({len(gave_back_partial)/max(1,len(pop)):.1%})")
        print(f"  Se quedaron con >=50% del pico: {len(kept_most)} ({len(kept_most)/max(1,len(pop)):.1%})")
        dinero_perdido_vs_pico = sum(r["max_fav_usd"] - r["real_pnl"] for r in pop)
        print(f"  DINERO TOTAL dejado sobre la mesa (pico - resultado real, sumado): ${dinero_perdido_vs_pico:.1f}\n")

    # el caso mas extremo: gano mucho de pico y termino en SL total
    print("=== EJEMPLOS: picos >= $30 que terminaron en SL (perdida total) ===")
    extreme = sorted([r for r in recs if r["max_fav_usd"] >= 30 and r["reason"] == "sl_hit"],
                      key=lambda r: -r["max_fav_usd"])[:15]
    for r in extreme:
        print(f"  {r['symbol']:14s} {r['opened']}  pico=+${r['max_fav_usd']:7.1f}  "
              f"resultado_real=${r['real_pnl']:7.1f}  perfil={r['profile'][:8]}")


if __name__ == "__main__":
    main()
