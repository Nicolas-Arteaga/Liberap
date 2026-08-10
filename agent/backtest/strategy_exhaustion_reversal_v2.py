"""
Estrategia "Reversion por Agotamiento" v2 -- misma señal minada que v1,
pero corrige el motivo real por el que v1 perdia plata (confirmado con
datos: el estado SI predice reversion mas que continuacion -- 35/224
rupturas alcistas vs 21/237 bajistas tenian este estado antes, ~1.67x mas
asociado a reversion -- el problema no era la señal, era la EJECUCION):

  1. CONFIRMACION: en vez de entrar en el momento exacto del extremo (el
     precio todavia puede seguir cayendo un poco mas antes de girar), se
     exige que el estado (RSI<35+bajo las MAs+cayendo) haya estado
     presente en alguna de las ultimas CONFIRM_LOOKBACK velas, y que la
     vela ACTUAL ya muestre el giro empezando (cierre > cierre anterior
     Y RSI subiendo respecto a la vela anterior) -- se entra cuando el
     rebote ya arranco, no adivinando el piso exacto.
  2. SL/TP basados en ATR (no % fijo) -- un SL de 1% fijo no se adapta a
     cuanto puede seguir moviendose el precio antes de revertir en un
     momento de alta volatilidad (que es justamente cuando dispara esta
     señal) -- un ATR mas ancho da lugar real al movimiento.

Uso: python -m backtest.strategy_exhaustion_reversal_v2   (desde agent/)
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
CONFIRM_LOOKBACK = 4   # velas hacia atras donde buscar el estado (no exige que sea la vela actual)
ATR_PERIOD = 14
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0      # R:R = 2:1 con estos multiplicadores
MARGIN = 150.0
SLOTS = 3
MAX_CANDLES_15M = 48   # zombie timeout 12h


def _sma(closes: list, period: int) -> float:
    window = closes[-period:]
    return sum(window) / len(window)


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

        buffer_needed = max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW + CONFIRM_LOOKBACK
        candles = engine.fetcher.get_klines_with_partial(symbol, INTERVAL, limit=buffer_needed + 5)
        if len(candles) < buffer_needed:
            j += 1
            continue

        closes_full = [float(c[4]) for c in candles]

        def exhaustion_state(closes: list):
            """True (0/1/None) segun side, evaluando el estado con SOLO
            estas velas cerradas -- se usa tanto en la vela actual como en
            las CONFIRM_LOOKBACK anteriores, para el chequeo de confirmacion."""
            if len(closes) < max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW:
                return None
            cp_ = closes[-1]
            mas_ = {p: _sma(closes, p) for p in MA_PERIODS}
            rsi_ = _rsi(closes)
            prior_ = (cp_ - closes[-1 - PRIOR_WINDOW]) / closes[-1 - PRIOR_WINDOW] * 100
            if rsi_ < RSI_LOW and cp_ < min(mas_.values()) and prior_ < -PRIOR_MOVE_PCT:
                return 0
            if rsi_ > RSI_HIGH and cp_ > max(mas_.values()) and prior_ > PRIOR_MOVE_PCT:
                return 1
            return None

        # 1. El estado de agotamiento tuvo que estar presente en alguna de
        # las ultimas CONFIRM_LOOKBACK velas (no necesariamente la actual).
        recent_state = None
        for back in range(0, CONFIRM_LOOKBACK + 1):
            upto = len(closes_full) - back
            s = exhaustion_state(closes_full[:upto])
            if s is not None:
                recent_state = s
                break
        if recent_state is None:
            j += 1
            continue

        # 2. Confirmacion: la vela ACTUAL ya muestra el giro arrancando --
        # cierre mejora respecto a la anterior Y el RSI tambien gira en la
        # direccion del rebote (no se entra adivinando el piso/techo exacto).
        rsi_now = _rsi(closes_full)
        rsi_prev = _rsi(closes_full[:-1])
        cp = closes_full[-1]
        prev_close = closes_full[-2]

        side = None
        if recent_state == 0 and cp > prev_close and rsi_now > rsi_prev:
            side = 0
        elif recent_state == 1 and cp < prev_close and rsi_now < rsi_prev:
            side = 1

        if side is None:
            j += 1
            continue

        atr = _atr(candles)
        if atr <= 0:
            j += 1
            continue

        if side == 0:
            tp = cp + ATR_TP_MULT * atr
            sl = cp - ATR_SL_MULT * atr
        else:
            tp = cp - ATR_TP_MULT * atr
            sl = cp + ATR_SL_MULT * atr

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
    print(f"Reversion por Agotamiento v2 | RSI(14) {RSI_LOW}/{RSI_HIGH} + confirmacion de giro | TP={ATR_TP_MULT}xATR SL={ATR_SL_MULT}xATR (R:R {ATR_TP_MULT/ATR_SL_MULT:.1f}:1)", flush=True)
    print("=" * 100, flush=True)

    print("--- BTCUSDT (donde se mino el patron) ---", flush=True)
    run_and_report(engine, "BTCUSDT")

    print("\n--- Sombras confirmadas visualmente (mismo patron, precio mas chico) ---", flush=True)
    for sym in ["SUIUSDT", "DOGEUSDT", "1000PEPEUSDT"]:
        run_and_report(engine, sym)


if __name__ == "__main__":
    main()
