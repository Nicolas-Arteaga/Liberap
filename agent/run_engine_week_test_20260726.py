import sys, json, time
sys.path.insert(0, '.')
from backtest.engine import BacktestEngine
from datetime import datetime, timezone

t0 = time.time()
engine = BacktestEngine()
symbols = engine.available_symbols()
print('simbolos disponibles:', len(symbols), flush=True)

profile = {
    'id': '9e00e6f3-45f2-e32b-b353-679e6d19f29c',
    'name': 'MA Slope Caso 3',
    'allowLong': False, 'allowShort': True,
    'patternParamsJson': json.dumps({
        "timeframe": "1h",
        "order": {"ma7VsMa25": "greater", "ma7VsMa50": "greater", "ma7VsMa99": "greater"},
        "slope": {"targetMa": "ma7", "windowCandles": 3, "currentOp": "lte", "currentDeg": -0.2, "priorOp": "gte", "priorDeg": 0.2},
        "touch": {"enabled": False},
        "distanceBetweenMas": {"enabled": False},
        "contextSlope": {"enabled": False},
        "peakProximity": {"enabled": True, "type": "recentHigh", "lookbackCandles": 10, "tolerancePct": 1.0},
        "exit": {"slReference": "recentHigh", "slLookbackCandles": 10, "slBufferPct": 1.0, "tpMinPct": 10.0}
    }),
    'tpMultiplier': 3.0, 'slMultiplier': 0.8, 'minRR': 4.0,
    'marginPerTrade': 150.0, 'maxOpenPositions': 3, 'maxTradeDurationCandles': 192,
}

start_ms = int(datetime(2026,7,11,0,0,tzinfo=timezone.utc).timestamp()*1000)
end_ms = int(datetime(2026,7,18,3,0,tzinfo=timezone.utc).timestamp()*1000)

def prog(done, total):
    if done % 50 == 0 or done == total:
        elapsed = time.time()-t0
        print(f'  {done}/{total} simbolos, {elapsed:.0f}s transcurridos', flush=True)

result = engine.run_ma_geometry(profile, symbols, start_ms, end_ms, progress_cb=prog)
print()
print("=== SEÑALES GENERADAS (total_signals, antes de filtro de cupo) ===")
print("total_signals:", result['total_signals'])
print("accepted_trades:", result['accepted_trades'])
for t in sorted(result['trades'], key=lambda x: x['open_time']):
    from datetime import datetime as dt
    local = dt.utcfromtimestamp(t['open_time']/1000)
    print(f"  {t['symbol']:12s} side={t['side']} open_utc={local}")

with open('week_test_result_20260726.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, default=str, ensure_ascii=False)
