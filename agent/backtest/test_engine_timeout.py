"""
Tests del timeout de posiciones del motor de backtest (zombie_timeout_decision).
Repair del gate de confiabilidad 2026-09-05, GAP timeout.

Regla FIEL a produccion (verge_agent.py:6506-6544):
  * antiguedad en velas de 15m FIJAS (candle_seconds=900), sin importar el TF;
  * zombie_timeout SOLO si el trade esta en PERDIDA;
  * tope duro max_duration a las 720h.

Cubre 5m / 15m / 1h / 4h: el resultado NO debe depender del timeframe de la
estrategia, solo de max_candles (en unidades de 15m) y del signo del PnL.

    python -m pytest agent/backtest/test_engine_timeout.py -q
    # o simplemente:  python agent/backtest/test_engine_timeout.py
"""
import os, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))

from engine import zombie_timeout_decision, ZOMBIE_CANDLE_MS, MAX_POSITION_DURATION_HOURS  # noqa

H = 3_600_000
OPEN = 1_800_000_000_000  # epoch ms arbitrario


def test_no_timeout_before_threshold():
    # 95 velas de 15m (23.75h), en perdida -> todavia no
    now = OPEN + 95 * ZOMBIE_CANDLE_MS
    assert zombie_timeout_decision(OPEN, now, 96, -0.02) is None


def test_zombie_when_losing_at_threshold():
    now = OPEN + 96 * ZOMBIE_CANDLE_MS  # 24h exactas
    assert zombie_timeout_decision(OPEN, now, 96, -0.001) == "zombie_timeout"


def test_no_zombie_when_winning_at_threshold():
    # mismo instante, pero EN GANANCIA -> se deja correr (este era el bug)
    now = OPEN + 96 * ZOMBIE_CANDLE_MS
    assert zombie_timeout_decision(OPEN, now, 96, +0.001) is None
    # y mucho despues, sigue sin cerrarse por timeout mientras gane
    now2 = OPEN + 300 * ZOMBIE_CANDLE_MS  # 75h
    assert zombie_timeout_decision(OPEN, now2, 96, +0.05) is None


def test_zombie_when_it_turns_negative_later():
    now = OPEN + 150 * ZOMBIE_CANDLE_MS  # 37.5h, ya paso el umbral
    assert zombie_timeout_decision(OPEN, now, 96, -0.008) == "zombie_timeout"


def test_max_duration_hard_cap_regardless_of_pnl():
    now = OPEN + (MAX_POSITION_DURATION_HOURS + 1) * H
    assert zombie_timeout_decision(OPEN, now, 96, +0.10) == "max_duration"
    assert zombie_timeout_decision(OPEN, now, 96, -0.10) == "zombie_timeout"  # perdida gana la prioridad


def test_independent_of_strategy_timeframe():
    # El mismo max_candles y el mismo (open, now, pnl<0) deben dar el MISMO
    # resultado para cualquier TF de estrategia -- el helper ni siquiera
    # recibe el TF. Simulamos "96 velas" para 4 timeframes distintos: la
    # regla real SIEMPRE usa 96 * 15m = 24h.
    for tf_label in ("5m", "15m", "1h", "4h"):
        now = OPEN + 96 * ZOMBIE_CANDLE_MS
        assert zombie_timeout_decision(OPEN, now, 96, -0.01) == "zombie_timeout", tf_label
        assert zombie_timeout_decision(OPEN, now - 1, 96, -0.01) is None, tf_label


def test_small_max_candles():
    # maxTradeDurationCandles=16 (default legacy) -> 4h
    now = OPEN + 16 * ZOMBIE_CANDLE_MS
    assert zombie_timeout_decision(OPEN, now, 16, -0.01) == "zombie_timeout"
    assert zombie_timeout_decision(OPEN, now - ZOMBIE_CANDLE_MS, 16, -0.01) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests OK")
    sys.exit(0 if passed == len(fns) else 1)
