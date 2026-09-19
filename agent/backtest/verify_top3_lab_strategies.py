"""
2026-08-18: pedido del usuario -- reconfirmar las 3 estrategias que vienen
performando mejor en vivo (Level Sweep 15m SL3/RR3, Level Sweep 60m
SL1.5/RR3, Death Cross SMA50/200 4h) con el motor YA arreglado (vetos
reales + limite real de 3 cupos x $150), en las dos variantes (CON/SIN
vetos) para comparar.
"""
import sys
import os
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, detect_signal, atr_series, resample, load_15m, DB_PATH, MARGIN, FEE  # noqa: E402
from backtest.golden_cross_mining import (  # noqa: E402
    load_15m as load_15m_dc, resample_4h, sma, atr_series as atr_series_4h, SLOW, FAST,
)
from setup_validator import validate_pre_trade  # noqa: E402

DAYS = 243
SLOTS = 3


def build_candidate(symbol, side, entry, mode_flag):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": f"{mode_flag}:lab", mode_flag: True,
        "price_at_signal": entry, "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def apply_capital_sim(trades, slots=SLOTS):
    trades = sorted(trades, key=lambda t: (t["open_time"], t["symbol"]))
    open_slots, accepted = [], []
    for t in trades:
        open_slots = [ct for ct in open_slots if ct > t["open_time"]]
        if len(open_slots) >= slots:
            continue
        open_slots.append(t["close_time"])
        accepted.append(t)
    return accepted


def report(label, trades, days=DAYS):
    n = len(trades)
    if n == 0:
        print(f"  {label}: sin trades")
        return
    total = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    monthly = total / (days / 30.44)
    print(f"  {label:20s} n={n:5d} WR={wins/n*100:5.1f}% PnL=${total:9.2f} (${monthly:8.2f}/mes)")


# ── Level Sweep (15m SL3/RR3 y 60m SL1.5/RR3) ──
def backtest_level_sweep(conn, basket, tf_min, atr_sl_mult, rr_mult, lookback, apply_vetos):
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
        volumes = [c[5] for c in candles]
        atr = atr_series(candles, 14)
        open_trade = None
        strat = {"entry_type": "level_sweep", "lookback": lookback}
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
                    all_trades.append({"symbol": symbol, "pnl": gross - fees,
                                        "open_time": open_trade["open_time"], "close_time": ts})
                    open_trade = None
                continue
            level_high = max(highs[i - lookback:i]) if i >= lookback else None
            level_low = min(lows[i - lookback:i]) if i >= lookback else None
            sig = detect_signal(strat, closes, highs, lows, i, level_high, level_low, volumes)
            if sig is None or sig != 1:  # SHORT unicamente (confirmado real)
                continue
            entry = c
            sl_dist = atr_sl_mult * a
            tp_dist = sl_dist * rr_mult
            sl, tp = entry + sl_dist, entry - tp_dist
            if apply_vetos:
                cand = build_candidate(symbol, sig, entry, "level_sweep_1h_mode")
                try:
                    v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue
            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}
    return apply_capital_sim(all_trades)


# ── Death Cross (SMA50/200 4h) ──
def backtest_death_cross(conn, basket, apply_vetos):
    all_trades = []
    for symbol in basket:
        candles = resample_4h(load_15m_dc(conn, symbol))
        if len(candles) < SLOW + 10:
            continue
        closes = [c[4] for c in candles]
        atr = atr_series_4h(candles, 14)
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
                side = open_trade["side"]
                hit_tp = l <= open_trade["tp"]
                hit_sl = h >= open_trade["sl"]
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = open_trade["qty"]
                    gross = qty * (open_trade["entry"] - close_px)
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({"symbol": symbol, "pnl": gross - fees,
                                        "open_time": open_trade["open_time"], "close_time": ts})
                    open_trade = None
                prev_diff = diff
                continue
            if prev_diff is not None and prev_diff >= 0 and diff < 0:
                entry = c
                sl_dist_orig = 2.0 * a
                sl, tp = entry + sl_dist_orig, entry - sl_dist_orig * 3.0
                if apply_vetos:
                    cand = build_candidate(symbol, 1, entry, "death_cross_mode")
                    try:
                        v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                    except Exception:
                        v_ok = True
                    if not v_ok:
                        prev_diff = diff
                        continue
                open_trade = {"side": 1, "entry": entry, "sl": sl, "tp": tp,
                               "open_time": ts, "qty": MARGIN / entry}
            prev_diff = diff
    return apply_capital_sim(all_trades)


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | periodo: {DAYS} dias | limite real: {SLOTS} cupos x $150\n")

    print("=== Level Sweep 15m SL3/RR3 ===")
    t0 = time.time()
    r = backtest_level_sweep(conn, basket, 15, 3.0, 3.0, 20, apply_vetos=False)
    report("SIN vetos", r)
    r = backtest_level_sweep(conn, basket, 15, 3.0, 3.0, 20, apply_vetos=True)
    report("CON vetos", r)
    print(f"  ({time.time()-t0:.1f}s)\n")

    print("=== Level Sweep 60m SL1.5/RR3 ===")
    t0 = time.time()
    r = backtest_level_sweep(conn, basket, 60, 1.5, 3.0, 10, apply_vetos=False)
    report("SIN vetos", r)
    r = backtest_level_sweep(conn, basket, 60, 1.5, 3.0, 10, apply_vetos=True)
    report("CON vetos", r)
    print(f"  ({time.time()-t0:.1f}s)\n")

    print("=== Death Cross (SMA50/200 4h) ===")
    t0 = time.time()
    r = backtest_death_cross(conn, basket, apply_vetos=False)
    report("SIN vetos", r)
    r = backtest_death_cross(conn, basket, apply_vetos=True)
    report("CON vetos", r)
    print(f"  ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
