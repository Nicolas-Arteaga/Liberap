from pydantic import BaseModel
from typing import List, Optional


class ObAnalyzeRequest(BaseModel):
    symbol: str
    interval: str = "15m"
    limit: int = 300


class ObZone(BaseModel):
    id: str
    direction: str  # "bullish" (LONG) | "bearish" (SHORT)
    top: float
    bottom: float
    bos_price: float          # precio al que se confirmo el cambio de estructura (BOS)
    formed_at: str
    formed_at_ms: int
    candle_index: int
    entry_status: str          # "IN_ZONE" | "APPROACHING" | "FAR"
    dist_to_entry_pct: float
    poc_confluence: bool
    poc_distance_pct: float
    confluence_score: float
    sl_price: float
    tp_price: float
    tp_distance_pct: float = 0.0
    # 2026-08-21: hallazgo real del backtest -- SHORT (bearish) es la unica
    # direccion que sostuvo estabilidad real (ambas mitades del periodo
    # positivas y proporcionadas, $92.26/mes). LONG (bullish) no fue estable.
    # Se sigue devolviendo la zona bullish para visibilidad (igual que FVG
    # muestra ambas direcciones), pero NO se recomienda operarla todavia.
    validated_stable: bool = False


class ObAnalyzeResponse(BaseModel):
    symbol: str
    interval: str
    analyzed_at: str
    current_price: float
    zones: List[ObZone]


class ObScanRequest(BaseModel):
    symbols: List[str]
    interval: str = "15m"
    # "score" (default): mayor confluence_score primero, igual que FVG.
    # "range": prioriza mayor tp_distance_pct (recorrido real hasta el TP).
    sort_by: str = "score"
    # SHORT-only es la config VALIDADA (backtest real, ver validated_stable).
    # LONG queda disponible para visibilidad/investigacion, no para operar.
    only_validated: bool = True


class ObScanItem(BaseModel):
    symbol: str
    direction: str
    top: float
    bottom: float
    current_price: float
    poc_confluence: bool
    poc_distance_pct: float
    entry_status: str
    dist_to_entry_pct: float
    sl_price: float
    tp_price: float
    tp_distance_pct: float
    confluence_score: float
    formed_at: str
    validated_stable: bool = False


class ObScanResponse(BaseModel):
    top_5: List[ObScanItem]
    scanned_count: int
    analyzed_at: str
    actionable_count: int = 0
