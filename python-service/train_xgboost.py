import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, classification_report, precision_score
from imblearn.over_sampling import SMOTE
import joblib
import json
import os
import argparse
from datetime import datetime

def train_style_ensemble(data_path, style="swing"):
    if not os.path.exists(data_path):
        print(f"❌ Dataset {data_path} not found.")
        return

    # Create directory structure
    save_dir = f"models/{style}"
    os.makedirs(save_dir, exist_ok=True)

    df = pd.read_csv(data_path)
    features = ['rsi', 'adx', 'atr', 'funding_rate', 'oi_change', 'vol_ratio', 'fng_value', 'trend_4h', 'liq_proxy']
    X = df[features]
    y = df['label']
    
    # Split
    train_idx = int(len(X) * 0.7)
    val_idx = int(len(X) * 0.85)
    X_train, y_train = X.iloc[:train_idx], y.iloc[:train_idx]
    X_val, y_val = X.iloc[train_idx:val_idx], y.iloc[train_idx:val_idx]
    X_test, y_test = X.iloc[val_idx:], y.iloc[val_idx:]
    
    print(f"🚀 Training {style.upper()} Ensemble on {len(X_train)} samples...")
    # Higher oversampling for scalping (rare events in fast TFs)
    sampling = 0.4 if style == "scalping" else 0.35
    smote = SMOTE(sampling_strategy=sampling, random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train, y_train)

    # 1. XGBoost
    model_xgb = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.03, random_state=42)
    model_xgb.fit(X_train_bal, y_train_bal)
    
    # 2. LightGBM
    model_lgb = lgb.LGBMClassifier(n_estimators=300, max_depth=6, learning_rate=0.03, random_state=42, verbose=-1)
    model_lgb.fit(X_train_bal, y_train_bal)
    
    # 3. Random Forest
    model_rf = RandomForestClassifier(n_estimators=150, max_depth=10, random_state=42)
    model_rf.fit(X_train_bal, y_train_bal)
    
    # --- Weighting (Validation) ---
    def get_p(model, Xv, yv):
        probs = model.predict_proba(Xv)[:, 1]
        preds = (probs >= 0.4).astype(int)
        return max(precision_score(yv, preds, zero_division=0), 0.1)

    w = [get_p(model_xgb, X_val, y_val), get_p(model_lgb, X_val, y_val), get_p(model_rf, X_val, y_val)]
    total_w = sum(w)
    weights = {"xgb": round(w[0]/total_w,3), "lgb": round(w[1]/total_w,3), "rf": round(w[2]/total_w,3)}
    
    # --- Threshold Discovery (Validation) ---
    prob_val = (model_xgb.predict_proba(X_val)[:, 1] * weights['xgb'] +
                model_lgb.predict_proba(X_val)[:, 1] * weights['lgb'] +
                model_rf.predict_proba(X_val)[:, 1] * weights['rf'])
    
    best_f1, opt_th = 0, 0.45
    for th in np.arange(0.3, 0.7, 0.05):
        f1 = f1_score(y_val, (prob_val >= th).astype(int))
        if f1 > best_f1: best_f1, opt_th = f1, th

    # --- Final Performance (Test Set) ---
    prob_test = (model_xgb.predict_proba(X_test)[:, 1] * weights['xgb'] +
                 model_lgb.predict_proba(X_test)[:, 1] * weights['lgb'] +
                 model_rf.predict_proba(X_test)[:, 1] * weights['rf'])
    final_preds = (prob_test >= opt_th).astype(int)
    
    report = classification_report(y_test, final_preds)
    final_f1 = f1_score(y_test, final_preds)
    final_prec = precision_score(y_test, final_preds, zero_division=0)
    
    print(f"\n--- {style.upper()} Final Performance (Test Set) ---")
    print(f"Optimal Threshold: {opt_th:.2f}")
    print(report)

    # --- Save ---
    model_xgb.save_model(f"{save_dir}/ensemble_xgb.json")
    model_lgb.booster_.save_model(f"{save_dir}/ensemble_lgb.txt")
    joblib.dump(model_rf, f"{save_dir}/ensemble_rf.joblib")
    
    meta = {
        "style": style,
        "features": features,
        "weights": weights,
        "thresholds": {"weak": 0.35, "medium": float(opt_th), "strong": float(min(opt_th*1.2, 0.85))},
        "performance": {
            "f1": float(final_f1),
            "precision": float(final_prec)
        },
        "last_training": datetime.now().isoformat()
    }
    with open(f"{save_dir}/model_meta.json", "w") as f: json.dump(meta, f)
    
    print(f"✅ {style.upper()} Models and Metrics saved to {save_dir}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", default="swing", choices=["scalping", "day", "swing"])
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    train_style_ensemble(args.data, args.style)
