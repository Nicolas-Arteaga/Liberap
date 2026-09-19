"""
2026-08-17: calibracion rapida pedida por el usuario -- MA Slope Caso 3
(1h, id real 9e00e6f3-45f2-e32b-b353-679e6d19f29c) corre por _run_generic
(walk independiente por simbolo, sin la competencia global tick-a-tick de
FVG) -- mucho mas rapido de backtestear. Real conocido: 74 trades,
+$64.78, desde 2026-07-10 hasta ahora (2026-08-17).
"""
import sys
import os
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import BacktestEngine, DB_PATH  # noqa: E402

PROFILE = {
    "id": "9e00e6f3-45f2-e32b-b353-679e6d19f29c",
    "name": "MA Slope Caso 3",
    "strategyType": "MaGeometry",
    "allowLong": False,
    "allowShort": True,
    "marginPerTrade": 150.0,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 3,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 192,
    "minConfluenceScore": 85,
    "maxRsiLong": 80,
    "minRsiShort": 20,
    "maxMa7DistancePct": 5,
    "patternParamsJson": json.dumps({
        "timeframe": "1h",
        "order": {"ma7VsMa25": "greater", "ma7VsMa50": "greater", "ma7VsMa99": "greater"},
        "slope": {"targetMa": "ma7", "windowCandles": 3, "currentOp": "lte", "currentDeg": -0.2,
                  "priorOp": "gte", "priorDeg": 0.2},
        "touch": {"enabled": False, "targetMa": "ma25", "tolerancePct": 0.3, "side": "fromBelow",
                  "requireCloseStaysOriginalSide": True},
        "distanceBetweenMas": {"enabled": False, "maA": "ma7", "maB": "ma99", "maxPct": 0.5},
        "contextSlope": {"enabled": False, "targetMa": "ma99", "windowCandles": 12, "op": "gte", "deg": -0.1},
        "peakProximity": {"enabled": True, "type": "recentHigh", "lookbackCandles": 10, "tolerancePct": 1},
        "exit": {"slReference": "recentHigh", "slLookbackCandles": 10, "slBufferPct": 1, "tpMinPct": 10},
    }),
}


def main():
    t_start = time.time()
    t0 = int(datetime(2026, 7, 10, tzinfo=timezone.utc).timestamp() * 1000)
    t1 = int(datetime(2026, 8, 17, tzinfo=timezone.utc).timestamp() * 1000)

    engine = BacktestEngine(DB_PATH)
    symbols = engine.available_symbols()
    print(f"Ventana: 2026-07-10 -> 2026-08-17 ({(t1-t0)/(1000*60*60*24):.0f} dias) | simbolos: {len(symbols)}")
    print("Comparar contra: 74 trades reales, +$64.78")

    def progress(done, total):
        print(f"  progreso: {done}/{total} simbolos | elapsed={((time.time()-t_start)/60):.1f}min", flush=True)

    result = engine.run_ma_geometry(PROFILE, symbols, t0, t1, progress_cb=progress)

    print(f"\n=== MA Slope Caso 3 | universo completo | con vetos reales ===")
    print(f"Señales: {result['total_signals']} | Aceptadas (3 cupos x $150): {result['accepted_trades']} | Rechazadas por cupo: {result['rejected_no_slot']}")
    print(f"WR: {result['win_rate_pct']}% | PnL total: ${result['total_pnl_usdt']:.2f}")
    print(f"\n>>> Comparar accepted_trades={result['accepted_trades']} (real=74) y total_pnl_usdt=${result['total_pnl_usdt']:.2f} (real=$64.78) <<<")
    print(f"\nTiempo total: {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
