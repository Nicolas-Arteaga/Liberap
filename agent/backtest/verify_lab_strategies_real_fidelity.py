"""
2026-08-17: re-test de las 4 estrategias del laboratorio activas en
produccion (Level Sweep 15m SL3/RR3, Level Sweep 1H, Level Sweep 60m
SL2/RR1.5, Band Touch 15m) con las DOS piezas de fidelidad que
strategy_lab.py nunca tuvo:

1. LIMITE REAL DE 3 CUPOS -- backtest_strategy() dejaba correr TODOS los
   simbolos que calificaban en simultaneo, como si hubiera capital
   infinito. Produccion real solo permite 3 posiciones de $150 a la vez
   POR ESTRATEGIA (MaxOpenPositions=3, config.py MAX_OPEN_POSITIONS).
   Mismo algoritmo greedy que _capital_sim en engine.py.

2. VETOS REALES -- validate_pre_trade() (setup_validator.py) nunca se
   llamaba. Band Touch/Level Sweep mandan "nexus15": {} vacio (igual que
   produccion real, confirmado en verge_agent.py), asi que la mayoria de
   los vetos de RSI/MA7/volumen son no-op para estas -- el que SI importa
   es stop_loss_too_expensive (usa el SL real, no depende de nexus15).

Corre cada estrategia en 2 variantes (CON vetos / SIN vetos) para ver cual
es mejor en la practica, no asumir.
"""
import sys
import os
import json
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, detect_signal, atr_series, resample, load_15m, DB_PATH, MARGIN, FEE,
)
from setup_validator import validate_pre_trade  # noqa: E402

DAYS = 243  # periodo cubierto por la DB historica (dic 2025 - jul 2026)
SLOTS = 3

CONFIGS = [
    ("Level Sweep 1H", "level_sweep", dict(tf_min=60, atr_sl_mult=2.0, rr_mult=2.0, lookback=10), "level_sweep_1h_mode"),
    ("Level Sweep 60m SL2 RR1.5", "level_sweep", dict(tf_min=60, atr_sl_mult=2.0, rr_mult=1.5, lookback=10), "level_sweep_1h_mode"),
    ("Level Sweep 15m SL3 RR3", "level_sweep", dict(tf_min=15, atr_sl_mult=3.0, rr_mult=3.0, lookback=20), "level_sweep_1h_mode"),
    ("Band Touch 15m", "band_touch", dict(tf_min=15, atr_sl_mult=3.0, rr_mult=3.0), "band_touch_mode"),
]


def build_candidate(symbol, side, entry, mode_flag):
    """Candidato con la MISMA forma que arma verge_agent.py para estas
    estrategias (_run_level_sweep_1h_scan / _run_band_touch_scan) --
    nexus15 vacio, mode flag real, price_at_signal."""
    return {
        "symbol": symbol,
        "confluence_score": 80.0,
        "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG",
        "side": side,
        "source": f"{mode_flag}:lab",
        mode_flag: True,
        "price_at_signal": entry,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def backtest_with_vetos(conn, basket, strat, mode_flag, apply_vetos):
    all_trades = []
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        candles = resample(rows, strat["tf_min"]) if strat["tf_min"] != 15 else rows
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        volumes = [c[5] for c in candles]
        atr = atr_series(candles, 14)
        lb = strat.get("lookback", 20)
        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
            if a is None or a <= 0:
                continue
            if open_trade:
                side = open_trade["side"]
                hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
                hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = MARGIN / open_trade["entry"]
                    gross = qty * (open_trade["entry"] - close_px) if side == 1 else qty * (close_px - open_trade["entry"])
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({
                        "symbol": symbol, "pnl": gross - fees,
                        "open_time": open_trade["open_time"], "close_time": ts,
                    })
                    open_trade = None
                continue

            level_high = max(highs[i - lb:i]) if i >= lb else None
            level_low = min(lows[i - lb:i]) if i >= lb else None
            sig = detect_signal(strat, closes, highs, lows, i, level_high, level_low, volumes)
            if sig is None:
                continue
            if strat.get("side") == "LONG" and sig != 0:
                continue
            if strat.get("side", "SHORT") == "SHORT" and sig != 1:
                continue

            entry = c
            sl_dist = strat["atr_sl_mult"] * a
            tp_dist = sl_dist * strat["rr_mult"]
            if sig == 0:
                sl, tp = entry - sl_dist, entry + tp_dist
            else:
                sl, tp = entry + sl_dist, entry - tp_dist

            if apply_vetos:
                candidate = build_candidate(symbol, sig, entry, mode_flag)
                try:
                    v_ok, _v_code, _ = validate_pre_trade(candidate, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True  # fail-open si algo del veto no puede evaluarse offline
                if not v_ok:
                    continue

            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}
    return all_trades


def apply_capital_sim(trades, slots=SLOTS, margin=MARGIN):
    """Mismo algoritmo greedy que _capital_sim en engine.py -- limite real
    de cupos simultaneos, nunca aplicado antes en el laboratorio."""
    trades = sorted(trades, key=lambda t: (t["open_time"], t["symbol"]))
    open_slots, accepted, rejected = [], [], 0
    for t in trades:
        open_slots = [ct for ct in open_slots if ct > t["open_time"]]
        if len(open_slots) >= slots:
            rejected += 1
            continue
        open_slots.append(t["close_time"])
        accepted.append(t)
    return accepted, rejected


def report(label, trades, rejected, days=DAYS):
    n = len(trades)
    if n == 0:
        print(f"  {label}: sin trades (0 aceptados, {rejected} rechazados por cupo)")
        return
    total = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    monthly = total / (days / 30.44)
    print(f"  {label:24s} n={n:5d} (rechazados x cupo={rejected:5d}) WR={wins/n*100:5.1f}% PnL=${total:9.2f} (${monthly:8.2f}/mes)")


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | periodo: {DAYS} dias | limite real: {SLOTS} cupos x $150")

    for name, entry_type, params, mode_flag in CONFIGS:
        strat = {"entry_type": entry_type, "side": "SHORT", **params}
        print(f"\n=== {name} ===")
        t0 = time.time()

        raw_sin_veto = backtest_with_vetos(conn, basket, strat, mode_flag, apply_vetos=False)
        accepted_sin, rej_sin = apply_capital_sim(raw_sin_veto)
        report("SIN vetos, CON limite 3 cupos", accepted_sin, rej_sin)

        raw_con_veto = backtest_with_vetos(conn, basket, strat, mode_flag, apply_vetos=True)
        accepted_con, rej_con = apply_capital_sim(raw_con_veto)
        report("CON vetos, CON limite 3 cupos", accepted_con, rej_con)

        print(f"  (tiempo: {time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
