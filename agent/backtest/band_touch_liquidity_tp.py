"""
2026-08-21: mismo experimento que level_sweep_liquidity_tp.py pero aplicado
a Band Touch (toque de banda de Bollinger + reversion) -- mismo concepto
de fondo ("rebote desde un nivel"), TP calculado como nivel de liquidez
real (estilo FVG) en vez de ATR x RR fijo. Usa la config ya encontrada
estable en Level Sweep (disprop=1.2, haircut=0.9, lb_impulse=40) como punto
de partida, no un barrido desde cero.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, load_15m, resample, atr_series, detect_signal, DB_PATH,
    MARGIN, FEE, _apply_capital_sim, _build_validate_candidate, evaluate,
)
import backtest.level_sweep_liquidity_tp as lstp  # noqa: E402
from backtest.level_sweep_liquidity_tp import liquidity_tp  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

# Config estable encontrada en Level Sweep -- se aplica igual aca (mismo
# mecanismo de TP, no un barrido nuevo desde cero).
lstp.DISPROPORTION_RATIO = 1.2
lstp.TP_HAIRCUT_RATIO = 0.9
lstp.RECENT_IMPULSE_LOOKBACK = 40

STRAT = dict(entry_type="band_touch", tf_min=15, side="SHORT", atr_sl_mult=2.0)


def backtest_liquidity_tp(conn, basket, apply_vetos=True, tf_min=15):
    all_trades = []
    for symbol in basket:
        rows15 = load_15m(conn, symbol)
        if len(rows15) < 400:
            continue
        candles = resample(rows15, tf_min) if tf_min != 15 else rows15
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        atr_arr = atr_series(candles, 14)

        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr_arr[i]
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
                    all_trades.append({"symbol": symbol, "pnl": gross - fees,
                                        "open_time": open_trade["open_time"], "close_time": ts})
                    open_trade = None
                continue

            sig = detect_signal(STRAT, closes, highs, lows, i, None, None, None)
            if sig is None or sig != 1:  # SHORT-only, mismo criterio que produccion real
                continue

            entry = c
            sl_dist = STRAT["atr_sl_mult"] * a
            sl = entry + sl_dist
            tp = liquidity_tp(closes, highs, lows, i, sig, entry)
            if tp is None or tp >= entry:
                continue

            if apply_vetos:
                candidate = _build_validate_candidate(STRAT, symbol, sig, entry, sl_dist)
                try:
                    v_ok, _, _ = validate_pre_trade(candidate, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue

            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}

    return _apply_capital_sim(all_trades)


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days = (t1 - t0) / (1000 * 60 * 60 * 24)
    print(f"Universo: {len(basket)} simbolos | {days:.0f} dias reales | Band Touch + TP liquidez real")

    for tf_min in (15, 60):
        trades = backtest_liquidity_tp(conn, basket, apply_vetos=True, tf_min=tf_min)
        res = evaluate(trades, days)
        print(f"tf={tf_min}m -> n={res.get('n')} WR={res.get('wr_pct')}% $/mes={res.get('monthly')} "
              f"h1={res.get('pnl_h1')} h2={res.get('pnl_h2')} passes_bar={res.get('passes_bar')} "
              f"stable={res.get('stable_between_halves')}", flush=True)


if __name__ == "__main__":
    main()
