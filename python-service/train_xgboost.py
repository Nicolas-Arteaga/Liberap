import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, classification_report, precision_score
from sklearn.model_selection import TimeSeriesSplit
from imblearn.over_sampling import SMOTE
import joblib
import json
import os
from datetime import datetime

def train_ensemble(data_path):
    if not os.path.exists(data_path):
        print("❌ Dataset not found.")
        return

    df = pd.read_csv(data_path)
    features = ['rsi', 'adx', 'atr', 'funding_rate', 'oi_change', 'vol_ratio', 'fng_value', 'trend_4h', 'liq_proxy']
    X = df[features]
    y = df['label']
    
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"🚀 Training Ensemble on {len(X_train)} samples...")
    smote = SMOTE(sampling_strategy=0.4, random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train, y_train)

    # 1. XGBoost
    print("🌲 Training XGBoost...")
    model_xgb = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.03, random_state=42)
    model_xgb.fit(X_train_bal, y_train_bal)
    
    # 2. LightGBM
    print("🌿 Training LightGBM...")
    model_lgb = lgb.LGBMClassifier(n_estimators=200, max_depth=6, learning_rate=0.03, random_state=42, verbose=-1)
    model_lgb.fit(X_train_bal, y_train_bal)
    
    # 3. Random Forest
    print("🌳 Training Random Forest...")
    model_rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model_rf.fit(X_train_bal, y_train_bal)
    
    # Ensemble Probability (Average)
    prob_xgb = model_xgb.predict_proba(X_test)[:, 1]
    prob_lgb = model_lgb.predict_proba(X_test)[:, 1]
    prob_rf = model_rf.predict_proba(X_test)[:, 1]
    
    ensemble_prob = (prob_xgb + prob_lgb + prob_rf) / 3
    
    # Find Optimal Strong Threshold
    best_f1 = 0
    opt_threshold = 0.4
    for th in np.arange(0.2, 0.7, 0.05):
        f1 = f1_score(y_test, (ensemble_prob >= th).astype(int))
        if f1 > best_f1:
            best_f1, opt_threshold = f1, th

    print(f"\n🎯 Optimal Ensemble Threshold: {opt_threshold:.2f} (F1: {best_f1:.4f})")
    
    # Stats
    preds = (ensemble_prob >= opt_threshold).astype(int)
    print("\n--- Ensemble Performance ---")
    print(classification_report(y_test, preds))
    
    # Save Models
    model_xgb.save_model("ensemble_xgb.json")
    model_lgb.booster_.save_model("ensemble_lgb.txt")
    joblib.dump(model_rf, "ensemble_rf.joblib")
    
    # Save Metadata
    meta = {
        "features": features,
        "thresholds": {
            "weak": float(opt_threshold * 0.8),
            "medium": float(opt_threshold),
            "strong": float(opt_threshold * 1.3)
        },
        "f1_score": float(best_f1),
        "last_training": datetime.now().isoformat()
    }
    with open("model_meta.json", "w") as f:
        json.dump(meta, f)
        
    print("✅ Ensemble Models saved. Ready for Millionaire Mode.")

if __name__ == "__main__":
    train_ensemble("millionaire_dataset.csv")
