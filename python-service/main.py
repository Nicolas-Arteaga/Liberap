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

# Load .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VERGE_AI")

app = FastAPI(title="VERGE AI Service (API Mode)", version="1.2.0")

# Configuration
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

@app.post("/detect-regime", response_model=RegimeResponse)
async def detect_regime(request: MarketDataRequest):
    try:
        if not request.data or len(request.data) < 20:
            return RegimeResponse(regime="Ranging", volatility_score=0.0, trend_strength=0.0)
            
        df = _df_from_request(request)
        
        # Calculate ADX for trend strength
        adx_indicator = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"])
        df["adx"] = adx_indicator.adx()
        
        # Calculate ATR for volatility
        atr_indicator = ta.volatility.AverageTrueRange(high=df["high"], low=df["low"], close=df["close"])
        df["atr"] = atr_indicator.average_true_range()
        
        # Normalized volatility
        current_close = df["close"].iloc[-1]
        volatility_score = (df["atr"].iloc[-1] / current_close) * 100 if current_close > 0 else 0
        
        adx_val = df["adx"].iloc[-1]
        
        regime = "Ranging"
        if pd.notna(adx_val) and adx_val > 25:
            # Check direction using simple SMA 20
            df["sma20"] = ta.trend.sma_indicator(df["close"], window=20)
            if current_close > df["sma20"].iloc[-1]:
                regime = "BullTrend"
            else:
                regime = "BearTrend"
                
        if volatility_score > 2.0:
            regime = "VolatileBreakout"
            
        return RegimeResponse(
            regime=regime,
            volatility_score=float(volatility_score) if pd.notna(volatility_score) else 0.0,
            trend_strength=float(adx_val) if pd.notna(adx_val) else 0.0
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