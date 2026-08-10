"""
Backtest FIEL (run_fvg_global -- competencia real cross-symbol con corte
top-5 por ciclo, igual que produccion) sobre TOP_40_SYMBOLS (canasta fija,
liquida, no depende del watchlist dinamico -- evita el problema de no
poder reconstruir el watchlist historico dia por dia). Corre el original
como baseline y una bateria de variantes de filtro, todas por el MISMO
motor y el MISMO universo, buscando una que le gane de verdad al original.
No toca perfiles de produccion ni el agente en vivo -- 100% offline.

Uso: python -m backtest.find_winning_fvg_variant   (desde agent/)
"""
import sys
import os
import logging
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_FILE = os.path.join(os.path.dirname(__file__), "find_winning_fvg_variant.log")
logging.basicConfig(level=logging.ERROR, handlers=[logging.FileHandler(_LOG_FILE, encoding="utf-8")])

from datetime import datetime, timezone
from backtest.engine import BacktestEngine, TOP_40_SYMBOLS

BASE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d",
    "strategyType": "FVG",
    "allowLong": True, "allowShort": True,
    "tpMultiplier": 3, "slMultiplier": 0.8, "minRR": 3,
    "marginPerTrade": 150, "maxOpenPositions": 3, "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80, "minNexusConfidence": 50,
}

def profile(name, extra_params=None):
    p = dict(BASE)
    p["name"] = name
    params = {"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}
    if extra_params:
        params.update(extra_params)
    p["patternParamsJson"] = json.dumps(params)
    return p

VARIANTS = [
    ("original (baseline)", {}),
    ("v2 gap2.5+tp25+ushape9", {"maxGapPct": 2.5, "maxTpDistancePct": 25, "maxUShapeCount": 9}),
    ("solo maxUShapeCount<9", {"maxUShapeCount": 9}),
    ("solo maxTpDistancePct<25", {"maxTpDistancePct": 25}),
    ("solo maxGapPct<2.5", {"maxGapPct": 2.5}),
    ("ushape<9 + tp<25 (sin gap)", {"maxUShapeCount": 9, "maxTpDistancePct": 25}),
    ("ushape<7 (mas estricto)", {"maxUShapeCount": 7}),
    ("ushape<9 + gap<1.5", {"maxUShapeCount": 9, "maxGapPct": 1.5}),
    ("requireExhaustion (short only edge conocido)", {"requireExhaustion": True}),
    ("ushape<9 + requireExhaustion", {"maxUShapeCount": 9, "requireExhaustion": True}),
]

START_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 9, tzinfo=timezone.utc).timestamp() * 1000)


def main():
    engine = BacktestEngine()
    symbols = TOP_40_SYMBOLS
    total_days = (END_MS - START_MS) / (1000 * 60 * 60 * 24)
    print(f"TOP_40_SYMBOLS ({len(symbols)}) | {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()} ({total_days:.0f} dias)", flush=True)

    results = []
    for name, extra in VARIANTS:
        p = profile(name, extra)
        print(f"\n{'='*100}\n{name}\n{'='*100}", flush=True)

        def progress(done, total, _name=name):
            if done % 2000 == 0 or done == total:
                print(f"  [{_name}] progreso: {done}/{total}", flush=True)

        r = engine.run_fvg_global(p, symbols, START_MS, END_MS, progress_cb=progress)
        pnl_mes = r['total_pnl_usdt'] / (total_days / 30.44)
        print(f"trades={r['accepted_trades']} WR={r['win_rate_pct']}% PnL=${r['total_pnl_usdt']} (${pnl_mes:.2f}/mes)", flush=True)
        results.append((name, r['accepted_trades'], r['win_rate_pct'], r['total_pnl_usdt'], pnl_mes))

    print(f"\n\n{'='*100}\nRESUMEN FINAL (motor fiel, mismo universo TOP_40, mismo periodo)\n{'='*100}")
    print(f"{'Variante':45s} {'trades':>7s} {'WR':>7s} {'PnL':>10s} {'PnL/mes':>9s}")
    baseline_pnl = results[0][3]
    for name, trades, wr, pnl, pnl_mes in results:
        marca = "  <== GANA AL ORIGINAL" if (name != results[0][0] and pnl > baseline_pnl) else ""
        print(f"{name:45s} {trades:7d} {wr:6.1f}% ${pnl:8.2f} ${pnl_mes:7.2f}{marca}")


if __name__ == "__main__":
    main()
