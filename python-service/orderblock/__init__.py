from fastapi import APIRouter, HTTPException
from .schemas import ObAnalyzeRequest, ObAnalyzeResponse, ObScanRequest, ObScanResponse
from .analyzer import OrderBlockAnalyzer
import logging

router = APIRouter(prefix="/orderblock", tags=["orderblock"])
logger = logging.getLogger("ORDERBLOCK")
_analyzer = OrderBlockAnalyzer()


@router.post("/analyze", response_model=ObAnalyzeResponse)
async def analyze_orderblock(request: ObAnalyzeRequest):
    """
    Analiza un símbolo: devuelve el/los Order Block pendientes de mitigar
    (bullish y/o bearish), cada uno con su score de confluencia (entrada +
    volumen/POC + frescura) y TP de liquidez real. `validated_stable=true`
    solo en la zona bearish (SHORT) -- es la única dirección que sostuvo
    estabilidad real en el backtest (ver PROGRESS_LOG 2026-08-21).
    """
    try:
        result = _analyzer.analyze_symbol(request)
        if result is None:
            raise HTTPException(status_code=422, detail=f"Datos insuficientes para {request.symbol}")
        logger.info(f"OB {request.symbol}: {len(result.zones)} zonas activas")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"OB error analizando {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan", response_model=ObScanResponse)
async def scan_orderblock(request: ObScanRequest):
    """
    Escanea una lista de símbolos y devuelve el top-5 por score de
    confluencia. `only_validated=true` (default) filtra a SOLO Order Blocks
    bearish (SHORT) -- la única dirección validada con backtest real
    ($92.26/mes, estable). Poner en false para ver también bullish/LONG
    (visibilidad/investigación, no recomendado para operar todavía).
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="Se requiere al menos un símbolo para escanear")
    try:
        result = _analyzer.scan(request)
        return result
    except Exception as e:
        logger.exception(f"OB scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
