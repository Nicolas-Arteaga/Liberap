from pydantic import BaseModel
from typing import List, Optional


class FvgAnalyzeRequest(BaseModel):
    symbol: str
    interval: str = "15m"
    limit: int = 200


class VolumeProfileBin(BaseModel):
    price_low: float
    price_high: float
    volume: float
    is_poc: bool = False
    is_hvn: bool = False


class FvgZone(BaseModel):
    id: str
    direction: str  # "bullish" | "bearish"
    top: float
    bottom: float
    gap_pct: float
    formed_at: str
    formed_at_ms: int
    candle_index: int
    fill_progress_pct: float
    poc_confluence: bool
    poc_distance_pct: float
    entry_status: str  # "IN_ZONE" | "APPROACHING" | "EXHAUSTED" | "FAR" | "TP_HIT"
    dist_to_entry_pct: float
    tp_progress_pct: float = 0.0
    confluence_score: float
    sl_price: float
    tp_price: float
    is_ifvg: bool = False
    source_interval: str = ""
    trend_aligned: bool = True


class FvgAnalyzeResponse(BaseModel):
    symbol: str
    interval: str
    analyzed_at: str
    current_price: float
    poc_price: float
    zones: List[FvgZone]
    volume_profile: List[VolumeProfileBin]


class FvgScanRequest(BaseModel):
    symbols: List[str]
    interval: str = "15m"
    # "score" (default): igual que siempre, mayor confluence_score primero.
    # "range": ignora el score compuesto y prioriza el mayor rango real hasta
    # el TP (mayor %  de recorrido simple) — para la estrategia FVG del agente,
    # donde importa "la mejor entrada armada", no el score.
    sort_by: str = "score"


class FvgScanItem(BaseModel):
    symbol: str
    direction: str
    top: float
    bottom: float
    gap_pct: float
    current_price: float
    poc_confluence: bool
    poc_distance_pct: float
    entry_status: str  # "IN_ZONE" | "APPROACHING" | "FAR"
    dist_to_entry_pct: float
    sl_price: float
    tp_price: float
    tp_distance_pct: float
    confluence_score: float
    fill_progress_pct: float
    formed_at: str


class FvgScanResponse(BaseModel):
    top_5: List[FvgScanItem]
    scanned_count: int
    analyzed_at: str
    trend_blocked_count: int = 0  # símbolos con gap accionable pero descartado por contra-tendencia
    actionable_count: int = 0     # símbolos con al menos un candidato válido (a favor de tendencia)


# ── CASCADA 15m -> 5m -> 1m (dirección -> confirmación -> ejecución) ──────

class FvgCascadeRequest(BaseModel):
    symbol: str
    limit: int = 200
    # Ancla la cascada: "15m" = cascada completa 15m->5m->1m (default,
    # comportamiento original). "5m" = cascada corta 5m->1m. "1m" = análisis
    # directo en 1m, sin cascada (no hay temporalidad más chica disponible).
    anchor_interval: str = "15m"


class FvgCascadeResult(BaseModel):
    symbol: str
    cascade_status: str  # "NONE" | "AWAITING_CONFIRMATION" | "AWAITING_EXECUTION" | "READY"
    bias_zone: Optional[FvgZone] = None
    confirmation_zone: Optional[FvgZone] = None
    execution_zone: Optional[FvgZone] = None
    entry_price_zone: Optional[FvgZone] = None  # la zona real a operar (execution > confirmation > bias)
    current_price: float
    confluence_score: float
    analyzed_at: str


class FvgCascadeScanRequest(BaseModel):
    symbols: List[str]


class FvgCascadeScanResponse(BaseModel):
    top_5: List[FvgCascadeResult]
    scanned_count: int
    analyzed_at: str
