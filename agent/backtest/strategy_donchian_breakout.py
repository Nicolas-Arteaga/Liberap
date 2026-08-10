"""
Estrategia nueva #4: Breakout de canal de Donchian con volumen -- patron
clasico trend-following (opuesto a la #3, que rebotaba EN el nivel; esta
opera A FAVOR de la ruptura). Cierre por encima del maximo de N velas ->
LONG. Cierre por debajo del minimo -> SHORT. Confirmacion de volumen igual
que las estrategias previas. SL = vuelta adentro del canal roto. TP = ATR
proyectado (medida de volatilidad reciente, no un nivel fijo -- estandar
para trend-following, donde no hay "nivel opuesto" como en mean-reversion).

Uso: python -m backtest.strategy_donchian_breakout   (desde agent/)
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
CHANNEL_LOOKBACK = 40
ATR_PERIOD = 14
ATR_TP_MULT = 2.5
ATR_SL_MULT = 1.5
VOLUME_LOOKBACK = 20
VOLUME_MULTIPLIER = 1.4
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48


def _atr(candles: list) -> float:
    """ATR standard de manual -- true range promedio de las ultimas ATR_PERIOD velas."""
    window = candles[-(ATR_PERIOD + 1):]
    if len(window) < 2:
        return 0.0
    trs = []
    for i in range(1, len(window)):
        h, l = float(window[i][2]), float(window[i][3])
        prev_close = float(window[i - 1][4])
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _ = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = max(CHANNEL_LOOKBACK, VOLUME_LOOKBACK, ATR_PERIOD + 1) * (15 * 60_000 // BASE_MS) + 20
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
            symbol, INTERVAL, limit=max(CHANNEL_LOOKBACK, VOLUME_LOOKBACK, ATR_PERIOD + 1) + 5
        )
        if len(candles) < CHANNEL_LOOKBACK + 1:
            j += 1
            continue

        channel_window = candles[-(CHANNEL_LOOKBACK + 1):-1]
        channel_high = max(float(c[2]) for c in channel_window)
        channel_low = min(float(c[3]) for c in channel_window)

        cur = candles[-1]
        cur_close, cur_vol = float(cur[4]), float(cur[5])
        volumes = [float(c[5]) for c in candles[-(VOLUME_LOOKBACK + 1):-1]]
        avg_vol = sum(volumes) / len(volumes) if volumes else 0.0
        vol_confirmed = avg_vol > 0 and cur_vol >= VOLUME_MULTIPLIER * avg_vol

        side = None
        if vol_confirmed:
            if cur_close > channel_high:
                side = 0  # LONG -- rompe el maximo del canal
            elif cur_close < channel_low:
                side = 1  # SHORT -- rompe el minimo del canal

        if side is None:
            j += 1
            continue

        atr = _atr(candles)
        if atr <= 0:
            j += 1
            continue

        cp = cur_close
        if side == 0:
            sl = cp - ATR_SL_MULT * atr
            tp = cp + ATR_TP_MULT * atr
        else:
            sl = cp + ATR_SL_MULT * atr
            tp = cp - ATR_TP_MULT * atr

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
    print(f"Estrategia: Donchian Breakout({CHANNEL_LOOKBACK}) en {INTERVAL} | vol>={VOLUME_MULTIPLIER}x | TP={ATR_TP_MULT}xATR | SL={ATR_SL_MULT}xATR", flush=True)

    all_trades = []
    for idx, symbol in enumerate(symbols):
        try:
            trades = run_symbol(engine, symbol)
            all_trades.extend(trades)
        except Exception:
            pass
        if (idx + 1) % 50 == 0 or idx + 1 == len(symbols):
            print(f"  progreso: {idx+1}/{len(symbols)} simbolos | {len(all_trades)} señales acumuladas", flush=True)

    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": "Donchian Breakout"}
    result = engine._capital_sim(all_trades, profile_stub, symbols_used=symbols)

    trades = result["trades"]
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("=" * 100)
    print(f"Donchian Breakout | señales={result['total_signals']} | trades={result['accepted_trades']} | "
          f"WR={result['win_rate_pct']}% | PnL=${result['total_pnl_usdt']} | PF={round(pf,3) if pf!=float('inf') else pf}")
    print("=" * 100)
    print("Referencia (misma ventana 15 dias): Caso 3=+$8.70 (PF 1.132) | FVG-15m=-$9.70 (PF 0.956)")
    print("Est.1 RSI+BB=+$10.08 (PF 1.031) | Est.2 Squeeze=-$45.07 (PF 0.887) | Est.3 SR Bounce=-$62.58 (PF 0.788)")


if __name__ == "__main__":
    main()
