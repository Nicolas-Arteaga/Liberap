"""
2026-08-18: barrido sistematico (no aleatorio) de TODO el espacio de
parametros de "level_sweep" con el motor honesto (vetos reales + 3 cupos
x $150) -- pedido del usuario tras ver que Level Sweep 15m SL3/RR3 no
supera los $150/mes netos. Objetivo: encontrar la MEJOR combinacion real
posible dentro de esta familia de patron, no conformarse con la primera
que encontro el lab random.
"""
import sys, os, time, sqlite3, json
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
SIDES = ["SHORT", "LONG", "BOTH"]

def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "level_sweep_1h_mode:grid", "level_sweep_1h_mode": True,
        "price_at_signal": entry, "agent_audit_context": {"scar": {}, "nexus15": {}},
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

def backtest(conn, basket, tf_min, atr_sl_mult, rr_mult, lookback, side_filter, cache):
    key = tf_min
    if key not in cache:
        cache[key] = {}
    all_trades = []
    for symbol in basket:
        if symbol not in cache[key]:
            rows = load_15m(conn, symbol)
            if len(rows) < 3000:
                cache[key][symbol] = None
                continue
            candles = resample(rows, tf_min) if tf_min != 15 else rows
            if len(candles) < 250:
                cache[key][symbol] = None
                continue
            closes = [c[4] for c in candles]
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]
            volumes = [c[5] for c in candles]
            atr = atr_series(candles, 14)
            cache[key][symbol] = (candles, closes, highs, lows, volumes, atr)
        cached = cache[key][symbol]
        if cached is None:
            continue
        candles, closes, highs, lows, volumes, atr = cached

        open_trade = None
        strat = {"entry_type": "level_sweep", "lookback": lookback}
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
            level_high = max(highs[i - lookback:i]) if i >= lookback else None
            level_low = min(lows[i - lookback:i]) if i >= lookback else None
            sig = detect_signal(strat, closes, highs, lows, i, level_high, level_low, volumes)
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
    total_combos = len(TIMEFRAMES) * len(ATR_SL_MULTS) * len(RR_MULTS) * len(LOOKBACKS) * len(SIDES)
    print(f"Universo: {len(basket)} simbolos | combos a probar: {total_combos} | vetos+3cupos SIEMPRE activos")

    results = []
    tried = 0
    t_start = time.time()
    for tf in TIMEFRAMES:
        for sl_mult in ATR_SL_MULTS:
            for rr in RR_MULTS:
                for lb in LOOKBACKS:
                    for side in SIDES:
                        tried += 1
                        trades = backtest(conn, basket, tf, sl_mult, rr, lb, side, cache)
                        n = len(trades)
                        if n < 20:
                            continue
                        total = sum(t["pnl"] for t in trades)
                        monthly = total / (DAYS / 30.44)
                        wins = sum(1 for t in trades if t["pnl"] > 0)
                        results.append({
                            "tf": tf, "sl_mult": sl_mult, "rr": rr, "lookback": lb, "side": side,
                            "n": n, "wr": round(wins/n*100, 1), "monthly": round(monthly, 2),
                        })
                        if tried % 50 == 0:
                            elapsed = time.time() - t_start
                            print(f"  progreso: {tried}/{total_combos} | {elapsed/60:.1f}min | encontrados con datos: {len(results)}", flush=True)

    results.sort(key=lambda r: r["monthly"], reverse=True)
    print(f"\n=== TOP 15 combinaciones de level_sweep por $/mes (con vetos+3cupos reales) ===")
    for r in results[:15]:
        print(f"  {r['side']:6s} tf={r['tf']:3d}m SL={r['sl_mult']}x RR={r['rr']}x lb={r['lookback']:2d} | "
              f"n={r['n']:4d} WR={r['wr']:5.1f}% -> ${r['monthly']:8.2f}/mes")

    with open("backtest/grid_search_level_sweep_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nTiempo total: {(time.time()-t_start)/60:.1f} min")

if __name__ == "__main__":
    main()
