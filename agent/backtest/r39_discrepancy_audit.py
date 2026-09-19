"""
ROUND 39 — AUDITORIA DE LA DISCREPANCIA R37 vs R38 ($367.8 vs $377.0).

Corre AMBOS algoritmos (R37 "simulate_rule" generico y R38 "Trail-
ingStopCalculator" real) sobre EXACTAMENTE la misma lista de trades
(una sola query, un solo set de klines cargado una vez), trade por
trade, y reporta las diferencias. Nada de "puede ser" -- se identifica
la causa exacta por cada trade discrepante.
"""
import os, sys, math, numpy as np, sqlite3, collections
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
KC = os.path.join(HERE, "..", "data", "klines.db")
CAP_BARS = 2880
FEE_PER_TRADE = 0.12
CORRUPT_SYMBOLS = {"ONUSDT", "BBUSDT"}


def load_trades(exclude_corrupt):
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    q = """SELECT "Symbol","Side","EntryPrice","SlPrice","TpPrice","OpenedAt","Amount"
           FROM "SimulatedTrades" WHERE "ExitReason" IN ('tp_hit','sl_hit')"""
    if exclude_corrupt:
        q += " AND \"Symbol\" NOT IN ('ONUSDT','BBUSDT')"
    cur.execute(q)
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


LEVELS = [(100, 0), (150, 50), (200, 100)]


def sim_r37_style(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size):
    """Replica EXACTA de r37_trail1_validation.simulate_rule para rule=Trail-1
    (steps=[(100,0),(150,50),(200,100)]) -- fav_bp = extremo de la barra
    actual (no ratchet explicito), aplica cada threshold pendiente vía
    max/min, set de aplicados."""
    sl_cur = sl0_px; tp_cur = tp0_px; trail_applied = set()
    n_bars = min(CAP_BARS, n - i_start)
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl_cur) if side > 0 else (hi >= sl_cur)
        if sl_hit:
            return side * (sl_cur - entry_px) * size - FEE_PER_TRADE, "sl", k
        tp_hit = (hi >= tp_cur) if side > 0 else (lo <= tp_cur)
        if tp_hit and tp_cur is not None:
            return side * (tp_cur - entry_px) * size - FEE_PER_TRADE, "tp", k
        fav_px = hi if side > 0 else lo
        fav_bp = side * math.log(fav_px / entry_px) * 1e4
        for (thr, lock_bp) in LEVELS:
            if thr not in trail_applied and fav_bp >= thr:
                trail_applied.add(thr)
                new_sl_px = entry_px * math.exp(side * lock_bp / 1e4)
                sl_cur = max(sl_cur, new_sl_px) if side > 0 else min(sl_cur, new_sl_px)
    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return side * (exit_px - entry_px) * size - FEE_PER_TRADE, "time", n_bars


def trailing_stop_calculator_compute(is_long, entry_price, favorable_excursion_bp, current_sl, current_level):
    for lvl in range(len(LEVELS), 0, -1):
        threshold_bp, lock_bp = LEVELS[lvl - 1]
        if favorable_excursion_bp < threshold_bp or lvl <= current_level:
            continue
        candidate_sl = entry_price * (1 + lock_bp / 1e4) if is_long else entry_price * (1 - lock_bp / 1e4)
        improves = candidate_sl > current_sl if is_long else candidate_sl < current_sl
        return (candidate_sl if improves else current_sl), lvl, improves
    return current_sl, current_level, False


def sim_r38_style(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size):
    """Replica EXACTA de TrailingStopCalculator.Compute -- fav_bp desde un
    ratchet explicito de max_fav (equivalente a MaxFavorablePrice real),
    salto directo al nivel mas alto por llamada."""
    sl_cur = sl0_px; max_fav = entry_px; trail_level = 0
    is_long = side > 0
    n_bars = min(CAP_BARS, n - i_start)
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl_cur) if is_long else (hi >= sl_cur)
        if sl_hit:
            return side * (sl_cur - entry_px) * size - FEE_PER_TRADE, "sl", k
        tp_hit = (hi >= tp0_px) if is_long else (lo <= tp0_px)
        if tp_hit:
            return side * (tp0_px - entry_px) * size - FEE_PER_TRADE, "tp", k
        fav_px = hi if is_long else lo
        max_fav = max(max_fav, fav_px) if is_long else min(max_fav, fav_px)
        fav_bp = (max_fav - entry_px) / entry_px * 1e4 if is_long else (entry_px - max_fav) / entry_px * 1e4
        sl_cur, trail_level, _ = trailing_stop_calculator_compute(is_long, entry_px, fav_bp, sl_cur, trail_level)
    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return side * (exit_px - entry_px) * size - FEE_PER_TRADE, "time", n_bars


def main():
    print("=== ROUND 39 — AUDITORIA DE LA DISCREPANCIA R37 vs R38 ===\n")

    # PASO 0: verificar si R37 incluia o no ON/BB (primera sospecha concreta a descartar)
    trades_incl = load_trades(exclude_corrupt=False)
    trades_excl = load_trades(exclude_corrupt=True)
    print(f"PASO 0 — pool total tp/sl CON corruptos (ON/BB): {len(trades_incl)}")
    print(f"         pool total tp/sl SIN corruptos (ON/BB): {len(trades_excl)}")
    print(f"         diferencia: {len(trades_incl) - len(trades_excl)} trades (deberia ser 12: ONUSDT x10, BBUSDT x2)\n")

    # Usamos el pool SIN corruptos (correcto, documentado en R37/R38) para el resto del audit,
    # pero cargado con UNA sola query/UNA sola carga de klines para los dos algoritmos.
    trades = trades_excl
    syms = sorted(set(t[0] for t in trades))
    kdata = {}
    for s in syms:
        d = load_symbol_klines(s)
        if d is not None:
            kdata[s] = d
    print(f"PASO 0b — simbolos con cobertura: {len(kdata)}/{len(syms)}\n")

    rows = []
    skipped = 0
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
        n = len(d["c"]); h, l = d["h"], d["l"]
        pnl37, reason37, k37 = sim_r37_style(h, l, i + 1, n, side, entry_px, sl_px, tp_px, size)
        pnl38, reason38, k38 = sim_r38_style(h, l, i + 1, n, side, entry_px, sl_px, tp_px, size)
        rows.append(dict(symbol=sym, side=side, opened=opened, pnl37=pnl37, pnl38=pnl38,
                          diff=pnl38 - pnl37, reason37=reason37, reason38=reason38, k37=k37, k38=k38))

    print(f"PASO 1 — trades comparados (mismo pool, misma carga de klines): {len(rows)}  (descartados: {skipped})")
    total37 = sum(r["pnl37"] for r in rows); total38 = sum(r["pnl38"] for r in rows)
    print(f"  PnL total estilo-R37: ${total37:.2f}   PnL total estilo-R38: ${total38:.2f}   diff=${total38-total37:.2f}\n")

    diffs = [r for r in rows if abs(r["diff"]) > 0.001]
    print(f"trades con diferencia >$0.001 entre los dos algoritmos: {len(diffs)} de {len(rows)}\n")

    diffs.sort(key=lambda r: -abs(r["diff"]))
    print("#" * 100)
    print(f"{'symbol':14s} {'side':4s} {'opened':20s} {'pnl37':>9s} {'pnl38':>9s} {'diff':>8s} {'reason37':>9s} {'reason38':>9s} {'k37':>5s} {'k38':>5s}")
    print("#" * 100)
    for r in diffs[:20]:
        print(f"{r['symbol']:14s} {r['side']:4d} {str(r['opened']):20s} {r['pnl37']:9.2f} {r['pnl38']:9.2f} "
              f"{r['diff']:8.2f} {r['reason37']:>9s} {r['reason38']:>9s} {r['k37']:5d} {r['k38']:5d}")

    # PASO 2: clasificar causa
    same_exit_reason = sum(1 for r in diffs if r["reason37"] == r["reason38"])
    diff_exit_reason = sum(1 for r in diffs if r["reason37"] != r["reason38"])
    same_k = sum(1 for r in diffs if r["k37"] == r["k38"])
    print(f"\nPASO 2 — clasificacion de los {len(diffs)} trades discrepantes:")
    print(f"  mismo motivo de salida (tp/sl/time) en ambos: {same_exit_reason}")
    print(f"  DISTINTO motivo de salida entre R37 y R38: {diff_exit_reason}")
    print(f"  mismo indice de barra de salida (k): {same_k}")

    print("\nfin PASO 1-2 de R39 -- ver informe para PASO 3 (caso critico misma vela) y veredicto")


if __name__ == "__main__":
    main()
