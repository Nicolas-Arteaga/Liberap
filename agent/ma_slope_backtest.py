"""
Backtest de "MA Slope Caso 3" (perfil id 9e00e6f3-45f2-e32b-b353-679e6d19f29c)
contra klines historicos limpios (agent/data/binance_vision_clean.db), SIN
look-ahead. Replica EXACTAMENTE la logica de produccion:

- verge_agent.py::_evaluate_ma_geometry_profile (grupos order/slope/touch/
  distanceBetweenMas/contextSlope/peakProximity/exit)
- verge_agent.py::_sma_series, _calculate_ma99_slope_angle, _normalized_slope_angle
- risk_manager.py: TP = max(RR objetivo * SL, min_tp_pct piso), rr_target=
  TpMultiplier del perfil (Trend/Mean Reversion caps NO aplican a ma_slope_mode
  porque set setup_type solo se usa para el cap, y ese cap es sobre rr_target
  ANTES del piso min_tp_pct — replicado igual)

PatternParamsJson real de "MA Slope Caso 3" (short-only, 1h):
  order: ma7>ma25>ma50>ma99 (situacion previa alcista)
  slope: ma7, ventana 3, giro de positivo (prior>=0.2) a negativo (current<=-0.2)
  peakProximity: precio actual a <=1% del maximo de las ultimas 10 velas
  exit: SL = maximo de ultimas 10 velas + 1% buffer, TP minimo 10%
  Perfil: TpMultiplier=3.0, SlMultiplier=0.8, MinRR=4.0 (veto si RR real < 4)

La DB limpia solo tiene 15m cacheado -> se resamplea a 1h agregando de a 4
velas alineadas a hora (no hay look-ahead: cada vela 1h se cierra recien
cuando cerraron sus 4 velas de 15m).

Uso: python ma_slope_backtest.py [--symbols N]
"""
import sys
import os
import sqlite3
import math
import argparse
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
TABLE = "klines_clean"
SRC_INTERVAL = "15m"

MIN_CANDLES = 150  # igual que MA_SLOPE_MIN_CANDLES en produccion
TP_MULTIPLIER = 3.0
SL_MULTIPLIER = 0.8
MIN_RR = 4.0
MIN_TP_PCT = 10.0
SL_BUFFER_PCT = 1.0
SL_LOOKBACK = 10
PEAK_LOOKBACK = 10
PEAK_TOL_PCT = 1.0
SLOPE_WINDOW = 3


def load_symbol_klines_15m(conn, symbol):
    cur = conn.cursor()
    cur.execute(
        f"SELECT open_time, open, high, low, close, volume FROM {TABLE} "
        "WHERE symbol=? AND interval=? ORDER BY open_time ASC",
        (symbol, SRC_INTERVAL),
    )
    return cur.fetchall()


def resample_to_1h(rows15):
    """Agrega de a 4 velas de 15m alineadas a la hora (open_time multiplo de
    3600000 ms) -> vela 1h. Descarta velas huerfanas al principio/final que
    no completan un bloque de 4, y bloques con gaps de tiempo (datos faltantes)."""
    HOUR_MS = 3600 * 1000
    buckets = {}
    for r in rows15:
        ot = r[0]
        bucket = ot - (ot % HOUR_MS)
        buckets.setdefault(bucket, []).append(r)

    out = []
    for bucket in sorted(buckets.keys()):
        group = sorted(buckets[bucket], key=lambda r: r[0])
        if len(group) != 4:
            continue
        # verificar que las 4 velas son contiguas (sin huecos)
        ok = all(group[i + 1][0] - group[i][0] == 15 * 60 * 1000 for i in range(3))
        if not ok:
            continue
        o = group[0][1]
        h = max(g[2] for g in group)
        l = min(g[3] for g in group)
        c = group[-1][4]
        v = sum(g[5] for g in group)
        out.append((bucket, o, h, l, c, v))
    return out


def sma_series(closes, period):
    if len(closes) < period:
        return []
    window_sum = sum(closes[:period])
    series = [window_sum / period]
    for i in range(period, len(closes)):
        window_sum += closes[i] - closes[i - period]
        series.append(window_sum / period)
    return series


def calculate_slope_angle(ma_values, window=12):
    if not ma_values or len(ma_values) < 2:
        return 0.0
    values = ma_values[-window:] if len(ma_values) >= window else ma_values
    n = len(values)
    if n < 2:
        return 0.0
    x = list(range(n))
    y = values
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    m = (n * sum_xy - sum_x * sum_y) / denom
    return math.degrees(math.atan(m))


def normalized_slope_angle(ma_values, window):
    if not ma_values:
        return 0.0
    base = ma_values[-1] if ma_values[-1] else 1.0
    normalized = [v / base * 100.0 for v in ma_values]
    return calculate_slope_angle(normalized, window=window)


def evaluate_candidate(closes, highs, lows, i):
    """i: indice de la vela 1h "actual" (ya cerrada). Devuelve dict candidato
    o None. Usa closes[:i+1] / highs[:i+1] / lows[:i+1] (nada del futuro)."""
    hist_closes = closes[: i + 1]
    hist_highs = highs[: i + 1]
    hist_lows = lows[: i + 1]

    if len(hist_closes) < MIN_CANDLES:
        return None

    ma7 = sma_series(hist_closes, 7)
    ma25 = sma_series(hist_closes, 25)
    ma50 = sma_series(hist_closes, 50)
    ma99 = sma_series(hist_closes, 99)
    if not ma7 or not ma25 or not ma50 or not ma99:
        return None

    ma7_now, ma25_now, ma50_now, ma99_now = ma7[-1], ma25[-1], ma50[-1], ma99[-1]

    # Grupo 1: orden ma7 > ma25 > ma50 > ma99 (Caso 3)
    if not (ma7_now > ma25_now and ma7_now > ma50_now and ma7_now > ma99_now):
        return None

    # Grupo 2: pendiente ma7, ventana 3: current<=-0.2 (giro bajista), prior>=0.2 (venia subiendo)
    current_slope = normalized_slope_angle(ma7, window=SLOPE_WINDOW)
    prior_slope = (
        normalized_slope_angle(ma7[:-SLOPE_WINDOW], window=SLOPE_WINDOW)
        if len(ma7) > SLOPE_WINDOW * 2 else 0.0
    )
    if not (current_slope <= -0.2):
        return None
    if not (prior_slope >= 0.2):
        return None

    # Grupo 6: peakProximity — precio actual a <=1% del maximo de ult. 10 velas
    current_price = hist_closes[-1]
    current_high = hist_highs[-1]
    extreme = max(hist_highs[-PEAK_LOOKBACK:])
    dist_pct = abs(current_price - extreme) / extreme * 100.0 if extreme else 999
    if dist_pct > PEAK_TOL_PCT:
        return None

    # Grupo 7: exit — SL = maximo de ult. 10 velas + 1% buffer (SHORT)
    sl_price = max(hist_highs[-SL_LOOKBACK:]) * (1 + SL_BUFFER_PCT / 100.0)

    return {
        "entry": current_price,
        "sl": sl_price,
        "current_high": current_high,
    }


def compute_tp(entry, sl_price):
    """Replica risk_manager.py: sl_distance = |entry-sl| (custom SL),
    tp_distance = sl_distance*rr_target, luego piso min_tp_pct."""
    sl_distance_price = abs(entry - sl_price)
    tp_distance_price = sl_distance_price * TP_MULTIPLIER
    min_tp_distance = entry * (MIN_TP_PCT / 100.0)
    if tp_distance_price < min_tp_distance:
        tp_distance_price = min_tp_distance
    tp_price = entry - tp_distance_price  # SHORT
    actual_rr = tp_distance_price / sl_distance_price if sl_distance_price > 0 else 0
    return tp_price, tp_distance_price, sl_distance_price, actual_rr


def backtest_symbol(symbol, rows1h):
    trades = []
    n = len(rows1h)
    if n < MIN_CANDLES + 20:
        return trades

    closes = [r[4] for r in rows1h]
    highs = [r[2] for r in rows1h]
    lows = [r[3] for r in rows1h]

    open_trade = None
    last_trade_day = None
    i = MIN_CANDLES

    while i < n:
        if open_trade:
            row = rows1h[i]
            h, l = row[2], row[3]
            if l <= open_trade["tp"]:
                trades.append({**open_trade, "close_reason": "TP", "close_time": row[0]})
                open_trade = None
            elif h >= open_trade["sl"]:
                trades.append({**open_trade, "close_reason": "SL", "close_time": row[0]})
                open_trade = None
            else:
                i += 1
                continue

        day_key = datetime.utcfromtimestamp(rows1h[i][0] / 1000).date()
        if last_trade_day == day_key:
            i += 1
            continue  # anti-churn: 1 entrada por dia por simbolo, igual que produccion

        cand = evaluate_candidate(closes, highs, lows, i)
        if not cand:
            i += 1
            continue

        tp_price, tp_dist, sl_dist, actual_rr = compute_tp(cand["entry"], cand["sl"])

        # MinRR veto del perfil (4.0) — igual que risk_manager.py fix 2026-07-25
        if actual_rr < MIN_RR:
            i += 1
            continue

        open_trade = {
            "symbol": symbol,
            "open_time": rows1h[i][0],
            "entry": cand["entry"],
            "sl": cand["sl"],
            "tp": tp_price,
            "rr": round(actual_rr, 2),
        }
        last_trade_day = day_key
        i += 1

    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=428)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"SELECT symbol, COUNT(*) n FROM {TABLE} WHERE interval=? GROUP BY symbol ORDER BY n DESC LIMIT ?",
        (SRC_INTERVAL, args.symbols),
    )
    symbols = [r[0] for r in cur.fetchall()]
    print(f">>> Backtesting MA Slope Caso 3 (SHORT, 1h) sobre {len(symbols)} simbolos", flush=True)

    all_trades = []
    for idx, sym in enumerate(symbols):
        rows15 = load_symbol_klines_15m(conn, sym)
        rows1h = resample_to_1h(rows15)
        trades = backtest_symbol(sym, rows1h)
        all_trades.extend(trades)
        if (idx + 1) % 20 == 0:
            print(f"  [{idx+1}/{len(symbols)}] {sym}: {len(trades)} trades (total acumulado={len(all_trades)})", flush=True)

    wins = [t for t in all_trades if t["close_reason"] == "TP"]
    losses = [t for t in all_trades if t["close_reason"] == "SL"]
    print()
    print("=== RESULTADO FINAL ===")
    print(f"Total trades: {len(all_trades)}")
    print(f"Wins (TP): {len(wins)} | Losses (SL): {len(losses)}")
    if all_trades:
        wr = len(wins) / len(all_trades) * 100
        print(f"Win rate: {wr:.1f}%")

    out_path = os.path.join(os.path.dirname(__file__), "ma_slope_case3_backtest_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=2, default=str)
    print(f"Guardado: {out_path}")


if __name__ == "__main__":
    main()
