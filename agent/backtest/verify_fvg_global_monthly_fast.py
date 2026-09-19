"""
2026-08-16: version RAPIDA del test anterior (verify_fvg_global_monthly.py,
matado tras 6 horas sin terminar -- error de diseño, escanear 426 simbolos
en CADA uno de los ~70.000 ticks de 5min era inviable). Esta version:

1. Restringe a TOP_40_SYMBOLS (los mas liquidos, los que en la practica
   dominan el top-5 real de todos modos -- el propio analyzer ordena por
   tp_distance_pct, y los majors/liquidos son los que mas aparecen en
   produccion real segun los logs de agent_audit).
2. Imprime progreso cada 2000 ticks para tener ETA real, no a ciegas.
"""
import sys
import os
import json
import sqlite3
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import BacktestEngine, DB_PATH, TOP_40_SYMBOLS  # noqa: E402

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
    print(f"Señales totales: {result['total_signals']} | Aceptadas (3 cupos x $150): {result['accepted_trades']} | Rechazadas por cupo: {result['rejected_no_slot']}")
    print(f"WR: {result['win_rate_pct']}% | PnL total: ${result['total_pnl_usdt']:.2f}")
    print(f"{'Mes':10s} {'Trades':>8s} {'WR%':>7s} {'PnL':>12s}")
    for month, m in result["monthly_breakdown"].items():
        print(f"{month:10s} {m['trades']:8d} {m['win_rate_pct']:6.1f}% {m['pnl']:11.2f}")


def main():
    t_script_start = time.time()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    conn.close()

    engine = BacktestEngine(DB_PATH)
    symbols = engine.available_symbols()
    print(f"Periodo: {datetime.utcfromtimestamp(t0/1000)} -> {datetime.utcfromtimestamp(t1/1000)} UTC ({(t1-t0)/(1000*60*60*24):.0f} dias)")
    print(f"Simbolos: universo COMPLETO ({len(symbols)}) | scan_step_ticks=3 (escanea candidatos nuevos cada 15min, TP/SL sigue fiel cada 5min)")

    CKPT_DIR = os.path.dirname(__file__)

    def make_progress(label, t_phase_start):
        def progress(done, total):
            pct = done / total * 100 if total else 0
            elapsed = time.time() - t_phase_start  # solo esta fase, sin arrastrar warmup/fase anterior
            eta = (elapsed / done * (total - done)) if done else 0
            print(f"  [{label}] progreso: {done}/{total} ({pct:.1f}%) | elapsed_fase={elapsed/60:.1f}min | ETA={eta/60:.1f}min", flush=True)
        return progress

    t_phase1 = time.time()
    result_sin_tope = engine.run_fvg_global(
        FVG_15M_PROFILE, symbols, t0, t1,
        progress_cb=make_progress("SIN TOPE", t_phase1),
        scan_step_ticks=3,
        checkpoint_path=os.path.join(CKPT_DIR, "fvg_global_checkpoint_sin_tope.json"),
    )
    print_result("FVG - 15m | universo completo | SIN TOPE", result_sin_tope)

    from risk_manager import RiskManager
    orig = RiskManager._calculate_position_nexus_style
    RiskManager._calculate_position_nexus_style = make_capped_wrapper(orig)
    try:
        engine2 = BacktestEngine(DB_PATH)
        t_phase2 = time.time()
        result_con_tope = engine2.run_fvg_global(
            FVG_15M_PROFILE, symbols, t0, t1,
            progress_cb=make_progress("TOPE -$5", t_phase2),
            scan_step_ticks=3,
            checkpoint_path=os.path.join(CKPT_DIR, "fvg_global_checkpoint_con_tope.json"),
        )
    finally:
        RiskManager._calculate_position_nexus_style = orig

    print_result("FVG - 15m | universo completo | TOPE FIJO -$5", result_con_tope)
    print(f"\nTiempo total: {(time.time()-t_script_start)/60:.1f} min")


if __name__ == "__main__":
    main()
