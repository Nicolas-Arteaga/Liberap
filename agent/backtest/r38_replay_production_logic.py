"""
ROUND 38, FASE 5 — REPLAY: reimplementa en Python la MISMA logica exacta
de `TrailingStopCalculator.Compute` (C#, src/Verge.Domain/Trading/
TrailingStopCalculator.cs) -- salto directo al nivel mas alto alcanzado,
monotonico, nunca empeora el SL -- y la corre sobre la misma poblacion de
2,985 trades de R37, para comparar contra el baseline/Trail-1 de R37.
"""
import os, sys, math, numpy as np, sqlite3, collections
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
KC = os.path.join(HERE, "..", "data", "klines.db")
CAP_BARS = 2880
FEE_PER_TRADE = 0.12
LEVELS = [(100, 0), (150, 50), (200, 100)]   # (thresholdBp, lockBp) -- igual que TrailingStopCalculator.Levels


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","SlPrice","TpPrice",
                   "OpenedAt","Amount" FROM "SimulatedTrades"
                   WHERE "ExitReason" IN ('tp_hit','sl_hit') AND "Symbol" NOT IN ('ONUSDT','BBUSDT')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(sym):
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    k = con.execute("SELECT open_time,open,high,low,close FROM klines_clean WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
    con.close()
    if len(k) < 3000:
        con2 = sqlite3.connect(f"file:{KC}?mode=ro", uri=True)
        k = con2.execute("SELECT open_time,open,high,low,close FROM klines WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        con2.close()
        if len(k) < 500:
            return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    return dict(t=t, o=o, h=h, l=l, c=c)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def trailing_stop_calculator_compute(is_long, entry_price, favorable_excursion_bp, current_sl, current_level):
    """Traduccion 1:1 de TrailingStopCalculator.Compute (C#)."""
    for lvl in range(len(LEVELS), 0, -1):
        threshold_bp, lock_bp = LEVELS[lvl - 1]
        if favorable_excursion_bp < threshold_bp or lvl <= current_level:
            continue
        candidate_sl = entry_price * (1 + lock_bp / 1e4) if is_long else entry_price * (1 - lock_bp / 1e4)
        improves = candidate_sl > current_sl if is_long else candidate_sl < current_sl
        return (candidate_sl if improves else current_sl), lvl, improves
    return current_sl, current_level, False


def simulate_production_logic(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size):
    """Replica EXACTA del orden del worker de produccion:
    1) chequear SL actual (adverso) primero
    2) chequear TP
    3) actualizar MaxFavorablePrice (ratchet) y llamar a TrailingStopCalculator
    en ese orden, tick a tick (acá: barra a barra, 15m)."""
    sl_cur = sl0_px
    max_fav = entry_px
    trail_level = 0
    is_long = side > 0
    n_bars = min(CAP_BARS, n - i_start)
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl_cur) if is_long else (hi >= sl_cur)
        if sl_hit:
            return side * (sl_cur - entry_px) * size - FEE_PER_TRADE
        tp_hit = (hi >= tp0_px) if is_long else (lo <= tp0_px)
        if tp_hit:
            return side * (tp0_px - entry_px) * size - FEE_PER_TRADE
        fav_px = hi if is_long else lo
        max_fav = max(max_fav, fav_px) if is_long else min(max_fav, fav_px)
        fav_bp = (max_fav - entry_px) / entry_px * 1e4 if is_long else (entry_px - max_fav) / entry_px * 1e4
        sl_cur, trail_level, _ = trailing_stop_calculator_compute(is_long, entry_px, fav_bp, sl_cur, trail_level)
    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return side * (exit_px - entry_px) * size - FEE_PER_TRADE


def main():
    print("=== ROUND 38 — REPLAY DE LA LOGICA REAL DE PRODUCCION (TrailingStopCalculator) ===\n")
    trades = load_trades()
    syms = sorted(set(t[0] for t in trades))
    kdata = {}
    for s in syms:
        d = load_symbol_klines(s)
        if d is not None:
            kdata[s] = d
    print(f"simbolos con cobertura: {len(kdata)}/{len(syms)}")

    total_pnl = 0.0; n_sim = 0; skipped = 0
    for (sym, side_raw, entry_px, sl_px, tp_px, opened, amount) in trades:
        if sym not in kdata or sl_px is None or tp_px is None:
            skipped += 1
            continue
        d = kdata[sym]
        i = find_bar_index(d["t"], int(opened.timestamp() * 1000))
        if i is None or i < 20 or i + 5 >= len(d["c"]):
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        entry_px = float(entry_px); sl_px = float(sl_px); tp_px = float(tp_px)
        size = float(amount) / entry_px
        pnl = simulate_production_logic(d["h"], d["l"], i + 1, len(d["c"]), side, entry_px, sl_px, tp_px, size)
        total_pnl += pnl
        n_sim += 1

    print(f"\ntrades replicados con TrailingStopCalculator real: {n_sim} (descartados: {skipped})")
    print(f"PnL total (replay del codigo de produccion, Trail-1): ${total_pnl:.1f}")
    print("\nComparar contra R37 Trail-1 (misma poblacion, 2,985 trades): "
          "TRAIN -$185.2 + VAL +$353.8 + OOS +$199.2 = $367.8 total")
    print("\nfin R38 replay")


if __name__ == "__main__":
    main()
