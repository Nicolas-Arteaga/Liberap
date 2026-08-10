"""
A/B de MA Slope Caso 3 con las señales nuevas del epic market-data-expansion
(#156, secciones 1-3: OFI, funding, liquidaciones) -- tareas 1.7/2.6/3.6.

Corre 4 veces el mismo periodo historico (17/7 - 1/8, ventana con OFI
completo) sobre el motor generico real (backtest/engine.py, reusa
verge_agent.py/risk_manager.py sin reimplementar nada): baseline sin
filtros, y baseline + cada filtro nuevo por separado. Compara profit
factor / PnL / win rate contra el baseline -- los datos deciden si algun
filtro se agrega a produccion, no un hunch.

Uso: python -m backtest.ab_confluence_caso3   (desde agent/)
"""
import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine

PROFILE = {
    "id": "9e00e6f3-45f2-e32b-b353-679e6d19f29c",
    "name": "MA Slope Caso 3",
    "strategyType": "MaGeometry",
    "allowLong": False,
    "allowShort": True,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 3,
    "marginPerTrade": 150,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 192,
    "minConfluenceScore": 85,
    "minNexusConfidence": 50,
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

START_MS = int(datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)

SCENARIOS = {
    "baseline (sin filtros)": None,
    "+ OFI direccional": {"ofi_direction": {"enabled": True, "min_abs_ofi": 0.1}},
    "+ funding extremo": {"funding_extreme": {"enabled": True, "max_abs_funding_pct": 0.05}},
    "+ cascada liquidaciones": {"liquidation_cascade": {"enabled": True, "recent_minutes": 15,
                                                          "baseline_hours": 4, "threshold_multiplier": 3.0}},
}


def summarize(result: dict) -> dict:
    trades = result.get("trades", [])
    n = len(trades)
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    return {
        "trades": n,
        "win_rate_pct": round(100 * len(wins) / n, 1) if n else 0.0,
        "pnl_total": round(result.get("total_pnl_usdt", 0), 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else float("inf"),
        "total_signals": result.get("total_signals", 0),
    }


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"Simbolos disponibles: {len(symbols)} | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}")
    print("=" * 100)

    rows = []
    for label, filters in SCENARIOS.items():
        print(f"Corriendo: {label}...", flush=True)
        result = engine.run_ma_geometry(
            PROFILE, symbols, START_MS, END_MS,
            signal_filters=filters,
        )
        s = summarize(result)
        s["scenario"] = label
        rows.append(s)
        print(f"  -> trades={s['trades']} (de {s['total_signals']} señales) | WR={s['win_rate_pct']}% | "
              f"PnL=${s['pnl_total']} | PF={s['profit_factor']}")

    print("=" * 100)
    print(f"{'Escenario':30s} | {'señales':>8s} | {'trades':>7s} | {'WR%':>6s} | {'PnL':>10s} | {'PF':>6s}")
    baseline = rows[0]
    for r in rows:
        print(f"{r['scenario']:30s} | {r['total_signals']:8d} | {r['trades']:7d} | {r['win_rate_pct']:6.1f} | "
              f"{r['pnl_total']:10.2f} | {r['profit_factor']:6.3f}")
    print("=" * 100)
    print(f"Baseline: PnL=${baseline['pnl_total']} PF={baseline['profit_factor']}")
    for r in rows[1:]:
        delta_pnl = r["pnl_total"] - baseline["pnl_total"]
        delta_pf = (r["profit_factor"] - baseline["profit_factor"]) if isinstance(r["profit_factor"], float) and isinstance(baseline["profit_factor"], float) else None
        veredicto = "MEJORA" if delta_pnl > 0 and (delta_pf is None or delta_pf > 0) else ("empeora" if delta_pnl < 0 else "neutro")
        print(f"  {r['scenario']}: delta PnL=${delta_pnl:+.2f} | delta PF={delta_pf:+.3f} -> {veredicto}" if delta_pf is not None
              else f"  {r['scenario']}: delta PnL=${delta_pnl:+.2f} -> {veredicto}")


if __name__ == "__main__":
    main()
