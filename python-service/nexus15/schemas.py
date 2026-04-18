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
    poc_proximity: float
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
    group_scores: GroupScores
    features: Nexus15Features
    detectivity: Dict[str, str]
