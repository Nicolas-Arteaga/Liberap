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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
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

app = FastAPI(title="VERGE AI - Full Stable Suite", version="1.8.1")

# Models Paths
XGB_PATH = "ensemble_xgb.json"
LGB_PATH = "ensemble_lgb.txt"
RF_PATH = "ensemble_rf.joblib"
META_PATH = "model_meta.json"

# --- Models ---

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
    tf1h: Optional[List[OHLCV]] = []
    tf4h: Optional[List[OHLCV]] = []

class MarketDataRequest(BaseModel):
    symbol: str
    timeframe: str
    data: List[OHLCV]

class RegimeResponse(BaseModel):
    regime: str
    volatility_score: float
    trend_strength: float
    structure: str = "Neutral"

class TechnicalsResponse(BaseModel):
    macd_histogram: float
    bb_width: float
    adx: float
    rsi: float

class WhaleData(BaseModel):
    whale_score: float
    recent_large_tx_count: int
    sentiment: str

class SuperAnalysisRequest(BaseModel):
    symbol: str
    ohlcv: MultiTimeframeOHLCV
    sentiment_score: float
    whale_activity: Optional[WhaleData] = None
    funding_rate: Optional[float] = 0.0
    oi_change: Optional[float] = 0.0

class SuperAnalysisResponse(BaseModel):
    signal_type: str
    strength: str
    confidence: float
    reasoning: List[str]
    suggested_leverage: int
    multi_tf_bias: str
    whale_alert: bool = False

# --- Core Logic ---

class EnsemblePredictor:
    def __init__(self):
        self.xgb = None; self.lgb = None; self.rf = None; self.meta = {}
        self.features = ['rsi', 'adx', 'atr', 'funding_rate', 'oi_change', 'vol_ratio', 'fng_value', 'trend_4h', 'liq_proxy']
        self.load_all()

    def load_all(self):
        try:
            if HAS_XGB and os.path.exists(XGB_PATH):
                self.xgb = xgb.Booster(); self.xgb.load_model(XGB_PATH)
            if HAS_LGB and os.path.exists(LGB_PATH):
                self.lgb = lgb.Booster(model_file=LGB_PATH)
            if HAS_JOBLIB and os.path.exists(RF_PATH):
                self.rf = joblib.load(RF_PATH)
            if os.path.exists(META_PATH):
                with open(META_PATH, "r") as f: self.meta = json.load(f)
            logger.info("✅ Models loaded successfully.")
        except Exception as e: logger.error(f"❌ Error loading models: {e}")

    def predict(self, feature_values):
        probs = []
        if self.xgb:
            dm = xgb.DMatrix([feature_values], feature_names=self.features)
            probs.append(self.xgb.predict(dm)[0])
        if self.lgb: probs.append(self.lgb.predict([feature_values])[0])
        if self.rf: probs.append(self.rf.predict_proba([feature_values])[0][1])
        return sum(probs) / len(probs) if probs else None

predictor = EnsemblePredictor()
sentiment_svc = SentimentService()

def get_fng_realtime():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=3)
        return float(r.json()['data'][0]['value'])
    except: return 50.0

# --- Endpoints ---

@app.get("/model-status")
async def model_status():
    return {
        "xgb": predictor.xgb is not None,
        "lgb": predictor.lgb is not None,
        "rf": predictor.rf is not None,
        "meta_loaded": bool(predictor.meta),
        "last_training": predictor.meta.get("last_training", "N/A"),
        "features": predictor.features
    }

@app.post("/analyze-technicals", response_model=TechnicalsResponse)
async def analyze_technicals(request: MarketDataRequest):
    df = pd.DataFrame([d.model_dump() for d in request.data])
    if len(df) < 20: return TechnicalsResponse(macd_histogram=0, bb_width=0, adx=0, rsi=50)
    
    rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    macd = ta.trend.MACD(df["close"]).macd_diff().iloc[-1]
    adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    bb_w = ta.volatility.BollingerBands(df["close"]).bollinger_wband().iloc[-1]
    
    return TechnicalsResponse(macd_histogram=float(macd), bb_width=float(bb_w), adx=float(adx), rsi=float(rsi))

@app.post("/detect-regime", response_model=RegimeResponse)
async def detect_regime(request: MarketDataRequest):
    df = pd.DataFrame([d.model_dump() for d in request.data])
    if len(df) < 20: return RegimeResponse(regime="Ranging", volatility_score=0, trend_strength=0)
    
    adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range().iloc[-1] / df["close"].iloc[-1]
    
    regime = "Ranging"
    if adx > 25: regime = "BullTrend" if df["close"].iloc[-1] > df["close"].rolling(20).mean().iloc[-1] else "BearTrend"
    
    return RegimeResponse(regime=regime, volatility_score=float(atr*100), trend_strength=float(adx))

@app.post("/analyze-super", response_model=SuperAnalysisResponse)
async def analyze_super(request: SuperAnalysisRequest):
    try:
        # Data Preparation
        df1h = pd.DataFrame([d.model_dump() for d in (request.ohlcv.tf1h or [])])
        if len(df1h) < 20: df1h = pd.DataFrame([d.model_dump() for d in (request.ohlcv.tf5m or [])])
        if len(df1h) < 10: # Extra lenient for testing
             return SuperAnalysisResponse(signal_type="Hold", strength="None", confidence=0.0, reasoning=["Insufficient Data"], suggested_leverage=1, multi_tf_bias="Neutral")

        df4h = pd.DataFrame([d.model_dump() for d in (request.ohlcv.tf4h or [])])
        trend_4h = 1 if (not df4h.empty and len(df4h) >= 20 and df4h['close'].iloc[-1] > df4h['close'].rolling(20).mean().iloc[-1]) else 0
        
        # Features
        rsi = ta.momentum.RSIIndicator(df1h["close"]).rsi().iloc[-1]
        adx = ta.trend.ADXIndicator(df1h["high"], df1h["low"], df1h["close"]).adx().iloc[-1]
        atr = ta.volatility.AverageTrueRange(df1h["high"], df1h["low"], df1h["close"]).average_true_range().iloc[-1] / df1h["close"].iloc[-1]
        vol_ma = df1h['volume'].rolling(20).mean().iloc[-1]
        vol_ratio = df1h['volume'].iloc[-1] / (vol_ma or 1)
        shadow = (df1h['high'].iloc[-1] - df1h['low'].iloc[-1]) / df1h['close'].iloc[-1]
        liq_proxy = shadow * df1h['volume'].iloc[-1] / (df1h['volume'].mean() * 10 or 1)
        fng = get_fng_realtime()

        fe_vals = [rsi, adx, atr, request.funding_rate or 0, request.oi_change or 0, vol_ratio, fng, trend_4h, liq_proxy]
        avg_prob = predictor.predict(fe_vals) if predictor.xgb else 0.45
        
        # Millionaire Filter Layer
        base_threshold = 0.50
        signal, strength = "Hold", "None"
        reasons = [f"Base Probability: {avg_prob:.1%}"]

        if trend_4h == 0:
            reasons.append("🚫 Filtered: Bearish 4h Trend.")
            return SuperAnalysisResponse(signal_type="Hold", strength="Weak", confidence=avg_prob, reasoning=reasons, suggested_leverage=1, multi_tf_bias="Bearish")

        if rsi > 70: base_threshold += 0.10; reasons.append(f"⚠️ RSI High ({rsi:.1f}), threshold increased.")
        if fng > 75: base_threshold += 0.05; reasons.append("⚠️ Greed adjustment (+5%).")

        if avg_prob >= (base_threshold + 0.10): signal, strength = "Buy", "Strong"
        elif avg_prob >= base_threshold: signal, strength = "Buy", "Medium"
        else: signal, strength = "Hold", "Weak"; reasons.append(f"❌ Below target ({base_threshold:.2f})")

        return SuperAnalysisResponse(
            signal_type=signal, strength=strength, confidence=round(avg_prob, 2),
            reasoning=reasons, suggested_leverage=5 if strength == "Strong" else 3 if strength == "Medium" else 1,
            multi_tf_bias="Bullish" if trend_4h else "Bearish"
        )
    except Exception as e:
        logger.exception("Error")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)