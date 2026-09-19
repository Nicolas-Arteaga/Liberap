"""
Verificacion 2026-08-14: re-simular vela por vela las 6 estrategias reales
con el tope de perdida en SL ($5, TP intacto) recien implementado en
verge_agent.py -- mismo helper _capped_sl_tp_dist portado aca para medir
offline antes/despues.
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, detect_signal, atr_series, resample, load_15m, DB_PATH, MARGIN, FEE
from backtest.golden_cross_mining import run_symbol as run_death_cross_symbol, TOP_40_SYMBOLS

MAX_LOSS = 5.0


def capped_dist(entry, margin, sl_dist_orig, rr_mult):
    qty = margin / entry if entry > 0 else 0
    tp_dist = sl_dist_orig * rr_mult
    if qty <= 0:
        return sl_dist_orig, tp_dist
    loss_full = qty * sl_dist_orig
    sl_dist = MAX_LOSS / qty if loss_full > MAX_LOSS else sl_dist_orig
    return sl_dist, tp_dist


def run_level_sweep(conn, basket, tf_min, atr_sl_mult, rr_mult, lookback, capped):
    all_trades = []
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        candles = resample(rows, tf_min) if tf_min != 15 else rows
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        atr = atr_series(candles, 14)
        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
            if a is None or a <= 0:
                continue
            if open_trade:
                side = 1
                hit_tp = l <= open_trade["tp"]
                hit_sl = h >= open_trade["sl"]
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = open_trade["qty"]
                    gross = qty * (open_trade["entry"] - close_px)
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({"pnl": gross - fees, "open_time": open_trade["open_time"]})
                    open_trade = None
                continue
            level_high = max(highs[i - lookback:i]) if i >= lookback else None
            level_low = min(lows[i - lookback:i]) if i >= lookback else None
            strat = {"entry_type": "level_sweep", "lookback": lookback}
            sig = detect_signal(strat, closes, highs, lows, i, level_high, level_low)
            if sig is None or sig != 1:
                continue
            entry = c
            sl_dist_orig = atr_sl_mult * a
            if capped:
                sl_dist, tp_dist = capped_dist(entry, MARGIN, sl_dist_orig, rr_mult)
            else:
                sl_dist, tp_dist = sl_dist_orig, sl_dist_orig * rr_mult
            sl = entry + sl_dist
            tp = entry - tp_dist
            qty_orig = MARGIN / entry
            open_trade = {"entry": entry, "sl": sl, "tp": tp, "open_time": ts, "qty": qty_orig}
    return all_trades


def run_band_touch(conn, basket, tf_min, atr_sl_mult, rr_mult, capped):
    all_trades = []
    BAND_PERIOD = 20
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        candles = resample(rows, tf_min) if tf_min != 15 else rows
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        atr = atr_series(candles, 14)
        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
            if a is None or a <= 0:
                continue
            if open_trade:
                hit_tp = l <= open_trade["tp"]
                hit_sl = h >= open_trade["sl"]
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = open_trade["qty"]
                    gross = qty * (open_trade["entry"] - close_px)
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({"pnl": gross - fees, "open_time": open_trade["open_time"]})
                    open_trade = None
                continue
            if i + 1 < BAND_PERIOD:
                continue
            window = closes[i + 1 - BAND_PERIOD:i + 1]
            mean = sum(window) / BAND_PERIOD
            std = (sum((x - mean) ** 2 for x in window) / BAND_PERIOD) ** 0.5
            upper = mean + 2 * std
            if not (c > upper):
                continue
            entry = c
            sl_dist_orig = atr_sl_mult * a
            if capped:
                sl_dist, tp_dist = capped_dist(entry, MARGIN, sl_dist_orig, rr_mult)
            else:
                sl_dist, tp_dist = sl_dist_orig, sl_dist_orig * rr_mult
            sl = entry + sl_dist
            tp = entry - tp_dist
            qty_orig = MARGIN / entry
            open_trade = {"entry": entry, "sl": sl, "tp": tp, "open_time": ts, "qty": qty_orig}
    return all_trades


def evaluate(trades, days, label):
    n = len(trades)
    if n == 0:
        print(f"{label}: sin trades")
        return
    total = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    worst = min(losses) if losses else 0
    trades_sorted = sorted(trades, key=lambda t: t["open_time"])
    half = n // 2
    h1 = sum(t["pnl"] for t in trades_sorted[:half])
    h2 = sum(t["pnl"] for t in trades_sorted[half:])
    monthly = total / (days / 30.44)
    print(f"{label}: n={n} WR={wins/n*100:.1f}% PnL total=${total:.2f} (${monthly:.2f}/mes) | peor perdida=${worst:.2f} | mitades: ${h1:.2f}/${h2:.2f}")


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)[:150]
    days = 243

    configs = [
        ("Level Sweep 1H", "level_sweep", dict(tf_min=60, atr_sl_mult=2.0, rr_mult=2.0, lookback=10)),
        ("Level Sweep 60m SL1.5 RR3", "level_sweep", dict(tf_min=60, atr_sl_mult=1.5, rr_mult=3.0, lookback=10)),
        ("Level Sweep 60m SL2 RR1.5", "level_sweep", dict(tf_min=60, atr_sl_mult=2.0, rr_mult=1.5, lookback=10)),
        ("Level Sweep 15m SL3 RR3", "level_sweep", dict(tf_min=15, atr_sl_mult=3.0, rr_mult=3.0, lookback=20)),
        ("Band Touch 15m", "band_touch", dict(tf_min=15, atr_sl_mult=3.0, rr_mult=3.0)),
    ]

    for name, kind, params in configs:
        print(f"\n=== {name} ===")
        if kind == "level_sweep":
            t_orig = run_level_sweep(conn, basket, capped=False, **params)
            t_capped = run_level_sweep(conn, basket, capped=True, **params)
        else:
            t_orig = run_band_touch(conn, basket, capped=False, **params)
            t_capped = run_band_touch(conn, basket, capped=True, **params)
        evaluate(t_orig, days, "  ORIGINAL")
        evaluate(t_capped, days, "  CON TOPE")

    print(f"\n=== Death Cross (SMA50/200 4h) ===")
    from backtest.golden_cross_mining import load_15m as load_klines_4h, resample_4h, sma, atr_series as atr_series_4h, SLOW, FAST

    def run_death_cross_real(symbol, capped):
        candles = resample_4h(load_klines_4h(conn, symbol))
        if len(candles) < SLOW + 10:
            return []
        closes = [c[4] for c in candles]
        atr = atr_series_4h(candles, 14)
        trades = []
        open_trade = None
        prev_diff = None
        for i in range(SLOW, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
            fast_v = sma(closes, FAST, i)
            slow_v = sma(closes, SLOW, i)
            if fast_v is None or slow_v is None or a is None or a <= 0:
                continue
            diff = fast_v - slow_v
            if open_trade:
                hit_tp = l <= open_trade["tp"]
                hit_sl = h >= open_trade["sl"]
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = open_trade["qty"]
                    gross = qty * (open_trade["entry"] - close_px)
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    trades.append({"pnl": gross - fees, "open_time": open_trade["open_time"]})
                    open_trade = None
                prev_diff = diff
                continue
            if prev_diff is not None and prev_diff >= 0 and diff < 0:
                entry = c
                sl_dist_orig = 2.0 * a
                if capped:
                    sl_dist, tp_dist = capped_dist(entry, MARGIN, sl_dist_orig, 3.0)
                else:
                    sl_dist, tp_dist = sl_dist_orig, sl_dist_orig * 3.0
                sl = entry + sl_dist
                tp = entry - tp_dist
                qty_orig = MARGIN / entry
                open_trade = {"entry": entry, "sl": sl, "tp": tp, "open_time": ts, "qty": qty_orig}
            prev_diff = diff
        return trades

    orig_trades, capped_trades = [], []
    for s in TOP_40_SYMBOLS:
        orig_trades.extend(run_death_cross_real(s, capped=False))
        capped_trades.extend(run_death_cross_real(s, capped=True))
    evaluate(orig_trades, days, "  ORIGINAL")
    evaluate(capped_trades, days, "  CON TOPE")


if __name__ == "__main__":
    main()
