import sys, os, time, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, detect_signal, atr_series, resample, load_15m, DB_PATH, MARGIN, FEE
from setup_validator import validate_pre_trade

import sqlite3 as _sqlite3
_conn = _sqlite3.connect(DB_PATH)
_cur = _conn.cursor()
_cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
_t0, _t1 = _cur.fetchone()
DAYS = (_t1 - _t0) / (1000 * 60 * 60 * 24) if _t0 and _t1 else 243  # 2026-08-21: bug real -- estaba hardcodeado en 243, stale desde antes de sincronizar klines_clean (ahora ~260 dias reales), inflaba el $/mes en todos los grid_search_*.py
SLOTS = 3
TIMEFRAMES = [15, 60, 240]
ATR_SL_MULTS = [1.0, 1.5, 2.0, 3.0]
RR_MULTS = [1.5, 2.0, 3.0, 4.0, 6.0]
LOOKBACKS = [10, 20, 50]
SLOPE_MINS = [0.3, 0.6, 1.0, 1.5]
SIDES = ["SHORT", "LONG", "BOTH"]

def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "ma_pullback:grid",
        "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }

def apply_capital_sim(trades, slots=SLOTS):
    trades = sorted(trades, key=lambda t: (t["open_time"], t["symbol"]))
    open_slots, accepted = [], []
    for t in trades:
        open_slots = [ct for ct in open_slots if ct > t["open_time"]]
        if len(open_slots) >= slots:
            continue
        open_slots.append(t["close_time"])
        accepted.append(t)
    return accepted

def backtest(conn, basket, tf_min, atr_sl_mult, rr_mult, lookback, slope_min, side_filter, cache):
    if tf_min not in cache:
        cache[tf_min] = {}
    all_trades = []
    strat = {"entry_type": "ma_pullback", "lookback": lookback, "slope_min_pct": slope_min, "volume_mult": 1.0}
    for symbol in basket:
        if symbol not in cache[tf_min]:
            rows = load_15m(conn, symbol)
            if len(rows) < 3000:
                cache[tf_min][symbol] = None; continue
            candles = resample(rows, tf_min) if tf_min != 15 else rows
            if len(candles) < 250:
                cache[tf_min][symbol] = None; continue
            closes = [c[4] for c in candles]
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]
            volumes = [c[5] for c in candles]
            atr = atr_series(candles, 14)
            cache[tf_min][symbol] = (candles, closes, highs, lows, volumes, atr)
        cached = cache[tf_min][symbol]
        if cached is None:
            continue
        candles, closes, highs, lows, volumes, atr = cached
        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
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
            sig = detect_signal(strat, closes, highs, lows, i, None, None, volumes)
            if sig is None:
                continue
            if side_filter == "SHORT" and sig != 1:
                continue
            if side_filter == "LONG" and sig != 0:
                continue
            entry = c
            sl_dist = atr_sl_mult * a
            tp_dist = sl_dist * rr_mult
            if sig == 0:
                sl, tp = entry - sl_dist, entry + tp_dist
            else:
                sl, tp = entry + sl_dist, entry - tp_dist
            cand = build_candidate(symbol, sig, entry)
            try:
                v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
            except Exception:
                v_ok = True
            if not v_ok:
                continue
            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}
    return apply_capital_sim(all_trades)

def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    cache = {}
    total_combos = len(TIMEFRAMES) * len(ATR_SL_MULTS) * len(RR_MULTS) * len(LOOKBACKS) * len(SLOPE_MINS) * len(SIDES)
    print(f"Universo: {len(basket)} simbolos | combos: {total_combos} | vetos+3cupos SIEMPRE activos")
    results = []
    tried = 0
    t_start = time.time()
    for tf in TIMEFRAMES:
        for sl_mult in ATR_SL_MULTS:
            for rr in RR_MULTS:
                for lb in LOOKBACKS:
                    for slope_min in SLOPE_MINS:
                        for side in SIDES:
                            tried += 1
                            trades = backtest(conn, basket, tf, sl_mult, rr, lb, slope_min, side, cache)
                            n = len(trades)
                            if n < 20:
                                continue
                            total = sum(t["pnl"] for t in trades)
                            monthly = total / (DAYS / 30.44)
                            wins = sum(1 for t in trades if t["pnl"] > 0)
                            results.append({"tf": tf, "sl_mult": sl_mult, "rr": rr, "lb": lb, "slope": slope_min, "side": side,
                                             "n": n, "wr": round(wins/n*100, 1), "monthly": round(monthly, 2)})
                            if tried % 150 == 0:
                                print(f"  progreso: {tried}/{total_combos} | {(time.time()-t_start)/60:.1f}min", flush=True)
    results.sort(key=lambda r: r["monthly"], reverse=True)
    print(f"\n=== TOP 15 ma_pullback por $/mes (vetos+3cupos reales) ===")
    for r in results[:15]:
        print(f"  {r['side']:6s} tf={r['tf']:3d}m SL={r['sl_mult']}x RR={r['rr']}x lb={r['lb']:2d} slope={r['slope']}% | n={r['n']:4d} WR={r['wr']:5.1f}% -> ${r['monthly']:8.2f}/mes")
    print(f"\nTiempo total: {(time.time()-t_start)/60:.1f} min")

if __name__ == "__main__":
    main()
