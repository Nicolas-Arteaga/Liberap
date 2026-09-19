"""
2026-08-16: pedido del usuario -- FVG-15m real (motor FIEL a produccion,
run_fvg_global: reloj global + top-5 por tp_distance_pct, NO run_fvg
aislado por simbolo que ya sabiamos con fidelidad limitada) contra TODO el
periodo historico disponible, desglosado por mes, sin tope de SL y con
tope fijo -$5 (mismo patron que _capped_sl_tp_dist en verge_agent.py: el
TP nunca se toca, solo se acerca el SL si el $ de riesgo supera el tope).

El cap se aplica ANTES de que el motor decida el resultado de cada trade
(en el momento en que _calculate_position_nexus_style arma el sl_price,
antes del candle walk) -- no es post-hoc clipping sobre resultados ya
cerrados, evita el error de hindsight bias que ya se cometio una vez esta
sesion.
"""
import sys
import os
import json
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import BacktestEngine, DB_PATH  # noqa: E402

MAX_LOSS = 5.0

FVG_15M_PROFILE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d",
    "name": "FVG - 15m",
    "strategyType": "FVG",
    "allowLong": True,
    "allowShort": True,
    "marginPerTrade": 150.0,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 3,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 60,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
    "minConfluenceScore": 80,
}


def make_capped_wrapper(orig_fn):
    def wrapped(self, symbol, signal_data, balance, profile=None):
        risk = orig_fn(self, symbol, signal_data, balance, profile)
        if risk is None:
            return risk
        entry = risk["entry_price"]
        margin = risk["margin"]
        qty = margin / entry if entry > 0 else 0
        if qty <= 0:
            return risk
        side = risk["side"]
        sl_dist = abs(entry - risk["sl_price"])
        loss_full = qty * sl_dist
        if loss_full > MAX_LOSS:
            capped_dist = MAX_LOSS / qty
            risk["sl_price"] = round(entry + capped_dist, 8) if side == 1 else round(entry - capped_dist, 8)
        return risk
    return wrapped


def print_result(label, result):
    print(f"\n=== {label} ===")
    print(f"Señales totales: {result['total_signals']} | Aceptadas (respetando 3 cupos x $150): {result['accepted_trades']} | Rechazadas por cupo: {result['rejected_no_slot']}")
    print(f"WR: {result['win_rate_pct']}% | PnL total: ${result['total_pnl_usdt']:.2f}")
    print(f"{'Mes':10s} {'Trades':>8s} {'WR%':>7s} {'PnL':>12s}")
    for month, m in result["monthly_breakdown"].items():
        print(f"{month:10s} {m['trades']:8d} {m['win_rate_pct']:6.1f}% {m['pnl']:11.2f}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    conn.close()

    print(f"Periodo disponible: {datetime.utcfromtimestamp(t0/1000)} -> {datetime.utcfromtimestamp(t1/1000)} UTC "
          f"({(t1-t0)/(1000*60*60*24):.0f} dias)")

    engine = BacktestEngine(DB_PATH)
    symbols = engine.available_symbols()
    print(f"Simbolos disponibles: {len(symbols)}")

    # ── SIN TOPE ──
    result_sin_tope = engine.run_fvg_global(FVG_15M_PROFILE, symbols, t0, t1)
    print_result("FVG - 15m | SIN TOPE (motor fiel run_fvg_global)", result_sin_tope)

    # ── CON TOPE -$5 ── (monkeypatch temporal solo para esta corrida)
    from risk_manager import RiskManager
    orig = RiskManager._calculate_position_nexus_style
    RiskManager._calculate_position_nexus_style = make_capped_wrapper(orig)
    try:
        engine2 = BacktestEngine(DB_PATH)
        result_con_tope = engine2.run_fvg_global(FVG_15M_PROFILE, symbols, t0, t1)
    finally:
        RiskManager._calculate_position_nexus_style = orig

    print_result("FVG - 15m | TOPE FIJO -$5 (mismo motor, SL capado, TP intacto)", result_con_tope)


if __name__ == "__main__":
    main()
