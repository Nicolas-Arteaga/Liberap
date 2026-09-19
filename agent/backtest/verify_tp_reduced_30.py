"""
2026-08-18: TP reducido 30% para Level Sweep 15m SL3/RR3, motor honesto
(vetos reales + 3 cupos x $150) -- pedido del usuario tras ver 3 trades
reales que se acercaron mucho al TP (85.7%, 74.5%, 65.7%) sin cerrar.
SL se deja igual, solo se acorta el TP.
"""
import sys, os, time, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, detect_signal, atr_series, resample, load_15m, DB_PATH, MARGIN, FEE
from setup_validator import validate_pre_trade

DAYS = 243
SLOTS = 3

def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "level_sweep_1h_mode:tp30", "level_sweep_1h_mode": True,
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

def backtest(conn, basket, tf_min, atr_sl_mult, rr_mult, lookback, tp_scale):
    all_trades = []
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        candles = resample(rows, tf_min) if tf_min != 15 else rows
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        volumes = [c[5] for c in candles]
        atr = atr_series(candles, 14)
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
            if sig is None or sig != 1:
                continue
            entry = c
            sl_dist = atr_sl_mult * a
            tp_dist = sl_dist * rr_mult * tp_scale
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

def report(label, trades, days=DAYS):
    n = len(trades)
    if n == 0:
        print(f"  {label}: sin trades"); return
    total = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    monthly = total / (days / 30.44)
    print(f"  {label:18s} n={n:5d} WR={wins/n*100:5.1f}% neto=${total:9.2f} (${monthly:8.2f}/mes)")

def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | 3 cupos x $150 | vetos reales SIEMPRE activos\n")
    print("=== Level Sweep 15m SL3/RR3 -- TP variado ===")
    for label, scale in [("TP normal (100%)", 1.0), ("TP -30%", 0.7), ("TP -15%", 0.85), ("TP -10%", 0.9)]:
        t0 = time.time()
        trades = backtest(conn, basket, 15, 3.0, 3.0, 20, scale)
        report(label, trades)
        print(f"    ({time.time()-t0:.1f}s)")

if __name__ == "__main__":
    main()
