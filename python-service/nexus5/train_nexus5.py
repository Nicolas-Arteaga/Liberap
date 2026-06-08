"""
NEXUS-5 Training Script — xgb_nexus5_v1
Uso: python train_nexus5.py --data data/nexus5_dataset.csv

El CSV debe tener las 18 features + columna 'label':
  1 = el precio se movió >3% en las próximas 3 velas (horizonte corto)
  0 = no

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

NEXUS5_FEATURES = [
    "compression_range",
    "ignition_candle",
    "efficiency_check",
    "displacement_fvg",
    "micro_choch",
    "instant_order_block",
    "compression_zone",
    "sos_detected",
    "jumping_creek",
    "fractal_high_break",
    "ema7_angle",
    "hh_hl_sequence",
    "relative_vol_multiplier",
    "vol_intensity",
    "buying_imbalance",
    "atr_expansion",
    "z_score",
    "rsi_velocity",
]


def train(data_path: str):
    save_dir = "models/nexus5"
    os.makedirs(save_dir, exist_ok=True)

    df = pd.read_csv(data_path)
    X = df[NEXUS5_FEATURES].values
    y = df['label'].values

    n = len(X)
    train_idx = int(n * 0.70)
    val_idx   = int(n * 0.85)

    X_train, y_train = X[:train_idx], y[:train_idx]
    X_val,   y_val   = X[train_idx:val_idx], y[train_idx:val_idx]
    X_test,  y_test  = X[val_idx:], y[val_idx:]

    # Walk-forward: train en ventanas temporales (anti-lookahead)
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=NEXUS5_FEATURES)
    dval   = xgb.DMatrix(X_val,   label=y_val,   feature_names=NEXUS5_FEATURES)
    dtest  = xgb.DMatrix(X_test,  label=y_test,  feature_names=NEXUS5_FEATURES)

    # Hyperparams optimizados para detección de ignición en 5m
    # max_depth más bajo para evitar overfitting en eventos raros (igniciones)
    # learning_rate más alto porque los eventos de ignición son muy distintivos
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 5,              # más conservador que NEXUS-15 (6)
        "learning_rate": 0.05,       # más rápido porque las señales son más claras
        "n_estimators": 400,
        "subsample": 0.85,
        "colsample_bytree": 0.80,
        "min_child_weight": 3,       # más permisivo para capturar igniciones raras
        "scale_pos_weight": 3.0,     # balanceo para clases desbalanceadas (igniciones son raras)
        "seed": 42,
    }

    model = xgb.train(
        params,
        dtrain,
        num_boost_round=400,
        evals=[(dval, "val")],
        early_stopping_rounds=25,
        verbose_eval=50,
    )

    # Threshold óptimo en validación
    # Para NEXUS-5 usamos un threshold más bajo (más agresivo) — preferimos falsos positivos
    # a perdernos una ignición real. El RSI Bypass y el volume check filtran el ruido.
    val_probs = model.predict(dval)
    best_f1, best_th = 0, 0.5
    for th in np.arange(0.25, 0.70, 0.05):
        f1 = f1_score(y_val, (val_probs >= th).astype(int))
        if f1 > best_f1:
            best_f1, best_th = f1, th

    # Evaluación final en test
    test_probs = model.predict(dtest)
    test_preds = (test_probs >= best_th).astype(int)
    print(classification_report(y_test, test_preds))

    # Guardar modelo
    model.save_model(f"{save_dir}/xgb_nexus5_v1.json")
    meta = {
        "features": NEXUS5_FEATURES,
        "threshold": float(best_th),
        "f1_test": float(f1_score(y_test, test_preds)),
        "n_estimators": model.best_iteration,
        "trained_at": datetime.now().isoformat(),
        "note": "NEXUS-5 Ignition Core — 5m candles, label=price moved >3% in next 3 candles",
    }
    with open(f"{save_dir}/nexus5_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"✅ NEXUS-5 model saved to {save_dir}/")
    print(f"   Threshold: {best_th:.2f} (más agresivo que NEXUS-15)")
    print(f"   F1 Test: {f1_score(y_test, test_preds):.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Train NEXUS-5 XGBoost model")
    ap.add_argument("--data", required=True, help="Path to CSV with 18 features + label column")
    args = ap.parse_args()
    train(args.data)
