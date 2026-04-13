"""
Script de entrenamiento para xgb_nexus15_v1.
Uso: python train_nexus15.py --data data/nexus15_dataset.csv

El CSV debe tener las 20 features + columna 'label' (1 = alcista en N+5 velas, 0 = no).
Walk-forward validation: 70% train, 15% val, 15% test.
"""
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import f1_score, precision_score, classification_report
import json
import os
import argparse
from datetime import datetime

NEXUS15_FEATURES = [
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "consecutive_bull_bars", "order_block_detected", "fair_value_gap",
    "bos_detected", "wyckoff_phase_num", "spring_detected", "upthrust_detected",
    "fractal_high_5", "fractal_low_5", "trend_structure",
    "volume_ratio_20", "cvd_delta_norm", "volume_surge_bullish",
    "poc_proximity", "rsi_14_norm", "macd_histogram", "atr_percent",
]


def train(data_path: str):
    save_dir = "models/nexus15"
    os.makedirs(save_dir, exist_ok=True)

    df = pd.read_csv(data_path)
    X = df[NEXUS15_FEATURES].values
    y = df['label'].values

    n = len(X)
    train_idx = int(n * 0.70)
    val_idx   = int(n * 0.85)

    X_train, y_train = X[:train_idx], y[:train_idx]
    X_val,   y_val   = X[train_idx:val_idx], y[train_idx:val_idx]
    X_test,  y_test  = X[val_idx:], y[val_idx:]

    # Walk-forward: train en ventanas temporales (anti-lookahead)
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=NEXUS15_FEATURES)
    dval   = xgb.DMatrix(X_val,   label=y_val,   feature_names=NEXUS15_FEATURES)
    dtest  = xgb.DMatrix(X_test,  label=y_test,  feature_names=NEXUS15_FEATURES)

    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 6,
        "learning_rate": 0.03,
        "n_estimators": 500,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "seed": 42,
    }

    model = xgb.train(
        params,
        dtrain,
        num_boost_round=500,
        evals=[(dval, "val")],
        early_stopping_rounds=30,
        verbose_eval=50,
    )

    # Threshold óptimo en validación
    val_probs = model.predict(dval)
    best_f1, best_th = 0, 0.5
    for th in np.arange(0.3, 0.75, 0.05):
        f1 = f1_score(y_val, (val_probs >= th).astype(int))
        if f1 > best_f1:
            best_f1, best_th = f1, th

    # Evaluación final en test
    test_probs = model.predict(dtest)
    test_preds = (test_probs >= best_th).astype(int)
    print(classification_report(y_test, test_preds))

    # Guardar
    model.save_model(f"{save_dir}/xgb_nexus15_v1.json")
    meta = {
        "features": NEXUS15_FEATURES,
        "threshold": float(best_th),
        "f1_test": float(f1_score(y_test, test_preds)),
        "n_estimators": model.best_iteration,
        "trained_at": datetime.now().isoformat(),
    }
    with open(f"{save_dir}/nexus15_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"✅ NEXUS-15 model saved to {save_dir}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    args = ap.parse_args()
    train(args.data)
