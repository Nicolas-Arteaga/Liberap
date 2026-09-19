"""
Backtest REAL de Order Block a traves del motor generico (engine.py), que
reusa risk_manager.py/verge_agent.py tal cual corren en produccion -- no
reimplementa nada de SL/TP/capital como el script suelto de ayer
(orderblock_backtest.py). Ver PROGRESS_LOG 2026-08-22.

Corre una pequenya grilla (interval x universo de simbolos) sobre TODO el
historial real disponible en klines_5m/klines_clean, imprime un ranking
ordenado por $/mes.
"""
import os
import sys
import sqlite3
import time

sys.path.insert(0, os.path.dirname(__file__))
from engine import BacktestEngine, DB_PATH, TOP_40_SYMBOLS  # noqa: E402


def real_days_available(conn) -> tuple:
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    row = cur.fetchone()
    return row[0], row[1]


def main():
    conn = sqlite3.connect(DB_PATH)
    start_ms, end_ms = real_days_available(conn)
    days = (end_ms - start_ms) / 86_400_000
    print(f"Rango real disponible: {days:.1f} dias")
    conn.close()

    engine = BacktestEngine(DB_PATH)
    symbols = engine.top40_symbols()
    print(f"Universo: {len(symbols)} simbolos (top-40 por capitalizacion)")

    base_profile = {
        "id": "ob-engine-test",
        "name": "Order Block Engine Test",
        "marginPerTrade": 150,
        "maxOpenPositions": 3,
        "minRR": 1.5,
        "maxTradeDurationCandles": 16,
        "allowLong": False,
        "allowShort": True,
    }

    grid = [
        {"label": "15m", "patternParamsJson": '{"timeframe": "15m"}'},
        {"label": "1h",  "patternParamsJson": '{"timeframe": "1h"}'},
    ]

    results = []
    for g in grid:
        profile = {**base_profile, "patternParamsJson": g["patternParamsJson"]}
        t0 = time.time()
        last_pct = [-1]

        def cb(done, total, _last=last_pct):
            pct = int(done / total * 100) if total else 0
            if pct != _last[0] and pct % 10 == 0:
                print(f"  [{g['label']}] {pct}% ({done}/{total})")
                _last[0] = pct

        res = engine.run_order_block(profile, symbols, start_ms, end_ms, progress_cb=cb)
        elapsed = time.time() - t0
        pnl = res["total_pnl_usdt"]
        n = res["accepted_trades"]
        wr = res["win_rate_pct"]
        monthly = res["monthly_breakdown"]
        n_months = max(1, len(monthly))
        pnl_per_month = pnl / n_months
        halves = list(monthly.items())
        half_ok = None
        if len(halves) >= 2:
            mid = len(halves) // 2
            h1 = sum(v["pnl"] for _, v in halves[:mid])
            h2 = sum(v["pnl"] for _, v in halves[mid:])
            weaker = min(abs(h1), abs(h2))
            stronger = max(abs(h1), abs(h2))
            half_ok = (h1 > 0 and h2 > 0) and (weaker >= 0.4 * stronger if stronger > 0 else False)
        results.append({
            "label": g["label"], "n": n, "wr": wr, "pnl": pnl,
            "pnl_month": pnl_per_month, "months": n_months, "stable": half_ok,
            "elapsed": elapsed,
        })
        print(f"[{g['label']}] n={n} WR={wr}% PnL total=${pnl:.2f} (~{n_months} meses) "
              f"${pnl_per_month:.2f}/mes stable_between_halves={half_ok} ({elapsed:.0f}s)")

    print("\n=== TOP RESULTADOS (motor real, risk_manager.py real) ===")
    results.sort(key=lambda r: r["pnl_month"], reverse=True)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['label']}: n={r['n']} WR={r['wr']}% ${r['pnl_month']:.2f}/mes "
              f"stable={r['stable']} (total ${r['pnl']:.2f} en {r['months']} meses)")


if __name__ == "__main__":
    main()
