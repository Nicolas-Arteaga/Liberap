from fastapi import APIRouter, HTTPException
from .schemas import AdnCompressionScanRequest, AdnCompressionScanResponse
from .analyzer import AdnCompressionAnalyzer
import logging

router = APIRouter(prefix="/adn-compression", tags=["adn-compression"])
logger = logging.getLogger("ADN_COMPRESSION")
_analyzer = AdnCompressionAnalyzer()


@router.post("/scan", response_model=AdnCompressionScanResponse)
async def scan_adn_compression(request: AdnCompressionScanRequest):
    """
    🧬 ADN COMPRESSION: escanea símbolos buscando el patrón de resorte
    comprimido (MA25/50/99 agrupadas + MA7 tejiendo el "ADN" >=2 veces),
    seguido de ignición y régimen de pullback a MA7 sin tocar MA25.
    timeframe="5m" para el radar micro/scalp, "1d" para el macro/swing —
    misma lógica fractal en ambos casos. Devuelve el TOP 10.
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _analyzer.analyze(request)
        logger.info(
            f"ADN-COMPRESSION @ {request.timeframe}: scanned={result.scanned_count} "
            f"qualified={result.qualified_count}"
        )
        return result
    except Exception as e:
        logger.exception(f"ADN-COMPRESSION scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
