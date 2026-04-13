from fastapi import APIRouter, HTTPException
from .schemas import Nexus15Request, Nexus15Response
from .analyzer import Nexus15Analyzer
import logging

router = APIRouter(prefix="/nexus15", tags=["nexus15"])
logger = logging.getLogger("NEXUS15")
_analyzer = Nexus15Analyzer()

@router.post("/analyze", response_model=Nexus15Response)
async def analyze_nexus15(request: Nexus15Request):
    """
    Endpoint NEXUS-15: recibe 25-50 velas de 15m y devuelve predicción
    probabilística con AI Confidence y scores de los 6 grupos.
    """
    if len(request.candles) < 25:
        raise HTTPException(status_code=400, detail="Se requieren al menos 25 velas de 15m")
    try:
        result = _analyzer.analyze(request)
        logger.info(f"✅ NEXUS-15 {request.symbol}: confidence={result.ai_confidence}% dir={result.direction}")
        return result
    except Exception as e:
        logger.exception(f"❌ NEXUS-15 error for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
