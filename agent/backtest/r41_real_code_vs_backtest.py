"""
ROUND 41 — comparacion trade-por-trade: codigo REAL (TrailingStopCalculator.cs,
compilado y ejecutado via tools/TrailReplayHarness, salida en
tools/TrailReplayHarness/replay_real_code_output.csv) vs la version
corregida del backtest de R37/R39 (formula lineal, agent/backtest/
r37_trail1_validation.py ya corregido en R39).
"""
import os, sys, math, csv, numpy as np, sqlite3, collections
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
KC = os.path.join(HERE, "..", "data", "klines.db")
CSV_PATH = os.path.join(HERE, "..", "..", "tools", "TrailReplayHarness", "replay_real_code_output.csv")
CAP_BARS = 2880
FEE_PER_TRADE = 0.12
LEVELS = [(100, 0), (150, 50), (200, 100)]


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


def sim_backtest_corrected(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size):
    """Version corregida (R39, formula lineal) de simulate_rule para Trail-1."""
    sl_cur = sl0_px; trail_applied = set()
    n_bars = min(CAP_BARS, n - i_start)
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl_cur) if side > 0 else (hi >= sl_cur)
        if sl_hit:
            return side * (sl_cur - entry_px) * size - FEE_PER_TRADE, "sl", k
        tp_hit = (hi >= tp0_px) if side > 0 else (lo <= tp0_px)
        if tp_hit:
            return side * (tp0_px - entry_px) * size - FEE_PER_TRADE, "tp", k
        fav_px = hi if side > 0 else lo
        fav_bp = side * math.log(fav_px / entry_px) * 1e4
        for (thr, lock_bp) in LEVELS:
            if thr not in trail_applied and fav_bp >= thr:
                trail_applied.add(thr)
                new_sl_px = entry_px * (1 + side * lock_bp / 1e4)
                sl_cur = max(sl_cur, new_sl_px) if side > 0 else min(sl_cur, new_sl_px)
    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return side * (exit_px - entry_px) * size - FEE_PER_TRADE, "time", n_bars


def main():
    print("=== ROUND 41 — CODIGO REAL vs BACKTEST CORREGIDO, trade por trade ===\n")
    rows_real = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows_real.append(r)
    print(f"filas del harness (codigo real): {len(rows_real)}")

    kdata = {}
    syms = sorted(set(r["symbol"] for r in rows_real))
    for s in syms:
        d = load_symbol_klines(s)
        if d is not None:
            kdata[s] = d

    import datetime
    diffs = []
    total_real = 0.0; total_bt = 0.0; n_cmp = 0; identical = 0
    for r in rows_real:
        sym = r["symbol"]
        if sym not in kdata:
            continue
        d = kdata[sym]
        side_raw = int(r["side"]); side = 1 if side_raw == 0 else -1
        entry_px = float(r["entry"]); sl0 = float(r["sl0"]); tp0 = float(r["tp0"])
        opened = datetime.datetime.fromisoformat(r["opened"].replace("Z", "+00:00"))
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None or i < 20 or i + 5 >= len(d["c"]):
            continue
        size = 150.0 / entry_px   # Amount=150 fijo en todos los trades de esta poblacion (verificado R37/R39)
        pnl_bt, reason_bt, k_bt = sim_backtest_corrected(d["h"], d["l"], i + 1, len(d["c"]), side, entry_px, sl0, tp0, size)
        pnl_real = float(r["pnl"])
        total_real += pnl_real; total_bt += pnl_bt; n_cmp += 1
        d_diff = abs(pnl_real - pnl_bt)
        if d_diff < 0.001:
            identical += 1
        else:
            diffs.append(dict(symbol=sym, side=side, opened=opened, pnl_real=pnl_real, pnl_bt=pnl_bt,
                               diff=pnl_real - pnl_bt, reason_bt=reason_bt, k_bt=k_bt,
                               reason_real=r["exitReason"], k_real=int(r["exitBar"])))

    print(f"\ncomparados: {n_cmp}")
    print(f"identicos (diff<$0.001): {identical} ({identical/n_cmp:.1%})")
    print(f"distintos: {len(diffs)} ({len(diffs)/n_cmp:.1%})")
    print(f"\nPnL total codigo real: ${total_real:.2f}")
    print(f"PnL total backtest corregido: ${total_bt:.2f}")
    print(f"diferencia absoluta: ${total_real-total_bt:.2f}  ({(total_real-total_bt)/abs(total_bt)*100 if total_bt else 0:.2f}%)")

    diffs.sort(key=lambda x: -abs(x["diff"]))
    print(f"\ntop 15 discrepancias:")
    for r in diffs[:15]:
        print(f"  {r['symbol']:14s} side={r['side']:2d} pnl_real={r['pnl_real']:8.2f} pnl_bt={r['pnl_bt']:8.2f} "
              f"diff={r['diff']:7.2f}  real:{r['reason_real']}@{r['k_real']}  bt:{r['reason_bt']}@{r['k_bt']}")

    print("\nfin R41")


if __name__ == "__main__":
    main()
