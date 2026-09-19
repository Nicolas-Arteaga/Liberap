"""
2026-08-21: META-LABELING -- en vez de que el modelo invente señales desde
cero (partiendo de un 22% WR base, como en ml_lab.py), se usa como FILTRO
sobre las señales que YA genera una estrategia real y validada (Level Sweep
15m SL3/RR2, $62/mes, WR 38.8% real) -- parte de una base mucho mas fuerte.
Tecnica estandar (Lopez de Prado) nunca probada en este proyecto.

Flujo:
  1. Recorre todos los simbolos, detecta cada señal RAW de la estrategia
     (detect_signal, mismos parametros reales del perfil en produccion).
  2. Por cada señal, computa features (compute_features_v2) Y el resultado
     real (gano/perdio, usando el SL/TP real de la estrategia, no uno
     generico).
  3. Split cronologico, entrena un clasificador: "dado que la estrategia
     disparo aca, va a ganar?"
  4. Filtra: solo toma las señales que el meta-modelo predice con mayor
     probabilidad de ganar, aplica el motor real (vetos + 3 cupos) SOLO
     sobre el tramo out-of-sample, compara $/mes filtrado vs sin filtrar.
"""
import sys
import os
import sqlite3
import time
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    load_basket, load_15m, resample, atr_series, detect_signal, DB_PATH,
    MARGIN, FEE, _apply_capital_sim, _build_validate_candidate,
)
from backtest.ml_lab import TRAIN_FRAC  # noqa: E402
from backtest.ml_lab_v2 import compute_features_v2  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

# Level Sweep 15m SL3/RR2 -- el mejor de los 5 activos hoy, $62.13/mes real.
STRAT = dict(entry_type="level_sweep", tf_min=15, side="SHORT", atr_sl_mult=3.0, rr_mult=2.0, lookback=10)


def simulate_outcome(rows, atr_arr, idx, side, sl_mult, rr_mult, horizon=300):
    """Simula el resultado REAL de la estrategia (su propio SL/TP), no uno generico."""
    a = atr_arr[idx]
    if a is None or (isinstance(a, float) and np.isnan(a)) or a <= 0:
        return None, None, None, None
    entry = rows[idx][4]
    sl_dist = sl_mult * a
    tp_dist = sl_dist * rr_mult
    if side == 0:
        sl, tp = entry - sl_dist, entry + tp_dist
    else:
        sl, tp = entry + sl_dist, entry - tp_dist
    end = min(idx + 1 + horizon, len(rows))
    for j in range(idx + 1, end):
        h, l = rows[j][2], rows[j][3]
        hit_tp = (h >= tp) if side == 0 else (l <= tp)
        hit_sl = (l <= sl) if side == 0 else (h >= sl)
        if hit_tp and hit_sl:
            return 0, -1.0, sl, tp
        if hit_tp:
            return 1, rr_mult, sl, tp
        if hit_sl:
            return 0, -1.0, sl, tp
    return None, None, None, None  # timeout


def build_dataset(conn, basket):
    tf_min = STRAT["tf_min"]
    lb = STRAT["lookback"]
    sl_mult, rr_mult = STRAT["atr_sl_mult"], STRAT["rr_mult"]
    btc_rows_15m = load_15m(conn, "BTCUSDT")
    btc_closes_by_ts = {r[0]: r[4] for r in btc_rows_15m}

    rows_all = []
    for si, symbol in enumerate(basket):
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

        feats15, _, ts15 = compute_features_v2(rows15, btc_closes_by_ts)
        ts15_list = ts15.tolist()
        feat_by_ts = {t: feats15.iloc[k] for k, t in enumerate(ts15_list)}

        for i in range(150, len(candles) - 300):
            level_high = max(highs[i - lb:i]) if i >= lb else None
            level_low = min(lows[i - lb:i]) if i >= lb else None
            sig = detect_signal(STRAT, closes, highs, lows, i, level_high, level_low, None)
            if sig is None or (STRAT["side"] == "SHORT" and sig != 1) or (STRAT["side"] == "LONG" and sig != 0):
                continue
            ct = candles[i][0]
            if ct not in feat_by_ts:
                continue
            frow = feat_by_ts[ct]
            if frow.isna().any():
                continue
            label, r, sl, tp = simulate_outcome(candles, atr_arr, i, sig, sl_mult, rr_mult)
            if label is None:
                continue
            row = frow.to_dict()
            row["label"] = label
            row["r_multiple"] = r
            row["symbol"] = symbol
            row["open_time"] = ct
            row["entry"] = candles[i][4]
            row["sl"] = sl
            row["tp"] = tp
            rows_all.append(row)
        if (si + 1) % 50 == 0:
            print(f"  {si+1}/{len(basket)} simbolos, {len(rows_all)} señales RAW encontradas", flush=True)
    return pd.DataFrame(rows_all)


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Meta-labeling: {STRAT} sobre {len(basket)} simbolos...")

    df = build_dataset(conn, basket)
    print(f"\nSeñales RAW totales: {len(df)} | WR base (sin filtro): {df['label'].mean()*100:.2f}%")

    df = df.sort_values("open_time").reset_index(drop=True)
    cut = int(len(df) * TRAIN_FRAC)
    cut_ts = df.iloc[cut]["open_time"]
    train = df[df["open_time"] < cut_ts]
    test = df[df["open_time"] >= cut_ts]
    print(f"Train: {len(train)} | Test out-of-sample: {len(test)}")

    feature_cols = [c for c in df.columns if c not in
                    ("label", "r_multiple", "symbol", "open_time", "entry", "sl", "tp")]
    model = lgb.LGBMClassifier(n_estimators=200, max_depth=4, learning_rate=0.03,
                                subsample=0.8, colsample_bytree=0.8, min_child_samples=30,
                                random_state=42, verbosity=-1)
    model.fit(train[feature_cols], train["label"])
    proba = model.predict_proba(test[feature_cols])[:, 1]
    auc = roc_auc_score(test["label"], proba)
    print(f"\nAUC meta-modelo (out-of-sample): {auc:.4f}")

    test = test.copy()
    test["proba"] = proba
    print(f"proba -- min={proba.min():.3f} max={proba.max():.3f} median={np.median(proba):.3f}")

    days = (test["open_time"].max() - test["open_time"].min()) / 86400000
    print(f"Ventana test: {days:.0f} dias")

    # Comparacion real: SIN filtro (todas las señales de test) vs CON
    # filtro (solo las que el meta-modelo predice con proba >= mediana,
    # o sea el 50% "mejor" segun el modelo) -- ambas con motor real
    # (vetos + 3 cupos), sobre EL MISMO tramo out-of-sample.
    def run_capital_sim(rows_df, label):
        trades = []
        for _, r in rows_df.iterrows():
            side = 1  # SHORT (STRAT)
            cand = _build_validate_candidate(STRAT, r["symbol"], side, r["entry"], abs(r["entry"] - r["sl"]))
            try:
                v_ok, _, _ = validate_pre_trade(cand, r["entry"], profile=None, btc_filter=None, btc_corr=None)
            except Exception:
                v_ok = True
            if not v_ok:
                continue
            qty = MARGIN / r["entry"]
            close_px = r["tp"] if r["label"] == 1 else r["sl"]
            gross = qty * (r["entry"] - close_px)  # SHORT
            fees = (qty * r["entry"] + qty * close_px) * FEE
            trades.append({"symbol": r["symbol"], "pnl": gross - fees,
                            "open_time": r["open_time"], "close_time": r["open_time"] + 3600_000})
        accepted = _apply_capital_sim(trades)
        total = sum(t["pnl"] for t in accepted)
        n = len(accepted)
        wr = (sum(1 for t in accepted if t["pnl"] > 0) / n * 100) if n else 0
        monthly = total / (days / 30.44) if days > 0 else 0
        print(f"{label}: {n} trades (post-vetos+cupos) | WR: {wr:.1f}% | PnL: ${total:.2f} | ${monthly:.2f}/mes")

    print()
    run_capital_sim(test, "SIN filtro (baseline)")
    median_p = np.median(proba)
    run_capital_sim(test[test["proba"] >= median_p], f"CON filtro (proba>={median_p:.3f}, mitad superior)")
    p75 = np.percentile(proba, 75)
    run_capital_sim(test[test["proba"] >= p75], f"CON filtro (proba>={p75:.3f}, cuartil superior)")


if __name__ == "__main__":
    main()
