"""
LSE Models — Pydantic schemas para el LiquiditySweepEngine
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum


class LSEState(str, Enum):
    idle = "idle"
    compression_detected = "compression_detected"
    sweep_detected = "sweep_detected"
    reclaimed = "reclaimed"
    triggered = "triggered"
    closed = "closed"


class LSEEntryMode(str, Enum):
    aggressive = "aggressive"   # Cierre de vela de reclaim
    conservative = "conservative"  # Ruptura del high del sweep


class CandleInput(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class LSEScanRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    candles_1h: List[CandleInput] = Field(default_factory=list, description="Velas 1H (mínimo 120)")
    candles_4h: List[CandleInput] = Field(default_factory=list, description="Velas 4H para filtro HTF")
    entry_mode: LSEEntryMode = LSEEntryMode.conservative


class LSESubScores(BaseModel):
    compression: float = Field(0.0, ge=0, le=20, description="Score compresión MA (0-20)")
    sweep: float = Field(0.0, ge=0, le=25, description="Score barrido de liquidez (0-25)")
    reclaim: float = Field(0.0, ge=0, le=20, description="Score reclaim del nivel (0-20)")
    volume: float = Field(0.0, ge=0, le=20, description="Score de volumen (0-20)")
    htf_context: float = Field(0.0, ge=0, le=15, description="Score contexto HTF 4H (0-15)")

    @property
    def total(self) -> float:
        return self.compression + self.sweep + self.reclaim + self.volume + self.htf_context


class LSESignal(BaseModel):
    symbol: str
    timeframe: str
    state: LSEState
    score: float = Field(0.0, ge=0, le=100)
    sub_scores: LSESubScores
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    sweep_low: Optional[float] = None
    reclaim_close: Optional[float] = None
    ma7: Optional[float] = None
    ma25: Optional[float] = None
    ma99: Optional[float] = None
    atr: Optional[float] = None
    volume_ratio: Optional[float] = None
    compression_pct: Optional[float] = None
    reasoning: List[str] = Field(default_factory=list)
    entry_mode: LSEEntryMode = LSEEntryMode.conservative
    detected_at: Optional[str] = None
    alert_message: Optional[str] = None


class LSESignalResponse(BaseModel):
    symbol: str
    timeframe: str
    signal_found: bool
    signal: Optional[LSESignal] = None
    pattern_name: str = "Wyckoff Spring + MA Compression Catalyst"
    analyzed_at: str
    # Motivo del fallo o trazas (siempre útil cuando signal_found=False)
    diagnostics: List[str] = Field(default_factory=list)


class LSEBacktestResult(BaseModel):
    symbol: str
    timeframe: str
    total_signals: int
    wins: int
    losses: int
    winrate: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    avg_r_multiple: float
    trades_per_week: float
    trades: List[Dict] = Field(default_factory=list)
