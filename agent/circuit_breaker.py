"""
CircuitBreaker — Per-Exchange Fault Tolerance
=============================================
Implements the Circuit Breaker pattern for each exchange source.

States:
  CLOSED    → Healthy. Calls allowed. Failures are counted.
  OPEN      → Quarantined. No calls until recovery_timeout elapses.
  HALF_OPEN → Recovery probe. One call allowed to test health.

Special cases (from HTTP response codes):
  HTTP 429 → rate limited: pause for Retry-After or 60s minimum.
  HTTP 418 → IP ban: quarantine for Retry-After or 4 hours.

Usage:
    from circuit_breaker import get_breakers, ExchangeCircuitBreaker

    breakers = get_breakers()      # one per exchange, shared singleton
    cb = breakers["bybit"]

    if cb.is_available:
        try:
            result = call_bybit(...)
            cb.record_success()
        except Exception as e:
            cb.record_failure()
"""

import time
import threading
import logging
from typing import Dict

logger = logging.getLogger("CircuitBreaker")


class ExchangeCircuitBreaker:
    """Thread-safe circuit breaker for a single exchange."""

    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_s: int = 300,    # 5 min before probing again
        success_threshold:  int = 2,      # consecutive successes to close
    ):
        self.name               = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout  = recovery_timeout_s
        self._success_threshold = success_threshold

        self._state          = self.CLOSED
        self._failure_count  = 0
        self._success_count  = 0
        self._opened_at      = 0.0

        # Soft blocks (don't change circuit state, just pause calls)
        self._rate_limited_until = 0.0   # 429 cooldown
        self._ban_until          = 0.0   # 418 hard ban

        self._mu = threading.Lock()

        # Stats
        self._stat_successes = 0
        self._stat_failures  = 0
        self._stat_429s      = 0
        self._stat_418s      = 0

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """True if the exchange can be called right now."""
        with self._mu:
            now = time.time()
            if now < self._ban_until:
                return False
            if now < self._rate_limited_until:
                return False
            return self._get_state_locked() in (self.CLOSED, self.HALF_OPEN)

    @property
    def state(self) -> str:
        with self._mu:
            return self._get_state_locked()

    def record_success(self):
        """Call after every successful exchange response."""
        with self._mu:
            self._stat_successes += 1
            self._failure_count = 0
            if self._state == self.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._state = self.CLOSED
                    logger.info(f"[CB:{self.name}] HALF_OPEN → CLOSED ✅ (exchange recovered)")

    def record_failure(
        self,
        is_ban:         bool = False,
        is_rate_limit:  bool = False,
        retry_after_s:  int  = 0,
    ):
        """
        Call after a failed exchange response.
        - is_ban=True       → HTTP 418, enter hard-ban quarantine
        - is_rate_limit=True → HTTP 429, temporary pause
        - neither           → generic failure, count toward threshold
        """
        with self._mu:
            self._stat_failures += 1

            if is_ban:
                self._stat_418s += 1
                wait = retry_after_s or 14_400  # 4 hours default
                self._ban_until = time.time() + wait
                # Also open the circuit — don't even try REST
                self._state = self.OPEN
                self._opened_at = time.time()
                logger.critical(
                    f"[CB:{self.name}] *** IP BAN (418) *** → OPEN for "
                    f"{wait}s (~{wait/3600:.1f}h). All calls quarantined."
                )
                return

            if is_rate_limit:
                self._stat_429s += 1
                wait = retry_after_s or 60
                self._rate_limited_until = time.time() + wait
                logger.warning(
                    f"[CB:{self.name}] Rate limit (429) → paused {wait}s. "
                    f"Total 429s: {self._stat_429s}"
                )
                return

            # Generic failure
            self._failure_count += 1

            if self._state == self.HALF_OPEN:
                # Failed during recovery probe → back to OPEN
                self._state     = self.OPEN
                self._opened_at = time.time()
                logger.warning(f"[CB:{self.name}] HALF_OPEN → OPEN ❌ (probe failed)")

            elif self._failure_count >= self._failure_threshold:
                if self._state != self.OPEN:
                    self._state     = self.OPEN
                    self._opened_at = time.time()
                    logger.error(
                        f"[CB:{self.name}] CLOSED → OPEN ❌ "
                        f"({self._failure_count} failures >= threshold {self._failure_threshold})"
                    )

    def get_status(self) -> dict:
        with self._mu:
            now = time.time()
            return {
                "exchange":           self.name,
                "state":              self._get_state_locked(),
                "is_available":       self.is_available,
                "failure_count":      self._failure_count,
                "ban_remaining_s":    max(0, int(self._ban_until - now)),
                "rl_remaining_s":     max(0, int(self._rate_limited_until - now)),
                "open_for_s":         int(now - self._opened_at) if self._state == self.OPEN else 0,
                "recovery_timeout_s": self._recovery_timeout,
                "stat_successes":     self._stat_successes,
                "stat_failures":      self._stat_failures,
                "stat_429s":          self._stat_429s,
                "stat_418s":          self._stat_418s,
            }

    def force_reset(self):
        """Manually reset the circuit breaker (for admin/testing)."""
        with self._mu:
            self._state              = self.CLOSED
            self._failure_count      = 0
            self._success_count      = 0
            self._opened_at          = 0.0
            self._ban_until          = 0.0
            self._rate_limited_until = 0.0
        logger.info(f"[CB:{self.name}] Circuit breaker force-reset to CLOSED.")

    # ──────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────

    def _get_state_locked(self) -> str:
        """Must be called under self._mu."""
        if self._state == self.OPEN:
            elapsed = time.time() - self._opened_at
            if elapsed >= self._recovery_timeout:
                self._state         = self.HALF_OPEN
                self._success_count = 0
                logger.info(
                    f"[CB:{self.name}] OPEN → HALF_OPEN (recovery timeout elapsed, probing...)"
                )
        return self._state


# ─────────────────────────────────────────────────────────────
# Singleton — one breaker per exchange, shared across all modules
# ─────────────────────────────────────────────────────────────

_breakers: Dict[str, ExchangeCircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breakers() -> Dict[str, ExchangeCircuitBreaker]:
    """
    Returns the global dict of ExchangeCircuitBreakers.
    Initialized lazily from the exchange registry.
    """
    global _breakers
    if not _breakers:
        with _breakers_lock:
            if not _breakers:
                from exchange_registry import EXCHANGES
                for name in EXCHANGES:
                    # Binance gets longer recovery (4h ban is real)
                    # Others get faster recovery (5 min)
                    recovery = 14_400 if name == "binance" else 300
                    _breakers[name] = ExchangeCircuitBreaker(
                        name=name,
                        failure_threshold=3,
                        recovery_timeout_s=recovery,
                        success_threshold=2,
                    )
                logger.info(f"[CB] Circuit breakers initialized: {list(_breakers.keys())}")
    return _breakers


def get_breaker(exchange_name: str) -> ExchangeCircuitBreaker:
    """Returns the circuit breaker for a specific exchange."""
    return get_breakers()[exchange_name]
