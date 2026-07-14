from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

class CandleInput(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class Nexus15Request(BaseModel):
    symbol: str
    timeframe: str = "15m"
    candles: List[CandleInput]  # últimas 25-50 velas
    direction_bias: Optional[str] = None  # "LONG" | "SHORT" | None (auto)

class GroupScores(BaseModel):
    g1_price_action: float
    g2_smc_ict: float
    g3_wyckoff: float
    g4_fractals: float
    g5_volume: float
    g6_ml: float

class Nexus15Features(BaseModel):
    # G1
    candle_body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    consecutive_bull_bars: int
    consecutive_bear_bars: int
    # G2
    order_block_detected: bool
    fair_value_gap: bool
    bos_detected: bool
    liquidity_sweep: bool
    # G3
    wyckoff_phase: str
    spring_detected: bool
    upthrust_detected: bool
    # G4
    fractal_high_5: bool
    fractal_low_5: bool
    trend_structure: int  # 1, -1, 0
    # G5
    volume_ratio_20: float
    cvd_delta: float
    volume_surge_bullish: bool
    volume_surge_bearish: bool
    poc_proximity: float
    volume_explosion: bool
    explosion_bullish: bool
    explosion_bearish: bool
    # G6
    rsi_14: float
    macd_histogram: float
    atr_percent: float

class Nexus15Response(BaseModel):
    symbol: str
    timeframe: str
    analyzed_at: str
    ai_confidence: float        # 0-100
    direction: str              # BULLISH / BEARISH / NEUTRAL
    recommendation: str         # Long / Short / Wait
    next_5_candles_prob: float
    next_15_candles_prob: float
    next_20_candles_prob: float
    estimated_range_percent: float
    regime: str
    volume_explosion: bool
    group_scores: GroupScores
    features: Nexus15Features
    detectivity: Dict[str, str]

# ── STRIKE 15m Schemas ────────────────────────────────────────────────────────────

class Strike15mRequest(BaseModel):
    symbols: List[str]  # List of symbols to scan
    timeframe: str = "15m"  # Always 15m for STRIKE

class Strike15mItem(BaseModel):
    symbol: str
    force_score: float  # 7.0 - 10.0
    ma99_distance_pct: float  # 0.0 - 1.0%
    volume_15m: float
    current_price: float
    ma99_value: float
    candle_open: float
    atr_20_15m: float
    is_perfect_shot: bool  # True if score 10/10 and 0% MA99 distance

class Strike15mResponse(BaseModel):
    top_5: List[Strike15mItem]
    scanned_count: int
    analyzed_at: str

# ── STAIRCASE Schemas ────────────────────────────────────────────────────────────

class StaircaseRequest(BaseModel):
    symbols: List[str]  # List of symbols to scan

class StaircaseItem(BaseModel):
    symbol: str
    order_score: float  # 0-100, measures EMA parallelism and order
    trend_1d: str  # "Bullish" or "Bearish"
    phase: str  # "Rest", "Consolidation", or "Impulse"
    current_price: float
    ema7_value: float
    ema25_value: float
    impulse_detected: bool  # True if 4-5% impulse detected recently

class StaircaseResponse(BaseModel):
    top_5: List[StaircaseItem]
    scanned_count: int
    analyzed_at: str

# ── ARROW PEAK Schemas ────────────────────────────────────────────────────────────

class ArrowPeakRequest(BaseModel):
    symbols: List[str]  # List of symbols to scan

class ArrowPeakItem(BaseModel):
    symbol: str
    prev_rise_pct: float  # Previous rise magnitude before peak (%)
    days_bleeding: int  # Number of red candles after peak (1-5)
    current_price: float
    peak_price: float  # The highest point of the arrow
    arrow_start_price: float  # Open of the first candle of the pump (base of the arrow)
    dist_ma99_pct: float  # Distance to MA99 in 15m (%)
    trigger_signal: bool = False  # True if the 15m execution trigger fired (price at MA99 + red > prev green)

class ArrowPeakResponse(BaseModel):
    top_5: List[ArrowPeakItem]
    scanned_count: int
    analyzed_at: str
