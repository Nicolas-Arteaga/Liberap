from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ScarScanRequest(BaseModel):
    symbols: List[str]
    # Optional override of funding rates from caller (Binance futures)
    funding_rates: Optional[dict] = None  # symbol -> float


class ScarFlagDetail(BaseModel):
    triggered: bool
    reason: Optional[str] = None
    value: Optional[float] = None


class ScarResultDto(BaseModel):
    symbol: str
    score_grial: int                     # 0 a 5
    prediction: str                      # "PUMP INMINENTE", "En monitoreo", "Sin señal"
    estimated_hours: Optional[int] = None

    flag_whale_withdrawal: bool
    flag_supply_drying: bool
    flag_price_stable: bool
    flag_funding_negative: bool
    flag_silence: bool

    # Detalles de cada flag (para debug y UI)
    detail_whale_withdrawal: Optional[ScarFlagDetail] = None
    detail_supply_drying: Optional[ScarFlagDetail] = None
    detail_price_stable: Optional[ScarFlagDetail] = None
    detail_funding_negative: Optional[ScarFlagDetail] = None
    detail_silence: Optional[ScarFlagDetail] = None

    # Datos de soporte
    days_since_last_pump: Optional[int] = None
    estimated_next_window: Optional[str] = None
    withdrawal_days_count: int = 0
    total_withdrawn_usd: float = 0.0
    mode: str = "degraded"              # "degraded" | "onchain"
    analyzed_at: str = ""


class ScarStatusResponse(BaseModel):
    symbol: str
    score_grial: int
    prediction: str
    flags: dict
    mode: str
    analyzed_at: str


class ScarTopSetup(BaseModel):
    symbol: str
    score_grial: int
    prediction: str
    estimated_hours: Optional[int]
    mode: str


class ScarHistoryEntry(BaseModel):
    date: str
    score_grial: int
    prediction: str
    flag_whale_withdrawal: bool
    flag_supply_drying: bool
    flag_price_stable: bool
    flag_funding_negative: bool
    flag_silence: bool


class ScarHistoryResponse(BaseModel):
    symbol: str
    history: List[ScarHistoryEntry]
    total_cycles: int
    last_pump_date: Optional[str] = None
    avg_withdrawal_days: Optional[float] = None
