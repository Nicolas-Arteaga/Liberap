import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
import os

def train_verge_model(data_path):
    """
    Trains the XGBoost model for Verge based on historical CSV data.
    """
    if not os.path.exists(data_path):
        print(f"❌ Error: {data_path} not found. Run train_model.py first.")
        return

    df = pd.read_csv(data_path)
    
    # Feature Selection (must match inference in main.py)
    features = ['rsi', 'macd_diff', 'adx', 'vol_ratio', 'roc', 'atr', 'volatility']
    X = df[features]
    y = df['label']
    
    # Split (Chronological split for time-series)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"🚀 Training XGBoost on {len(X_train)} samples...")
    print(f"Class distribution: {y_train.value_counts().to_dict()}")
    
    # Calculate scale_pos_weight for imbalance
    pos_count = sum(y_train == 1)
    neg_count = sum(y_train == 0)
    spw = neg_count / pos_count if pos_count > 0 else 1
    print(f"⚖️ Using scale_pos_weight: {spw:.2f}")

    model = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.03,
        scale_pos_weight=spw,
        objective='binary:logistic',
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Threshold Optimization (Find best threshold for F1)
    import numpy as np
    probs = model.predict_proba(X_test)[:, 1]
    
    best_threshold = 0.5
    best_f1 = 0
    
    for th in np.arange(0.1, 0.9, 0.05):
        current_preds = (probs >= th).astype(int)
        current_f1 = f1_score(y_test, current_preds)
        if current_f1 > best_f1:
            best_f1 = current_f1
            best_threshold = th
            
    print(f"\n🎯 Optimal Threshold found: {best_threshold:.2f} (Max F1: {best_f1:.4f})")
    
    final_preds = (probs >= best_threshold).astype(int)
    acc = accuracy_score(y_test, final_preds)
    
    print("\n--- Final Model Performance ---")
    print(f"Accuracy: {acc:.1%}")
    print(f"F1 Score (Pos Class): {best_f1:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, final_preds))
    
    # Save model and meta-data (threshold)
    model.save_model("xgboost_v1.json")
    with open("model_meta.json", "w") as f:
        import json
        json.dump({"threshold": float(best_threshold), "features": features}, f)
        
    print("✅ Model and Metadata saved. Ready for production.")

if __name__ == "__main__":
    # symbol = "BTC/USDT"
    data_file = "historical_BTC_USDT.csv"
    train_verge_model(data_file)
