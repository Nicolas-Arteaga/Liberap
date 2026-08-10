"""
Validacion del patron "Short del Blow-off Top" a traves del MOTOR REAL de
backtest (backtest/engine.py::_run_generic), que reusa risk_manager.py de
produccion de verdad -- no reimplementa TP/SL/zombie-timeout/capital-sim a
mano como strategy_meme_short_top.py.

FIX 2026-08-02 (encontrado por el usuario): la version anterior de este
script llamaba a _run_generic UNA VEZ POR SIMBOLO (loop con lista de 1
elemento), lo que le daba a CADA simbolo sus propios 3 cupos de capital
independientes -- en la practica, hasta 23x3 posiciones concurrentes en
vez de 3 TOTALES compartidas entre toda la canasta, que es como funciona
de verdad en produccion (maxOpenPositions=3 es por PERFIL, no por simbolo).
Ahora se llama _run_generic UNA sola vez con la canasta COMPLETA -- el
motor ya acumula todas las señales y aplica _capital_sim UNA vez al final
sobre el conjunto combinado (mismo patron que usa engine.run_parallel).

Uso: python -m backtest.run_meme_short_top_via_engine   (desde agent/)
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine
from backtest.strategy_meme_short_top import (
    BASKET, START_MS, END_MS, INTERVAL, RSI_PERIOD, MA_PERIODS, RSI_HIGH,
    PRIOR_WINDOW, PRIOR_MOVE_PCT, CONFIRM_LOOKBACK, VOLUME_LOOKBACK, VOLUME_MULT,
    ATR_PERIOD, ATR_SL_MULT, ATR_TP_MULT, MARGIN, SLOTS, MAX_CANDLES_15M,
    _sma, _rsi, _atr,
)

PROFILE = {
    "id": "meme-short-top-test",
    "name": "Short del Blow-off Top (memecoins, validacion via motor real)",
    "marginPerTrade": MARGIN,
    "maxOpenPositions": SLOTS,
    "maxTradeDurationCandles": MAX_CANDLES_15M,
}


def make_candidate_fn(engine: BacktestEngine):
    """Generico -- recibe el simbolo como argumento en cada llamada de
    _run_generic, no lo fija de antemano (ese era el bug: antes se creaba
    un candidate_fn distinto POR simbolo y se llamaba _run_generic con una
    lista de 1 solo elemento cada vez, dandole 3 cupos propios a cada uno)."""
    def candidate_fn(symbol):
        buffer_needed = max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW + CONFIRM_LOOKBACK
        candles = engine.fetcher.get_klines_with_partial(symbol, INTERVAL, limit=buffer_needed + 5)
        if len(candles) < buffer_needed:
            return None

        closes_full = [float(c[4]) for c in candles]
        volumes_full = [float(c[5]) for c in candles]

        def exhaustion_short_state(closes):
            if len(closes) < max(MA_PERIODS) + RSI_PERIOD + PRIOR_WINDOW:
                return False
            cp_ = closes[-1]
            mas_ = {p: _sma(closes, p) for p in MA_PERIODS}
            rsi_ = _rsi(closes)
            prior_ = (cp_ - closes[-1 - PRIOR_WINDOW]) / closes[-1 - PRIOR_WINDOW] * 100
            return rsi_ > RSI_HIGH and cp_ > max(mas_.values()) and prior_ > PRIOR_MOVE_PCT

        def volume_confirmed(upto):
            vols = volumes_full[:upto]
            if len(vols) < VOLUME_LOOKBACK + 1:
                return False
            recent_vol = vols[-1]
            avg_vol = sum(vols[-VOLUME_LOOKBACK - 1:-1]) / VOLUME_LOOKBACK
            return avg_vol > 0 and recent_vol >= VOLUME_MULT * avg_vol

        found = False
        for back in range(0, CONFIRM_LOOKBACK + 1):
            upto = len(closes_full) - back
            if exhaustion_short_state(closes_full[:upto]) and volume_confirmed(upto):
                found = True
                break
        if not found:
            return None

        rsi_now = _rsi(closes_full)
        rsi_prev = _rsi(closes_full[:-1])
        cp = closes_full[-1]
        prev_close = closes_full[-2]
        if not (cp < prev_close and rsi_now < rsi_prev):
            return None

        atr = _atr(candles)
        if atr <= 0:
            return None

        sl = cp + ATR_SL_MULT * atr
        tp = cp - ATR_TP_MULT * atr

        return {
            "symbol": symbol,
            "side": 1,
            "custom_sl_price": sl,
            "custom_tp_price": tp,
            "meme_short_top_mode": True,
            "nexus_confidence": 0,
        }
    return candidate_fn


def main():
    engine = BacktestEngine()
    print(f"Validando via motor real (_run_generic + risk_manager.py) | POOLED: 3 cupos TOTALES compartidos entre {len(BASKET)} simbolos", flush=True)
    print(f"ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}", flush=True)
    print("=" * 100, flush=True)

    cfn = make_candidate_fn(engine)
    result = engine._run_generic(PROFILE, BASKET, START_MS, END_MS, INTERVAL, cfn)

    print(f"señales totales={result['total_signals']} | trades aceptados={result['accepted_trades']} | "
          f"rechazados sin cupo={result['rejected_no_slot']} | WR={result['win_rate_pct']}% | "
          f"PnL TOTAL=${result['total_pnl_usdt']}", flush=True)

    total_days = (END_MS - START_MS) / (1000 * 60 * 60 * 24)
    print(f"Periodo: {total_days:.0f} dias | trades/dia promedio: {result['accepted_trades']/total_days:.2f}")

    # Desglose por simbolo (cuantos de los trades ACEPTADOS le tocaron a cada uno)
    from collections import Counter
    by_symbol = Counter(t["symbol"] for t in result["trades"])
    pnl_by_symbol = {}
    for t in result["trades"]:
        pnl_by_symbol[t["symbol"]] = pnl_by_symbol.get(t["symbol"], 0.0) + t["pnl"]
    print("=" * 100)
    for sym in BASKET:
        if by_symbol.get(sym, 0) > 0:
            print(f"{sym:15s} | trades={by_symbol.get(sym,0):3d} | PnL=${round(pnl_by_symbol.get(sym,0),2):8.2f}")


if __name__ == "__main__":
    main()
