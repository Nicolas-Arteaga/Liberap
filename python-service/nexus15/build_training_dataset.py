"""
Construye data/nexus15_dataset.csv para train_nexus15.py, a partir de las
klines 15m ya cacheadas en agent/data/klines.db (subproducto del escaneo en
vivo del agente — ~2.5 meses para los símbolos con más historia).

Reusa Nexus15FeatureEngine.compute() y la MISMA construcción de feature_vector
que analyzer.py usa en vivo (ver nexus15/analyzer.py líneas 42-56, incluyendo
_wyckoff_to_num y las normalizaciones de cvd_delta/rsi_14) — evita el bug
clásico de "features distintas en training vs. serving", que sería fácil de
cometer reescribiendo la lógica a mano acá.

Label: 1 si close[i+HORIZON] > close[i] (misma definición que ya documentaba
train_nexus15.py: "alcista en N+5 velas"), 0 si no. Sin lookahead: cada
ejemplo usa solo las FEATURE_WINDOW velas hasta el índice i inclusive para
calcular features, y closes[i+HORIZON] (ya conocido en el momento de
entrenar porque es historia, no en vivo) solo para el label.

Split temporal real: train_nexus15.py hace un split posicional 70/15/15
sobre el CSV tal como lo lee — para que eso sea un split cronológico
GENUINO (no por símbolo), acá se ordenan todos los ejemplos de TODOS los
símbolos por open_time real antes de guardar, no símbolo por símbolo.

Limitación conocida: se usa stride=STRIDE_CANDLES en vez de todas las velas,
para reducir el solapamiento entre ventanas consecutivas (cada ventana de
FEATURE_WINDOW velas comparte la mayoría de sus velas con la siguiente si el
stride fuera 1) — no elimina la autocorrelación entre ejemplos cercanos del
mismo símbolo, pero la reduce. Ver spec 5.3 (split temporal, no aleatorio).

Uso: python build_training_dataset.py [--out data/nexus15_dataset.csv]
"""
import os
import sys
import argparse

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "agent"))
sys.path.insert(0, os.path.dirname(__file__))

FEATURE_WINDOW = 100   # velas de contexto por ejemplo (suficiente para MACD/RSI/ATR/POC estables)
HORIZON = 5             # "N+5 velas" — mismo horizonte que ya documentaba train_nexus15.py
STRIDE_CANDLES = 6      # separación entre ejemplos consecutivos del mismo símbolo (~1.5h a 15m)
MIN_CANDLES_REQUIRED = FEATURE_WINDOW + HORIZON + 1
INTERVAL = "15m"
MAX_CANDLES_PER_SYMBOL = 2000  # ~20.8 días — acota runtime (compute() de feature_engine no es vectorizado,
                                # ~10ms/ejemplo; sin este tope, 723 símbolos * ~4200 velas promedio tardaría horas)


def _wyckoff_to_num(phase: str) -> float:
    return {"Markup": 1.0, "Accumulation": 0.6, "Ranging": 0.5,
            "Distribution": 0.4, "Markdown": 0.0}.get(phase, 0.5)


def _build_feature_vector(feats: dict) -> list:
    """Idéntico a analyzer.py::Nexus15Analyzer.analyze (líneas 42-56) — no duplicar lógica ahí sin actualizar acá."""
    return [
        feats["candle_body_ratio"], feats["upper_wick_ratio"],
        feats["lower_wick_ratio"], feats["consecutive_bull_bars"],
        int(feats["order_block_detected"]), int(feats["fair_value_gap"]),
        int(feats["bos_detected"]),
        _wyckoff_to_num(feats["wyckoff_phase"]),
        int(feats["spring_detected"]), int(feats["upthrust_detected"]),
        int(feats["fractal_high_5"]), int(feats["fractal_low_5"]),
        feats["trend_structure"], feats["volume_ratio_20"],
        feats["cvd_delta"] / 1e6,
        int(feats["volume_surge_bullish"]), feats["poc_proximity"],
        feats["rsi_14"] / 100.0,
        feats["macd_histogram"],
        feats["atr_percent"],
    ]


LABEL_THRESHOLD_PCT = 0.0  # 0 = binario ingenuo (close futuro > close actual). >0 = descarta movimientos
                           # ambiguos entre -threshold y +threshold (ruido que no aporta señal real).


def build_examples_for_symbol(symbol: str, klines: list, engine) -> list:
    """
    klines: salida de kline_cache.get_klines() (oldest first, con open_time).
    Devuelve lista de dicts {open_time, symbol, <20 features>, label}.

    Con LABEL_THRESHOLD_PCT > 0: se descartan los ejemplos cuyo retorno a
    HORIZON velas cae entre -threshold y +threshold — son movimientos chicos,
    indistinguibles de ruido, que diluyen la señal real (2026-07-17: el
    primer intento con label ingenuo, sin este filtro, dio AUC~0.54, apenas
    por encima de azar — ver PROGRESS_LOG).
    """
    n = len(klines)
    if n < MIN_CANDLES_REQUIRED:
        return []

    df_full = pd.DataFrame(klines)
    examples = []
    i = FEATURE_WINDOW - 1
    while i + HORIZON < n:
        close_now = df_full.iloc[i]["close"]
        close_future = df_full.iloc[i + HORIZON]["close"]
        ret_pct = (close_future - close_now) / close_now * 100.0

        if LABEL_THRESHOLD_PCT > 0 and abs(ret_pct) < LABEL_THRESHOLD_PCT:
            i += STRIDE_CANDLES
            continue

        window = df_full.iloc[i - FEATURE_WINDOW + 1: i + 1]  # solo hasta i inclusive — sin lookahead
        try:
            feats = engine.compute(window)
            vec = _build_feature_vector(feats)
        except Exception:
            i += STRIDE_CANDLES
            continue

        label = 1 if ret_pct > 0 else 0

        row = {"open_time": df_full.iloc[i]["open_time"], "symbol": symbol, "label": label, "ret_pct": round(ret_pct, 4)}
        from model_loader import NEXUS15_FEATURES
        row.update(dict(zip(NEXUS15_FEATURES, vec)))
        examples.append(row)
        i += STRIDE_CANDLES

    return examples


def main():
    global STRIDE_CANDLES, LABEL_THRESHOLD_PCT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data", "nexus15_dataset.csv"))
    ap.add_argument("--min-candles", type=int, default=MIN_CANDLES_REQUIRED)
    ap.add_argument("--max-candles-per-symbol", type=int, default=MAX_CANDLES_PER_SYMBOL)
    ap.add_argument("--stride", type=int, default=STRIDE_CANDLES)
    ap.add_argument("--label-threshold-pct", type=float, default=LABEL_THRESHOLD_PCT,
                     help="Descarta ejemplos con retorno a HORIZON velas dentro de +-este %% (reduce ruido)")
    args = ap.parse_args()
    STRIDE_CANDLES = args.stride
    LABEL_THRESHOLD_PCT = args.label_threshold_pct

    from kline_cache import get_cache
    from feature_engine import Nexus15FeatureEngine
    cache = get_cache()
    engine = Nexus15FeatureEngine()

    symbols = cache.get_symbols_with_history(INTERVAL, min_candles=args.min_candles)
    print(f"[BuildDataset] {len(symbols)} símbolos con >= {args.min_candles} velas de {INTERVAL}.")

    all_examples = []
    skipped = 0
    for idx, symbol in enumerate(symbols):
        klines = cache.get_klines(symbol, INTERVAL, limit=100_000)
        if len(klines) > args.max_candles_per_symbol:
            klines = klines[-args.max_candles_per_symbol:]  # las más recientes — el régimen actual importa más
        examples = build_examples_for_symbol(symbol, klines, engine)
        if not examples:
            skipped += 1
            continue
        all_examples.extend(examples)
        if (idx + 1) % 50 == 0:
            print(f"[BuildDataset] {idx + 1}/{len(symbols)} símbolos procesados, {len(all_examples)} ejemplos hasta ahora.")

    if not all_examples:
        print("[BuildDataset] ERROR: no se generó ningún ejemplo. Nada para entrenar.")
        sys.exit(1)

    df = pd.DataFrame(all_examples)
    # Orden cronológico GLOBAL (no por símbolo) — para que el split 70/15/15
    # posicional de train_nexus15.py sea un split temporal real.
    df = df.sort_values("open_time").reset_index(drop=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)

    pos = int(df["label"].sum())
    print(f"[BuildDataset] Dataset guardado en {args.out}: {len(df)} ejemplos "
          f"({len(symbols) - skipped} símbolos con datos, {skipped} sin suficiente historia) | "
          f"label positivo: {pos} ({pos/len(df)*100:.1f}%), negativo: {len(df)-pos} ({(len(df)-pos)/len(df)*100:.1f}%)")


if __name__ == "__main__":
    main()
