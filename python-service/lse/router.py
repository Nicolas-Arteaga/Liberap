"""
LSE Router — Expone el motor LiquiditySweepEngine vía FastAPI.
Se integra en paralelo a Nexus-15 y SCAR.
"""
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from .models import (
    LSEScanRequest,
    LSESignalResponse,
    LSEState,
    LSEBatchScanRequest,
    LSEBatchScanResponse,
    LSEBatchSignalRow,
)
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
        # Validación mínima — agente/producción: 400 claro; dashboard (preview_only): 200 + diagnostics (evita spam 400 en Top scan)
        if len(request.candles_1h) < 120:
            detail_msg = (
                f"Mínimo 120 velas en el timeframe principal (MA99); recibidas {len(request.candles_1h)}."
            )
            if request.preview_only:
                return LSESignalResponse(
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    signal_found=False,
                    signal=None,
                    diagnostics=[f"⚠️ {detail_msg}"],
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                )
            raise HTTPException(status_code=400, detail=detail_msg)

        signal, diagnostics = run_lse_detection(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles_1h=request.candles_1h,
            candles_4h=request.candles_4h,
            entry_mode=request.entry_mode,
            detection_mode=request.detection_mode,
            preview_only=request.preview_only,
        )

        if signal is not None:
            logger.info(
                "LSE scan OK %s detection_mode=%s entry_mode=%s score=%s preview=%s",
                request.symbol,
                request.detection_mode.value,
                request.entry_mode.value,
                signal.score,
                request.preview_only,
            )
            if not request.preview_only:
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


def _run_lse_batch_sync(request: LSEBatchScanRequest) -> LSEBatchScanResponse:
    """
    Procesa varios símbolos en una sola petición (mismo patrón que el agente antes hacía en bucle).
    Dual-mode: resetea SM entre modos, igual que el cliente legacy.
    """
    if not request.detection_modes:
        raise ValueError("detection_modes no puede estar vacío")

    sm = LSEStateMachine.get()
    rows: list[LSEBatchSignalRow] = []
    processed = 0

    for item in request.items:
        if len(item.candles_1h) < 120:
            logger.debug(
                "[LSE batch] skip %s: solo %d velas (min 120)",
                item.symbol,
                len(item.candles_1h),
            )
            continue

        processed += 1
        for dm in request.detection_modes:
            if len(request.detection_modes) > 1:
                sm.reset(item.symbol, item.timeframe)

            signal, diagnostics = run_lse_detection(
                symbol=item.symbol,
                timeframe=item.timeframe,
                candles_1h=item.candles_1h,
                candles_4h=item.candles_4h,
                entry_mode=request.entry_mode,
                detection_mode=dm,
                preview_only=request.preview_only,
            )

            if signal is not None:
                logger.info(
                    "LSE batch hit %s detection_mode=%s score=%s",
                    item.symbol,
                    dm.value,
                    signal.score,
                )
                if not request.preview_only:
                    log_signal(signal, event="SIGNAL_EMITTED")
                rows.append(
                    LSEBatchSignalRow(
                        symbol=item.symbol,
                        timeframe=item.timeframe,
                        detection_mode=dm,
                        signal=signal,
                    )
                )
            else:
                logger.debug(
                    "[LSE batch] %s mode=%s no signal: %s",
                    item.symbol,
                    dm.value,
                    diagnostics[:1] if diagnostics else "—",
                )

    rows.sort(key=lambda r: r.signal.score, reverse=True)
    rows = rows[: request.top_k]

    return LSEBatchScanResponse(
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        items_in_request=len(request.items),
        symbols_processed=processed,
        signals=rows,
    )


@router.post("/scan-batch", response_model=LSEBatchScanResponse)
async def scan_lse_batch(request: LSEBatchScanRequest):
    """
    Un solo round-trip para el TOP-K de LSE sobre varios símbolos.
    Pensado para el agente: timeout largo en cliente (p. ej. 3–10 min), no 10s por símbolo.
    """
    try:
        return await asyncio.to_thread(_run_lse_batch_sync, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error en LSE scan-batch")
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
