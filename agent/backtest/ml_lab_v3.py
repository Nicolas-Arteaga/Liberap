"""
2026-08-21: v3 -- agrega Order Flow Imbalance (OFI) real como feature, el
primer dato de microestructura de mercado usado en este proyecto para
entrenar un modelo (v1/v2 solo usaban precio/volumen derivados). OFI tiene
~1 mes real de historia (22/jul-21/ago), 462 simbolos, en vivo -- mucho
menos ventana que las velas (243+ dias), asi que el dataset de esta corrida
es necesariamente mas chico y solo cubre ese mes.

Reusa compute_features_v2 (fuerza vs BTC, micro-momentum, distancia a
extremos) + agrega:
  - ofi_now: ultimo OFI conocido en o antes de esa vela (sin look-ahead)
  - ofi_chg_1h: cambio del OFI en la ultima hora (4 velas de 15m)

Mismo rigor de siempre: split cronologico real, out-of-sample real.
"""
import sys
import os
import sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, load_15m, DB_PATH  # noqa: E402
from backtest.ml_lab import label_outcomes, STRIDE, HORIZON, TRAIN_FRAC  # noqa: E402
from backtest.ml_lab_v2 import compute_features_v2  # noqa: E402

OFI_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "klines.db")


def load_ofi_series(ofi_conn, symbol):
    cur = ofi_conn.cursor()
    cur.execute("SELECT timestamp, ofi FROM orderbook_ofi WHERE symbol=? ORDER BY timestamp ASC", (symbol,))
    return cur.fetchall()  # (timestamp_seconds, ofi)


def align_ofi(ofi_rows, open_times_ms):
    """Une OFI (segundos) a la lista de velas (ms) -- ultimo valor conocido
    en o antes de cada vela, sin look-ahead. O(n) merge, mismo criterio que
    get_ofi_series_aligned en kline_cache.py."""
    result = [None] * len(open_times_ms)
    idx, n = 0, len(ofi_rows)
    last = None
    for i, ot_ms in enumerate(open_times_ms):
        ot_s = ot_ms // 1000
        while idx < n and ofi_rows[idx][0] <= ot_s:
            last = ofi_rows[idx][1]
            idx += 1
        result[i] = last
    return result


def build_dataset_v3(conn, ofi_conn, basket):
    btc_rows = load_15m(conn, "BTCUSDT")
    btc_closes_by_ts = {r[0]: r[4] for r in btc_rows}

    # Ventana real de cobertura OFI -- no tiene sentido samplear fuera de esto.
    cur = ofi_conn.cursor()
    cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM orderbook_ofi")
    ofi_min_s, ofi_max_s = cur.fetchone()
    ofi_min_ms, ofi_max_ms = ofi_min_s * 1000, ofi_max_s * 1000
    print(f"Ventana OFI real: {pd.to_datetime(ofi_min_ms, unit='ms')} -> {pd.to_datetime(ofi_max_ms, unit='ms')}")

    rows_all = []
    for si, symbol in enumerate(basket):
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        ofi_rows = load_ofi_series(ofi_conn, symbol)
        if len(ofi_rows) < 100:
            continue  # simbolo sin cobertura OFI real -- no samplear

        feats, atr_arr, ts = compute_features_v2(rows, btc_closes_by_ts)
        ofi_aligned = align_ofi(ofi_rows, ts.tolist())
        ofi_series = pd.Series(ofi_aligned, dtype=float)
        ofi_chg_1h = ofi_series - ofi_series.shift(4)
        feats["ofi_now"] = ofi_series.values
        feats["ofi_chg_1h"] = ofi_chg_1h.values

        for idx in range(150, len(rows) - HORIZON, STRIDE):
            if ts[idx] < ofi_min_ms or ts[idx] > ofi_max_ms - HORIZON * 15 * 60_000:
                continue  # fuera de la ventana real de cobertura OFI
            if feats.iloc[idx].isna().any():
                continue
            for side in (0, 1):
                label, r = label_outcomes(rows, atr_arr, idx, side)
                if label is None:
                    continue
                row = feats.iloc[idx].to_dict()
                row["side"] = side
                row["label"] = label
                row["r_multiple"] = r
                row["symbol"] = symbol
                row["open_time"] = ts[idx]
                rows_all.append(row)
        if (si + 1) % 50 == 0:
            print(f"  {si+1}/{len(basket)} simbolos procesados, {len(rows_all)} muestras acumuladas", flush=True)
    return pd.DataFrame(rows_all)


def main():
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score

    conn = sqlite3.connect(DB_PATH)
    ofi_conn = sqlite3.connect(OFI_DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | construyendo dataset v3 (con OFI real)...")

    df = build_dataset_v3(conn, ofi_conn, basket)
    print(f"\nDataset total: {len(df)} muestras | WR base: {df['label'].mean()*100:.2f}%")

    if len(df) < 1000:
        print("Dataset insuficiente -- muy pocos simbolos con cobertura OFI real. Abortando.")
        return

    df = df.sort_values("open_time").reset_index(drop=True)
    cut = int(len(df) * TRAIN_FRAC)
    cut_ts = df.iloc[cut]["open_time"]
    train = df[df["open_time"] < cut_ts]
    test = df[df["open_time"] >= cut_ts]
    print(f"Train: {len(train)} muestras | Test (out-of-sample): {len(test)} muestras")

    feature_cols = [c for c in df.columns if c not in ("label", "r_multiple", "symbol", "open_time")]
    X_train, y_train = train[feature_cols], train["label"]
    X_test, y_test = test[feature_cols], test["label"]

    model = lgb.LGBMClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
        random_state=42, verbosity=-1,
    )
    model.fit(X_train, y_train)

    proba_test = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba_test)
    print(f"\n=== VALIDACION OUT-OF-SAMPLE v3 (con OFI real) ===")
    print(f"AUC test: {auc:.4f} (v1=0.5298, v2=0.5269)")

    test = test.copy()
    test["proba"] = proba_test
    print(f"Proba test -- min={proba_test.min():.4f} max={proba_test.max():.4f} "
          f"p90={np.percentile(proba_test,90):.4f} p95={np.percentile(proba_test,95):.4f} p99={np.percentile(proba_test,99):.4f}")
    for thresh in (0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.60, 0.65, 0.70):
        sub = test[test["proba"] >= thresh]
        if len(sub) < 20:
            print(f"  umbral {thresh}: solo {len(sub)} señales, insuficiente para medir")
            continue
        wr = sub["label"].mean() * 100
        avg_r = sub["r_multiple"].mean()
        print(f"  umbral proba>={thresh}: {len(sub)} señales | WR real: {wr:.2f}% | avg R: {avg_r:+.3f}")
    test.to_pickle(os.path.join(os.path.dirname(__file__), "ml_lab_v3_test_proba.pkl"))

    importances = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1])
    print("\nFeatures mas importantes:")
    for name, imp in importances[:15]:
        marker = " <-- OFI (nuevo)" if "ofi" in name else ""
        print(f"  {name}: {imp}{marker}")

    model.booster_.save_model(os.path.join(os.path.dirname(__file__), "ml_lab_v3_model.txt"))
    print("\nModelo guardado en ml_lab_v3_model.txt")


if __name__ == "__main__":
    main()
