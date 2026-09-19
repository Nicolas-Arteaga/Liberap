"""
2026-08-19: pedido directo del usuario -- correr el backtest EXACTO de los
ultimos 6 dias reales (12-18 ago) para las 2 estrategias Level Sweep con
los parametros REALES de produccion (StrategyProfiles.PatternParamsJson),
y comparar contra lo que paso en la cuenta real. Requirio primero
sincronizar klines_clean (solo tenia datos hasta el 31/jul).
"""
import sys
import os
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    backtest_strategy, evaluate, load_basket, strat_label, DB_PATH,
)

STRATS = [
    dict(entry_type="level_sweep", tf_min=15, side="SHORT", atr_sl_mult=3.0, rr_mult=3.0, lookback=20),
    dict(entry_type="level_sweep", tf_min=60, side="SHORT", atr_sl_mult=1.5, rr_mult=3.0, lookback=10),
]

WINDOW_DAYS = 6


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)

    cur = conn.cursor()
    cur.execute("SELECT MAX(open_time) FROM klines_clean WHERE interval='15m'")
    max_ts = cur.fetchone()[0]
    window_start = max_ts - WINDOW_DAYS * 86400000

    for strat in STRATS:
        label = strat_label(strat)
        trades_all = backtest_strategy(conn, basket, strat, apply_vetos=True, be_lock=False)
        trades_window = [t for t in trades_all if t["open_time"] >= window_start]

        # Re-aplicar el limite de 3 cupos SOLO dentro de la ventana (arranca
        # la semana con los 3 cupos libres, igual que si el perfil recien
        # se hubiera activado).
        from backtest.strategy_lab import _apply_capital_sim
        trades_window = _apply_capital_sim(trades_window)

        total = sum(t["pnl"] for t in trades_window)
        n = len(trades_window)
        wins = sum(1 for t in trades_window if t["pnl"] > 0)
        wr = (wins / n * 100) if n else 0.0

        print(f"\n=== {label} -- ultimos {WINDOW_DAYS} dias reales ===")
        print(f"Trades cerrados en la ventana: {n} | WR: {wr:.1f}% | PnL total: ${total:.2f}")
        for t in trades_window:
            print(f"   {t['symbol']}: ${t['pnl']:.2f}")


if __name__ == "__main__":
    main()
