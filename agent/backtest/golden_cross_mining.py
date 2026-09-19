"""
Golden Cross (SMA50 cruza arriba de SMA200) -- estrategia de tendencia de
largo plazo, NADA que ver con lo que se probo toda la sesion (FVG/sweeps/
mean-reversion intradiario). Investigada 2026-08-11 via research externo:
75% WR, drawdown mas bajo, pocos trades en comparaciones publicadas
(SMA50/200 en daily, 2022-2026). Acá se prueba en 4h (resampleado desde
klines_clean 15m) porque con ~8 meses de historia real no hay suficiente
para daily. LONG en Golden Cross, SHORT en Death Cross (simetrico), salida
por cruce contrario o SL/TP por ATR.

Uso: python -m backtest.golden_cross_mining   (desde agent/)
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import TOP_40_SYMBOLS  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
BUCKET_MS = 4 * 3600 * 1000
FAST, SLOW = 50, 200
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
ATR_TP_MULT = 6.0  # tendencia de largo plazo, deja correr mas (R:R 3:1)


def load_15m(conn, symbol):
    cur = conn.cursor()
    cur.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines_clean "
        "WHERE symbol=? AND interval='15m' ORDER BY open_time ASC",
        (symbol,),
    )
    return cur.fetchall()


def resample_4h(rows):
    buckets = {}
    for r in rows:
        b = r[0] - (r[0] % BUCKET_MS)
        buckets.setdefault(b, []).append(r)
    out = []
    for b in sorted(buckets.keys()):
        g = sorted(buckets[b], key=lambda x: x[0])
        if len(g) < 16:  # 4h = 16 velas de 15m, exige el bucket completo
            continue
        out.append((b, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)))
    return out


def sma(vals, period, idx):
    if idx + 1 < period:
        return None
    return sum(vals[idx + 1 - period:idx + 1]) / period


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


def run_symbol(conn, symbol):
    rows15 = load_15m(conn, symbol)
    candles = resample_4h(rows15)
    if len(candles) < SLOW + 10:
        return []
    closes = [c[4] for c in candles]
    atr = atr_series(candles, ATR_PERIOD)

    trades = []
    open_trade = None
    prev_diff = None
    for i in range(SLOW, len(candles)):
        ts, o, h, l, c, v = candles[i]
        a = atr[i]
        fast = sma(closes, FAST, i)
        slow = sma(closes, SLOW, i)
        if fast is None or slow is None or a is None or a <= 0:
            continue
        diff = fast - slow

        if open_trade:
            side = open_trade["side"]
            hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
            hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
            cross_exit = (side == 0 and diff < 0) or (side == 1 and diff > 0)
            if hit_tp or hit_sl or cross_exit:
                if hit_tp:
                    close_px = open_trade["tp"]
                elif hit_sl:
                    close_px = open_trade["sl"]
                else:
                    close_px = c
                pnl_pct = (close_px - open_trade["entry"]) / open_trade["entry"] if side == 0 else (open_trade["entry"] - close_px) / open_trade["entry"]
                trades.append({"pnl_pct": pnl_pct, "side": side, "open_time": open_trade["open_time"]})
                open_trade = None
            prev_diff = diff
            continue

        if prev_diff is not None:
            golden = prev_diff <= 0 and diff > 0
            death = prev_diff >= 0 and diff < 0
            if golden:
                entry = c
                open_trade = {"side": 0, "entry": entry, "sl": entry - ATR_SL_MULT * a, "tp": entry + ATR_TP_MULT * a, "open_time": ts}
            elif death:
                entry = c
                open_trade = {"side": 1, "entry": entry, "sl": entry + ATR_SL_MULT * a, "tp": entry - ATR_TP_MULT * a, "open_time": ts}
        prev_diff = diff

    return trades


def main():
    conn = sqlite3.connect(DB_PATH)
    all_trades = []
    for symbol in TOP_40_SYMBOLS:
        trades = run_symbol(conn, symbol)
        all_trades.extend(trades)
        if trades:
            print(f"  {symbol:12s} {len(trades):3d} trades", flush=True)

    all_trades.sort(key=lambda t: t["open_time"])
    n = len(all_trades)
    print(f"\nTotal: {n} trades")
    if n == 0:
        return
    wins = sum(1 for t in all_trades if t["pnl_pct"] > 0)
    avg_pct = sum(t["pnl_pct"] for t in all_trades) / n
    print(f"WR={wins/n*100:.1f}% | avg pnl%/trade={avg_pct*100:.3f}%")

    for side, label in ((0, "LONG (Golden Cross)"), (1, "SHORT (Death Cross)")):
        sub = [t for t in all_trades if t["side"] == side]
        if not sub:
            continue
        m = len(sub)
        w = sum(1 for t in sub if t["pnl_pct"] > 0)
        avg = sum(t["pnl_pct"] for t in sub) / m
        print(f"{label}: n={m} WR={w/m*100:.1f}% avg%={avg*100:.3f}%")

    half = n // 2
    for label, sub in (("1ra mitad", all_trades[:half]), ("2da mitad", all_trades[half:])):
        m = len(sub)
        if m == 0:
            continue
        w = sum(1 for t in sub if t["pnl_pct"] > 0)
        avg = sum(t["pnl_pct"] for t in sub) / m
        print(f"{label}: n={m} WR={w/m*100:.1f}% avg%={avg*100:.3f}%")


if __name__ == "__main__":
    main()
