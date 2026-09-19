"""
2026-08-21: pieza de FVG que todavia no se habia probado -- el perfil de
VOLUMEN (POC/HVN, python-service/fvg/volume_profile.py). FVG no solo usa un
TP de liquidez real (ya probado en level_sweep_liquidity_tp.py, $9.79/mes
estable) -- tambien exige que la zona de entrada este cerca de un nodo de
alto volumen (HVN, >=70% del volumen del POC) como filtro de confluencia
real (donde REALMENTE se negocio, no solo donde el precio toco un maximo/
minimo). Nunca se aplico esta pieza a ninguna otra estrategia.

Reusa la config ya estable de Level Sweep (TP de liquidez, disprop=1.2) y
le agrega: solo tomar la señal si el precio de entrada esta a <=X% de
distancia de un HVN real (mismo perfil de volumen de 200 velas que usa FVG).
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, load_15m, atr_series, detect_signal, DB_PATH,
    MARGIN, FEE, _apply_capital_sim, _build_validate_candidate, evaluate,
)
import backtest.level_sweep_liquidity_tp as lstp  # noqa: E402
from backtest.level_sweep_liquidity_tp import liquidity_tp, STRAT  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

lstp.DISPROPORTION_RATIO = 1.2
lstp.TP_HAIRCUT_RATIO = 0.9
lstp.RECENT_IMPULSE_LOOKBACK = 40

VP_WINDOW = 200
BIN_COUNT = 60
HVN_RATIO = 0.7
MAX_POC_DIST_PCT = 0.5  # mismo umbral que ENTRY_APPROACH_PCT real de FVG


def hvn_bins(highs_window, lows_window, vols_window, bin_count=BIN_COUNT):
    price_min = min(lows_window)
    price_max = max(highs_window)
    if price_max <= price_min:
        return [], 0.0
    bin_size = (price_max - price_min) / bin_count
    bin_volumes = [0.0] * bin_count
    for low, high, vol in zip(lows_window, highs_window, vols_window):
        candle_range = high - low
        if candle_range <= 0:
            idx = min(max(int((high - price_min) / bin_size), 0), bin_count - 1)
            bin_volumes[idx] += vol
            continue
        first_bin = max(0, int((low - price_min) / bin_size))
        last_bin = min(bin_count - 1, int((high - price_min) / bin_size))
        for b in range(first_bin, last_bin + 1):
            bin_low = price_min + b * bin_size
            bin_high = bin_low + bin_size
            overlap = min(high, bin_high) - max(low, bin_low)
            if overlap > 0:
                bin_volumes[b] += vol * (overlap / candle_range)
    poc_volume = max(bin_volumes) if bin_volumes else 0.0
    hvns = []
    for b in range(bin_count):
        if poc_volume > 0 and bin_volumes[b] >= HVN_RATIO * poc_volume:
            bin_low = price_min + b * bin_size
            bin_high = bin_low + bin_size
            hvns.append((bin_low, bin_high))
    return hvns, poc_volume


def dist_to_nearest_hvn_pct(entry_price, hvns):
    if not hvns:
        return 999.0
    best = None
    for lo, hi in hvns:
        if lo <= entry_price <= hi:
            return 0.0
        dist = (lo - entry_price) if entry_price < lo else (entry_price - hi)
        dist_pct = abs(dist) / entry_price * 100.0
        if best is None or dist_pct < best:
            best = dist_pct
    return best


def backtest(conn, basket, apply_vetos=True, apply_poc_filter=True):
    lb = STRAT["lookback"]
    all_trades = []
    n_signals, n_poc_pass = 0, 0
    import time
    t_start = time.time()
    for si, symbol in enumerate(basket):
        rows15 = load_15m(conn, symbol)
        if len(rows15) < 400:
            continue
        candles = rows15
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        vols = [c[5] for c in candles]
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
            if sig is None or sig != 1:
                continue
            n_signals += 1

            entry = c
            if apply_poc_filter:
                start = max(0, i - VP_WINDOW)
                hvns, _ = hvn_bins(highs[start:i + 1], lows[start:i + 1], vols[start:i + 1])
                dist_pct = dist_to_nearest_hvn_pct(entry, hvns)
                if dist_pct > MAX_POC_DIST_PCT:
                    continue
            n_poc_pass += 1

            sl_dist = STRAT["atr_sl_mult"] * a
            sl = entry + sl_dist
            tp = liquidity_tp(closes, highs, lows, i, sig, entry)
            if tp is None or tp >= entry:
                continue

            if apply_vetos:
                candidate = _build_validate_candidate(STRAT, symbol, sig, entry, sl_dist)
                try:
                    v_ok, _, _ = validate_pre_trade(candidate, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True
                if not v_ok:
                    continue

            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}

        if (si + 1) % 20 == 0:
            elapsed = time.time() - t_start
            print(f"  {si+1}/{len(basket)} simbolos | señales={n_signals} poc_pass={n_poc_pass} | {elapsed/60:.1f}min", flush=True)

    print(f"  señales RAW: {n_signals} | pasaron filtro POC: {n_poc_pass}")
    return _apply_capital_sim(all_trades)


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days = (t1 - t0) / (1000 * 60 * 60 * 24)
    print(f"Universo: {len(basket)} simbolos | {days:.0f} dias reales | Level Sweep 15m + TP liquidez + filtro POC/HVN")

    trades = backtest(conn, basket, apply_vetos=True, apply_poc_filter=True)
    res = evaluate(trades, days)
    print(f"\nCON filtro POC: n={res.get('n')} WR={res.get('wr_pct')}% $/mes={res.get('monthly')} "
          f"h1={res.get('pnl_h1')} h2={res.get('pnl_h2')} passes_bar={res.get('passes_bar')} "
          f"stable={res.get('stable_between_halves')}")


if __name__ == "__main__":
    main()
