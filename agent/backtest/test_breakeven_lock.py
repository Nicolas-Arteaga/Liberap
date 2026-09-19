"""
2026-08-18: valida candle-a-candle (NO post-hoc) el lock a breakeven antes de
reactivarlo en produccion -- corregido tras el error de haberlo desplegado
sin backtestear primero. Corre las mejores estrategias ya conocidas del
barrido de anoche CON y SIN el lock, mismo motor honesto (vetos reales +
3 cupos x $150), y compara $/mes.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import backtest_strategy, evaluate, load_basket, strat_label, DB_PATH  # noqa: E402

BEST_STRATS = [
    dict(entry_type="rsi_extreme", tf_min=60, side="LONG", atr_sl_mult=3.0, rr_mult=6.0,
         rsi_thresh=[75, 25], lookback=10),
    dict(entry_type="ma_pullback", tf_min=15, side="LONG", atr_sl_mult=3.0, rr_mult=6.0,
         lookback=10, slope_min_pct=1.0),
    dict(entry_type="ma_cross", tf_min=60, side="LONG", atr_sl_mult=3.0, rr_mult=2.0,
         ma_pair=[9, 21], lookback=10),
    dict(entry_type="level_sweep", tf_min=60, side="SHORT", atr_sl_mult=3.0, rr_mult=3.0,
         lookback=20),
    dict(entry_type="band_touch", tf_min=15, side="SHORT", atr_sl_mult=2.0, rr_mult=3.0,
         lookback=10),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days_covered = (t1 - t0) / (1000 * 60 * 60 * 24) if t0 and t1 else 240

    print(f"{'Estrategia':<45} {'sin lock':>12} {'con lock':>12} {'diff':>10}")
    print("-" * 82)
    for strat in BEST_STRATS:
        label = strat_label(strat)
        try:
            trades_off = backtest_strategy(conn, basket, strat, apply_vetos=True, be_lock=False)
            res_off = evaluate(trades_off, days_covered)
            trades_on = backtest_strategy(conn, basket, strat, apply_vetos=True, be_lock=True)
            res_on = evaluate(trades_on, days_covered)
        except Exception as e:
            print(f"{label:<45} ERROR: {e}")
            continue

        m_off = res_off.get("monthly", 0) or 0
        m_on = res_on.get("monthly", 0) or 0
        diff = m_on - m_off
        print(f"{label:<45} {m_off:>11.2f} {m_on:>11.2f} {diff:>+9.2f}")
        print(f"   n_off={res_off.get('n')} wr_off={res_off.get('wr_pct')}%  |  "
              f"n_on={res_on.get('n')} wr_on={res_on.get('wr_pct')}%")


if __name__ == "__main__":
    main()
