from fastapi import APIRouter, HTTPException
from .schemas import (
    FvgAnalyzeRequest, FvgAnalyzeResponse, FvgScanRequest, FvgScanResponse,
    FvgCascadeRequest, FvgCascadeResult, FvgCascadeScanRequest, FvgCascadeScanResponse,
)
from .analyzer import FvgAnalyzer
import logging

router = APIRouter(prefix="/fvg", tags=["fvg"])
logger = logging.getLogger("FVG")
_analyzer = FvgAnalyzer()


@router.post("/analyze", response_model=FvgAnalyzeResponse)
async def analyze_fvg(request: FvgAnalyzeRequest):
    """
    Analiza un símbolo: devuelve todas las zonas FVG sin rellenar (con su
    score de confluencia con el volume profile) más el volume profile
    completo de la ventana, para dibujar en el gráfico.
    """
    try:
        result = _analyzer.analyze_symbol(request)
        if result is None:
            raise HTTPException(status_code=422, detail=f"Datos insuficientes para {request.symbol}")
        logger.info(f"FVG {request.symbol}: {len(result.zones)} zonas activas")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"FVG error analizando {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan", response_model=FvgScanResponse)
async def scan_fvg(request: FvgScanRequest):
    """
    Escanea una lista de símbolos y devuelve el top-5 por score de
    confluencia (tamaño del gap + cercanía a un nodo de alto volumen +
    qué tan sin rellenar está).
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _analyzer.scan(request)
        return result
    except Exception as e:
        logger.exception(f"FVG scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cascade", response_model=FvgCascadeResult)
async def cascade_fvg(request: FvgCascadeRequest):
    """
    Cascada 15m -> 5m -> 1m: 15m define el sesgo, 5m confirma (zona misma
    dirección solapada con la de 15m), 1m ejecuta (zona misma dirección
    solapada con la de 5m, para entrada/SL más ajustados). Devuelve las 3
    zonas (las que existan) más la zona real a operar (la más fina disponible).
    """
    try:
        result = _analyzer.analyze_cascade(request)
        if result is None:
            raise HTTPException(status_code=422, detail=f"Datos insuficientes para {request.symbol}")
        logger.info(f"FVG-CASCADE {request.symbol}: status={result.cascade_status}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"FVG-CASCADE error analizando {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cascade-scan", response_model=FvgCascadeScanResponse)
async def cascade_scan_fvg(request: FvgCascadeScanRequest):
    """
    Escanea una lista de símbolos con la cascada completa y devuelve el
    top-5 de setups ACCIONABLES (confirmados en 5m como mínimo, con la
    zona de entrada en punto de entrada o a punto de llegar).
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _analyzer.scan_cascade(request)
        return result
    except Exception as e:
        logger.exception(f"FVG-CASCADE-SCAN error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
