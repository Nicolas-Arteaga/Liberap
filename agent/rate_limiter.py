"""
BinanceRateLimiter - Global Rate Limit Singleton
==================================================
Controls ALL REST calls to Binance Futures.

Features:
  - Token bucket tracking weights per 1-minute window
  - Reads X-MBX-USED-WEIGHT-1M header from every response
  - HTTP 429 → temporary rate limit with Retry-After
  - HTTP 418 → DEGRADED MODE (WS + cache only) for configurable duration
  - Thread-safe with threading.Lock
  - Status endpoint for /health reporting

Usage (in any module):
    from rate_limiter import get_limiter
    limiter = get_limiter()

    if limiter.acquire(weight=5):
        resp = session.get(url)
        limiter.record(resp.status_code, resp.headers)
    else:
        # Use cached data — do NOT call Binance
"""

import time
import threading
import logging
from typing import Optional

logger = logging.getLogger("RateLimiter")

# Binance Futures REST weight limits
WEIGHT_LIMIT_PER_MINUTE = 2400   # Binance official limit
SAFETY_MARGIN_PCT       = 0.80   # Use max 80% — never approach the ceiling

# Degraded mode durations
BAN_COOLDOWN_SECONDS    = 4 * 3600   # 4 hours after a 418
RATE_LIMIT_MIN_WAIT     = 30         # Minimum wait on 429 if no Retry-After


class BinanceRateLimiter:
    """
    Thread-safe singleton rate limiter for Binance Futures REST API.
    Never instantiate directly — use get_limiter().
    """

    def __init__(self):
        self._mu = threading.Lock()

        # Weight tracking (1-minute rolling window)
        self._weight_used:        int   = 0
        self._window_start:       float = time.time()

        # Degraded mode (HTTP 418 — IP ban)
        self._degraded_until:     float = 0.0
        self._degraded_reason:    str   = ""

        # Temporary rate limit (HTTP 429)
        self._rl_until:           float = 0.0

        # Statistics
        self._stat_requests:      int   = 0
        self._stat_blocked:       int   = 0
        self._stat_429:           int   = 0
        self._stat_418:           int   = 0

    # ──────────────────────────────────────────────────────────
    # Public state checks
    # ──────────────────────────────────────────────────────────

    @property
    def is_degraded(self) -> bool:
        """True when an IP ban (418) is active. All REST is disabled."""
        return time.time() < self._degraded_until

    @property
    def is_rate_limited(self) -> bool:
        """True when a temporary 429 cooldown is active."""
        return time.time() < self._rl_until

    @property
    def can_use_rest(self) -> bool:
        """True when REST calls are safe to make."""
        return not self.is_degraded and not self.is_rate_limited

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _refresh_window(self):
        """Reset weight counter when the 60-second window rolls over."""
        if time.time() - self._window_start >= 60:
            self._weight_used   = 0
            self._window_start  = time.time()

    def _weight_budget(self) -> int:
        return int(WEIGHT_LIMIT_PER_MINUTE * SAFETY_MARGIN_PCT)

    # ──────────────────────────────────────────────────────────
    # Acquire / Record
    # ──────────────────────────────────────────────────────────

    def acquire(self, weight: int = 1) -> bool:
        """
        Call BEFORE making a REST request.
        Returns True if the request is safe to proceed, False if it must be skipped.
        Thread-safe.
        """
        with self._mu:
            if self.is_degraded:
                rem = int(self._degraded_until - time.time())
                logger.debug(f"[RL] DEGRADED — REST blocked ({rem}s remaining). Use cache.")
                self._stat_blocked += 1
                return False

            if self.is_rate_limited:
                rem = int(self._rl_until - time.time())
                logger.debug(f"[RL] Rate limited — REST blocked ({rem}s remaining).")
                self._stat_blocked += 1
                return False

            self._refresh_window()
            if self._weight_used + weight > self._weight_budget():
                logger.warning(
                    f"[RL] Weight budget reached ({self._weight_used}/{self._weight_budget()}). "
                    f"Skipping request (weight={weight})."
                )
                self._stat_blocked += 1
                return False

            self._weight_used  += weight
            self._stat_requests += 1
            return True

    def record(self, status_code: int, headers: dict):
        """
        Call AFTER every REST response to update state from Binance headers.
        This is the single point of truth for rate limit tracking.
        """
        with self._mu:
            # Sync weight from Binance's own counter (most accurate)
            for header_name in ("X-MBX-USED-WEIGHT-1M", "x-mbx-used-weight-1m"):
                raw = headers.get(header_name)
                if raw:
                    try:
                        self._weight_used = int(raw)
                        logger.debug(f"[RL] Binance weight sync: {self._weight_used}/{WEIGHT_LIMIT_PER_MINUTE}")
                    except ValueError:
                        pass
                    break

            if status_code == 429:
                self._stat_429 += 1
                raw_wait = headers.get("Retry-After", "")
                wait = int(raw_wait) if raw_wait.isdigit() else RATE_LIMIT_MIN_WAIT
                self._rl_until = time.time() + wait
                logger.warning(
                    f"[RL] HTTP 429 — Temporary rate limit. REST paused for {wait}s. "
                    f"Total 429s: {self._stat_429}"
                )

            elif status_code == 418:
                self._stat_418 += 1
                raw_wait = headers.get("Retry-After", "")
                wait = int(raw_wait) if raw_wait.isdigit() else BAN_COOLDOWN_SECONDS
                self._degraded_until  = time.time() + wait
                self._degraded_reason = f"IP ban (HTTP 418) — {wait}s cooldown (~{wait/3600:.1f}h)"
                logger.critical(
                    f"[RL] *** HTTP 418 — IP BAN DETECTED *** "
                    f"Entering DEGRADED MODE for {wait}s (~{wait/3600:.1f}h). "
                    f"All REST requests disabled. Agent runs on WS + SQLite cache only."
                )

    def force_degraded(self, reason: str, duration_s: int = BAN_COOLDOWN_SECONDS):
        """Manually enter degraded mode (e.g., if caller detects repeated failures)."""
        with self._mu:
            self._degraded_until  = time.time() + duration_s
            self._degraded_reason = reason
        logger.warning(f"[RL] Degraded mode forced: {reason} ({duration_s}s)")

    def force_exit_degraded_mode(self):
        """Manually exit degraded mode for testing if ban is lifted."""
        with self._mu:
            self._degraded_until = 0.0
            self._degraded_reason = ""
        logger.info("[RateLimiter] Forced exit from degraded mode. Testing REST access...")

    # ──────────────────────────────────────────────────────────
    # Status
    # ──────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        with self._mu:
            self._refresh_window()
            return {
                "degraded":              self.is_degraded,
                "degraded_reason":       self._degraded_reason if self.is_degraded else None,
                "degraded_remaining_s":  max(0, int(self._degraded_until - time.time())),
                "rate_limited":          self.is_rate_limited,
                "rl_remaining_s":        max(0, int(self._rl_until - time.time())),
                "weight_used":           self._weight_used,
                "weight_limit":          WEIGHT_LIMIT_PER_MINUTE,
                "weight_budget":         self._weight_budget(),
                "weight_pct":            round(self._weight_used / WEIGHT_LIMIT_PER_MINUTE * 100, 1),
                "total_requests":        self._stat_requests,
                "total_blocked":         self._stat_blocked,
                "total_429s":            self._stat_429,
                "total_418s":            self._stat_418,
            }


# ──────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ──────────────────────────────────────────────────────────────

_limiter: Optional[BinanceRateLimiter] = None
_limiter_lock = threading.Lock()


def get_limiter() -> BinanceRateLimiter:
    """Returns the global BinanceRateLimiter singleton. Thread-safe."""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = BinanceRateLimiter()
                logger.info("[RL] BinanceRateLimiter initialized.")
    return _limiter
