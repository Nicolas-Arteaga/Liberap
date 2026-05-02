"""
LSE State Machine — Gestiona el ciclo de vida de señales LSE por símbolo/timeframe.

Estados:
  idle → compression_detected → sweep_detected → reclaimed → triggered → closed

Evita señales duplicadas y aplica cooldown post-cierre.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from .models import LSEState

logger = logging.getLogger("LSE_STATE_MACHINE")


class SymbolStateMachineEntry:
    def __init__(self):
        self.state: LSEState = LSEState.idle
        self.candles_in_state: int = 0
        self.cooldown_remaining: int = 0
        self.last_triggered_at: Optional[datetime] = None
        self.sweep_low: Optional[float] = None
        self.sweep_high: Optional[float] = None
        self.entry_price: Optional[float] = None

    def transition(self, new_state: LSEState, cooldown_candles: int = 0):
        old = self.state
        self.state = new_state
        self.candles_in_state = 0
        if new_state == LSEState.triggered:
            self.last_triggered_at = datetime.now(timezone.utc)
        if new_state == LSEState.closed:
            self.cooldown_remaining = cooldown_candles
        logger.debug("🔄 [%s] State: %s → %s", "SM", old.value, new_state.value)

    def tick(self):
        """Llamar en cada nueva vela."""
        self.candles_in_state += 1
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
            if self.cooldown_remaining == 0:
                self.state = LSEState.idle
                logger.info("✅ Cooldown terminado → idle")

    def is_in_cooldown(self) -> bool:
        return self.state == LSEState.closed and self.cooldown_remaining > 0

    def can_emit_signal(self) -> bool:
        return self.state not in (LSEState.triggered, LSEState.closed)


class LSEStateMachine:
    """
    Singleton global que mantiene el estado de cada (symbol, timeframe).
    """
    _instance: Optional["LSEStateMachine"] = None

    def __init__(self):
        self._states: Dict[Tuple[str, str], SymbolStateMachineEntry] = {}

    @classmethod
    def get(cls) -> "LSEStateMachine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _key(self, symbol: str, timeframe: str) -> Tuple[str, str]:
        return (symbol.upper(), timeframe)

    def _entry(self, symbol: str, timeframe: str) -> SymbolStateMachineEntry:
        k = self._key(symbol, timeframe)
        if k not in self._states:
            self._states[k] = SymbolStateMachineEntry()
        return self._states[k]

    def get_state(self, symbol: str, timeframe: str) -> LSEState:
        return self._entry(symbol, timeframe).state

    def can_emit(self, symbol: str, timeframe: str) -> bool:
        return self._entry(symbol, timeframe).can_emit_signal()

    def tick(self, symbol: str, timeframe: str):
        self._entry(symbol, timeframe).tick()

    def on_compression_detected(self, symbol: str, timeframe: str):
        entry = self._entry(symbol, timeframe)
        if entry.state == LSEState.idle:
            entry.transition(LSEState.compression_detected)

    def on_sweep_detected(self, symbol: str, timeframe: str, sweep_low: float, sweep_high: float):
        entry = self._entry(symbol, timeframe)
        if entry.state in (LSEState.idle, LSEState.compression_detected):
            entry.sweep_low = sweep_low
            entry.sweep_high = sweep_high
            entry.transition(LSEState.sweep_detected)

    def on_reclaimed(self, symbol: str, timeframe: str, entry_price: float):
        entry = self._entry(symbol, timeframe)
        if entry.state == LSEState.sweep_detected:
            entry.entry_price = entry_price
            entry.transition(LSEState.reclaimed)

    def on_triggered(self, symbol: str, timeframe: str):
        entry = self._entry(symbol, timeframe)
        if entry.state == LSEState.reclaimed:
            entry.transition(LSEState.triggered)

    def on_closed(self, symbol: str, timeframe: str, cooldown_candles: int):
        entry = self._entry(symbol, timeframe)
        entry.transition(LSEState.closed, cooldown_candles=cooldown_candles)

    def enter_emit_cooldown(self, symbol: str, timeframe: str, cooldown_candles: int):
        """Tras emitir señal válida: cooldown sin estados intermedios inconsistentes."""
        entry = self._entry(symbol, timeframe)
        entry.transition(LSEState.closed, cooldown_candles=cooldown_candles)

    def reset(self, symbol: str, timeframe: str):
        k = self._key(symbol, timeframe)
        if k in self._states:
            del self._states[k]

    def get_all_states(self) -> Dict[str, str]:
        return {f"{k[0]}_{k[1]}": v.state.value for k, v in self._states.items()}
