import requests
from fastapi import FastAPI, HTTPException
from typing import List
from pydantic import BaseModel
import pandas as pd
import ta
import uvicorn
import logging
import sys
import os
from dotenv import load_dotenv
import numpy as np
import xgboost as xgb
import json
from datetime import datetime
from sentiment_service import SentimentService

# Load .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VERGE_AI")

app = FastAPI(title="VERGE AI Service (API Mode)", version="1.3.0")

# Configuration
MODEL_PATH = os.environ.get("MODEL_PATH", "xgboost_v1.json")
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    logger.error("❌ HF_TOKEN environment variable not set!")
    HF_TOKEN = "dev_token_placeholder"  # Solo para desarrollo local

logger.info(f"🔑 Token configurado: {'✓' if HF_TOKEN != 'dev_token_placeholder' else '✗'}")

API_URL = "https://router.huggingface.co/hf-inference/models/cardiffnlp/twitter-roberta-base-sentiment"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

class SentimentRequest(BaseModel):
    text: str

class SentimentResponse(BaseModel):
    sentiment: str
    confidence: float
    scores: dict

class OHLCV(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class MarketDataRequest(BaseModel):
    symbol: str
    timeframe: str
    data: List[OHLCV]

class RegimeResponse(BaseModel):
    regime: str
    volatility_score: float
    trend_strength: float

class TechnicalsResponse(BaseModel):
    macd_histogram: float
    bb_width: float
    adx: float
    rsi: float

class WhaleData(BaseModel):
    whale_score: float
    recent_large_tx_count: int
    sentiment: str

class MultiTimeframeOHLCV(BaseModel):
    tf1m: List[OHLCV]
    tf5m: List[OHLCV]
    tf15m: List[OHLCV]

class SuperAnalysisRequest(BaseModel):
    symbol: str
    ohlcv: MultiTimeframeOHLCV
    sentiment_score: float
    whale_activity: WhaleData

class SuperAnalysisResponse(BaseModel):
    signal_type: str # Buy / Sell / Hold
    confidence: float # 0.0 to 1.0
    reasoning: List[str]
    suggested_leverage: int
    multi_tf_bias: str
    whale_alert: bool

def get_neutral_fallback(error_msg: str):
    logger.warning(f"⚠️ Falling back to NEUTRAL due to error: {error_msg}")
    return SentimentResponse(
        sentiment="neutral",
        confidence=1.0,
        scores={"negative": 0.0, "neutral": 1.0, "positive": 0.0}
    )

@app.get("/health")
async def health_check():
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": "test"}, timeout=5)
        return {
            "status": "healthy" if response.status_code == 200 else "degraded",
            "mode": "api",
            "hf_status": response.status_code,
            "message": "Connected to HuggingFace API" if response.status_code == 200 else f"HF API error: {response.text}"
        }
    except Exception as e:
        return {"status": "error", "mode": "api", "error": str(e)}

class MonitoringService:
    """
    Logs predictions vs reality and auto-deactivates if performance drops.
    """
    def __init__(self, log_file="predictions_log.json"):
        self.log_file = log_file
        self.history = []
        self.active = True

    def log_prediction(self, prediction, probability, metadata):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "prediction": prediction,
            "probability": probability,
            "metadata": metadata,
            "realized": None
        }
        self.history.append(entry)
        # In a real scenario, we would persist this to a file or DB

    def verify_performance(self):
        # Rolling accuracy of last 50
        relevant = [h for h in self.history if h["realized"] is not None][-50:]
        if len(relevant) < 10: return True # Wait for enough data
        
        accuracy = sum(1 for h in relevant if h["prediction"] == h["realized"]) / len(relevant)
        if accuracy < 0.5:
            self.active = False
            logger.error(f"🚨 AUTO-DEACTIVATION: Rolling accuracy ({accuracy:.1%}) below 50%")
        return self.active

monitor = MonitoringService()

class XGBoostPredictor:
    """
    XGBoost-based MVP for Crypto Prediction.
    """
    def __init__(self, model_path=None):
        self.model = None
        self.model_path = model_path
        self.threshold = 0.5 # Default
        self.features = ['rsi', 'macd_diff', 'adx', 'vol_ratio', 'roc', 'atr', 'volatility']
        self.load_model()

    def load_model(self):
        if self.model_path and os.path.exists(self.model_path):
            try:
                self.model = xgb.Booster()
                self.model.load_model(self.model_path)
                logger.info(f"✅ Model loaded successfully from {self.model_path}")
                
                # Load metadata
                meta_path = "model_meta.json"
                if os.path.exists(meta_path):
                    with open(meta_path, "r") as f:
                        meta = json.load(f)
                        self.threshold = meta.get("threshold", 0.5)
                        self.features = meta.get("features", self.features)
                        logger.info(f"🎯 Threshold set to {self.threshold}")

            except Exception as e:
                logger.error(f"❌ Failed to load model from {self.model_path}: {e}")
                self.model = None
        else:
            logger.warning(f"⚠️ Model file NOT FOUND at {self.model_path}. Inference disabled.")

    def predict(self, feature_values):
        if not self.model:
            return None
        
        dmatrix = xgb.DMatrix([feature_values], feature_names=self.features)
        prob = self.model.predict(dmatrix)[0]
        return prob

# Global Predictor Instance
predictor = XGBoostPredictor(MODEL_PATH)
sentiment_svc = SentimentService()

@app.get("/model-status")
async def get_model_status():
    loaded = predictor.model is not None
    last_mod = None
    if loaded and os.path.exists(MODEL_PATH):
        mtime = os.path.getmtime(MODEL_PATH)
        last_mod = datetime.fromtimestamp(mtime).isoformat()
    
    return {
        "model_loaded": loaded,
        "model_path": MODEL_PATH,
        "last_training_date": last_mod,
        "status": "Ready" if loaded else "Waiting for model (Execute train_xgboost.py)"
    }

@app.post("/analyze-super", response_model=SuperAnalysisResponse)
async def analyze_super(request: SuperAnalysisRequest):
    try:
        if not predictor.model:
             raise HTTPException(status_code=503, detail="Modelo no entrenado. Ejecute train_xgboost.py primero.")

        if not monitor.active:
            raise HTTPException(status_code=503, detail="AI Service deactivated due to low performance.")

        logger.info(f"🚀 XGBoost Analysis starting for {request.symbol}")
        
        # 0. Fetch real-time Sentiment
        v_sentiment = sentiment_svc.get_combined_sentiment(request.symbol)
        
        # 1. Feature Extraction
        df1m = pd.DataFrame([d.model_dump() for d in request.ohlcv.tf1m])
        df5m = pd.DataFrame([d.model_dump() for d in request.ohlcv.tf5m])
        
        if len(df1m) < 14 or len(df5m) < 14:
             return SuperAnalysisResponse(signal_type="Hold", confidence=0.0, reasoning=["Insufficient Data"], suggested_leverage=1, multi_tf_bias="Neutral", whale_alert=False)

        rsi1m = ta.momentum.RSIIndicator(df1m["close"]).rsi().iloc[-1]
        rsi5m = ta.momentum.RSIIndicator(df5m["close"]).rsi().iloc[-1]
        
        # 2. XGBoost Prediction (Features must match train_model.py exactly)
        # Using 5m as the primary timeframe for features
        rsi = ta.momentum.RSIIndicator(df5m["close"]).rsi().iloc[-1]
        macd_diff = ta.trend.MACD(df5m["close"]).macd_diff().iloc[-1]
        adx = ta.trend.ADXIndicator(df5m["high"], df5m["low"], df5m["close"]).adx().iloc[-1]
        vol_ma = df5m['volume'].rolling(window=20).mean().iloc[-1]
        vol_ratio = df5m['volume'].iloc[-1] / vol_ma if vol_ma > 0 else 1
        
        roc = ta.momentum.ROCIndicator(df5m["close"], window=12).roc().iloc[-1]
        atr = ta.volatility.AverageTrueRange(df5m["high"], df5m["low"], df5m["close"], window=14).average_true_range().iloc[-1]
        volatility = df5m["close"].tail(24).std() / df5m["close"].iloc[-1]
        
        feature_values = [
            rsi,
            macd_diff,
            adx,
            vol_ratio,
            roc,
            atr,
            volatility
        ]
        
        prob = predictor.predict(feature_values)
        
        if prob is None:
             raise HTTPException(status_code=503, detail="Error en inferencia del modelo.")

        # 3. Decision Logic (Using Optimized Threshold)
        signal = "Hold"
        confidence = abs(prob - predictor.threshold) * 2
        
        if prob > predictor.threshold: signal = "Buy"
        elif prob < (predictor.threshold * 0.8): signal = "Sell" # Risk avoid for now
        
        reasons = []
        if prob > predictor.threshold: 
            reasons.append(f"XGBoost: Probability of increase ({prob:.1%}) exceeds optimized threshold ({predictor.threshold:.2f})")
        if prob < (predictor.threshold * 0.8):
            reasons.append(f"XGBoost: Low probability of increase ({prob:.1%}) suggests risk avoidance.")

        # Log for Monitoring
        monitor.log_prediction(signal, prob, {"symbol": request.symbol})

        return SuperAnalysisResponse(
            signal_type=signal,
            confidence=round(confidence, 2),
            reasoning=reasons,
            suggested_leverage=10 if confidence > 0.75 else 5 if confidence > 0.5 else 3,
            multi_tf_bias="Bullish" if rsi1m > 50 else "Bearish",
            whale_alert=False
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in analyze_super")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-sentiment", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest):
    try:
        if not request.text or not request.text.strip():
            logger.info("Empty text received, returning neutral")
            return get_neutral_fallback("Empty text")

        logger.info(f"🔍 Analyzing text: {request.text[:50]}...")
        
        # Llamar a la API de HuggingFace
        response = requests.post(API_URL, headers=headers, json={"inputs": request.text}, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            # Format: [[{'label': 'LABEL_0', 'score': 0.89}, ...]]
            
            if not result or not isinstance(result, list) or not result[0]:
                return get_neutral_fallback("Unexpected API response format")

            predictions = result[0]
            labels_map = {'LABEL_0': 'negative', 'LABEL_1': 'neutral', 'LABEL_2': 'positive'}
            
            best = max(predictions, key=lambda x: x['score'])
            sentiment = labels_map.get(best['label'], 'neutral')
            confidence = best['score']
            
            scores = { labels_map.get(p['label'], p['label']): p['score'] for p in predictions }
            
            logger.info(f"✅ Success: {sentiment} ({confidence:.0%})")
            return SentimentResponse(sentiment=sentiment, confidence=confidence, scores=scores)
        
        logger.error(f"❌ HF API Error {response.status_code}: {response.text}")
        return get_neutral_fallback(f"HF API returned {response.status_code}")
            
    except Exception as e:
        logger.exception("💥 Exception in analyze_sentiment")
        return get_neutral_fallback(str(e))

def _df_from_request(request: MarketDataRequest) -> pd.DataFrame:
    df = pd.DataFrame([d.model_dump() for d in request.data])
    return df

def detect_swings(df: pd.DataFrame, window: int = 5):
    """Detect Swing Highs and Swing Lows"""
    df['swing_high'] = df['high'].rolling(window=window*2+1, center=True).max()
    df['swing_low'] = df['low'].rolling(window=window*2+1, center=True).min()
    
    is_high = df['high'] == df['swing_high']
    is_low = df['low'] == df['swing_low']
    
    return is_high, is_low

@app.post("/detect-regime", response_model=RegimeResponse)
async def detect_regime(request: MarketDataRequest):
    try:
        if not request.data or len(request.data) < 30:
            return RegimeResponse(regime="Ranging", volatility_score=0.0, trend_strength=0.0)
            
        df = _df_from_request(request)
        
        # 1. basic Indicators
        adx_indicator = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"])
        df["adx"] = adx_indicator.adx()
        atr_indicator = ta.volatility.AverageTrueRange(high=df["high"], low=df["low"], close=df["close"])
        df["atr"] = atr_indicator.average_true_range()
        
        current_close = df["close"].iloc[-1]
        volatility_score = (df["atr"].iloc[-1] / current_close) * 100 if current_close > 0 else 0
        adx_val = df["adx"].iloc[-1]
        
        # 2. Market Structure (BOS/CHOCH)
        is_high, is_low = detect_swings(df, window=5)
        highs = df[is_high]['high'].tolist()
        lows = df[is_low]['low'].tolist()
        
        structure = "Neutral"
        bos = False
        choch = False
        
        if len(highs) >= 2 and len(lows) >= 2:
            last_high = highs[-1]
            prev_high = highs[-2]
            last_low = lows[-1]
            prev_low = lows[-2]
            
            # BOS Detection (Trend Continuation)
            if current_close > last_high:
                bos = True
                structure = "Bullish"
            elif current_close < last_low:
                bos = True
                structure = "Bearish"
                
            # CHOCH Detection (Trend Reversal)
            # Simplificado: si veníamos de Bullish (highs subiendo) y rompemos el último Low relevante
            if last_high > prev_high and current_close < last_low:
                choch = True
                structure = "Bearish"
            elif last_low < prev_low and current_close > last_high:
                choch = True
                structure = "Bullish"

        # 3. Regime Determination
        regime = "Ranging"
        if pd.notna(adx_val) and adx_val > 25:
            df["sma20"] = ta.trend.sma_indicator(df["close"], window=20)
            if current_close > df["sma20"].iloc[-1]:
                regime = "BullTrend"
            else:
                regime = "BearTrend"
                
        if volatility_score > 1.8 and regime == "Ranging": # Umbral ajustado
            regime = "VolatileBreakout"
            
        # 4. Liquidity Zones (Basic)
        # Find price levels with multiple touches
        price_rounded = df['close'].round(2)
        counts = price_rounded.value_counts()
        liquidity_zones = counts[counts >= 3].index.tolist()[:3] # Top 3 zones

        return RegimeResponse(
            regime=regime,
            volatility_score=float(volatility_score) if pd.notna(volatility_score) else 0.0,
            trend_strength=float(adx_val) if pd.notna(adx_val) else 0.0,
            structure=structure,
            bos_detected=bos,
            choch_detected=choch,
            liquidity_zones=[float(z) for z in liquidity_zones]
        )
    except Exception as e:
        logger.exception("Error in detect_regime")
        return RegimeResponse(regime="Ranging", volatility_score=0, trend_strength=0)

@app.post("/analyze-technicals", response_model=TechnicalsResponse)
async def analyze_technicals(request: MarketDataRequest):
    try:
        if not request.data or len(request.data) < 20:
            return TechnicalsResponse(macd_histogram=0, bb_width=0, adx=0, rsi=50)

        df = _df_from_request(request)
        
        macd = ta.trend.MACD(close=df["close"])
        bb = ta.volatility.BollingerBands(close=df["close"])
        adx = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"])
        rsi = ta.momentum.RSIIndicator(close=df["close"])
        
        return TechnicalsResponse(
            macd_histogram=float(macd.macd_diff().iloc[-1]) if pd.notna(macd.macd_diff().iloc[-1]) else 0.0,
            bb_width=float(bb.bollinger_wband().iloc[-1]) if pd.notna(bb.bollinger_wband().iloc[-1]) else 0.0,
            adx=float(adx.adx().iloc[-1]) if pd.notna(adx.adx().iloc[-1]) else 0.0,
            rsi=float(rsi.rsi().iloc[-1]) if pd.notna(rsi.rsi().iloc[-1]) else 50.0
        )
    except Exception as e:
        logger.exception("Error in analyze_technicals")
        return TechnicalsResponse(macd_histogram=0, bb_width=0, adx=0, rsi=50)

if __name__ == "__main__":
    logger.info("🚀 VERGE AI Service (API Mode) starting...")
    logger.info(f"📡 API URL: {API_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")