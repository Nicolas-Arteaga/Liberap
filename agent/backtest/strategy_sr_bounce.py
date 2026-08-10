"""
Estrategia nueva #3: Rebote en soporte/resistencia con confirmacion de
volumen -- patron clasico de rango. Soporte/resistencia = minimo/maximo
movil de las ultimas N velas (Donchian, simplificacion estandar y legitima
de "nivel reciente"). Entra cuando una vela toca el nivel con la MECHA
(no el cierre -- rechazo) y el volumen de esa vela es alto respecto al
promedio reciente (confirma rechazo real, no ruido). TP = nivel opuesto
del rango. SL = mas alla del nivel tocado.

Mismo patron de implementacion y misma base de comparacion que
strategy_rsi_bb.py / strategy_squeeze_breakout.py.
Uso: python -m backtest.strategy_sr_bounce   (desde agent/)
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
RANGE_LOOKBACK = 40       # velas para definir el rango (soporte = min, resistencia = max)
VOLUME_LOOKBACK = 20
VOLUME_MULTIPLIER = 1.3
TOUCH_TOLERANCE_PCT = 0.002  # 0.2% de margen para considerar "toco" el nivel
SL_BUFFER_PCT = 0.008
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _ = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = max(RANGE_LOOKBACK, VOLUME_LOOKBACK) * (15 * 60_000 // BASE_MS) + 20
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
            symbol, INTERVAL, limit=max(RANGE_LOOKBACK, VOLUME_LOOKBACK) + 5
        )
        if len(candles) < RANGE_LOOKBACK + 1:
            j += 1
            continue

        # candles[-1] es la vela actual (parcial/en formacion) -- el rango
        # de referencia se calcula con las anteriores (cerradas), sin
        # incluir la vela que estamos evaluando, para no usar su propio
        # movimiento como parte del nivel que "rompe".
        range_window = candles[-(RANGE_LOOKBACK + 1):-1]
        support = min(float(c[3]) for c in range_window)   # low minimo
        resistance = max(float(c[2]) for c in range_window)  # high maximo

        cur = candles[-1]
        cur_high, cur_low, cur_close, cur_vol = float(cur[2]), float(cur[3]), float(cur[4]), float(cur[5])
        volumes = [float(c[5]) for c in candles[-(VOLUME_LOOKBACK + 1):-1]]
        avg_vol = sum(volumes) / len(volumes) if volumes else 0.0
        vol_confirmed = avg_vol > 0 and cur_vol >= VOLUME_MULTIPLIER * avg_vol

        side = None
        if vol_confirmed:
            # Rebote en soporte: la mecha perfora/toca el soporte pero el
            # cierre queda por ENCIMA (rechazo real, no ruptura).
            touched_support = cur_low <= support * (1 + TOUCH_TOLERANCE_PCT)
            if touched_support and cur_close > support:
                side = 0  # LONG
            else:
                touched_resistance = cur_high >= resistance * (1 - TOUCH_TOLERANCE_PCT)
                if touched_resistance and cur_close < resistance:
                    side = 1  # SHORT

        if side is None:
            j += 1
            continue

        cp = cur_close
        if side == 0:
            sl = support * (1 - SL_BUFFER_PCT)
            tp = resistance
            if tp <= cp or sl >= cp:
                j += 1
                continue
        else:
            sl = resistance * (1 + SL_BUFFER_PCT)
            tp = support
            if tp >= cp or sl <= cp:
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
    print(f"Estrategia: Soporte/Resistencia (Donchian {RANGE_LOOKBACK}) en {INTERVAL} | vol>={VOLUME_MULTIPLIER}x | TP=nivel opuesto | SL=mas alla del nivel tocado", flush=True)

    all_trades = []
    for idx, symbol in enumerate(symbols):
        try:
            trades = run_symbol(engine, symbol)
            all_trades.extend(trades)
        except Exception:
            pass
        if (idx + 1) % 50 == 0 or idx + 1 == len(symbols):
            print(f"  progreso: {idx+1}/{len(symbols)} simbolos | {len(all_trades)} señales acumuladas", flush=True)

    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": "Soporte/Resistencia Bounce"}
    result = engine._capital_sim(all_trades, profile_stub, symbols_used=symbols)

    trades = result["trades"]
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("=" * 100)
    print(f"Soporte/Resistencia Bounce | señales={result['total_signals']} | trades={result['accepted_trades']} | "
          f"WR={result['win_rate_pct']}% | PnL=${result['total_pnl_usdt']} | PF={round(pf,3) if pf!=float('inf') else pf}")
    print("=" * 100)
    print("Referencia: MA Slope Caso 3 historico real = +$76.74 (WR 64.3%) | FVG-15m historico real = +$83.35 (WR 13.9%)")
    print("Estrategia #1 (RSI+Bollinger): +$10.08 (WR 53.2%, PF 1.031) | Estrategia #2 (Squeeze Breakout): -$45.07 (WR 46.6%, PF 0.887)")


if __name__ == "__main__":
    main()
