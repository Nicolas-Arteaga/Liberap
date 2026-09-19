"""
2026-08-21: hipotesis nueva, sacada de leer el codigo REAL de FVG a fondo
(python-service/fvg/analyzer.py::_liquidity_target) -- lo que distingue a
FVG de TODO lo que se probo esta semana no es (solo) que compite contra el
universo completo (eso ya se probo clonado y fallo, ver ml_lab_ranked.py /
universal_confluence_scanner.py) sino que su TP nunca es un multiplo fijo
de ATR: es el nivel de liquidez real (swing high/low que dejo el impulso),
con deteccion de "impulso viejo desproporcionado" (si el extremo de toda
la ventana es mucho mas lejos que el alcance de la pata reciente, el
objetivo pasa a ser solo la mitad del camino restante) y un haircut del
10% siempre (nunca apunta al 100% del nivel "obvio").

Esto aplica esa MISMA logica de TP a Level Sweep (barrido de nivel +
reclaim) en vez de su TP generico ATR x RR_mult -- son conceptualmente
parecidos (los dos son "el precio barrio un nivel"), nunca se probo
combinarlos. Motor honesto de siempre: vetos reales + 3 cupos x $150,
mismo periodo real completo, split cronologico para chequear estabilidad.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, load_15m, resample, atr_series, detect_signal, DB_PATH,
    MARGIN, FEE, _apply_capital_sim, _build_validate_candidate, evaluate,
)
from setup_validator import validate_pre_trade  # noqa: E402

RECENT_IMPULSE_LOOKBACK = 40
DISPROPORTION_RATIO = 1.5
FADING_IMPULSE_TARGET_RATIO = 0.5
TP_HAIRCUT_RATIO = 0.9
FULL_WINDOW = 200  # misma ventana que usa FVG real (limit=200 velas)

STRAT = dict(entry_type="level_sweep", tf_min=15, side="SHORT", atr_sl_mult=3.0, lookback=10)


def liquidity_tp(closes, highs, lows, i, side, entry):
    """side: 1=SHORT (busca minimo), 0=LONG (busca maximo). Misma logica
    que FvgAnalyzer._liquidity_target, adaptada a listas planas en vez de
    DataFrame -- ventana de las ultimas FULL_WINDOW velas hasta i (nunca mira
    el futuro)."""
    start = max(0, i - FULL_WINDOW)
    window_highs = highs[start:i + 1]
    window_lows = lows[start:i + 1]
    recent_start = max(start, i - RECENT_IMPULSE_LOOKBACK)
    recent_highs = highs[recent_start:i + 1]
    recent_lows = lows[recent_start:i + 1]

    if side == 0:  # LONG -- objetivo hacia arriba
        entry_edge = entry
        swing_high = max(window_highs)
        local_high = max(recent_highs)
        if swing_high <= entry_edge or local_high <= entry_edge:
            return None  # sin nivel de liquidez real por encima, no hay TP valido
        local_reach = local_high - entry_edge
        full_reach = swing_high - entry_edge
        if full_reach > local_reach * DISPROPORTION_RATIO:
            raw_target = entry_edge + full_reach * FADING_IMPULSE_TARGET_RATIO
        else:
            raw_target = swing_high
        return entry_edge + (raw_target - entry_edge) * TP_HAIRCUT_RATIO
    else:  # SHORT -- objetivo hacia abajo
        entry_edge = entry
        swing_low = min(window_lows)
        local_low = min(recent_lows)
        if swing_low >= entry_edge or local_low >= entry_edge:
            return None
        local_reach = entry_edge - local_low
        full_reach = entry_edge - swing_low
        if full_reach > local_reach * DISPROPORTION_RATIO:
            raw_target = entry_edge - full_reach * FADING_IMPULSE_TARGET_RATIO
        else:
            raw_target = swing_low
        return entry_edge - (entry_edge - raw_target) * TP_HAIRCUT_RATIO


def backtest_liquidity_tp(conn, basket, apply_vetos=True, tf_min=15):
    lb = STRAT["lookback"]
    all_trades = []
    for symbol in basket:
        rows15 = load_15m(conn, symbol)
        if len(rows15) < 400:
            continue
        candles = resample(rows15, tf_min) if tf_min != 15 else rows15
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        atr_arr = atr_series(candles, 14)

        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr_arr[i]
            if a is None or a <= 0:
                continue
            if open_trade:
                side = open_trade["side"]
                hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
                hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = MARGIN / open_trade["entry"]
                    gross = qty * (open_trade["entry"] - close_px) if side == 1 else qty * (close_px - open_trade["entry"])
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({"symbol": symbol, "pnl": gross - fees,
                                        "open_time": open_trade["open_time"], "close_time": ts})
                    open_trade = None
                continue

            level_high = max(highs[i - lb:i]) if i >= lb else None
            level_low = min(lows[i - lb:i]) if i >= lb else None
            sig = detect_signal(STRAT, closes, highs, lows, i, level_high, level_low, None)
            if sig is None or sig != 1:  # SHORT-only: LONG probado y confirmado peor (-$42.98/mes vs +$21.08/mes)
                continue

            entry = c
            sl_dist = STRAT["atr_sl_mult"] * a
            sl = entry + sl_dist if sig == 1 else entry - sl_dist
            tp = liquidity_tp(closes, highs, lows, i, sig, entry)
            if tp is None or (sig == 1 and tp >= entry) or (sig == 0 and tp <= entry):
                continue  # sin nivel de liquidez real utilizable, descartar la señal

            if apply_vetos:
                candidate = _build_validate_candidate(STRAT, symbol, sig, entry, sl_dist)
                try:
                    v_ok, _, _ = validate_pre_trade(candidate, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue

            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}

    return _apply_capital_sim(all_trades)


def main():
    global RECENT_IMPULSE_LOOKBACK, TP_HAIRCUT_RATIO, DISPROPORTION_RATIO
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days = (t1 - t0) / (1000 * 60 * 60 * 24)
    print(f"Universo: {len(basket)} simbolos | {days:.0f} dias reales | Level Sweep 15m SHORT + TP de liquidez real (estilo FVG)")

    # Config estable encontrada (disprop=1.2) -- probando ahora en distintos
    # timeframes a ver si escala el $/mes sin perder la estabilidad.
    RECENT_IMPULSE_LOOKBACK = 40
    TP_HAIRCUT_RATIO = 0.9
    DISPROPORTION_RATIO = 1.2
    for tf_min in (15, 60, 240):
        trades = backtest_liquidity_tp(conn, basket, apply_vetos=True, tf_min=tf_min)
        res = evaluate(trades, days)
        print(f"tf={tf_min}m disprop=1.2 -> "
              f"n={res.get('n')} WR={res.get('wr_pct')}% $/mes={res.get('monthly')} "
              f"h1={res.get('pnl_h1')} h2={res.get('pnl_h2')} passes_bar={res.get('passes_bar')} "
              f"stable={res.get('stable_between_halves')}", flush=True)


if __name__ == "__main__":
    main()
