"""
MultiSourceFetcher — Multi-Exchange REST Fallback Chain
=======================================================
Replaces Binance-only REST calls with a priority chain:

  Binance REST → Bybit REST → OKX REST → SQLite cache

Rules:
  - Each exchange is gated by its CircuitBreaker.
  - On 429 → record_failure(is_rate_limit=True, retry_after_s=N)
  - On 418 → record_failure(is_ban=True, retry_after_s=N)
  - On success → record_success()
  - If all REST fail → return cached data (stale is better than nothing)
  - Thread-safe (session per instance).

Usage (from binance_fetcher.py):
    from multi_source_fetcher import MultiSourceFetcher
    fetcher = MultiSourceFetcher()
    klines = fetcher.fetch_klines("BTCUSDT", "15m", 50)
    watchlist = fetcher.fetch_watchlist(limit=200)
"""

import time
import logging
import requests
from typing import Optional, List

from exchange_registry import EXCHANGE_PRIORITY_LIST, ExchangeConfig
from circuit_breaker import get_breakers

logger = logging.getLogger("MultiSourceFetcher")


class MultiSourceFetcher:
    """
    Fetches REST data from multiple exchanges using a priority chain.
    Binance is always tried first; others are fallbacks.
    """

    def __init__(self, timeout_s: int = 8):
        self._session  = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._timeout  = timeout_s
        self._breakers = get_breakers()

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def fetch_klines(
        self,
        symbol:   str,
        interval: str = "15m",
        limit:    int = 50,
    ) -> List[dict]:
        """
        Fetches klines for a symbol from the first available exchange.
        Returns normalized list of kline dicts, or [] if all fail.
        """
        for exc in EXCHANGE_PRIORITY_LIST:
            cb = self._breakers.get(exc.name)
            if cb and not cb.is_available:
                logger.debug(f"[MSF] {exc.name} skipped (circuit {cb.state})")
                continue

            klines = self._do_fetch_klines(exc, symbol, interval, limit)
            if klines:
                logger.debug(f"[MSF] Klines for {symbol} from {exc.name} ({len(klines)} candles)")
                return klines

        logger.warning(f"[MSF] All exchanges failed for klines {symbol}. Returning [].")
        return []

    def fetch_watchlist(self, limit: int = 200) -> List[str]:
        """
        Fetches the top-N USDT futures symbols by volume from the first available exchange.
        Returns list of canonical symbols (BTCUSDT format), or [] if all fail.
        """
        for exc in EXCHANGE_PRIORITY_LIST:
            if not exc.rest_watchlist_url or not exc.rest_watchlist_parser:
                continue

            cb = self._breakers.get(exc.name)
            if cb and not cb.is_available:
                logger.debug(f"[MSF] {exc.name} watchlist skipped (circuit {cb.state})")
                continue

            symbols = self._do_fetch_watchlist(exc, limit)
            if symbols:
                logger.info(f"[MSF] Watchlist ({len(symbols)} symbols) from {exc.name}")
                return symbols

        logger.warning("[MSF] All exchanges failed for watchlist. Returning [].")
        return []

    def get_status(self) -> dict:
        """Returns the status of all circuit breakers."""
        return {name: cb.get_status() for name, cb in self._breakers.items()}

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _do_fetch_klines(
        self,
        exc:      ExchangeConfig,
        symbol:   str,
        interval: str,
        limit:    int,
    ) -> List[dict]:
        cb = self._breakers.get(exc.name)
        try:
            params = exc.rest_kline_params(symbol, interval, limit)
            resp   = self._session.get(exc.rest_kline_url, params=params, timeout=self._timeout)

            if resp.status_code == 200:
                klines = exc.rest_kline_parser(resp.json())
                if klines:
                    if cb:
                        cb.record_success()
                    return klines
                # Empty but 200 — not a circuit breaker event
                logger.debug(f"[MSF:{exc.name}] 200 but empty klines for {symbol}")
                return []

            # Handle error codes
            retry_after = self._parse_retry_after(resp.headers)
            if resp.status_code == 418:
                logger.critical(f"[MSF:{exc.name}] HTTP 418 — IP ban detected!")
                if cb:
                    cb.record_failure(is_ban=True, retry_after_s=retry_after)
            elif resp.status_code == 429:
                logger.warning(f"[MSF:{exc.name}] HTTP 429 — rate limited.")
                if cb:
                    cb.record_failure(is_rate_limit=True, retry_after_s=retry_after)
            else:
                logger.warning(f"[MSF:{exc.name}] HTTP {resp.status_code} for {symbol}")
                if cb:
                    cb.record_failure()

        except requests.exceptions.Timeout:
            logger.warning(f"[MSF:{exc.name}] Timeout fetching klines {symbol}")
            if cb:
                cb.record_failure()
        except Exception as e:
            logger.error(f"[MSF:{exc.name}] Exception fetching klines {symbol}: {e}")
            if cb:
                cb.record_failure()

        return []

    def _do_fetch_watchlist(self, exc: ExchangeConfig, limit: int) -> List[str]:
        cb = self._breakers.get(exc.name)
        try:
            resp = self._session.get(exc.rest_watchlist_url, timeout=self._timeout)

            if resp.status_code == 200:
                symbols = exc.rest_watchlist_parser(resp.json())
                if symbols:
                    if cb:
                        cb.record_success()
                    return symbols[:limit]
                return []

            retry_after = self._parse_retry_after(resp.headers)
            if resp.status_code == 418:
                if cb:
                    cb.record_failure(is_ban=True, retry_after_s=retry_after)
            elif resp.status_code == 429:
                if cb:
                    cb.record_failure(is_rate_limit=True, retry_after_s=retry_after)
            else:
                if cb:
                    cb.record_failure()

        except Exception as e:
            logger.error(f"[MSF:{exc.name}] Exception fetching watchlist: {e}")
            if cb:
                cb.record_failure()

        return []

    @staticmethod
    def _parse_retry_after(headers) -> int:
        """Parses Retry-After header. Returns 0 if not present."""
        for key in ("Retry-After", "retry-after"):
            val = headers.get(key, "")
            if str(val).isdigit():
                return int(val)
        return 0


# ─────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────

import threading
_fetcher: Optional[MultiSourceFetcher] = None
_fetcher_lock = threading.Lock()


def get_multi_fetcher() -> MultiSourceFetcher:
    """Returns the global MultiSourceFetcher singleton. Thread-safe."""
    global _fetcher
    if _fetcher is None:
        with _fetcher_lock:
            if _fetcher is None:
                _fetcher = MultiSourceFetcher()
                logger.info("[MSF] MultiSourceFetcher initialized.")
    return _fetcher
