"""
Mineria de patrones (metodo inverso al escaneo de condiciones, pedido del
usuario 2026-08-02): en vez de elegir una condicion y ver si predice,
encontrar TODOS los movimientos grandes reales de BTC (>=1.5% en 2h) y
mirar hacia atras el estado de las MAs justo ANTES de que arranque cada
uno -- comparando contra la tasa base (que tan comun es ese estado en
CUALQUIER momento) para ver que patron esta genuinamente sobre-
representado antes de una ruptura real, no solo presente siempre.

Mismo filtro anti data-snooping que btc_condition_scan.py: primera mitad
vs segunda mitad del historico, por separado.

Uso: python -m backtest.btc_breakout_mining   (desde agent/)
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.btc_condition_scan import load_klines, sma_series, rsi_series, atr_series, DB_PATH, SYMBOL, RSI_PERIOD, ATR_PERIOD  # noqa: E402

MOVE_THRESHOLD_PCT = 1.5   # % minimo para contar como "ruptura real"
MOVE_WINDOW = 8            # velas de 15m hacia adelante (2h) para medir el movimiento
COMPRESSION_THRESHOLD = 0.004


def detect_events(candles: list, closes: list, highs: list, lows: list) -> tuple:
    """Devuelve (up_events, down_events) -- indices donde arranca un movimiento
    grande, sin solapar detecciones del mismo movimiento (non-max-suppression
    simple: una vez marcado un evento, no se vuelve a marcar hasta MOVE_WINDOW
    velas despues)."""
    n = len(candles)
    up_events, down_events = [], []
    last_event_end = -1
    for i in range(n - MOVE_WINDOW - 1):
        if i <= last_event_end:
            continue
        window_highs = highs[i + 1: i + MOVE_WINDOW + 1]
        window_lows = lows[i + 1: i + MOVE_WINDOW + 1]
        up_move = (max(window_highs) - closes[i]) / closes[i] * 100
        down_move = (closes[i] - min(window_lows)) / closes[i] * 100
        if up_move >= MOVE_THRESHOLD_PCT and up_move > down_move:
            up_events.append(i)
            last_event_end = i + MOVE_WINDOW
        elif down_move >= MOVE_THRESHOLD_PCT and down_move > up_move:
            down_events.append(i)
            last_event_end = i + MOVE_WINDOW
    return up_events, down_events


def build_features(i, closes, ma7, ma25, ma50, ma99, rsi):
    vals = [ma7[i], ma25[i], ma50[i], ma99[i]]
    if any(v is None for v in vals) or rsi[i] is None or i < 8:
        return None
    spread_pct = (max(vals) - min(vals)) / closes[i] * 100
    prior_return_pct = (closes[i] - closes[i - 8]) / closes[i - 8] * 100
    return {
        "below_all_mas": closes[i] < min(vals),
        "above_all_mas": closes[i] > max(vals),
        "compressed": spread_pct < COMPRESSION_THRESHOLD * 100,
        "prior_falling": prior_return_pct < -0.5,
        "prior_rising": prior_return_pct > 0.5,
        "prior_flat": -0.5 <= prior_return_pct <= 0.5,
        "rsi_low": rsi[i] < 35,
        "rsi_mid": 35 <= rsi[i] <= 65,
        "rsi_high": rsi[i] > 65,
        "ma7_below_ma99": ma7[i] < ma99[i],
        "ma7_above_ma99": ma7[i] > ma99[i],
    }


def summarize(event_indices, valid_indices, closes, ma7, ma25, ma50, ma99, rsi):
    feature_names = ["below_all_mas", "above_all_mas", "compressed", "prior_falling",
                      "prior_rising", "prior_flat", "rsi_low", "rsi_mid", "rsi_high",
                      "ma7_below_ma99", "ma7_above_ma99"]
    event_feats = [build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in event_indices]
    event_feats = [f for f in event_feats if f is not None]
    if not event_feats:
        return {}
    baseline_feats = [build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in valid_indices]
    baseline_feats = [f for f in baseline_feats if f is not None]

    out = {}
    for name in feature_names:
        event_rate = sum(1 for f in event_feats if f[name]) / len(event_feats)
        base_rate = sum(1 for f in baseline_feats if f[name]) / len(baseline_feats) if baseline_feats else 0
        lift = (event_rate / base_rate) if base_rate > 0 else None
        out[name] = (event_rate, base_rate, lift)
    return out


def main():
    conn = sqlite3.connect(DB_PATH)
    candles = load_klines(conn, SYMBOL)
    n = len(candles)
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    print(f"{SYMBOL}: {n} velas de 15m | buscando rupturas >= {MOVE_THRESHOLD_PCT}% en {MOVE_WINDOW} velas ({MOVE_WINDOW*15}min)", flush=True)

    ma7 = sma_series(closes, 7)
    ma25 = sma_series(closes, 25)
    ma50 = sma_series(closes, 50)
    ma99 = sma_series(closes, 99)
    rsi = rsi_series(closes, RSI_PERIOD)

    up_events, down_events = detect_events(candles, closes, highs, lows)
    print(f"Eventos detectados: {len(up_events)} rupturas alcistas | {len(down_events)} rupturas bajistas", flush=True)

    valid_start, valid_end = 100, n - MOVE_WINDOW - 1
    mid = valid_start + (valid_end - valid_start) // 2
    all_valid = list(range(valid_start, valid_end))

    for label, events in [("RUPTURAS ALCISTAS (subio >=1.5%)", up_events), ("RUPTURAS BAJISTAS (cayo >=1.5%)", down_events)]:
        print("\n" + "=" * 100)
        print(label)
        print("=" * 100)
        ev1 = [i for i in events if i < mid]
        ev2 = [i for i in events if i >= mid]
        base1 = [i for i in all_valid if i < mid]
        base2 = [i for i in all_valid if i >= mid]
        s1 = summarize(ev1, base1, closes, ma7, ma25, ma50, ma99, rsi)
        s2 = summarize(ev2, base2, closes, ma7, ma25, ma50, ma99, rsi)

        print(f"{'Caracteristica ANTES del evento':28s} | {'1ra mitad (n='+str(len(ev1))+')':>26s} | {'2da mitad (n='+str(len(ev2))+')':>26s} | robusto?")
        for name in s1:
            r1, b1, l1 = s1[name]
            r2, b2, l2 = s2.get(name, (0, 0, None))
            robust = l1 is not None and l2 is not None and l1 > 1.25 and l2 > 1.25
            print(f"{name:28s} | tasa={r1*100:5.1f}% base={b1*100:5.1f}% lift={l1:.2f}x | tasa={r2*100:5.1f}% base={b2*100:5.1f}% lift={l2:.2f}x | {'SI' if robust else 'no'}")


if __name__ == "__main__":
    main()
