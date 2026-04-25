"""
SCAR FastAPI Router — Exposes /scar endpoints consumed by the ABP backend.
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from .schemas import (
    ScarScanRequest, ScarResultDto,
    ScarTopSetup, ScarHistoryResponse, ScarHistoryEntry
)
from . import detector, data_store

logger = logging.getLogger("SCAR_ROUTER")

router = APIRouter(prefix="/scar", tags=["SCAR - Whale Extraction Detector"])


@router.post("/scan", response_model=List[ScarResultDto])
async def scar_scan(request: ScarScanRequest):
    """
    Scan a list of symbols for the 5 SCAR signals.
    Returns all results sorted by score_grial descending.
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols list cannot be empty")
    if len(request.symbols) > 200:
        raise HTTPException(status_code=400, detail="max 200 symbols per request")

    logger.info("🐋 SCAR scan requested for %d symbols", len(request.symbols))
    results = detector.scan_symbols(
        request.symbols,
        funding_rates=request.funding_rates,
        max_workers=8
    )
    return results


@router.get("/score/{symbol}", response_model=ScarResultDto)
async def get_score(symbol: str):
    """Get SCAR score for a single symbol (triggers fresh analysis)."""
    symbol = symbol.upper()
    result = detector.analyze_symbol(symbol)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Could not analyze {symbol}")
    return result


@router.get("/alerts", response_model=List[ScarResultDto])
async def get_active_alerts(threshold: int = Query(default=3, ge=0, le=5)):
    """Return today's signals with score_grial >= threshold (from DB cache)."""
    rows = data_store.get_active_alerts(threshold)
    results = []
    for r in rows:
        results.append(ScarResultDto(
            symbol=r["token_symbol"],
            score_grial=r["score_grial"],
            prediction=r["prediction"] or "Sin señal activa",
            flag_whale_withdrawal=bool(r["flag_whale_withdrawal"]),
            flag_supply_drying=bool(r["flag_supply_drying"]),
            flag_price_stable=bool(r["flag_price_stable"]),
            flag_funding_negative=bool(r["flag_funding_negative"]),
            flag_silence=bool(r["flag_silence"]),
            mode="degraded",
            analyzed_at=r.get("date", ""),
        ))
    return results


@router.get("/top-setups", response_model=List[ScarTopSetup])
async def get_top_setups(limit: int = Query(default=10, ge=1, le=50)):
    """Return top N tokens by score_grial from today's cached results."""
    rows = data_store.get_top_setups(limit)
    return [
        ScarTopSetup(
            symbol=r["token_symbol"],
            score_grial=r["score_grial"],
            prediction=r["prediction"] or "Sin señal activa",
            estimated_hours=None,
            mode="degraded",
        )
        for r in rows
    ]


@router.get("/history/{symbol}", response_model=ScarHistoryResponse)
async def get_history(symbol: str, days: int = Query(default=30, ge=1, le=90)):
    """Return historical SCAR signals for a specific token."""
    symbol = symbol.upper()
    rows = data_store.get_history(symbol, days)
    template = data_store.get_template(symbol)

    history = [
        ScarHistoryEntry(
            date=r["date"],
            score_grial=r["score_grial"],
            prediction=r["prediction"] or "",
            flag_whale_withdrawal=bool(r["flag_whale_withdrawal"]),
            flag_supply_drying=bool(r["flag_supply_drying"]),
            flag_price_stable=bool(r["flag_price_stable"]),
            flag_funding_negative=bool(r["flag_funding_negative"]),
            flag_silence=bool(r["flag_silence"]),
        )
        for r in rows
    ]

    return ScarHistoryResponse(
        symbol=symbol,
        history=history,
        total_cycles=template.get("total_cycles", 0) if template else 0,
        last_pump_date=template.get("last_pump_date") if template else None,
        avg_withdrawal_days=template.get("avg_withdrawal_days") if template else None,
    )


@router.post("/train/{symbol}")
async def train_template(symbol: str):
    """
    Manually trigger template update for a token after a pump event.
    Analyzes historical signal patterns and updates the scar_templates table.
    """
    symbol = symbol.upper()
    history = data_store.get_history(symbol, days=30)

    if len(history) < 3:
        raise HTTPException(status_code=400, detail=f"Not enough history for {symbol}")

    # Count days with active withdrawal signals as proxy for withdrawal period
    withdrawal_days = [h for h in history if h.get("flag_whale_withdrawal")]
    avg_days = len(withdrawal_days) if withdrawal_days else 7.0

    data_store.upsert_template(
        symbol=symbol,
        avg_days=float(avg_days),
        last_pump_date=None,
        last_pump_price=None,
        total_cycles=(data_store.get_template(symbol) or {}).get("total_cycles", 0) + 1
    )

    logger.info("✅ SCAR template trained for %s: avg_days=%.1f", symbol, avg_days)
    return {"status": "ok", "symbol": symbol, "avg_withdrawal_days": avg_days}
