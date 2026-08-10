"""
Estrategia nueva #1 (pedido del usuario 2026-08-01: "probá TODAS las que
puedas hasta que una me supere"): Mean Reversion clasico -- RSI(14) extremo
+ rebote de Bandas de Bollinger(20,2). Patron de manual de trading, no
inventado -- se prueba tal cual, sin trucos, para tener una referencia
honesta.

Reusa el mismo fetcher/DB historica que backtest/engine.py (sin lookahead,
misma tabla de klines) y el mismo _capital_sim (3 slots, $150 margen fijo,
0.04% fee por lado) para que el resultado sea comparable 1:1 contra Caso 3
y FVG-15m. NO reusa risk_manager.py -- este patron define su propio
SL/TP simple (SL mas alla de la banda, TP en la banda media), no tiene
sentido forzarlo por los caminos de "modo estructural" pensados para FVG/
MA Slope.

Uso: python -m backtest.strategy_rsi_bb   (desde agent/)
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine, BASE_INTERVAL, BASE_MS, FEE_PER_SIDE

START_MS = int(datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)

INTERVAL = "15m"
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
SL_BUFFER_PCT = 0.015  # 1.5% mas alla de la banda tocada
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48  # zombie timeout: 48 velas de 15m = 12h


def _rsi(closes: list) -> float:
    """RSI de Wilder, standard de manual -- sobre las ultimas RSI_PERIOD+1 velas."""
    if len(closes) < RSI_PERIOD + 1:
        return 50.0
    window = closes[-(RSI_PERIOD + 1):]
    gains, losses = 0.0, 0.0
    for i in range(1, len(window)):
        delta = window[i] - window[i - 1]
        if delta > 0:
            gains += delta
        else:
            losses += -delta
    avg_gain = gains / RSI_PERIOD
    avg_loss = losses / RSI_PERIOD
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _bollinger(closes: list) -> tuple:
    """SMA20 + bandas a 2 desvios standard -- standard de manual."""
    window = closes[-BB_PERIOD:]
    n = len(window)
    mean = sum(window) / n
    variance = sum((c - mean) ** 2 for c in window) / n
    std = variance ** 0.5
    return mean - BB_STD * std, mean, mean + BB_STD * std  # lower, mid, upper


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _times_base = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = max(BB_PERIOD, RSI_PERIOD + 1) * (15 * 60_000 // BASE_MS) + 20
    if n < min_needed:
        return []

    trades = []
    open_trade = None
    last_trade_day = None
    j = min_needed
    while j < n:
        now_ms = rows_base[j][0] + BASE_MS
        if now_ms < START_MS:
            j += 1
            continue
        if now_ms > END_MS:
            break
        engine.fetcher.set_now(now_ms)

        if open_trade:
            h, l, c = rows_base[j][2], rows_base[j][3], rows_base[j][4]
            side = open_trade["side"]
            hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
            hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
            if hit_tp:
                trades.append({**open_trade, "close_reason": "TP", "close_time": now_ms})
                open_trade = None
            elif hit_sl:
                trades.append({**open_trade, "close_reason": "SL", "close_time": now_ms})
                open_trade = None
            else:
                candles_open_15m = (now_ms - open_trade["open_time"]) / (15 * 60_000)
                if candles_open_15m >= MAX_CANDLES_15M:
                    trades.append({**open_trade, "close_reason": "zombie_timeout",
                                    "close_time": now_ms, "_zombie_close_price": c})
                    open_trade = None
            j += 1
            continue

        day_key = datetime.utcfromtimestamp(now_ms / 1000).date()
        if last_trade_day == day_key:
            j += 1
            continue

        candles = engine.fetcher.get_klines_with_partial(symbol, INTERVAL, limit=BB_PERIOD + RSI_PERIOD + 5)
        if len(candles) < BB_PERIOD + RSI_PERIOD:
            j += 1
            continue
        closes = [float(c[4]) for c in candles]
        cp = closes[-1]
        rsi = _rsi(closes)
        lower, mid, upper = _bollinger(closes)

        side = None
        if rsi <= RSI_OVERSOLD and cp <= lower:
            side = 0  # LONG
        elif rsi >= RSI_OVERBOUGHT and cp >= upper:
            side = 1  # SHORT

        if side is None:
            j += 1
            continue

        if side == 0:
            sl = cp * (1 - SL_BUFFER_PCT)
            tp = mid
            if tp <= cp:
                j += 1
                continue
        else:
            sl = cp * (1 + SL_BUFFER_PCT)
            tp = mid
            if tp >= cp:
                j += 1
                continue

        open_trade = {
            "symbol": symbol, "side": side, "open_time": now_ms,
            "entry": cp, "sl": sl, "tp": tp, "margin": MARGIN,
        }
        last_trade_day = day_key
        j += 1

    return trades


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"Simbolos: {len(symbols)} | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}", flush=True)
    print(f"Estrategia: RSI({RSI_PERIOD}) extremo (<={RSI_OVERSOLD}/>={RSI_OVERBOUGHT}) + Bollinger({BB_PERIOD},{BB_STD}) en {INTERVAL} | SL={SL_BUFFER_PCT*100}% mas alla de banda | TP=banda media", flush=True)

    all_trades = []
    for idx, symbol in enumerate(symbols):
        try:
            trades = run_symbol(engine, symbol)
            all_trades.extend(trades)
        except Exception as e:
            pass
        if (idx + 1) % 50 == 0 or idx + 1 == len(symbols):
            print(f"  progreso: {idx+1}/{len(symbols)} simbolos | {len(all_trades)} señales acumuladas", flush=True)

    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": "RSI+Bollinger Mean Reversion"}
    result = engine._capital_sim(all_trades, profile_stub, symbols_used=symbols)

    trades = result["trades"]
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("=" * 100)
    print(f"RSI+Bollinger Mean Reversion | señales={result['total_signals']} | trades={result['accepted_trades']} | "
          f"WR={result['win_rate_pct']}% | PnL=${result['total_pnl_usdt']} | PF={round(pf,3) if pf!=float('inf') else pf}")
    print("=" * 100)
    print("Referencia: MA Slope Caso 3 historico real = +$76.74 (WR 64.3%) | FVG-15m historico real = +$83.35 (WR 13.9%)")


if __name__ == "__main__":
    main()
