"""
ArrowPeakBacktest — replay de ARROW REVERSAL (Arrow Peak, siempre SHORT)
contra klines históricos ya cacheados, reusando la MISMA lógica de
detección que corre en vivo (python-service/nexus15/arrow_peak_analyzer.py
::_analyze_symbol, portada acá función por función) — para saber si el
100% de precisión visto en Historial (6 trades reales desde el 12/07) es
un edge real o una racha de muestra chica, y si depende del régimen de BTC
(el usuario notó que tanto Arrow Reversal como MA Slope Caso 3 vienen
ganando en un contexto de BTC bajista/lateral — Arrow Peak es SHORT-only
siempre, así que tiene sentido sospechar dependencia de régimen).

No hay velas 1D cacheadas (solo 1 símbolo, 9 velas) — se reconstruyen
agregando las velas de 1h por día calendario UTC real (no un bucket fijo de
24, para tolerar huecos reales del caché): open=primera, high=max, low=min,
close=última, volume=suma. Es resampling estándar, no un hack.

Uso:
    python arrow_peak_backtest.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
    python arrow_peak_backtest.py  (corre contra todos los símbolos con historia suficiente)
"""
import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from kline_cache import get_cache
from backtest_engine import BacktestTrade, BacktestResult

SL_BUFFER_PCT = 1.0
TP_BUFFER_PCT = 2.0
TP_MIN_DISTANCE_PCT = 10.0
MIN_1H_CANDLES = 24 * 20  # ~20 días reales para tener margen de sobra sobre los 10-15 días que pide el patrón


def _build_daily_from_1h(klines_1h: list) -> list:
    """Agrupa velas de 1h por día calendario UTC. Devuelve velas diarias ordenadas, oldest first."""
    buckets = defaultdict(list)
    for k in klines_1h:
        day = datetime.fromtimestamp(k["open_time"] / 1000, tz=timezone.utc).date()
        buckets[day].append(k)

    daily = []
    for day in sorted(buckets.keys()):
        candles = buckets[day]
        daily.append({
            "day": day,
            "open_time": candles[0]["open_time"],
            "open": candles[0]["open"],
            "high": max(c["high"] for c in candles),
            "low": min(c["low"] for c in candles),
            "close": candles[-1]["close"],
            "volume": sum(c["volume"] for c in candles),
        })
    return daily


def _detect_arrow_peak(daily: list, as_of_idx: int):
    """
    Puerto directo de ArrowPeakAnalyzer._analyze_symbol (pasos 1-4, sin el
    fetch HTTP) — usa SOLO daily[:as_of_idx+1] (días ya cerrados hasta ese
    punto, sin lookahead). Devuelve dict con peak_price/arrow_start_price/
    bleeding_days o None si no califica.
    """
    if as_of_idx < 14:
        return None
    window = daily[max(0, as_of_idx - 29): as_of_idx + 1]
    if len(window) < 15:
        return None

    last_10 = window[-10:]
    peak_i_local = max(range(len(last_10)), key=lambda i: last_10[i]["high"])
    peak_global_idx = len(window) - 10 + peak_i_local
    peak_price = window[peak_global_idx]["high"]

    before_peak = window[:peak_global_idx + 1]
    n_before = len(before_peak)

    is_clean_arrow = False
    prev_rise_pct = 0.0
    arrow_start_price = 0.0
    for end_pos in (n_before, n_before - 1):
        if is_clean_arrow:
            break
        for length in (5, 4, 3):
            start_pos = end_pos - length
            if start_pos < 0:
                continue
            sub = before_peak[start_pos:end_pos]
            if all(c["close"] > c["open"] for c in sub):
                first_open = sub[0]["open"]
                rise_pct = (peak_price - first_open) / first_open * 100
                if rise_pct >= 20.0:
                    is_clean_arrow = True
                    prev_rise_pct = rise_pct
                    arrow_start_price = float(first_open)
                    break
    if not is_clean_arrow:
        return None

    after_peak = window[peak_global_idx + 1:]
    if len(after_peak) < 1:
        return None
    if not all(c["close"] < c["open"] for c in after_peak):
        return None
    bleeding_days = len(after_peak)
    if bleeding_days < 1 or bleeding_days > 3:
        return None

    return {
        "peak_price": peak_price,
        "arrow_start_price": arrow_start_price,
        "prev_rise_pct": prev_rise_pct,
        "bleeding_days": bleeding_days,
    }


def _ema(values: list, span: int) -> list:
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def run_arrow_peak_backtest(symbol: str, fee_pct: float = 0.0) -> BacktestResult:
    cache = get_cache()
    klines_1h = cache.get_klines(symbol, "1h", limit=100_000)
    klines_15m = cache.get_klines(symbol, "15m", limit=100_000)
    result = BacktestResult(profile_name="Arrow Reversal", symbol=symbol)
    result.candles_available = len(klines_15m)

    if len(klines_1h) < MIN_1H_CANDLES or len(klines_15m) < 110:
        return result

    daily = _build_daily_from_1h(klines_1h)
    if len(daily) < 15:
        return result

    closes_15m = [k["close"] for k in klines_15m]
    highs_15m = [k["high"] for k in klines_15m]
    lows_15m = [k["low"] for k in klines_15m]
    opens_15m = [k["open"] for k in klines_15m]
    ma99_series = _ema(closes_15m, 99)

    # Índice del día calendario de cada vela 15m (para saber qué días diarios ya cerraron)
    day_index_by_ts = {d["day"]: i for i, d in enumerate(daily)}
    day_list = [d["day"] for d in daily]

    open_trade: Optional[BacktestTrade] = None
    n = len(klines_15m)
    i = 100
    while i < n:
        if open_trade:
            hi, lo = highs_15m[i], lows_15m[i]
            if hi >= open_trade.sl_price:
                open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.sl_price, "SL"
            elif lo <= open_trade.tp_price:
                open_trade.exit_idx, open_trade.exit_price, open_trade.exit_reason = i, open_trade.tp_price, "TP"
            if open_trade.exit_price is not None:
                open_trade.pnl_pct = (open_trade.entry_price - open_trade.exit_price) / open_trade.entry_price * 100.0
                open_trade.pnl_pct -= fee_pct
                result.trades.append(open_trade)
                open_trade = None
            i += 1
            continue

        candle_day = datetime.fromtimestamp(klines_15m[i]["open_time"] / 1000, tz=timezone.utc).date()
        # Último día calendario estrictamente ANTERIOR a la vela actual, ya cerrado — sin lookahead
        prior_days = [d for d in day_list if d < candle_day]
        if len(prior_days) < 15:
            i += 1
            continue
        as_of_idx = day_index_by_ts[prior_days[-1]]

        pattern = _detect_arrow_peak(daily, as_of_idx)
        if pattern:
            dist_ma99_pct = (closes_15m[i] - ma99_series[i]) / ma99_series[i] * 100
            is_red = closes_15m[i] < opens_15m[i]
            prev_was_green = closes_15m[i - 1] > opens_15m[i - 1]
            red_bigger = is_red and prev_was_green and abs(closes_15m[i] - opens_15m[i]) > abs(closes_15m[i - 1] - opens_15m[i - 1])
            touches_ma99 = abs(dist_ma99_pct) < 0.5
            if touches_ma99 and red_bigger:
                entry_price = closes_15m[i]
                sl_price = pattern["peak_price"] * (1 + SL_BUFFER_PCT / 100.0)
                custom_tp = pattern["arrow_start_price"] * (1 + TP_BUFFER_PCT / 100.0)
                if custom_tp >= entry_price:
                    custom_tp = None
                if custom_tp is not None:
                    tp_price = custom_tp
                else:
                    tp_price = entry_price * (1 - TP_MIN_DISTANCE_PCT / 100.0)
                if sl_price > entry_price:  # sanity check, side=SHORT
                    open_trade = BacktestTrade(symbol, 1, i, entry_price, sl_price, tp_price)
                    open_trade.entry_time_ms = klines_15m[i]["open_time"]  # para alinear régimen de BTC por timestamp real, no por índice
        i += 1

    return result


def classify_btc_regime(btc_by_ts: dict, btc_sorted_ts: list, entry_time_ms: int, lookback_days: int = 7) -> str:
    """
    % de cambio de BTC en los lookback_days previos al timestamp REAL de
    entrada (no por índice de lista — cada símbolo tiene su propia historia
    con distinto largo/inicio, comparar por índice cruzaría mal los datos).
    'down'/'up'/'flat'/'unknown' (si no hay BTC cacheado para ese rango).
    """
    import bisect
    lookback_ms = lookback_days * 24 * 3600 * 1000
    now_idx = bisect.bisect_right(btc_sorted_ts, entry_time_ms) - 1
    start_idx = bisect.bisect_right(btc_sorted_ts, entry_time_ms - lookback_ms) - 1
    if now_idx < 0 or start_idx < 0 or now_idx >= len(btc_sorted_ts):
        return "unknown"
    start_close = btc_by_ts[btc_sorted_ts[start_idx]]
    now_close = btc_by_ts[btc_sorted_ts[now_idx]]
    chg = (now_close - start_close) / start_close * 100
    if chg <= -3.0:
        return "down"
    if chg >= 3.0:
        return "up"
    return "flat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=None, help="Coma-separado; si se omite, corre contra todos los símbolos con historia suficiente")
    ap.add_argument("--fee-pct", type=float, default=0.08, help="Fee ida+vuelta, %% (default 0.08 ~ taker Binance futures)")
    args = ap.parse_args()

    cache = get_cache()
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = cache.get_symbols_with_history("1h", min_candles=MIN_1H_CANDLES)

    btc_klines = cache.get_klines("BTCUSDT", "15m", limit=100_000)
    btc_by_ts = {k["open_time"]: k["close"] for k in btc_klines}
    btc_sorted_ts = sorted(btc_by_ts.keys())

    all_trades = []
    per_symbol = []
    for idx, symbol in enumerate(symbols):
        res = run_arrow_peak_backtest(symbol, fee_pct=args.fee_pct)
        if res.closed:
            per_symbol.append(res.summary())
            all_trades.extend(res.closed)
        if (idx + 1) % 50 == 0:
            print(f"[ArrowPeakBacktest] {idx + 1}/{len(symbols)} símbolos procesados...")

    if not all_trades:
        print("[ArrowPeakBacktest] Ningún trade generado en todo el universo probado.")
        return

    wins = [t for t in all_trades if t.pnl_pct and t.pnl_pct > 0]
    losses = [t for t in all_trades if t.pnl_pct and t.pnl_pct <= 0]
    total_win = sum(t.pnl_pct for t in wins)
    total_loss = abs(sum(t.pnl_pct for t in losses))
    pf = (total_win / total_loss) if total_loss > 0 else (float("inf") if total_win > 0 else 0.0)

    print(f"\n=== ARROW REVERSAL BACKTEST — {len(symbols)} símbolos, {len(all_trades)} trades totales ===")
    print(f"Win rate: {len(wins)}/{len(all_trades)} = {len(wins)/len(all_trades)*100:.1f}%")
    print(f"Profit factor: {pf:.2f}")
    print(f"PnL total: {sum(t.pnl_pct for t in all_trades):.2f}%")

    # Split por régimen de BTC en el momento REAL (timestamp) de cada entrada —
    # responde la pregunta real del usuario: ¿Arrow Reversal depende de que BTC esté bajista?
    regime_buckets = defaultdict(list)
    for t in all_trades:
        ts = getattr(t, "entry_time_ms", None)
        regime = classify_btc_regime(btc_by_ts, btc_sorted_ts, ts) if ts else "unknown"
        regime_buckets[regime].append(t)

    print("\n--- Split por régimen de BTC en el momento de cada entrada ---")
    for regime in ("down", "flat", "up", "unknown"):
        trades = regime_buckets.get(regime, [])
        if not trades:
            continue
        w = [t for t in trades if t.pnl_pct and t.pnl_pct > 0]
        l = [t for t in trades if t.pnl_pct and t.pnl_pct <= 0]
        tw = sum(t.pnl_pct for t in w)
        tl = abs(sum(t.pnl_pct for t in l))
        pf_r = (tw / tl) if tl > 0 else (float("inf") if tw > 0 else 0.0)
        print(f"  BTC {regime:8s}: {len(trades)} trades | win_rate={len(w)/len(trades)*100:.1f}% | PF={pf_r:.2f}")

    print("\n--- Top símbolos por cantidad de trades ---")
    for s in sorted(per_symbol, key=lambda x: -x["total_trades"])[:15]:
        print(f"  {s['symbol']}: {s['total_trades']} trades, win_rate={s['win_rate_pct']}%, PF={s['profit_factor']}")


if __name__ == "__main__":
    main()
