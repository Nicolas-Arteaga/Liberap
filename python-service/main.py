import requests
from fastapi import FastAPI, HTTPException
from typing import List, Optional, Dict
from pydantic import BaseModel
import pandas as pd
import ta
import uvicorn
import logging
import sys
import os
import json
import numpy as np
from datetime import datetime, timedelta
from sentiment_service import SentimentService
from dotenv import load_dotenv

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("VERGE_AI")

# Graceful Imports
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False
try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False
try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

load_dotenv()

app = FastAPI(title="VERGE AI - Phase 2.0 Multi-Style", version="2.0.0")

# --- Helper Models & Schema ---

class OHLCV(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class MultiTimeframeOHLCV(BaseModel):
    tf1m: Optional[List[OHLCV]] = []
    tf5m: Optional[List[OHLCV]] = []
    tf15m: Optional[List[OHLCV]] = []
    tf1h: Optional[List[OHLCV]] = []
    tf4h: Optional[List[OHLCV]] = []

class SuperAnalysisRequest(BaseModel):
    symbol: str
    ohlcv: MultiTimeframeOHLCV
    sentiment_score: float
    timeframe: Optional[str] = "1h" # New parameter for style detection
    funding_rate: Optional[float] = 0.0
    oi_change: Optional[float] = 0.0

class SuperAnalysisResponse(BaseModel):
    signal_type: str
    strength: str
    confidence: float
    reasoning: List[str]
    suggested_leverage: int
    multi_tf_bias: str
    style_active: str

# --- Multi-Style Intelligence Engine ---

class MultiStylePredictor:
    def __init__(self):
        self.predictors = {} # Cache for {style: Ensemble}
        self.style_map = {"5m": "scalping", "15m": "day", "30m": "day", "1h": "swing", "4h": "swing"}

    def _load_style(self, style):
        if style in self.predictors: return self.predictors[style]
        
        path = f"models/{style}/"
        if not os.path.exists(path): 
            # Fallback to root models if specific dir doesn't exist (backward compatibility)
            if style == "swing": path = "./" 
            else: return None
            
        try:
            p = {"xgb": None, "lgb": None, "rf": None, "meta": {}}
            if HAS_XGB and os.path.exists(f"{path}ensemble_xgb.json"):
                p["xgb"] = xgb.Booster(); p["xgb"].load_model(f"{path}ensemble_xgb.json")
            if HAS_LGB and os.path.exists(f"{path}ensemble_lgb.txt"):
                p["lgb"] = lgb.Booster(model_file=f"{path}ensemble_lgb.txt")
            if HAS_JOBLIB and os.path.exists(f"{path}ensemble_rf.joblib"):
                p["rf"] = joblib.load(f"{path}ensemble_rf.joblib")
            if os.path.exists(f"{path}model_meta.json"):
                with open(f"{path}model_meta.json", "r") as f: p["meta"] = json.load(f)
            
            if p["xgb"] or p["lgb"] or p["rf"]:
                self.predictors[style] = p
                return p
        except Exception as e:
            logger.error(f"Error loading {style}: {e}")
        return None

    def predict(self, style_key, features):
        p = self._load_style(style_key)
        if not p: return None
        
        probs = []
        w = p["meta"].get("weights", {"xgb": 0.33, "lgb": 0.33, "rf": 0.33})
        try:
            if p["xgb"]:
                dm = xgb.DMatrix([features], feature_names=p["meta"].get("features", []))
                probs.append(p["xgb"].predict(dm)[0] * w.get("xgb", 0.33))
            if p["lgb"]:
                probs.append(p["lgb"].predict([features])[0] * w.get("lgb", 0.33))
            if p["rf"]:
                probs.append(p["rf"].predict_proba([features])[0][1] * w.get("rf", 0.33))
            return sum(probs) if probs else None
        except: return None

predictor = MultiStylePredictor()

@app.post("/analyze-super", response_model=SuperAnalysisResponse)
async def analyze_super(request: SuperAnalysisRequest):
    try:
        # 1. Style Selection
        tf = request.timeframe or "1h"
        style = predictor.style_map.get(tf, "swing")
        
        # 2. Data Selection
        df_map = {"1h": request.ohlcv.tf1h, "15m": request.ohlcv.tf15m, "5m": request.ohlcv.tf5m}
        raw_data = df_map.get(tf, request.ohlcv.tf1h)
        if not raw_data or len(raw_data) < 10: raw_data = request.ohlcv.tf5m # Last try
        
        df = pd.DataFrame([d.model_dump() for d in raw_data])
        if len(df) < 5: return SuperAnalysisResponse(signal_type="Hold", strength="None", confidence=0.0, reasoning=["No Data"], suggested_leverage=1, multi_tf_bias="Neutral", style_active=style)

        # 3. Feature Prep (Fast Scale)
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1] if len(df) > 14 else 20
        atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range().iloc[-1] / df["close"].iloc[-1]
        vol_ma = df['volume'].rolling(min(len(df), 20)).mean().iloc[-1]
        vol_ratio = df['volume'].iloc[-1] / (vol_ma or 1)
        shadow = (df['high'] - df['low']) / df['close']
        liq_proxy = shadow * df['volume'].iloc[-1] / (df['volume'].mean() * 10 or 1)
        
        df4h = pd.DataFrame([d.model_dump() for d in (request.ohlcv.tf4h or [])])
        trend_4h = 1 if (not df4h.empty and len(df4h) >= 20 and df4h['close'].iloc[-1] > df4h['close'].rolling(20).mean().iloc[-1]) else 0
        
        fe_vals = [rsi, adx, atr, request.funding_rate or 0, request.oi_change or 0, vol_ratio, 50.0, trend_4h, liq_proxy]
        
        # 4. Predict
        avg_prob = predictor.predict(style, fe_vals)
        if avg_prob is None: avg_prob = 0.45 # Fallback

        # 5. Elite Filter
        p_meta = predictor.predictors.get(style, {}).get("meta", {})
        base_th = p_meta.get("thresholds", {}).get("medium", 0.55)
        
        signal, strength = "Hold", "None"
        reasons = [f"[{style.upper()}] Prob: {avg_prob:.1%}"]
        
        # Strategy Logic
        if trend_4h == 0 and style == "swing":
            reasons.append("🚫 Swing Filter: Bearish 4h trend detected.")
            return SuperAnalysisResponse(signal_type="Hold", strength="Weak", confidence=avg_prob, reasoning=reasons, suggested_leverage=1, multi_tf_bias="Bearish", style_active=style)

        if rsi > 70: base_th += 0.15; reasons.append("⚠️ Overbought: Threshold raised.")
        
        if avg_prob >= (base_th + 0.1): signal, strength = "Buy", "Strong"
        elif avg_prob >= base_th: signal, strength = "Buy", "Medium"
        else: signal, strength = "Hold", "Weak"; reasons.append(f"❌ Weak Signal (Target {base_th:.2f})")

        return SuperAnalysisResponse(
            signal_type=signal, strength=strength, confidence=round(avg_prob, 2),
            reasoning=reasons, suggested_leverage=5 if strength == "Strong" else 3 if strength == "Medium" else 1,
            multi_tf_bias="Bullish" if trend_4h else "Bearish",
            style_active=style
        )
    except Exception as e:
        logger.exception("Error")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)