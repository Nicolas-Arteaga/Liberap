"""
2026-08-17: chequeo de CALIBRACION pedido por el usuario -- antes de seguir
gastando horas en el periodo completo (8 meses), correr solo la ventana
12/jul - 12/ago 2026 (universo completo, SIN TOPE -- igual que produccion
real, sin el cap de SL que no corrio en real) y comparar contra el
resultado REAL conocido: ~$150 generados por FVG-15m en esa ventana segun
el usuario. Si el backtest da algo parecido, el motor (`run_fvg_global`)
es confiable y vale la pena correr el periodo completo. Si no, el motor
tiene algun problema de fidelidad que hay que resolver antes de confiar en
cualquier numero mas grande.
"""
import sys
import os
import json
import sqlite3
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import BacktestEngine, DB_PATH  # noqa: E402

FVG_15M_PROFILE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d",
    "name": "FVG - 15m",
    "strategyType": "FVG",
    "allowLong": True,
    "allowShort": True,
    "marginPerTrade": 150.0,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 3,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 60,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
    "minConfluenceScore": 80,
}


def print_result(label, result):
    print(f"\n=== {label} ===")
    print(f"Señales totales: {result['total_signals']} | Aceptadas (3 cupos x $150): {result['accepted_trades']} | Rechazadas por cupo: {result['rejected_no_slot']}")
    print(f"WR: {result['win_rate_pct']}% | PnL total: ${result['total_pnl_usdt']:.2f}")
    print(f"{'Mes':10s} {'Trades':>8s} {'WR%':>7s} {'PnL':>12s}")
    for month, m in result["monthly_breakdown"].items():
        print(f"{month:10s} {m['trades']:8d} {m['win_rate_pct']:6.1f}% {m['pnl']:11.2f}")


def main():
    t_script_start = time.time()
    t0 = int(datetime(2026, 7, 12, tzinfo=timezone.utc).timestamp() * 1000)
    t1 = int(datetime(2026, 8, 12, tzinfo=timezone.utc).timestamp() * 1000)

    engine = BacktestEngine(DB_PATH)
    symbols = engine.available_symbols()
    print(f"Ventana de calibracion: 2026-07-12 -> 2026-08-12 ({(t1-t0)/(1000*60*60*24):.0f} dias)")
    print(f"Simbolos: universo COMPLETO ({len(symbols)})")
    print(f"Comparar contra: ~$150 reales generados por FVG-15m en produccion en esta misma ventana")

    def progress(done, total):
        pct = done / total * 100 if total else 0
        elapsed = time.time() - t_script_start
        eta = (elapsed / done * (total - done)) if done else 0
        print(f"  progreso: {done}/{total} ({pct:.1f}%) | elapsed={elapsed/60:.1f}min | ETA={eta/60:.1f}min", flush=True)

    result = engine.run_fvg_global(
        FVG_15M_PROFILE, symbols, t0, t1,
        progress_cb=progress,
        scan_step_ticks=3,
        checkpoint_path=os.path.join(os.path.dirname(__file__), "fvg_calibration_checkpoint.json"),
    )
    print_result("FVG - 15m | 12/jul-12/ago | SIN TOPE | universo completo", result)
    print(f"\nTiempo total: {(time.time()-t_script_start)/60:.1f} min")
    print(f"\n>>> Comparar total_pnl_usdt=${result['total_pnl_usdt']:.2f} contra los ~$150 reales <<<")


if __name__ == "__main__":
    main()
