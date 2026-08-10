"""
Comparacion REAL (no retroactiva) entre "FVG - 15m" original y
"FVG - 15m v2 (filtros minados)" -- ambas corridas de CERO a traves del
motor real (backtest/engine.py::run_fvg, que reusa risk_manager.py real),
mismo periodo completo, mismos simbolos, cada una con sus propios 3 cupos
de capital (igual que en produccion, son perfiles distintos).

Esto reemplaza la validacion anterior (retroactiva sobre trades ya
cerrados), que tenia un problema real: al borrar trades que no pasaban el
filtro, no dejaba que OTROS candidatos (rechazados antes por falta de
cupo) ocuparan esos cupos liberados -- subestimaba o distorsionaba el
resultado real. Esta corrida deja que el motor recalcule los candidatos y
la asignacion de cupos desde cero con el filtro puesto desde el dia 1.

Uso: python -m backtest.run_fvg_v2_vs_original_real   (desde agent/)
"""
import sys
import os
import logging
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_FILE = os.path.join(os.path.dirname(__file__), "fvg_v2_vs_original.log")
logging.basicConfig(level=logging.ERROR, handlers=[logging.FileHandler(_LOG_FILE, encoding="utf-8")])

from datetime import datetime, timezone
from backtest.engine import BacktestEngine

ORIGINAL = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d",
    "name": "FVG - 15m (original)",
    "strategyType": "FVG",
    "allowLong": True, "allowShort": True,
    "tpMultiplier": 3, "slMultiplier": 0.8, "minRR": 3,
    "marginPerTrade": 150, "maxOpenPositions": 3, "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80, "minNexusConfidence": 50,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
}

V2 = {
    "id": "9371a472-236b-46d7-a9be-9fcce683b29e",
    "name": "FVG - 15m v2 (filtros minados)",
    "strategyType": "FVG",
    "allowLong": True, "allowShort": True,
    "tpMultiplier": 3, "slMultiplier": 0.8, "minRR": 3,
    "marginPerTrade": 150, "maxOpenPositions": 3, "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80, "minNexusConfidence": 50,
    "patternParamsJson": json.dumps({
        "timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3,
        "maxGapPct": 2.5, "maxTpDistancePct": 25, "maxUShapeCount": 9,
    }),
}

START_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 9, tzinfo=timezone.utc).timestamp() * 1000)


def run_one(engine, profile, symbols):
    print(f"\n{'='*100}\n{profile['name']}\n{'='*100}", flush=True)

    def progress(done, total):
        if done % 50 == 0 or done == total:
            print(f"  progreso: {done}/{total}", flush=True)

    result = engine.run_parallel("FVG", profile, symbols, START_MS, END_MS, progress_cb=progress, max_workers=2)
    print(f"señales={result['total_signals']} | trades aceptados={result['accepted_trades']} | "
          f"rechazados sin cupo={result['rejected_no_slot']} | WR={result['win_rate_pct']}% | "
          f"PnL TOTAL=${result['total_pnl_usdt']}", flush=True)
    return result


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    total_days = (END_MS - START_MS) / (1000 * 60 * 60 * 24)
    print(f"{len(symbols)} simbolos | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()} ({total_days:.0f} dias)", flush=True)

    r_orig = run_one(engine, ORIGINAL, symbols)
    r_v2 = run_one(engine, V2, symbols)

    print(f"\n{'='*100}\nCOMPARACION FINAL (motor real, mismo periodo, mismos simbolos)\n{'='*100}")
    print(f"{'Perfil':35s} {'trades':>8s} {'WR':>7s} {'PnL':>12s} {'PnL/mes':>10s}")
    for label, r in (("FVG - 15m (original)", r_orig), ("FVG - 15m v2 (filtros minados)", r_v2)):
        pnl_mes = r['total_pnl_usdt'] / (total_days / 30.44)
        print(f"{label:35s} {r['accepted_trades']:8d} {r['win_rate_pct']:6.1f}% ${r['total_pnl_usdt']:10.2f} ${pnl_mes:8.2f}")


if __name__ == "__main__":
    main()
