"""
Estrategia nueva #2: Breakout de compresion de volatilidad (Bollinger
Squeeze), patron clasico (TTM Squeeze simplificado) -- cuando el ancho de
las bandas de Bollinger cae a un minimo relativo respecto a su propia
historia reciente, el mercado esta "comprimido" y suele romper con fuerza.
Entra en la ruptura (cierre fuera de la banda) confirmada por volumen por
encima del promedio reciente. TP = measured move (proyecta el ancho del
squeeze desde el punto de ruptura). SL = vuelta al punto medio del squeeze.

Mismo patron de implementacion y misma base de comparacion que
strategy_rsi_bb.py (agent/backtest/). Uso: python -m backtest.strategy_squeeze_breakout (desde agent/)
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine, BASE_INTERVAL, BASE_MS

START_MS = int(datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)

INTERVAL = "15m"
BB_PERIOD = 20
BB_STD = 2.0
WIDTH_LOOKBACK = 50       # ventana para juzgar si el ancho actual es un minimo relativo
WIDTH_PERCENTILE = 0.20   # squeeze = ancho actual esta en el 20% mas bajo de esa ventana
VOLUME_LOOKBACK = 20
VOLUME_MULTIPLIER = 1.5   # confirmacion: volumen de ruptura >= 1.5x el promedio reciente
SL_MID_BUFFER_PCT = 0.005  # pequeño colchon mas alla del punto medio del squeeze
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48


def _bollinger_width(closes: list) -> tuple:
    window = closes[-BB_PERIOD:]
    n = len(window)
    mean = sum(window) / n
    variance = sum((c - mean) ** 2 for c in window) / n
    std = variance ** 0.5
    lower, upper = mean - BB_STD * std, mean + BB_STD * std
    width = (upper - lower) / mean if mean else 0.0
    return lower, mean, upper, width


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _ = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = max(BB_PERIOD + WIDTH_LOOKBACK, VOLUME_LOOKBACK) * (15 * 60_000 // BASE_MS) + 20
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

        candles = engine.fetcher.get_klines_with_partial(
            symbol, INTERVAL, limit=BB_PERIOD + WIDTH_LOOKBACK + 5
        )
        if len(candles) < BB_PERIOD + WIDTH_LOOKBACK:
            j += 1
            continue

        closes = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]

        # Serie de anchos historicos (una lectura por vela, ventana movil BB_PERIOD)
        widths = []
        for k in range(BB_PERIOD, len(closes) + 1):
            _, _, _, w = _bollinger_width(closes[:k])
            widths.append(w)
        if len(widths) < WIDTH_LOOKBACK:
            j += 1
            continue

        current_width = widths[-1]
        recent_widths = sorted(widths[-WIDTH_LOOKBACK:])
        threshold_idx = int(len(recent_widths) * WIDTH_PERCENTILE)
        is_squeeze = current_width <= recent_widths[threshold_idx]

        if not is_squeeze:
            j += 1
            continue

        lower, mid, upper, _ = _bollinger_width(closes)
        cp = closes[-1]
        avg_vol = sum(volumes[-VOLUME_LOOKBACK - 1:-1]) / VOLUME_LOOKBACK
        cur_vol = volumes[-1]
        vol_confirmed = avg_vol > 0 and cur_vol >= VOLUME_MULTIPLIER * avg_vol

        side = None
        if vol_confirmed:
            if cp >= upper:
                side = 0  # ruptura alcista
            elif cp <= lower:
                side = 1  # ruptura bajista

        if side is None:
            j += 1
            continue

        measured_move = upper - lower  # ancho del squeeze en precio, proyectado desde la ruptura
        if side == 0:
            tp = cp + measured_move
            sl = mid * (1 - SL_MID_BUFFER_PCT)
            if sl >= cp:
                j += 1
                continue
        else:
            tp = cp - measured_move
            sl = mid * (1 + SL_MID_BUFFER_PCT)
            if sl <= cp:
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
    print(f"Estrategia: Bollinger Squeeze Breakout | BB({BB_PERIOD},{BB_STD}) en {INTERVAL} | squeeze=percentil {WIDTH_PERCENTILE*100:.0f}% de {WIDTH_LOOKBACK} velas | vol>={VOLUME_MULTIPLIER}x | TP=measured move | SL=punto medio", flush=True)

    all_trades = []
    for idx, symbol in enumerate(symbols):
        try:
            trades = run_symbol(engine, symbol)
            all_trades.extend(trades)
        except Exception:
            pass
        if (idx + 1) % 50 == 0 or idx + 1 == len(symbols):
            print(f"  progreso: {idx+1}/{len(symbols)} simbolos | {len(all_trades)} señales acumuladas", flush=True)

    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": "Bollinger Squeeze Breakout"}
    result = engine._capital_sim(all_trades, profile_stub, symbols_used=symbols)

    trades = result["trades"]
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("=" * 100)
    print(f"Bollinger Squeeze Breakout | señales={result['total_signals']} | trades={result['accepted_trades']} | "
          f"WR={result['win_rate_pct']}% | PnL=${result['total_pnl_usdt']} | PF={round(pf,3) if pf!=float('inf') else pf}")
    print("=" * 100)
    print("Referencia: MA Slope Caso 3 historico real = +$76.74 (WR 64.3%) | FVG-15m historico real = +$83.35 (WR 13.9%)")
    print("Estrategia #1 (RSI+Bollinger): +$10.08 (WR 53.2%, PF 1.031)")


if __name__ == "__main__":
    main()
