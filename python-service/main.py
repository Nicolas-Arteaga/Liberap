import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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
        response = requests.post(API_URL, headers=headers, json={"inputs": request.text}, timeout=10)
        
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
            
            logger.info(f"✅ Success: {sentiment} ({confidence:P0})")
            return SentimentResponse(sentiment=sentiment, confidence=confidence, scores=scores)
        
        logger.error(f"❌ HF API Error {response.status_code}: {response.text}")
        return get_neutral_fallback(f"HF API returned {response.status_code}")
            
    except Exception as e:
        logger.exception("💥 Exception in analyze_sentiment")
        return get_neutral_fallback(str(e))

if __name__ == "__main__":
    logger.info("🚀 VERGE AI Service (API Mode) starting...")
    logger.info(f"📡 API URL: {API_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")