"""
2026-08-19: v2 -- fusion de cosas que nunca se probaron juntas en este
proyecto, a pedido explicito del usuario ("hace cosas locas, fusiona
cosas"). Mismo rigor de siempre (split cronologico real, out-of-sample,
motor honesto) pero features nuevas que v1 no tenia:

  - Fuerza relativa vs BTC: como se mueve la moneda COMPARADA con el
    lider del mercado en la misma ventana, no en el vacio (v1 solo tenia
    momentum absoluto).
  - Micro-momentum (1-3 velas): v1 solo tenia momentum de 1h/4h/24h, nada
    de reaccion inmediata.
  - Distancia a maximo/minimo de las ultimas 96 velas (24h): proximidad a
    ruptura real, no solo distancia a una media movil.
  - Volumen como z-score (no solo ratio) -- captura anomalias mas fuerte.
  - Descartadas explicitamente: whale_events y orderbook_ofi tienen
    timestamps corruptos (epoch 1970, bug de datos separado, no arreglado
    hoy) -- no se pueden alinear con precio, se prueban en otra sesion una
    vez arreglado ese bug.
"""
import sys
import os
import sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, load_15m, DB_PATH  # noqa: E402
from backtest.ml_lab import label_outcomes, STRIDE, HORIZON, TRAIN_FRAC  # noqa: E402


def compute_features_v2(rows, btc_closes_by_ts):
    n = len(rows)
    closes = np.array([r[4] for r in rows], dtype=float)
    highs = np.array([r[2] for r in rows], dtype=float)
    lows = np.array([r[3] for r in rows], dtype=float)
    vols = np.array([r[5] for r in rows], dtype=float)
    ts = np.array([r[0] for r in rows], dtype=np.int64)

    def sma(period):
        return pd.Series(closes).rolling(period).mean().values

    def rsi(period=14):
        s = pd.Series(closes)
        delta = s.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - 100 / (1 + rs)).values

    def atr(period=14):
        s_h, s_l, s_c = pd.Series(highs), pd.Series(lows), pd.Series(closes)
        pc = s_c.shift(1)
        tr = pd.concat([s_h - s_l, (s_h - pc).abs(), (s_l - pc).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean().values

    ma7, ma25, ma99 = sma(7), sma(25), sma(99)
    r14 = rsi(14)
    a14 = atr(14)
    std20 = pd.Series(closes).rolling(20).std().values
    bb_mid = sma(20)
    bb_upper = bb_mid + 2 * std20
    bb_lower = bb_mid - 2 * std20
    bb_pct = (closes - bb_lower) / np.where((bb_upper - bb_lower) == 0, np.nan, bb_upper - bb_lower)

    vol_ma20 = pd.Series(vols).rolling(20).mean().values
    vol_std20 = pd.Series(vols).rolling(20).std().values
    vol_zscore = (vols - vol_ma20) / np.where(vol_std20 == 0, np.nan, vol_std20)  # NUEVO

    mom_4 = closes / np.roll(closes, 4) - 1
    mom_16 = closes / np.roll(closes, 16) - 1
    mom_96 = closes / np.roll(closes, 96) - 1
    for arr, k in [(mom_4, 4), (mom_16, 16), (mom_96, 96)]:
        arr[:k] = np.nan

    # NUEVO: micro-momentum inmediato
    mom_1 = closes / np.roll(closes, 1) - 1
    mom_2 = closes / np.roll(closes, 2) - 1
    mom_3 = closes / np.roll(closes, 3) - 1
    for arr, k in [(mom_1, 1), (mom_2, 2), (mom_3, 3)]:
        arr[:k] = np.nan

    # NUEVO: distancia a maximo/minimo de las ultimas 96 velas (24h)
    high_96 = pd.Series(highs).rolling(96).max().values
    low_96 = pd.Series(lows).rolling(96).min().values
    dist_from_high96 = (closes - high_96) / high_96 * 100
    dist_from_low96 = (closes - low_96) / low_96 * 100

    dist_ma7 = (closes - ma7) / ma7 * 100
    dist_ma25 = (closes - ma25) / ma25 * 100
    dist_ma99 = (closes - ma99) / ma99 * 100
    ma7_slope = (ma7 - np.roll(ma7, 4)) / np.roll(ma7, 4) * 100
    ma7_slope[:4] = np.nan

    atr_pct = a14 / closes * 100
    atr_ratio = a14 / np.where(np.roll(a14, 96) == 0, np.nan, np.roll(a14, 96))
    atr_ratio[:96] = np.nan

    hour = pd.to_datetime(ts, unit="ms").hour.values
    dow = pd.to_datetime(ts, unit="ms").dayofweek.values

    # NUEVO: fuerza relativa vs BTC -- el propio momentum de 16 velas (4h)
    # MENOS el de BTC en la misma ventana exacta de tiempo (alineado por ts).
    btc_vals = np.array([btc_closes_by_ts.get(t, np.nan) for t in ts], dtype=float)
    btc_mom_16 = btc_vals / np.roll(btc_vals, 16) - 1
    btc_mom_16[:16] = np.nan
    rel_strength_btc = mom_16 - btc_mom_16

    df = pd.DataFrame({
        "rsi14": r14, "dist_ma7": dist_ma7, "dist_ma25": dist_ma25, "dist_ma99": dist_ma99,
        "ma7_slope": ma7_slope, "atr_pct": atr_pct, "atr_ratio": atr_ratio, "bb_pct": bb_pct,
        "vol_zscore": vol_zscore, "mom_1": mom_1, "mom_2": mom_2, "mom_3": mom_3,
        "mom_1h": mom_4, "mom_4h": mom_16, "mom_24h": mom_96,
        "dist_from_high96": dist_from_high96, "dist_from_low96": dist_from_low96,
        "rel_strength_btc": rel_strength_btc,
        "hour": hour, "dow": dow,
    })
    return df, a14, ts


def build_dataset_v2(conn, basket):
    btc_rows = load_15m(conn, "BTCUSDT")
    btc_closes_by_ts = {r[0]: r[4] for r in btc_rows}
    print(f"BTC referencia cargada: {len(btc_closes_by_ts)} velas")

    rows_all = []
    for si, symbol in enumerate(basket):
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        feats, atr_arr, ts = compute_features_v2(rows, btc_closes_by_ts)
        for idx in range(150, len(rows) - HORIZON, STRIDE):
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
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | construyendo dataset v2 (stride={STRIDE}, horizon={HORIZON})...")

    df = build_dataset_v2(conn, basket)
    print(f"\nDataset total: {len(df)} muestras | WR base: {df['label'].mean()*100:.2f}%")

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
    print(f"\n=== VALIDACION OUT-OF-SAMPLE v2 ===")
    print(f"AUC test: {auc:.4f} (v1 fue 0.5298)")

    test = test.copy()
    test["proba"] = proba_test
    for thresh in (0.55, 0.60, 0.65, 0.70, 0.75):
        sub = test[test["proba"] >= thresh]
        if len(sub) < 20:
            print(f"  umbral {thresh}: solo {len(sub)} señales, insuficiente para medir")
            continue
        wr = sub["label"].mean() * 100
        avg_r = sub["r_multiple"].mean()
        print(f"  umbral proba>={thresh}: {len(sub)} señales | WR real: {wr:.2f}% | avg R: {avg_r:+.3f} "
              f"| esperanza: {'POSITIVA' if avg_r > 0 else 'negativa'}")

    importances = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1])
    print("\nFeatures mas importantes:")
    for name, imp in importances[:15]:
        print(f"  {name}: {imp}")

    model.booster_.save_model(os.path.join(os.path.dirname(__file__), "ml_lab_v2_model.txt"))
    df.to_pickle(os.path.join(os.path.dirname(__file__), "ml_lab_v2_dataset.pkl"))
    print("\nModelo guardado en ml_lab_v2_model.txt")


if __name__ == "__main__":
    main()
