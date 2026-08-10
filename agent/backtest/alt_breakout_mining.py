"""
Mineria de patrones cross-alt (pedido del usuario 2026-08-02): en vez de
minar patrones en BTC y tratar de trasladarlos, minar directamente sobre
una CANASTA de altcoins de alta beta -- exigiendo que el patron encontrado
tenga lift real tanto en el pool combinado COMO simbolo por simbolo, para
no confundir "funciona en 1 alt con suerte" con "funciona en altcoins en
general". Umbral de movimiento mas alto que en BTC (3% en vez de 1.5%) --
los alts se mueven mas fuerte para el mismo evento de mercado.

Uso: python -m backtest.alt_breakout_mining   (desde agent/)
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.btc_condition_scan import load_klines, sma_series, rsi_series, DB_PATH, RSI_PERIOD  # noqa: E402
from backtest.btc_breakout_mining import detect_events, build_features, MOVE_WINDOW  # noqa: E402

BASKET = ["SUIUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT",
          "DOTUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT", "UNIUSDT", "SANDUSDT", "GALAUSDT",
          "ALGOUSDT", "XLMUSDT", "VETUSDT", "ETCUSDT", "RUNEUSDT"]

MOVE_THRESHOLD_PCT = 3.0  # mas alto que en BTC -- los alts se mueven mas fuerte


def main():
    conn = sqlite3.connect(DB_PATH)
    feature_names = ["below_all_mas", "above_all_mas", "compressed", "prior_falling",
                      "prior_rising", "prior_flat", "rsi_low", "rsi_mid", "rsi_high",
                      "ma7_below_ma99", "ma7_above_ma99"]

    per_symbol_up = {name: [] for name in feature_names}   # lift por simbolo (para rupturas alcistas)
    per_symbol_down = {name: [] for name in feature_names}
    pool_up_events_feats = []
    pool_up_base_feats = []
    pool_down_events_feats = []
    pool_down_base_feats = []

    total_up, total_down = 0, 0
    for symbol in BASKET:
        candles = load_klines(conn, symbol)
        if len(candles) < 2000:
            print(f"  {symbol}: sin suficiente historia, salteado", flush=True)
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        ma7 = sma_series(closes, 7)
        ma25 = sma_series(closes, 25)
        ma50 = sma_series(closes, 50)
        ma99 = sma_series(closes, 99)
        rsi = rsi_series(closes, RSI_PERIOD)

        # Umbral mas alto para alts -- reusa detect_events pero con el
        # threshold de este modulo, no el de btc_breakout_mining.
        import backtest.btc_breakout_mining as mining_mod
        orig_threshold = mining_mod.MOVE_THRESHOLD_PCT
        mining_mod.MOVE_THRESHOLD_PCT = MOVE_THRESHOLD_PCT
        up_events, down_events = detect_events(candles, closes, highs, lows)
        mining_mod.MOVE_THRESHOLD_PCT = orig_threshold

        n = len(candles)
        valid_start, valid_end = 100, n - MOVE_WINDOW - 1
        all_valid = list(range(valid_start, valid_end))

        up_feats = [build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in up_events]
        up_feats = [f for f in up_feats if f is not None]
        down_feats = [build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in down_events]
        down_feats = [f for f in down_feats if f is not None]
        base_feats = [build_features(i, closes, ma7, ma25, ma50, ma99, rsi) for i in all_valid]
        base_feats = [f for f in base_feats if f is not None]

        pool_up_events_feats.extend(up_feats)
        pool_down_events_feats.extend(down_feats)
        pool_up_base_feats.extend(base_feats)
        pool_down_base_feats.extend(base_feats)

        total_up += len(up_feats)
        total_down += len(down_feats)
        print(f"  {symbol}: {len(up_feats)} rupturas alcistas, {len(down_feats)} bajistas (>= {MOVE_THRESHOLD_PCT}%)", flush=True)

        if len(up_feats) >= 15 and len(base_feats) >= 200:
            for name in feature_names:
                er = sum(1 for f in up_feats if f[name]) / len(up_feats)
                br = sum(1 for f in base_feats if f[name]) / len(base_feats)
                if br > 0:
                    per_symbol_up[name].append(er / br)
        if len(down_feats) >= 15 and len(base_feats) >= 200:
            for name in feature_names:
                er = sum(1 for f in down_feats if f[name]) / len(down_feats)
                br = sum(1 for f in base_feats if f[name]) / len(base_feats)
                if br > 0:
                    per_symbol_down[name].append(er / br)

    print(f"\nTotal pooled: {total_up} rupturas alcistas | {total_down} bajistas sobre {len(BASKET)} altcoins", flush=True)

    def report(label, events_feats, base_feats, per_symbol_lifts):
        print("\n" + "=" * 110)
        print(label)
        print("=" * 110)
        print(f"{'Caracteristica':28s} | {'lift POOL':>10s} | {'lift promedio x simbolo':>24s} | {'simbolos con lift>1.2':>22s} | robusto?")
        for name in feature_names:
            er = sum(1 for f in events_feats if f[name]) / len(events_feats) if events_feats else 0
            br = sum(1 for f in base_feats if f[name]) / len(base_feats) if base_feats else 0
            pool_lift = (er / br) if br > 0 else None
            lifts = per_symbol_lifts[name]
            avg_lift = sum(lifts) / len(lifts) if lifts else None
            n_strong = sum(1 for l in lifts if l > 1.2)
            robust = (pool_lift is not None and pool_lift > 1.2 and avg_lift is not None and avg_lift > 1.2
                      and n_strong >= max(3, len(lifts) * 0.5))
            pl_str = f"{pool_lift:.2f}x" if pool_lift is not None else "--"
            al_str = f"{avg_lift:.2f}x" if avg_lift is not None else "--"
            print(f"{name:28s} | {pl_str:>10s} | {al_str:>24s} | {n_strong}/{len(lifts)} simbolos{'':>10s} | {'SI' if robust else 'no'}")

    report("RUPTURAS ALCISTAS (subio >=3% en 2h) -- POOL de altcoins", pool_up_events_feats, pool_up_base_feats, per_symbol_up)
    report("RUPTURAS BAJISTAS (cayo >=3% en 2h) -- POOL de altcoins", pool_down_events_feats, pool_down_base_feats, per_symbol_down)


if __name__ == "__main__":
    main()
