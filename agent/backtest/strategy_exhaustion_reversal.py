"""
Estrategia "Reversion por Agotamiento" -- construida a partir del hallazgo
REAL de btc_breakout_mining.py (robusto en las 2 mitades de 8 meses de
historia de BTC, no una hipotesis probada al voleo):

  LONG: RSI(14) < 35 + precio por DEBAJO de las 4 MAs (7/25/50/99) +
        cayo >0.5% en las ultimas 2h -> lift 1.65-1.92x (por debajo de
        las MAs) y 1.85-2.82x (venia cayendo) sobre la tasa base de
        rupturas alcistas >=1.5% en las siguientes 2h.
  SHORT (espejo): RSI(14) > 65 + precio por ENCIMA de las 4 MAs + subio
        >0.5% en las ultimas 2h -> lift 1.79-1.93x sobre rupturas
        bajistas.

TP=1.8% (un poco arriba del umbral de 1.5% usado para minar el patron,
para capturar una porcion real del movimiento) | SL=1.0% (R:R ~1.8:1).

Uso: python -m backtest.strategy_exhaustion_reversal   (desde agent/)
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine, BASE_INTERVAL, BASE_MS

# Toda la historia disponible (8 meses) -- la mineria ya probo que el
# patron es robusto en esta ventana completa, usarla entera acá también.
START_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 7, 31, tzinfo=timezone.utc).timestamp() * 1000)

INTERVAL = "15m"
RSI_PERIOD = 14
MA_PERIODS = (7, 25, 50, 99)
RSI_LOW, RSI_HIGH = 35.0, 65.0
PRIOR_WINDOW = 8       # velas de 15m = 2h
PRIOR_MOVE_PCT = 0.5   # % minimo de movimiento previo para contar "cayendo"/"subiendo"
TP_PCT = 1.8
SL_PCT = 1.0
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48   # zombie timeout 12h


def _sma(closes: list, period: int) -> float:
    window = closes[-period:]
    return sum(window) / len(window)


def _rsi(closes: list) -> float:
    if len(closes) < RSI_PERIOD + 1:
        return 50.0
    window = closes[-(RSI_PERIOD + 1):]
    gains, losses = 0.0, 0.0
    for i in range(1, len(window)):
        d = window[i] - window[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / RSI_PERIOD, losses / RSI_PERIOD
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def run_symbol(engine: BacktestEngine, symbol: str) -> list:
    engine.fetcher.set_active_symbol(symbol, intervals=(BASE_INTERVAL, INTERVAL))
    rows_base, _ = engine.fetcher._active_by_interval[BASE_INTERVAL]
    n = len(rows_base)
    min_needed = (max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW) * (15 * 60_000 // BASE_MS) + 20
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
            symbol, INTERVAL, limit=max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW + 5
        )
        if len(candles) < max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW:
            j += 1
            continue

        closes = [float(c[4]) for c in candles]
        cp = closes[-1]
        mas = {p: _sma(closes, p) for p in MA_PERIODS}
        rsi = _rsi(closes)
        prior_return_pct = (cp - closes[-1 - PRIOR_WINDOW]) / closes[-1 - PRIOR_WINDOW] * 100

        below_all = cp < min(mas.values())
        above_all = cp > max(mas.values())

        side = None
        if rsi < RSI_LOW and below_all and prior_return_pct < -PRIOR_MOVE_PCT:
            side = 0  # LONG -- agotamiento de caida
        elif rsi > RSI_HIGH and above_all and prior_return_pct > PRIOR_MOVE_PCT:
            side = 1  # SHORT -- agotamiento de subida

        if side is None:
            j += 1
            continue

        if side == 0:
            tp = cp * (1 + TP_PCT / 100)
            sl = cp * (1 - SL_PCT / 100)
        else:
            tp = cp * (1 - TP_PCT / 100)
            sl = cp * (1 + SL_PCT / 100)

        open_trade = {
            "symbol": symbol, "side": side, "open_time": now_ms,
            "entry": cp, "sl": sl, "tp": tp, "margin": MARGIN,
        }
        last_trade_day = day_key
        j += 1

    return trades


def run_and_report(engine: BacktestEngine, symbol: str, label: str = None):
    trades = run_symbol(engine, symbol)
    profile_stub = {"marginPerTrade": MARGIN, "maxOpenPositions": SLOTS, "name": f"Exhaustion Reversal ({symbol})"}
    result = engine._capital_sim(trades, profile_stub, symbols_used=[symbol])
    accepted = result["trades"]
    wins = [t for t in accepted if t.get("pnl", 0) > 0]
    losses = [t for t in accepted if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    print(f"{label or symbol:15s} | señales={len(trades):5d} | trades={result['accepted_trades']:4d} | "
          f"WR={result['win_rate_pct']:5.1f}% | PnL=${result['total_pnl_usdt']:9.2f} | "
          f"PF={round(pf,3) if pf!=float('inf') else pf}", flush=True)
    return result


def main():
    engine = BacktestEngine()
    print(f"Ventana: {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()} (8 meses completos)", flush=True)
    print(f"Reversion por Agotamiento | RSI(14) {RSI_LOW}/{RSI_HIGH} | precio fuera de las 4 MAs | movimiento previo >={PRIOR_MOVE_PCT}% en {PRIOR_WINDOW} velas | TP={TP_PCT}% SL={SL_PCT}%", flush=True)
    print("=" * 100, flush=True)

    print("--- BTCUSDT (donde se mino el patron) ---", flush=True)
    run_and_report(engine, "BTCUSDT")

    print("\n--- Sombras confirmadas visualmente (mismo patron, precio mas chico) ---", flush=True)
    for sym in ["SUIUSDT", "DOGEUSDT", "1000PEPEUSDT"]:
        run_and_report(engine, sym)


if __name__ == "__main__":
    main()
