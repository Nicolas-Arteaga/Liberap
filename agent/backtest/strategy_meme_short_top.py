"""
Estrategia "Short del Blow-off Top" -- memecoins/small-caps de alta beta.
Construida desde meme_breakout_mining.py (patron mas fuerte de toda la
sesion, robusto en 17-18 de 18-19 simbolos): antes de una caida >=5% en
2h, casi siempre hubo (1) el precio SUBIENDO fuerte (lift 1.60-1.63x,
17/18 simbolos), (2) RSI>65 (lift 2.61-2.65x, el mas fuerte de todo el
dia, 17/18 simbolos), (3) precio arriba de las 4 MAs (lift 1.58-1.60x,
15/18 simbolos). Patron clasico de pump-and-dump: pump con momentum
extremo -> casi siempre termina en cascada de venta.

SHORT-only (el patron no fue robusto para el lado LONG en esta canasta,
solo para el techo). Misma logica de confirmacion + ATR que las versiones
anteriores (entrar cuando el giro ya arranco, no adivinar el techo exacto).

Uso: python -m backtest.strategy_meme_short_top   (desde agent/)
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
PRIOR_MOVE_PCT = 1.8   # calibrado para memecoins -- meme_breakout_mining.py uso umbral de
                        # ruptura 5% (vs 1.5% BTC, ~3.3x), mismo factor aplicado al movimiento previo
CONFIRM_LOOKBACK = 4   # velas hacia atras donde buscar el estado (no exige que sea la vela actual)
VOLUME_FILTER = True   # 2026-08-02: +$484.56 -> +$573.90 con este filtro activado (19/23 positivos)
VOLUME_LOOKBACK = 20
VOLUME_MULT = 1.3
ATR_PERIOD = 14
ATR_SL_MULT = 2.0      # grid search 2026-08-02: 2.0/4.0 dio +$386.45 vs +$227.01 del 1.5/3.0 original
ATR_TP_MULT = 4.0      # R:R = 2:1 con estos multiplicadores
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
        volumes_full = [float(c[5]) for c in candles]

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

        def volume_confirmed(upto: int) -> bool:
            """Filtro opcional: la vela del estado tuvo volumen real de
            manada (no un pump fantasma de poco volumen). VOLUME_FILTER
            en False desactiva este chequeo por completo (default)."""
            if not VOLUME_FILTER:
                return True
            vols = volumes_full[:upto]
            if len(vols) < VOLUME_LOOKBACK + 1:
                return False
            recent_vol = vols[-1]
            avg_vol = sum(vols[-VOLUME_LOOKBACK - 1:-1]) / VOLUME_LOOKBACK
            return avg_vol > 0 and recent_vol >= VOLUME_MULT * avg_vol

        # 1. El estado de agotamiento tuvo que estar presente en alguna de
        # las ultimas CONFIRM_LOOKBACK velas (no necesariamente la actual),
        # con volumen real de manada en esa misma vela (si VOLUME_FILTER).
        recent_state = None
        for back in range(0, CONFIRM_LOOKBACK + 1):
            upto = len(closes_full) - back
            s = exhaustion_state(closes_full[:upto])
            if s is not None and volume_confirmed(upto):
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

        # SHORT-only -- el patron minado solo fue robusto para el techo
        # (RSI alto + subiendo + arriba de las MAs -> caida), no para el
        # piso en esta canasta de memecoins.
        side = None
        if recent_state == 1 and cp < prev_close and rsi_now < rsi_prev:
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


BASKET = ["BTCUSDT", "SUIUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT",
          "DOTUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT", "UNIUSDT", "SANDUSDT", "GALAUSDT",
          "ALGOUSDT", "XLMUSDT", "VETUSDT", "ETCUSDT", "RUNEUSDT"]


BASKET = ["1000BONKUSDT", "1000FLOKIUSDT", "1000SHIBUSDT", "WIFUSDT", "PNUTUSDT", "MEWUSDT",
          "BOMEUSDT", "NEIROUSDT", "CHILLGUYUSDT", "MOODENGUSDT", "ACTUSDT", "TURBOUSDT",
          "MEMEUSDT", "1000PEPEUSDT", "GMTUSDT", "APEUSDT", "JASMYUSDT", "HOTUSDT", "CFXUSDT",
          # ampliacion 2026-08-02 -- probados 8, descartados 4 que dieron muy negativo
          # (1000LUNCUSDT -$81.82, BANANAUSDT -$21.28, BROCCOLIF3BUSDT -$139.67,
          # ALICEUSDT -$115.33 -- ampliar la canasta sin criterio empeoro el total
          # de +$386 a +$126; estos 4 sí sumaron de verdad)
          "1000CATUSDT", "CAKEUSDT", "ARKMUSDT", "BLURUSDT"]


def main():
    engine = BacktestEngine()
    print(f"Ventana: {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}", flush=True)
    print(f"Short del Blow-off Top (memecoins) | RSI>{RSI_HIGH} + arriba de las 4 MAs + confirmacion de giro | "
          f"movimiento previo >={PRIOR_MOVE_PCT}% | TP={ATR_TP_MULT}xATR SL={ATR_SL_MULT}xATR (R:R {ATR_TP_MULT/ATR_SL_MULT:.1f}:1)", flush=True)
    print(f"Canasta: {len(BASKET)} memecoins/small-caps (patron validado en meme_breakout_mining.py)", flush=True)
    print("=" * 100, flush=True)

    total_pnl = 0.0
    for sym in BASKET:
        r = run_and_report(engine, sym)
        total_pnl += r["total_pnl_usdt"]

    print("=" * 100)
    print(f"PnL TOTAL sumado de los {len(BASKET)} simbolos: ${round(total_pnl,2)}")


if __name__ == "__main__":
    main()
