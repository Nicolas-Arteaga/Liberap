from pydantic import BaseModel
from typing import List


class AdnCompressionScanRequest(BaseModel):
    symbols: List[str]
    timeframe: str = "5m"  # "5m" (micro/scalp) o "1d" (macro/swing)


class AdnCompressionItem(BaseModel):
    symbol: str
    timeframe: str
    phase: str  # "COILED" | "PULLBACK_TO_MA7" | "EXTENDED" | "EXHAUSTED"
    direction: str  # "LONG" | "SHORT"
    ma7_crossings: int  # cruces de MA7 contra el paquete 25/50/99 dentro de la compresión ("ADN")
    compression_candles: int  # cuántas velas duró la compresión confirmada
    ignition_multiplier: float  # tamaño de la vela de ignición más grande vs. el promedio de la compresión (0 si aún no ignicionó)
    candles_since_ignition: int
    current_price: float
    ma7_now: float
    ma25_now: float
    ma99_now: float
    dist_to_ma7_pct: float
    dist_to_ma25_pct: float
    touched_ma25_since_ignition: bool
    reasons: List[str]


class AdnCompressionScanResponse(BaseModel):
    top_10: List[AdnCompressionItem]
    scanned_count: int
    qualified_count: int
    analyzed_at: str
