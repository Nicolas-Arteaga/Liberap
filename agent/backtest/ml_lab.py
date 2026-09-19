"""
2026-08-19: Laboratorio ML real -- pedido explicito tras que el usuario
señalara (con razon) que el "laboratorio evolutivo" de ayer no era mas que
un buscador de parametros dentro de 5 plantillas fijas (nivel, banda, RSI,
cruce de medias, pullback de MA) -- no podia encontrar nada que esas 5
plantillas no pudieran expresar de entrada, por eso el techo nunca superaba
~$125/mes por mas generaciones que corriera.

Esto es distinto: en vez de una regla escrita a mano, un modelo de gradient
boosting (LightGBM) aprende de ~25 features numericas crudas (RSI, distancia
a medias, ATR%, %B de Bollinger, momentum de 1h/4h/24h, volumen relativo,
hora del dia) que combinacion de esas features predice un trade rentable --
la combinacion la encuentra el modelo, no un humano.

Disciplina de honestidad de esta sesion, aplicada aca tambien:
  - Split CRONOLOGICO train/test (nunca random shuffle) -- el modelo nunca
    ve el futuro durante el entrenamiento.
  - Metricas reportadas SOLO sobre el test set (out-of-sample real).
  - El backtest final de la estrategia derivada del modelo usa el mismo
    motor honesto de siempre: vetos reales (validate_pre_trade) + limite
    real de 3 cupos x $150 (_apply_capital_sim).
  - No se promete ningun numero de $/mes hasta tener el resultado real del
    test set.
"""
import sys
import os
import sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_basket, load_15m, DB_PATH, MARGIN, FEE, _apply_capital_sim  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

STRIDE = 4          # samplea cada 4 velas de 15m (1h) -- reduce autocorrelacion/tamano
HORIZON = 96         # 24h max para resolver el trade (TP/SL/timeout)
ATR_SL_MULT = 2.0
RR_MULT = 3.0
TRAIN_FRAC = 0.70    # 70% cronologico para train, 30% para test (nunca mezclado)


def compute_features(rows):
    """rows: lista de (open_time, open, high, low, close, volume) ordenada.
    Devuelve DataFrame con ~25 features numericas por vela, indexado igual
    que rows (NaN donde no hay historia suficiente)."""
    n = len(rows)
    closes = np.array([r[4] for r in rows], dtype=float)
    highs = np.array([r[2] for r in rows], dtype=float)
    lows = np.array([r[3] for r in rows], dtype=float)
    vols = np.array([r[5] for r in rows], dtype=float)
    ts = np.array([r[0] for r in rows], dtype=np.int64)

    def sma(period):
        s = pd.Series(closes)
        return s.rolling(period).mean().values

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
    vol_rel = vols / np.where(vol_ma20 == 0, np.nan, vol_ma20)

    mom_4 = closes / np.roll(closes, 4) - 1     # 1h
    mom_16 = closes / np.roll(closes, 16) - 1    # 4h
    mom_96 = closes / np.roll(closes, 96) - 1    # 24h
    for arr, k in [(mom_4, 4), (mom_16, 16), (mom_96, 96)]:
        arr[:k] = np.nan

    dist_ma7 = (closes - ma7) / ma7 * 100
    dist_ma25 = (closes - ma25) / ma25 * 100
    dist_ma99 = (closes - ma99) / ma99 * 100
    ma7_slope = (ma7 - np.roll(ma7, 4)) / np.roll(ma7, 4) * 100
    ma7_slope[:4] = np.nan

    atr_pct = a14 / closes * 100
    atr_ratio = a14 / np.where(np.roll(a14, 96) == 0, np.nan, np.roll(a14, 96))  # volatilidad actual vs hace 24h
    atr_ratio[:96] = np.nan

    hour = pd.to_datetime(ts, unit="ms").hour.values
    dow = pd.to_datetime(ts, unit="ms").dayofweek.values

    df = pd.DataFrame({
        "rsi14": r14, "dist_ma7": dist_ma7, "dist_ma25": dist_ma25, "dist_ma99": dist_ma99,
        "ma7_slope": ma7_slope, "atr_pct": atr_pct, "atr_ratio": atr_ratio, "bb_pct": bb_pct,
        "vol_rel": vol_rel, "mom_1h": mom_4, "mom_4h": mom_16, "mom_24h": mom_96,
        "hour": hour, "dow": dow,
    })
    return df, a14, ts


def label_outcomes(rows, atr_arr, idx, side, sl_mult=ATR_SL_MULT, rr_mult=RR_MULT, horizon=HORIZON):
    """Simula hacia adelante desde idx (entry=close[idx]) con SL/TP por ATR.
    side: 0=LONG, 1=SHORT. Devuelve (label, r_multiple) o (None, None) si no
    resuelve dentro del horizonte (se descarta, no se etiqueta a ciegas)."""
    a = atr_arr[idx]
    if a is None or np.isnan(a) or a <= 0:
        return None, None
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
            return 0, -1.0  # ambiguo en la misma vela -> conservador, cuenta como perdida
        if hit_tp:
            return 1, rr_mult
        if hit_sl:
            return 0, -1.0
    return None, None  # timeout, no se etiqueta


def build_dataset(conn, basket, max_symbols=None):
    rows_all = []
    symbols = basket if max_symbols is None else basket[:max_symbols]
    for si, symbol in enumerate(symbols):
        rows = load_15m(conn, symbol)
        if len(rows) < 400:
            continue
        feats, atr_arr, ts = compute_features(rows)
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
            print(f"  {si+1}/{len(symbols)} simbolos procesados, {len(rows_all)} muestras acumuladas", flush=True)
    return pd.DataFrame(rows_all)


def main():
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score

    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)
    print(f"Universo: {len(basket)} simbolos | construyendo dataset (stride={STRIDE}, horizon={HORIZON})...")

    df = build_dataset(conn, basket)
    print(f"\nDataset total: {len(df)} muestras | WR base: {df['label'].mean()*100:.2f}%")

    # Split CRONOLOGICO real -- nunca mezclar train/test por tiempo.
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
    print(f"\n=== VALIDACION OUT-OF-SAMPLE (el modelo nunca vio estos datos en train) ===")
    print(f"AUC test: {auc:.4f} (0.50 = no mejor que azar, 1.0 = perfecto)")

    test = test.copy()
    test["proba"] = proba_test
    for thresh in (0.55, 0.60, 0.65, 0.70):
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
    for name, imp in importances[:10]:
        print(f"  {name}: {imp}")

    model.booster_.save_model(os.path.join(os.path.dirname(__file__), "ml_lab_model.txt"))
    df.to_pickle(os.path.join(os.path.dirname(__file__), "ml_lab_dataset.pkl"))
    print("\nModelo guardado en ml_lab_model.txt, dataset en ml_lab_dataset.pkl")


if __name__ == "__main__":
    main()
