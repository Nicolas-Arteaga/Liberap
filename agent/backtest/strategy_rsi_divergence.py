"""
Estrategia nueva #5: Divergencia RSI/precio -- patron clasico de reversion
por agotamiento de momentum. Divergencia bajista: precio forma un maximo
mas alto (higher high) pero el RSI en ese mismo punto forma un maximo MAS
BAJO que el pivote anterior -> el impulso alcista pierde fuerza aunque el
precio siga subiendo -> SHORT. Espejo para divergencia alcista -> LONG.

Deteccion de pivotes: un punto es pivote (alto/bajo local) si es el
extremo entre PIVOT_WINDOW velas antes y despues -- estandar de manual,
introduce PIVOT_WINDOW velas de confirmacion (mismo lag que cualquier
trader mirando el grafico esperaria).

Uso: python -m backtest.strategy_rsi_divergence   (desde agent/)
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
RSI_PERIOD = 14
LOOKBACK = 60          # ventana de velas para buscar los 2 ultimos pivotes
PIVOT_WINDOW = 3        # velas a cada lado para confirmar un pivote
ATR_PERIOD = 14
ATR_TP_MULT = 2.0
SL_BUFFER_PCT = 0.005   # colchon mas alla del pivote de precio
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48


def _rsi_series(closes: list) -> list:
    """RSI de Wilder por cada punto (a partir del indice RSI_PERIOD), misma formula que strategy_rsi_bb.py."""
    out = [None] * len(closes)
    if len(closes) < RSI_PERIOD + 1:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, RSI_PERIOD + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / RSI_PERIOD, losses / RSI_PERIOD
    out[RSI_PERIOD] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss)) if avg_loss > 0 else 100.0
    for i in range(RSI_PERIOD + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain, loss = max(delta, 0.0), max(-delta, 0.0)
        avg_gain = (avg_gain * (RSI_PERIOD - 1) + gain) / RSI_PERIOD
        avg_loss = (avg_loss * (RSI_PERIOD - 1) + loss) / RSI_PERIOD
        out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss)) if avg_loss > 0 else 100.0
    return out


def _find_pivots(values: list, window: int) -> list:
    """Indices donde values[i] es el maximo/minimo entre i-window y i+window. Devuelve (idx, is_high)."""
    pivots = []
    for i in range(window, len(values) - window):
        seg = values[i - window: i + window + 1]
        if values[i] == max(seg):
            pivots.append((i, True))
        elif values[i] == min(seg):
            pivots.append((i, False))
    return pivots


def _atr(candles: list) -> float:
    window = candles[-(ATR_PERIOD + 1):]
    if len(window) < 2:
        return 0.0
    trs = []
    for i in range(1, len(window)):
        h, l = float(window[i][2]), float(window[i][3])
        prev_close = float(window[i - 1][4])
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    return sum(trs) / len(trs) if trs else 0.0


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _ = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = (LOOKBACK + RSI_PERIOD) * (15 * 60_000 // BASE_MS) + 20
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

        candles = engine.fetcher.get_klines_with_partial(symbol, INTERVAL, limit=LOOKBACK + RSI_PERIOD + 5)
        if len(candles) < LOOKBACK + RSI_PERIOD:
            j += 1
            continue

        closes = [float(c[4]) for c in candles]
        rsis = _rsi_series(closes)

        # Solo trabajamos con la ventana reciente donde ya hay RSI valido.
        valid_start = next((i for i, v in enumerate(rsis) if v is not None), None)
        if valid_start is None or len(closes) - valid_start < LOOKBACK:
            j += 1
            continue

        recent_closes = closes[-LOOKBACK:]
        recent_rsi = rsis[-LOOKBACK:]
        if any(v is None for v in recent_rsi):
            j += 1
            continue

        price_pivots = _find_pivots(recent_closes, PIVOT_WINDOW)
        highs = [p for p in price_pivots if p[1]]
        lows = [p for p in price_pivots if not p[1]]

        side = None
        pivot_price_level = None

        if len(highs) >= 2:
            (i1, _), (i2, _) = highs[-2], highs[-1]
            if recent_closes[i2] > recent_closes[i1] and recent_rsi[i2] < recent_rsi[i1]:
                side = 1  # divergencia bajista -> SHORT
                pivot_price_level = recent_closes[i2]

        if side is None and len(lows) >= 2:
            (i1, _), (i2, _) = lows[-2], lows[-1]
            if recent_closes[i2] < recent_closes[i1] and recent_rsi[i2] > recent_rsi[i1]:
                side = 0  # divergencia alcista -> LONG
                pivot_price_level = recent_closes[i2]

        if side is None:
            j += 1
            continue

        # La divergencia debe estar formada en velas RECIENTES (no un
        # patron viejo que ya perdio vigencia) -- exige que el segundo
        # pivote este dentro de las ultimas PIVOT_WINDOW*3 velas.
        last_pivot_idx = (highs[-1][0] if side == 1 else lows[-1][0])
        if last_pivot_idx < len(recent_closes) - PIVOT_WINDOW * 3:
            j += 1
            continue

        atr = _atr(candles)
        if atr <= 0:
            j += 1
            continue

        cp = closes[-1]
        if side == 0:
            sl = min(cp, pivot_price_level) * (1 - SL_BUFFER_PCT)
            tp = cp + ATR_TP_MULT * atr
            if sl >= cp:
                j += 1
                continue
        else:
            sl = max(cp, pivot_price_level) * (1 + SL_BUFFER_PCT)
            tp = cp - ATR_TP_MULT * atr
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
    print(f"Estrategia: Divergencia RSI/Precio | RSI({RSI_PERIOD}) en {INTERVAL} | pivotes ventana={PIVOT_WINDOW} | TP={ATR_TP_MULT}xATR | SL=pivote+colchon", flush=True)

    all_trades = []
    for idx, symbol in enumerate(symbols):
        try:
            trades = run_symbol(engine, symbol)
            all_trades.extend(trades)
        except Exception:
            pass
        if (idx + 1) % 50 == 0 or idx + 1 == len(symbols):
            print(f"  progreso: {idx+1}/{len(symbols)} simbolos | {len(all_trades)} señales acumuladas", flush=True)

    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": "RSI Divergence"}
    result = engine._capital_sim(all_trades, profile_stub, symbols_used=symbols)

    trades = result["trades"]
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("=" * 100)
    print(f"RSI Divergence | señales={result['total_signals']} | trades={result['accepted_trades']} | "
          f"WR={result['win_rate_pct']}% | PnL=${result['total_pnl_usdt']} | PF={round(pf,3) if pf!=float('inf') else pf}")
    print("=" * 100)
    print("Referencia (misma ventana 15 dias): Caso 3=+$8.70 (PF 1.132) | FVG-15m=-$9.70 (PF 0.956)")
    print("Est.1 RSI+BB=+$10.08 (PF 1.031) | Est.2 Squeeze=-$45.07 (PF 0.887) | Est.3 SR Bounce=-$62.58 (PF 0.788) | Est.4 Donchian=-$16.94 (PF 0.969)")


if __name__ == "__main__":
    main()
