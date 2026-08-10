"""
Sanity check: el backtest de 8 meses/426 simbolos dio -$478.45 para
"FVG - 15m" original, pero sabemos por datos REALES de produccion que en
la ventana 12/7-4/8/2026 ese mismo perfil gano +$149.67 (268 trades). Si
el motor no puede reproducir ese numero conocido en esa ventana chica, el
backtest tiene un problema de fidelidad (como el que ya se encontro y
arreglo para MA Slope Caso 3 el 26/7) y no sirve para comparar variantes
hasta que se arregle.

Uso: python -m backtest.sanity_check_fvg_original   (desde agent/)
"""
import sys
import os
import logging
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_FILE = os.path.join(os.path.dirname(__file__), "sanity_check_fvg.log")
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

# Ventana REAL conocida: 268 trades reales, +$149.67, 12/7 -> 4/8/2026
START_MS = int(datetime(2026, 7, 12, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 4, 8, tzinfo=timezone.utc).timestamp() * 1000)


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"REAL conocido: 268 trades, +$149.67 (12/7 -> 4/8)", flush=True)
    print(f"Backtest: {len(symbols)} simbolos | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}", flush=True)

    def progress(done, total):
        if done % 50 == 0 or done == total:
            print(f"  progreso: {done}/{total}", flush=True)

    result = engine.run_parallel("FVG", ORIGINAL, symbols, START_MS, END_MS, progress_cb=progress, max_workers=2)
    print(f"señales={result['total_signals']} | trades aceptados={result['accepted_trades']} | "
          f"rechazados sin cupo={result['rejected_no_slot']} | WR={result['win_rate_pct']}% | "
          f"PnL TOTAL=${result['total_pnl_usdt']}", flush=True)
    print(f"\nComparacion: REAL=+$149.67 (268 trades) vs BACKTEST=${result['total_pnl_usdt']} ({result['accepted_trades']} trades)")


if __name__ == "__main__":
    main()
