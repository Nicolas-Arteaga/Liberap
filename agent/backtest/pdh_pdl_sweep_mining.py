"""
"Barrer el maximo/minimo del dia anterior" -- el ejemplo exacto del
usuario 2026-08-11: trazar high/low del dia calendario previo (UTC), y
cuando el precio mecha mas alla de ese nivel y CIERRA de vuelta adentro
(liquidez cazada, reversal), entrar en la direccion de la reversion.
SL/TP por ATR (lo unico que funciono bien toda la sesion, ver Pump
Reaper). Corrido sobre klines 15m reales de binance_vision_clean.db,
canasta liquida (TOP_40_SYMBOLS), validado con split temporal.

Uso: python -m backtest.pdh_pdl_sweep_mining   (desde agent/)
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import TOP_40_SYMBOLS  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")

ATR_PERIOD = 14
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0
WICK_MIN_PCT = 0.05  # la mecha mas alla del nivel tiene que ser al menos 0.05% del precio


def load_klines(conn, symbol, interval="15m", table="klines_clean"):
    cur = conn.cursor()
    cur.execute(
        f"SELECT open_time, open, high, low, close, volume FROM {table} "
        "WHERE symbol=? AND interval=? ORDER BY open_time ASC",
        (symbol, interval),
    )
    return cur.fetchall()


def atr_series(candles, period=14):
    trs = [0.0]
    for i in range(1, len(candles)):
        h, l, pc = candles[i][2], candles[i][3], candles[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = [None] * len(candles)
    if len(trs) < period:
        return atr
    s = sum(trs[1:period + 1])
    atr[period] = s / period
    for i in range(period + 1, len(candles)):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period
    return atr


def daily_levels(candles):
    """Devuelve dict: day_key -> (high, low) del dia calendario (UTC)."""
    by_day = {}
    for c in candles:
        day = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).date()
        h, l = by_day.get(day, (c[2], c[3]))
        by_day[day] = (max(h, c[2]), min(l, c[3]))
    return by_day


def run_symbol(conn, symbol):
    candles = load_klines(conn, symbol)
    if len(candles) < 200:
        return []
    atr = atr_series(candles, ATR_PERIOD)
    levels = daily_levels(candles)
    days_sorted = sorted(levels.keys())
    day_idx = {d: i for i, d in enumerate(days_sorted)}

    trades = []
    open_trade = None
    for i in range(ATR_PERIOD + 1, len(candles)):
        ts, o, h, l, c, v = candles[i]
        day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
        idx = day_idx.get(day)
        if idx is None or idx == 0:
            continue
        prev_day = days_sorted[idx - 1]
        prev_high, prev_low = levels[prev_day]
        a = atr[i]
        if a is None or a <= 0:
            continue

        if open_trade:
            side = open_trade["side"]
            hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
            hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
            if hit_tp:
                trades.append({**open_trade, "pnl_r": ATR_TP_MULT})
                open_trade = None
            elif hit_sl:
                trades.append({**open_trade, "pnl_r": -ATR_SL_MULT})
                open_trade = None
            continue

        # Sweep del minimo (piso) -> LONG, mecha abajo, cierra adentro
        wick_low_pct = (prev_low - l) / prev_low * 100 if prev_low > 0 else 0
        if l < prev_low and c > prev_low and wick_low_pct >= WICK_MIN_PCT:
            entry = c
            sl = entry - ATR_SL_MULT * a
            tp = entry + ATR_TP_MULT * a
            open_trade = {"symbol": symbol, "side": 0, "entry": entry, "sl": sl, "tp": tp,
                          "open_time": ts}
            continue

        # Sweep del maximo (techo) -> SHORT, mecha arriba, cierra adentro
        wick_high_pct = (h - prev_high) / prev_high * 100 if prev_high > 0 else 0
        if h > prev_high and c < prev_high and wick_high_pct >= WICK_MIN_PCT:
            entry = c
            sl = entry + ATR_SL_MULT * a
            tp = entry - ATR_TP_MULT * a
            open_trade = {"symbol": symbol, "side": 1, "entry": entry, "sl": sl, "tp": tp,
                          "open_time": ts}

    return trades


def main():
    conn = sqlite3.connect(DB_PATH)
    all_trades = []
    for symbol in TOP_40_SYMBOLS:
        trades = run_symbol(conn, symbol)
        all_trades.extend(trades)
        print(f"  {symbol:12s} {len(trades):4d} trades", flush=True)

    all_trades.sort(key=lambda t: t["open_time"])
    n = len(all_trades)
    print(f"\nTotal: {n} trades (en R, no en $ -- 1R = riesgo de 1 trade)")
    if n == 0:
        return

    wins = sum(1 for t in all_trades if t["pnl_r"] > 0)
    total_r = sum(t["pnl_r"] for t in all_trades)
    print(f"WR={wins/n*100:.1f}% | Total R={total_r:.2f} | R promedio/trade={total_r/n:.3f}")

    half = n // 2
    for label, sub in (("1ra mitad", all_trades[:half]), ("2da mitad", all_trades[half:])):
        m = len(sub)
        if m == 0:
            continue
        w = sum(1 for t in sub if t["pnl_r"] > 0)
        r = sum(t["pnl_r"] for t in sub)
        print(f"{label}: n={m} WR={w/m*100:.1f}% Total R={r:.2f}")

    for side, label in ((0, "LONG (sweep de piso)"), (1, "SHORT (sweep de techo)")):
        sub = [t for t in all_trades if t["side"] == side]
        m = len(sub)
        if m == 0:
            continue
        w = sum(1 for t in sub if t["pnl_r"] > 0)
        r = sum(t["pnl_r"] for t in sub)
        print(f"{label}: n={m} WR={w/m*100:.1f}% Total R={r:.2f}")


if __name__ == "__main__":
    main()
