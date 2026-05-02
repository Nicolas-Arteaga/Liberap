"""
LSE Router — Expone el motor LiquiditySweepEngine vía FastAPI.
Se integra en paralelo a Nexus-15 y SCAR.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from .models import LSEScanRequest, LSESignalResponse, LSESignal, LSEState
from .detector import run_lse_detection
from .lse_logger import log_signal
from .state_machine import LSEStateMachine

logger = logging.getLogger("LSE_ROUTER")

router = APIRouter(prefix="/lse", tags=["Liquidity Sweep Engine"])


@router.post("/scan", response_model=LSESignalResponse)
async def scan_lse(request: LSEScanRequest):
    """
    Analiza velas recientes buscando el patrón de Spring con compresión MA.
    Retorna la señal si se cumplen todas las condiciones, o signal_found=False.
    """
    try:
        # Validación mínima
        if len(request.candles_1h) < 120:
            raise HTTPException(status_code=400, detail="Mínimo 120 velas 1H requeridas para cálculo MA99.")

        signal, diagnostics = run_lse_detection(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles_1h=request.candles_1h,
            candles_4h=request.candles_4h,
            entry_mode=request.entry_mode,
        )

        if signal is not None:
            # Emitir señal validada
            log_signal(signal, event="SIGNAL_EMITTED")
            return LSESignalResponse(
                symbol=request.symbol,
                timeframe=request.timeframe,
                signal_found=True,
                signal=signal,
                diagnostics=signal.reasoning,
                analyzed_at=datetime.now(timezone.utc).isoformat()
            )

        # No hay señal (o está en cooldown)
        return LSESignalResponse(
            symbol=request.symbol,
            timeframe=request.timeframe,
            signal_found=False,
            signal=None,
            diagnostics=diagnostics,
            analyzed_at=datetime.now(timezone.utc).isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en LSE scan para %s", request.symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{symbol}")
async def get_state(symbol: str, timeframe: str = "1h"):
    """Consulta el estado actual de la State Machine para un símbolo."""
    state = LSEStateMachine.get().get_state(symbol, timeframe)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "state": state.value,
        "can_emit": LSEStateMachine.get().can_emit(symbol, timeframe)
    }


@router.post("/reset-state/{symbol}")
async def reset_state(symbol: str, timeframe: str = "1h"):
    """Resetea el estado de un símbolo (útil para debug o forzar re-evaluación)."""
    LSEStateMachine.get().reset(symbol, timeframe)
    return {"symbol": symbol, "timeframe": timeframe, "status": "reset_to_idle"}


@router.get("/active-states")
async def get_all_active_states():
    """Devuelve un diccionario con todos los estados activos en memoria."""
    return LSEStateMachine.get().get_all_states()
