"""
NEXUS-5 "Ignition Core" — Pydantic Schemas
Detects Phase 1 (Compression) and Phase 2 (Ignition) on 5m candles.
Supports both LONG and SHORT ignition signals.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class CandleInput(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class Nexus5Request(BaseModel):
    """Request body for /nexus5/analyze endpoint."""
    symbol: str
    timeframe: str = "5m"
    candles: List[CandleInput]            # 5m candles — mínimo 30
    candles_1m: Optional[List[CandleInput]] = None  # optional, for entry timing
    candles_3m: Optional[List[CandleInput]] = None  # optional, for entry timing


class GroupScores(BaseModel):
    g1_price_action: float    # 0-100
    g2_smc_ict: float         # 0-100
    g3_wyckoff: float         # 0-100
    g4_fractals: float        # 0-100
    g5_volume: float          # 0-100
    g6_ml: float              # 0-100


class Nexus5Features(BaseModel):
    """18 features de los 6 grupos — todos orientados a detectar ignición."""

    # ── G1: Price Action — Ruptura Sniper ───────────────────────────────────
    compression_range: float        # (max-min)/close de últimas 20 velas (<4% = compresión)
    ignition_candle: bool           # vela actual cruza max del rango con cuerpo fuerte
    efficiency_check: float         # velocidad actual vs histórica (0.0 = lento, 1.0 = máximo)

    # ── G2: SMC/ICT — Desplazamiento ────────────────────────────────────────
    displacement_fvg: bool          # Fair Value Gap gigante (>0.3% del precio)
    micro_choch: bool               # Change of Character — primer quiebre de estructura 5m
    instant_order_block: bool       # Order Block en últimas 5 velas

    # ── G3: Wyckoff Intraday — Fases de Resorte ─────────────────────────────
    compression_zone: bool          # rango <4% por 12+ velas consecutivas
    sos_detected: bool              # Sign of Strength — primera vela fuera de lateralización
    jumping_creek: bool             # cruce del techo con volumen >2x

    # ── G4: Fractales & Estructura — Micro-Tendencia ────────────────────────
    fractal_high_break: bool        # ruptura fractal alto 5m
    ema7_angle: float               # ángulo normalizado de EMA-7 (0.0-1.0, >0.5 = momentum)
    hh_hl_sequence: bool            # dos mínimos crecientes consecutivos

    # ── G5: Volume Profile & Order Flow (CORAZÓN) ───────────────────────────
    relative_vol_multiplier: float  # vol actual / promedio 20 velas (target >3x)
    vol_intensity: float            # volumen / body size (bots peleando)
    buying_imbalance: float         # % volumen de compra en últimas 5 velas (0.0-1.0)

    # ── G6: ML Features — Anomalías Estadísticas ────────────────────────────
    atr_expansion: float            # ATR% actual / ATR% promedio 50 velas (>1.5 = resorte soltado)
    z_score: float                  # distancia del precio vs MA50 en desvíos estándar
    rsi_velocity: float             # cambio de RSI en últimas 3 velas (no el nivel absoluto)

    # ── PUMP CYCLICITY — El Reloj del Market Maker (v6.2) ─────────────────────
    cycle_detected: bool            # True si detectó patrón de 24h en los pumps
    minutes_to_next_pump: float      # minutos restantes para el próximo pump esperado
    confidence_boost: float         # boost de confianza basado en proximidad al pump

    # ── ESTRUCTURAL ANALYSIS — Reglas de Oro (v9.0 Bottom Sniper) ────────────────
    # Basado en temporalidad de 15m para MA50/MA99 reales
    slope_ma50: float               # Pendiente de MA50 (0.0 = horizontal, <0 = diagonal abajo)
    ma99_long_slope: float          # Pendiente de MA99 a largo plazo (40 velas) - detecta caída previa
    is_bottom_sniper: bool          # True si cumple setup de FIDA (caída larga + plano + debajo MA99)
    gravity_ma99_safe: bool         # True si MA99 NO está en caída en picada
    vol_ratio: float               # Volumen actual / promedio últimas 10 velas
    compression_viper: bool        # True si precio y MA50 hacen zig-zag y distancia MA50-MA99 < 1.5%
    ma50_horizontal: bool          # True si MA50 está horizontal (slope < 0.1% en últimas 10 velas)
    ma50_ma99_dist: float           # Distancia entre MA50 y MA99 (para compresión)
    price_to_ma99_pct: float        # Precio relativo a MA99 (para Deep Bottom y Anti-FOMO)


class Nexus5Response(BaseModel):
    """Response from NEXUS-5 Ignition Core analysis."""
    symbol: str
    timeframe: str
    analyzed_at: str

    # ── Core Signals ─────────────────────────────────────────────────────────
    ai_confidence: float            # 0-100 — convicción global del análisis
    direction: str                  # LONG / SHORT / NEUTRAL
    recommendation: str             # Long / Short / Wait
    phase: str                      # COMPRESSION / IGNITION / EXPANSION / IDLE
    phase_score: float              # 0-100 — qué tan cerca de ignición (100 = explotó ahora)
    entry_timeframe: str            # "1m" / "3m" / "5m" recomendado para entrar

    # ── Ignition-Specific Flags ───────────────────────────────────────────────
    compression_state: bool         # True si está en Fase 1 (compresión activa)
    ignition_detected: bool         # True si acaba de romper (Fase 2 iniciada)
    bypass_active: bool             # True si se anuló veto RSI por volumen extremo

    # ── Forward Probabilities ───────────────────────────────────────────────
    next_3_candles_prob: float      # probabilidad de que el movimiento siga en las próximas 3 velas
    next_5_candles_prob: float      # próximas 5 velas (~25 min)
    next_10_candles_prob: float     # próximas 10 velas (~50 min)
    estimated_range_percent: float  # rango estimado del movimiento en %

    # ── Market Context ───────────────────────────────────────────────────────
    regime: str                     # BullTrend / BearTrend / Ranging
    volume_explosion: bool          # detección de explosión de volumen

    # ── Scores & Features ─────────────────────────────────────────────────────
    group_scores: GroupScores
    features: Nexus5Features
    detectivity: Dict[str, str]     # human-readable explanation por grupo
