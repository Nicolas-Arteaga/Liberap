from fastapi import APIRouter, HTTPException
from .schemas import Nexus15Request, Nexus15Response, Strike15mRequest, Strike15mResponse, StaircaseRequest, StaircaseResponse, ArrowPeakRequest, ArrowPeakResponse
from .analyzer import Nexus15Analyzer
from .strike_analyzer import Strike15mAnalyzer
from .staircase_analyzer import StaircaseAnalyzer
from .arrow_peak_analyzer import ArrowPeakAnalyzer
import logging
import json
import time

router = APIRouter(prefix="/nexus15", tags=["nexus15"])
logger = logging.getLogger("NEXUS15")
_analyzer = Nexus15Analyzer()
_strike_analyzer = Strike15mAnalyzer()
_staircase_analyzer = StaircaseAnalyzer()
_arrow_peak_analyzer = ArrowPeakAnalyzer()

# Redis publisher (optional — if Redis is unavailable, analysis still works)
_redis_client = None
REDIS_PUBLISH_CHANNEL = "verge:superscore"
NEXUS_PUBLISH_MIN_CONFIDENCE = 70.0  # Only publish strong signals

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(
            "redis://localhost:6379/0",
            socket_connect_timeout=1,
            socket_timeout=1
        )
        _redis_client.ping()
        logger.info("[NEXUS15] Redis publisher connected — high-confidence signals will be forwarded to agent.")
    except Exception as e:
        logger.warning(f"[NEXUS15] Redis not available for publishing ({e}). Analysis-only mode.")
        _redis_client = None
    return _redis_client


def _publish_to_bridge(result: Nexus15Response):
    """Publishes a high-confidence Nexus-15 result to Redis for the agent to consume."""
    if result.ai_confidence < NEXUS_PUBLISH_MIN_CONFIDENCE:
        return
    if result.direction not in ("BULLISH", "BEARISH"):
        return
    r = _get_redis()
    if r is None:
        return
    try:
        payload = json.dumps({
            "symbol":    result.symbol,
            "score":     round(result.ai_confidence, 1),
            "direction": result.direction,
            "regime":    result.regime,
            "estado":    "NEXUS_HOT",
            "nexus15":   round(result.ai_confidence, 1),
            "timestamp": time.time(),
            "source":    "nexus15_ui",
            "estimatedRangePercent": result.estimated_range_percent,
            "features":  result.features.model_dump() if result.features else {},
            "groupScores": result.group_scores.model_dump() if result.group_scores else {}
        })
        r.publish(REDIS_PUBLISH_CHANNEL, payload)
        logger.info(
            f"[NEXUS15] Published to Redis bridge: {result.symbol} "
            f"{result.direction} {result.ai_confidence}%"
        )
    except Exception as e:
        logger.debug(f"[NEXUS15] Redis publish error (non-fatal): {e}")


@router.post("/analyze", response_model=Nexus15Response)
async def analyze_nexus15(request: Nexus15Request):
    """
    Endpoint NEXUS-15: recibe velas de 15m y devuelve prediccion
    probabilistica con AI Confidence y scores de los 6 grupos.
    Si la confianza es >= 70% y hay direccion clara, publica en Redis
    para que el agente de trading lo tome como candidato prioritario.
    """
    if len(request.candles) < 25:
        raise HTTPException(status_code=400, detail="Se requieren al menos 25 velas de 15m")
    try:
        result = _analyzer.analyze(request, direction_bias=request.direction_bias)
        logger.info(f"NEXUS-15 {request.symbol}: confidence={result.ai_confidence}% dir={result.direction}")

        # Forward hot signals to the agent via Redis Bridge
        _publish_to_bridge(result)

        return result
    except Exception as e:
        logger.exception(f"NEXUS-15 error for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strike15m", response_model=Strike15mResponse)
async def analyze_strike15m(request: Strike15mRequest):
    """
    Endpoint STRIKE 15m: Detecta velas de ignición de alta potencia en MA99.
    Escanea múltiples símbolos y devuelve el TOP 5 con mayor fuerza.
    """
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _strike_analyzer.analyze(request)
        logger.info(f"STRIKE-15m: Scanned {result.scanned_count} symbols, found {len(result.top_5)} opportunities")
        return result
    except Exception as e:
        logger.exception(f"STRIKE-15m error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/staircase", response_model=StaircaseResponse)
async def analyze_staircase(request: StaircaseRequest):
    """
    Endpoint STAIRCASE: Detecta patrones de escalera institucional (movimientos ordenados escalonados).
    Filtra por alineación perfecta de EMAs en 1D y busca patrones de escalón en 15m.
    Devuelve el TOP 5 con mayor Score de Orden.
    """
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _staircase_analyzer.analyze(request)
        logger.info(f"STAIRCASE: Scanned {result.scanned_count} symbols, found {len(result.top_5)} opportunities")
        return result
    except Exception as e:
        logger.exception(f"STAIRCASE error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/arrow-peak", response_model=ArrowPeakResponse)
async def analyze_arrow_peak(request: ArrowPeakRequest):
    """
    Endpoint ARROW PEAK: Detecta vértices de agotamiento (subidas parabólicas que empiezan a revertir).
    Busca pumps de +15% en los últimos 10 días que tienen 1-5 velas rojas consecutivas.
    Devuelve el TOP 5 organizado por días de sangrado (1-5).
    """
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _arrow_peak_analyzer.analyze(request)
        logger.info(f"ARROW PEAK: Scanned {result.scanned_count} symbols, found {len(result.top_5)} opportunities")
        return result
    except Exception as e:
        logger.exception(f"ARROW PEAK error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

