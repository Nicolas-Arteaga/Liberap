"""
2026-08-17: corrida del PERIODO COMPLETO (8 meses) de MA Slope Caso 3, con
el motor ya calibrado (validate_pre_trade real + MaxTradeDurationCandles
corregido a 192). Desglose mensual para ver si aparece la decadencia que
el usuario recuerda (empieza fuerte, se apaga con el tiempo) -- mismo
patron ya documentado para este caso en sesiones anteriores.
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
    t0 = 1764547200000  # 2025-12-01, inicio real de la DB
    t1 = 1785541500000  # 2026-07-31, fin real de la DB

    engine = BacktestEngine(DB_PATH)
    symbols = engine.available_symbols()
    print(f"Periodo COMPLETO: {datetime.utcfromtimestamp(t0/1000)} -> {datetime.utcfromtimestamp(t1/1000)} "
          f"({(t1-t0)/(1000*60*60*24):.0f} dias) | simbolos: {len(symbols)}")

    def progress(done, total):
        if done % 20 == 0 or done == total:
            print(f"  progreso: {done}/{total} simbolos | elapsed={((time.time()-t_start)/60):.1f}min", flush=True)

    result = engine.run_ma_geometry(PROFILE, symbols, t0, t1, progress_cb=progress)

    print(f"\n=== MA Slope Caso 3 | PERIODO COMPLETO (8 meses) | universo completo | con vetos reales ===")
    print(f"Señales: {result['total_signals']} | Aceptadas (3 cupos x $150): {result['accepted_trades']} | Rechazadas por cupo: {result['rejected_no_slot']}")
    print(f"WR: {result['win_rate_pct']}% | PnL total: ${result['total_pnl_usdt']:.2f}")
    print(f"\nDesglose mensual:")
    print(f"{'Mes':10s} {'Trades':>8s} {'WR%':>7s} {'PnL':>12s}")
    for month, m in result["monthly_breakdown"].items():
        print(f"{month:10s} {m['trades']:8d} {m['win_rate_pct']:6.1f}% {m['pnl']:11.2f}")
    print(f"\nTiempo total: {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
