import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python-service"))
from backtest.strategy_lab import load_basket, DB_PATH, evaluate  # noqa: E402
from backtest.orderblock_backtest import backtest_orderblock  # noqa: E402

conn = sqlite3.connect(DB_PATH)
basket = load_basket(conn)
cur = conn.cursor()
cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
t0, t1 = cur.fetchone()
days = (t1 - t0) / (1000 * 60 * 60 * 24)

print("=== BOTH sides, CON filtro POC/HVN ===")
trades = backtest_orderblock(conn, basket, apply_vetos=True, use_liquidity_tp=True, side_filter=None, apply_poc_filter=True)
res = evaluate(trades, days)
print(f"n={res.get('n')} WR={res.get('wr_pct')}% $/mes={res.get('monthly')} "
      f"h1={res.get('pnl_h1')} h2={res.get('pnl_h2')} stable={res.get('stable_between_halves')}")
