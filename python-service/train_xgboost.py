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
    features = ['rsi', 'macd_diff', 'adx', 'vol_ratio'] # Simplified MVP features
    X = df[features]
    y = df['label'] # target: 1 if >0.5% in 1h
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)
    
    print(f"🚀 Training XGBoost on {len(X_train)} samples...")
    
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.05,
        objective='binary:logistic'
    )
    
    model.fit(X_train, y_train)
    
    # Evaluation
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    f1 = f1_score(y_test, preds)
    
    print("\n--- Model Performance ---")
    print(f"Accuracy: {acc:.1%}")
    print(f"F1 Score: {f1:.2f}")
    print("\nClassification Report:")
    print(classification_report(y_test, preds))
    
    if acc > 0.55:
        model.save_model("xgboost_v1.json")
        print("✅ Model saved as xgboost_v1.json. Ready for production.")
    else:
        print("⚠️ Model accuracy < 55%. Needs better feature engineering or more data.")

if __name__ == "__main__":
    # symbol = "BTC/USDT"
    data_file = "historical_BTC_USDT.csv"
    train_verge_model(data_file)
