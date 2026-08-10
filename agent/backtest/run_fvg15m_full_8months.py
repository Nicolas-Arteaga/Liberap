"""
FVG - 15m (perfil REAL de produccion, el que ya acumulo ~$90 en ~20 dias
en vivo) corrido sobre los 8 meses completos de historia (dic2025-jul2026)
y TODOS los simbolos de futuros disponibles, con el motor real
(engine.run_parallel, que aplica _capital_sim UNA sola vez sobre el
conjunto combinado -- 3 cupos compartidos de verdad, no por simbolo).

Uso: python -m backtest.run_fvg15m_full_8months   (desde agent/)
"""
import sys
import os
import logging
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine

PROFILE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d",
    "name": "FVG - 15m",
    "strategyType": "FVG",
    "allowLong": True,
    "allowShort": True,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 3,
    "marginPerTrade": 150,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80,
    "minNexusConfidence": 50,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
}

START_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 7, 31, tzinfo=timezone.utc).timestamp() * 1000)


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"FVG - 15m | {len(symbols)} simbolos | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()} (8 meses)", flush=True)

    def progress(done, total):
        if done % 50 == 0 or done == total:
            print(f"  progreso: {done}/{total}", flush=True)

    result = engine.run_parallel("FVG", PROFILE, symbols, START_MS, END_MS, progress_cb=progress, max_workers=4)

    print("=" * 100)
    print(f"señales={result['total_signals']} | trades aceptados={result['accepted_trades']} | "
          f"rechazados sin cupo={result['rejected_no_slot']} | WR={result['win_rate_pct']}% | "
          f"PnL TOTAL=${result['total_pnl_usdt']}")
    total_days = (END_MS - START_MS) / (1000 * 60 * 60 * 24)
    print(f"Periodo: {total_days:.0f} dias | trades/dia promedio: {result['accepted_trades']/total_days:.2f}")
    print(f"PnL por mes: ${result['total_pnl_usdt']/(total_days/30.44):.2f}")


if __name__ == "__main__":
    main()
