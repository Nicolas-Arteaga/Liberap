"""
NEXUS-5 "Ignition Core" — FastAPI Router
Endpoints:
  POST /nexus5/analyze        → Análisis individual (como NEXUS-15)
  POST /nexus5/analyze-batch  → Recibe lista de símbolos, retorna todos en Fase 1 o 2
"""
from fastapi import APIRouter, HTTPException, Body
from .schemas import Nexus5Request, Nexus5Response
from .analyzer import Nexus5Analyzer
import logging
import json
import time
from typing import List

router = APIRouter(prefix="/nexus5", tags=["nexus5"])
logger = logging.getLogger("NEXUS5")
_analyzer = Nexus5Analyzer()

# Redis publisher (optional — si Redis no está disponible, el análisis funciona igual)
_redis_client = None
REDIS_PUBLISH_CHANNEL = "verge:nexus5:superscore"
NEXUS_PUBLISH_MIN_CONFIDENCE = 60.0  # más agresivo que NEXUS-15 (70)


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
        logger.info("[NEXUS5] Redis publisher connected — ignition signals will be forwarded to agent.")
    except Exception as e:
        logger.warning(f"[NEXUS5] Redis not available for publishing ({e}). Analysis-only mode.")
        _redis_client = None
    return _redis_client


def _publish_to_bridge(result: Nexus5Response):
    """Publica resultado NEXUS-5 en Redis para que el agente lo consuma."""
    if result.ai_confidence < NEXUS_PUBLISH_MIN_CONFIDENCE:
        return
    if result.direction not in ("BULLISH", "BEARISH"):
        return
    r = _get_redis()
    if r is None:
        return
    try:
        payload = json.dumps({
            "symbol":             result.symbol,
            "score":              round(result.ai_confidence, 1),
            "direction":          result.direction,
            "regime":             result.regime,
            "estado":             "NEXUS5_HOT",
            "nexus5":             round(result.ai_confidence, 1),
            "phase":              result.phase,
            "phase_score":        result.phase_score,
            "entry_timeframe":    result.entry_timeframe,
            "compression_state":  result.compression_state,
            "ignition_detected":  result.ignition_detected,
            "bypass_active":      result.bypass_active,
            "timestamp":          time.time(),
            "source":             "nexus5_ui",
            "estimatedRangePercent": result.estimated_range_percent,
            "features":           result.features.model_dump() if result.features else {},
            "groupScores":        result.group_scores.model_dump() if result.group_scores else {}
        })
        r.publish(REDIS_PUBLISH_CHANNEL, payload)
        logger.info(
            f"[NEXUS5] Published to Redis: {result.symbol} "
            f"{result.direction} {result.ai_confidence}% "
            f"Phase={result.phase}({result.phase_score:.0f}) "
            f"Entry={result.entry_timeframe}"
        )
    except Exception as e:
        logger.debug(f"[NEXUS5] Redis publish error (non-fatal): {e}")


@router.post("/analyze", response_model=Nexus5Response)
async def analyze_nexus5(request: Nexus5Request):
    """
    Endpoint NEXUS-5 Ignition Core: recibe velas de 5m y devuelve análisis
    con detección de fases (Compression/Ignition/Expansion/Idle),
    RSI Bypass, y recomendación de timeframe de entrada (1m/3m/5m).

    Si la confianza es >= 60% y hay dirección clara, publica en Redis
    para que el agente de trading lo tome como candidato prioritario.
    """
    if len(request.candles) < 30:
        raise HTTPException(status_code=400, detail="Se requieren al menos 30 velas de 5m")
    try:
        result = _analyzer.analyze(request)
        logger.info(
            f"NEXUS-5 {request.symbol}: confidence={result.ai_confidence}% "
            f"dir={result.direction} phase={result.phase}({result.phase_score:.0f}) "
            f"entry_tf={result.entry_timeframe}"
        )

        # Forward hot signals to the agent via Redis Bridge
        _publish_to_bridge(result)

        return result
    except Exception as e:
        logger.exception(f"NEXUS-5 error for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-batch", response_model=List[Nexus5Response])
async def analyze_batch(requests: List[Nexus5Request]):
    """
    Endpoint batch para el agente: recibe una lista de Nexus5Request,
    retorna TODOS los resultados que están en Fase 1 (COMPRESSION con phase_score > 60)
    o Fase 2 (IGNITION), ordenados por urgencia:
    1. IGNITION primero (los más urgentes)
    2. Luego COMPRESSION por phase_score descendente
    """
    results = []

    for req in requests:
        try:
            if len(req.candles) < 30:
                continue
            result = _analyzer.analyze(req)

            # Solo retornar los que están en fase activa (no IDLE)
            if result.phase == "IDLE":
                continue
            if result.phase == "COMPRESSION" and result.phase_score < 60:
                continue

            # Publicar señales calientes en Redis
            _publish_to_bridge(result)

            results.append(result)
        except Exception as e:
            logger.debug(f"[NEXUS5] Batch skip: {e}")
            continue

    # Ordenar: Snake Rank (v7.2) — prioridad por distancia MA50-MA99 más corta
    def sort_key(r):
        phase_priority = {"IGNITION": 0, "EXPANSION": 1, "COMPRESSION": 2, "IDLE": 3}
        # Snake Rank: distancia MA50-MA99 más corta primero
        ma50_ma99_distance = r.features.ma50_ma99_distance if r.features else 1.0
        return (
            phase_priority.get(r.phase, 3),
            ma50_ma99_distance,  # Distancia más corta = mejor ranking
            -r.ai_confidence  # Mayor confianza = mejor ranking
        )

    results.sort(key=sort_key)

    logger.info(f"[NEXUS5] Batch complete: {len(results)} active signals from {len(requests)} requests")

    return results
