"""
Mineria de patrones sobre un pool GRANDE y DIVERSO de altcoins (350
simbolos: blue-chip de 8 meses + alts variados de 4 meses, sin memecoins
ya usados en Pump Reaper ni tickers TradFi) -- objetivo del usuario
2026-08-02: encontrar un patron que generalice a "cualquier altcoin", no
uno especifico de memecoins (que caducan/rotan rapido).

Mismo metodo y mismo filtro de robustez que btc_breakout_mining.py /
alt_breakout_mining.py / meme_breakout_mining.py: buscar rupturas grandes
reales y mirar que las precedia, exigiendo lift consistente en la mayoria
de los simbolos, no solo en el promedio.

Uso: python -m backtest.universal_breakout_mining   (desde agent/)
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.btc_condition_scan import load_klines, sma_series, rsi_series, DB_PATH, RSI_PERIOD  # noqa: E402
from backtest.btc_breakout_mining import detect_events, build_features, MOVE_WINDOW  # noqa: E402

MOVE_THRESHOLD_PCT = 3.0

BASKET_FILE = os.path.join(os.path.dirname(__file__), "..", "meme_universal_basket.txt")


def load_basket():
    with open(BASKET_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket()
    feature_names = ["below_all_mas", "above_all_mas", "compressed", "prior_falling",
                      "prior_rising", "prior_flat", "rsi_low", "rsi_mid", "rsi_high",
                      "ma7_below_ma99", "ma7_above_ma99"]

    per_symbol_up = {name: [] for name in feature_names}
    per_symbol_down = {name: [] for name in feature_names}
    pool_up_events_feats = []
    pool_down_events_feats = []
    pool_base_feats = []

    total_up, total_down, processed = 0, 0, 0
    for idx, symbol in enumerate(basket):
        candles = load_klines(conn, symbol)
        if len(candles) < 2000:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        ma7 = sma_series(closes, 7)
        ma25 = sma_series(closes, 25)
        ma50 = sma_series(closes, 50)
        ma99 = sma_series(closes, 99)
        rsi = rsi_series(closes, RSI_PERIOD)

        import backtest.btc_breakout_mining as mining_mod
        orig_threshold = mining_mod.MOVE_THRESHOLD_PCT
        mining_mod.MOVE_THRESHOLD_PCT = MOVE_THRESHOLD_PCT
        up_events, down_events = detect_events(candles, closes, highs, lows)
        mining_mod.MOVE_THRESHOLD_PCT = orig_threshold

        n = len(candles)
        valid_start, valid_end = 100, n - MOVE_WINDOW - 1
        all_valid = list(range(valid_start, valid_end))

        up_feats = [f for f in (build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in up_events) if f is not None]
        down_feats = [f for f in (build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in down_events) if f is not None]
        base_feats = [f for f in (build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in all_valid) if f is not None]

        pool_up_events_feats.extend(up_feats)
        pool_down_events_feats.extend(down_feats)
        pool_base_feats.extend(base_feats)

        total_up += len(up_feats)
        total_down += len(down_feats)
        processed += 1

        if len(up_feats) >= 10 and len(base_feats) >= 200:
            for name in feature_names:
                er = sum(1 for f in up_feats if f[name]) / len(up_feats)
                br = sum(1 for f in base_feats if f[name]) / len(base_feats)
                if br > 0:
                    per_symbol_up[name].append(er / br)
        if len(down_feats) >= 10 and len(base_feats) >= 200:
            for name in feature_names:
                er = sum(1 for f in down_feats if f[name]) / len(down_feats)
                br = sum(1 for f in base_feats if f[name]) / len(base_feats)
                if br > 0:
                    per_symbol_down[name].append(er / br)

        if (idx + 1) % 50 == 0:
            print(f"  progreso: {idx+1}/{len(basket)} simbolos | {processed} procesados | {total_up} rupturas alcistas | {total_down} bajistas", flush=True)

    print(f"\nTotal: {processed} simbolos procesados | {total_up} rupturas alcistas | {total_down} bajistas (>= {MOVE_THRESHOLD_PCT}%)", flush=True)

    def report(label, events_feats, per_symbol_lifts):
        print("\n" + "=" * 115)
        print(label)
        print("=" * 115)
        print(f"{'Caracteristica':28s} | {'lift POOL':>10s} | {'lift promedio x simbolo':>24s} | {'simbolos con lift>1.2':>22s} | robusto?")
        for name in feature_names:
            er = sum(1 for f in events_feats if f[name]) / len(events_feats) if events_feats else 0
            br = sum(1 for f in pool_base_feats if f[name]) / len(pool_base_feats) if pool_base_feats else 0
            pool_lift = (er / br) if br > 0 else None
            lifts = per_symbol_lifts[name]
            avg_lift = sum(lifts) / len(lifts) if lifts else None
            n_strong = sum(1 for l in lifts if l > 1.2)
            robust = (pool_lift is not None and pool_lift > 1.2 and avg_lift is not None and avg_lift > 1.2
                      and n_strong >= max(10, len(lifts) * 0.5))
            pl_str = f"{pool_lift:.2f}x" if pool_lift is not None else "--"
            al_str = f"{avg_lift:.2f}x" if avg_lift is not None else "--"
            print(f"{name:28s} | {pl_str:>10s} | {al_str:>24s} | {n_strong}/{len(lifts)} simbolos{'':>6s} | {'SI' if robust else 'no'}")

    report("RUPTURAS ALCISTAS (subio >=3% en 2h) -- POOL de 350 altcoins diversos", pool_up_events_feats, per_symbol_up)
    report("RUPTURAS BAJISTAS (cayo >=3% en 2h) -- POOL de 350 altcoins diversos", pool_down_events_feats, per_symbol_down)


if __name__ == "__main__":
    main()
