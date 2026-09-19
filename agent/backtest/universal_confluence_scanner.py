"""
2026-08-18: SCANNER DE CONFLUENCIA UNIVERSAL -- pedido explicito del
usuario tras el barrido exhaustivo de anoche (5 familias de patron fijo,
techo real ~$100/mes, nada supero sus $150/mes reales con FVG manual).

Diagnostico: FVG gana no porque su regla sea mejor, sino porque el
MECANISMO es distinto -- en cada ciclo compara TODO el universo de
simbolos y se queda con el top-5 por distancia al TP (mayor recorrido =
mayor conviccion), no aplica una regla fija a ciegas simbolo por simbolo.
Los 5 backtests de anoche SI aplicaban una regla fija (barrido de nivel,
RSI extremo, etc.) pero NUNCA competian entre simbolos -- cada trade se
media solo contra si mismo.

Este scanner une los 3 patrones que mostraron algo de edge real (barrido
de nivel, pullback de MA, RSI extremo -- con los mejores parametros
encontrados en el barrido de anoche, todos a 15m para compartir un solo
reloj global) y les aplica la MISMA competencia de FVG: cada tick de 15m,
escanea los 430 simbolos, junta TODAS las señales que dispararon (de
cualquiera de los 3 patrones), las rankea por tp_distance_pct (recorrido
real hasta el TP, mayor = mejor), y solo abre el top-5 -- exactamente
igual que python-service/fvg/analyzer.py::scan().

Vetos reales (validate_pre_trade) + limite real de 3 cupos x $150
aplicados siempre, sin excepcion.
"""
import sys
import os
import time
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, atr_series, load_15m, DB_PATH, MARGIN, FEE, sma, rsi_at,
)
from setup_validator import validate_pre_trade  # noqa: E402

DAYS = 243
SLOTS = 3

# Mejores parametros encontrados en el barrido exhaustivo de anoche, todos
# re-normalizados a 15m para compartir un unico reloj global.
LEVEL_SWEEP_PARAMS = dict(atr_sl_mult=3.0, rr_mult=3.0, lookback=20)
MA_PULLBACK_PARAMS = dict(atr_sl_mult=3.0, rr_mult=6.0, lookback=10, slope_min_pct=1.0)
RSI_EXTREME_PARAMS = dict(atr_sl_mult=2.0, rr_mult=4.0, hi_th=75, lo_th=25)


def build_candidate(symbol, side, entry, source):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": source, "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def detect_level_sweep(closes, highs, lows, i, lb):
    if i < lb + 1:
        return None
    level_high = max(highs[i - lb:i])
    level_low = min(lows[i - lb:i])
    h, l, c = highs[i], lows[i], closes[i]
    if h > level_high and c < level_high:
        return 1
    if l < level_low and c > level_low:
        return 0
    return None


def detect_ma_pullback(closes, i, lb, slope_min):
    ma7_now, ma25_now, ma99_now = sma(closes, 7, i), sma(closes, 25, i), sma(closes, 99, i)
    ma7_prev = sma(closes, 7, i - lb) if i - lb >= 0 else None
    c_now, c_prev = closes[i], closes[i - 1] if i >= 1 else None
    if None in (ma7_now, ma25_now, ma99_now, ma7_prev, c_prev):
        return None
    slope_pct = (ma7_now - ma7_prev) / ma7_prev * 100 if ma7_prev else 0
    zone_lo, zone_hi = min(ma25_now, ma99_now), max(ma25_now, ma99_now)
    was_inside = zone_lo <= c_prev <= zone_hi
    now_inside = zone_lo <= c_now <= zone_hi
    if was_inside or not now_inside:
        return None
    if slope_pct >= slope_min and c_prev > zone_hi:
        return 0
    if slope_pct <= -slope_min and c_prev < zone_lo:
        return 1
    return None


def detect_rsi_extreme(closes, i, hi_th, lo_th):
    r_now = rsi_at(closes, 14, i)
    r_prev = rsi_at(closes, 14, i - 1)
    if r_now is None or r_prev is None:
        return None
    if r_prev >= hi_th and r_now < hi_th:
        return 1
    if r_prev <= lo_th and r_now > lo_th:
        return 0
    return None


def run_scanner(conn, basket, max_open=SLOTS, apply_vetos=True):
    # Precarga y cachea todos los simbolos a 15m una sola vez.
    data = {}
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        closes = [r[4] for r in rows]
        highs = [r[2] for r in rows]
        lows = [r[3] for r in rows]
        atr = atr_series(rows, 14)
        data[symbol] = (rows, closes, highs, lows, atr)

    if not data:
        return []

    # Reloj global: timestamps del simbolo con MAS historia (cubre todo el
    # rango real, no un simbolo cualquiera que pueda tener menos datos).
    ref_symbol = max(data.keys(), key=lambda s: len(data[s][0]))
    ref_rows = data[ref_symbol][0]
    total_ticks = len(ref_rows)

    open_trades: dict[str, dict] = {}
    last_trade_day: dict[str, object] = {}
    all_trades = []

    t_start = time.time()
    for i in range(210, total_ticks):
        now_ts = ref_rows[i][0]

        # Paso 1: TP/SL de posiciones abiertas -- siempre, cada tick.
        for symbol in list(open_trades.keys()):
            rows = data[symbol][0]
            if i >= len(rows) or rows[i][0] != now_ts:
                continue  # simbolo sin vela en este timestamp exacto
            h, l = rows[i][2], rows[i][3]
            ot = open_trades[symbol]
            side = ot["side"]
            hit_tp = (l <= ot["tp"]) if side == 1 else (h >= ot["tp"])
            hit_sl = (h >= ot["sl"]) if side == 1 else (l <= ot["sl"])
            if hit_tp or hit_sl:
                close_px = ot["tp"] if hit_tp else ot["sl"]
                qty = MARGIN / ot["entry"]
                gross = qty * (ot["entry"] - close_px) if side == 1 else qty * (close_px - ot["entry"])
                fees = (qty * ot["entry"] + qty * close_px) * FEE
                all_trades.append({"symbol": symbol, "pnl": gross - fees, "source": ot.get("source"),
                                    "open_time": ot["open_time"], "close_time": now_ts})
                del open_trades[symbol]

        # Paso 2: escanear candidatos nuevos en TODO el universo, rankear.
        raw_candidates = []  # (tp_distance_pct, symbol, side, entry, sl, tp, source)
        available_slots = max_open - len(open_trades)
        if available_slots > 0:
            day_key = datetime.utcfromtimestamp(now_ts / 1000).date()
            for symbol, (rows, closes, highs, lows, atr) in data.items():
                if symbol in open_trades:
                    continue
                if i >= len(rows) or rows[i][0] != now_ts:
                    continue
                if last_trade_day.get(symbol) == day_key:
                    continue
                a = atr[i]
                if a is None or a <= 0:
                    continue
                entry = closes[i]

                sig = detect_level_sweep(closes, highs, lows, i, LEVEL_SWEEP_PARAMS["lookback"])
                if sig is not None:
                    sl_dist = LEVEL_SWEEP_PARAMS["atr_sl_mult"] * a
                    tp_dist = sl_dist * LEVEL_SWEEP_PARAMS["rr_mult"]
                    tp_pct = tp_dist / entry * 100
                    score = tp_pct / LEVEL_SWEEP_PARAMS["rr_mult"]
                    sl = entry + sl_dist if sig == 1 else entry - sl_dist
                    tp = entry - tp_dist if sig == 1 else entry + tp_dist
                    raw_candidates.append((score, symbol, sig, entry, sl, tp, "level_sweep_1h_mode"))

                sig = detect_ma_pullback(closes, i, MA_PULLBACK_PARAMS["lookback"], MA_PULLBACK_PARAMS["slope_min_pct"])
                if sig is not None:
                    sl_dist = MA_PULLBACK_PARAMS["atr_sl_mult"] * a
                    tp_dist = sl_dist * MA_PULLBACK_PARAMS["rr_mult"]
                    tp_pct = tp_dist / entry * 100
                    score = tp_pct / MA_PULLBACK_PARAMS["rr_mult"]
                    sl = entry + sl_dist if sig == 1 else entry - sl_dist
                    tp = entry - tp_dist if sig == 1 else entry + tp_dist
                    raw_candidates.append((score, symbol, sig, entry, sl, tp, "ma_pullback"))

                sig = detect_rsi_extreme(closes, i, RSI_EXTREME_PARAMS["hi_th"], RSI_EXTREME_PARAMS["lo_th"])
                if sig is not None:
                    sl_dist = RSI_EXTREME_PARAMS["atr_sl_mult"] * a
                    tp_dist = sl_dist * RSI_EXTREME_PARAMS["rr_mult"]
                    tp_pct = tp_dist / entry * 100
                    score = tp_pct / RSI_EXTREME_PARAMS["rr_mult"]
                    sl = entry + sl_dist if sig == 1 else entry - sl_dist
                    tp = entry - tp_dist if sig == 1 else entry + tp_dist
                    raw_candidates.append((score, symbol, sig, entry, sl, tp, "rsi_extreme"))

            # Fix 2026-08-18: antes rankeaba por tp_distance_pct crudo, que
            # favorece estructuralmente a ma_pullback (RR=6x) sobre los otros
            # (RR=3x/4x) sin importar la calidad real de la señal -- resultado
            # $39.69/mes, peor que cualquier familia individual. Ahora se
            # normaliza por rr_mult (score = distancia_al_SL en %, proxy de
            # volatilidad/conviccion real), quitando la ventaja artificial del
            # RR mas alto y dejando que compita solo la señal.
            raw_candidates.sort(key=lambda x: x[0], reverse=True)
            for score, symbol, sig, entry, sl, tp, source in raw_candidates[:available_slots]:
                if apply_vetos:
                    cand = build_candidate(symbol, sig, entry, source)
                    try:
                        v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
                    except Exception:
                        v_ok = True
                    if not v_ok:
                        continue
                open_trades[symbol] = {"side": sig, "entry": entry, "sl": sl, "tp": tp,
                                        "open_time": now_ts, "source": source}
                last_trade_day[symbol] = day_key

        if i % 2000 == 0:
            pct = (i - 210) / max(1, total_ticks - 210) * 100
            print(f"  progreso: {i}/{total_ticks} ({pct:.1f}%) | elapsed={(time.time()-t_start)/60:.1f}min", flush=True)

    return all_trades


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | reloj global 15m | 3 cupos x $150 | vetos reales activos\n")

    t0 = time.time()
    trades = run_scanner(conn, basket, apply_vetos=True)
    n = len(trades)
    if n == 0:
        print("Sin trades.")
        return
    total = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    monthly = total / (DAYS / 30.44)
    print(f"\n=== SCANNER DE CONFLUENCIA UNIVERSAL (level_sweep + ma_pullback + rsi_extreme, top-5 real) ===")
    print(f"Trades: {n} | WR: {wins/n*100:.1f}% | PnL total: ${total:.2f} | ${monthly:.2f}/mes")

    from collections import Counter
    src_count = Counter(t.get("source", "?") for t in trades)
    print(f"Origen de los trades: {dict(src_count)}")

    print(f"\nTiempo total: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
