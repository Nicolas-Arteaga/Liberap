import sys, json, time
sys.path.insert(0, '.')
from backtest.engine import BacktestEngine
from datetime import datetime

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

start_ms = int(datetime(2025,12,1).timestamp()*1000)
end_ms = int(datetime(2026,7,26).timestamp()*1000)

def prog(done, total):
    if done % 10 == 0 or done == total:
        elapsed = time.time()-t0
        print(f'  {done}/{total} simbolos, {elapsed:.0f}s transcurridos', flush=True)

result = engine.run_ma_geometry(profile, symbols, start_ms, end_ms, progress_cb=prog)
out = {k:v for k,v in result.items() if k!='trades'}
print(json.dumps(out, indent=2, ensure_ascii=False), flush=True)
with open('ma_slope_case3_ENGINE_v6_zombie_20260726.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, default=str, ensure_ascii=False)
print('Guardado: ma_slope_case3_ENGINE_v6_zombie_20260726.json', flush=True)
