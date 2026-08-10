import sys, os, logging, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.ERROR, handlers=[logging.FileHandler(os.path.join(os.path.dirname(__file__), "sanity_day1_global.log"), encoding="utf-8")])
from datetime import datetime, timezone
from backtest.engine import BacktestEngine

PROFILE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d", "name": "FVG - 15m", "strategyType": "FVG",
    "allowLong": True, "allowShort": True, "tpMultiplier": 3, "slMultiplier": 0.8, "minRR": 3,
    "marginPerTrade": 150, "maxOpenPositions": 3, "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80, "minNexusConfidence": 50,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
}
START_MS = int(datetime(2026, 7, 12, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 7, 13, tzinfo=timezone.utc).timestamp() * 1000)

def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"{len(symbols)} simbolos", flush=True)

    def progress(done, total):
        print(f"  progreso: {done}/{total}", flush=True)

    result = engine.run_fvg_global(PROFILE, symbols, START_MS, END_MS, progress_cb=progress)
    print(f"señales={result['total_signals']} trades={result['accepted_trades']} rechazados_sin_cupo={result['rejected_no_slot']} PnL=${result['total_pnl_usdt']}")
    for t in sorted(result["trades"], key=lambda x: x["open_time"]):
        print(f"  {t['symbol']:15s} side={t['side']} open={datetime.fromtimestamp(t['open_time']/1000,tz=timezone.utc)} pnl=${t['pnl']:.2f}")

if __name__ == "__main__":
    main()
