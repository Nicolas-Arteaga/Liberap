"""
BinanceFetcher — Market Data Provider (Phase 2: Multi-Exchange)
===============================================================
Data priority (strict order, no exceptions):
  1. SQLite KlineCache (live_prices table) — zero latency, zero exchange calls
  2. Multi-Exchange REST chain (Binance → Bybit → OKX) — only when cache empty

Changes from Phase 1:
  - REST fallback now goes through MultiSourceFetcher instead of direct Binance-only calls.
  - If Binance REST is banned, Bybit/OKX REST will be tried automatically.
  - Circuit breaker state is tracked per exchange in circuit_breaker.py.
  - The BinanceRateLimiter is still used for Binance-specific weight tracking.

Rules:
  - NEVER call any exchange REST directly from this file.
  - Always use self._multi_fetcher for REST calls.
  - The WS server writes to KlineCache continuously. This fetcher only reads from it.
  - REST is used ONLY for on-demand history when cache has < 25 candles.
"""

import logging
import time
from typing import Optional

from rate_limiter import get_limiter
from kline_cache import get_cache
from multi_source_fetcher import get_multi_fetcher

logger = logging.getLogger("BinanceFetcher")


class BinanceFetcher:
    """
    Reads market data from:
      1. KlineCache (SQLite) — primary, always checked first
      2. Multi-exchange REST chain — fallback for missing history only

    Thread-safe (uses thread-local connections in KlineCache).
    The name 'BinanceFetcher' is kept for backward compatibility with verge_agent.py.
    """

    def __init__(self):
        self._limiter       = get_limiter()          # Binance weight tracker (still used for Binance calls)
        self._cache         = get_cache()
        self._multi_fetcher = get_multi_fetcher()    # Multi-exchange REST chain

    # ──────────────────────────────────────────────────────────
    # Public API (unchanged interface — backward compatible)
    # ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float:
        """
        Returns the latest price for a symbol.

        Priority:
          1. Live price from KlineCache (updated by any WS exchange every ~2s)
          2. Last close from klines in cache
          3. Multi-source REST (tries Binance → Bybit → OKX in order)
        """
        # 1. Live price from cache
        price = self._cache.get_live_price(symbol)
        if price > 0:
            return price

        # 2. Last kline close from cache
        klines = self._cache.get_klines(symbol, "15m", limit=1)
        if klines:
            return float(klines[-1]["close"])

        # 3. Multi-source REST fallback
        logger.info(f"[Fetcher] Cache miss for {symbol} price. Trying multi-source REST...")
        fetched = self._multi_fetcher.fetch_klines(symbol, "15m", limit=1)
        if fetched:
            return float(fetched[-1]["close"])

        logger.warning(f"[Fetcher] No price available for {symbol} from any source.")
        return 0.0

    def get_ticker(self, symbol: str) -> Optional[dict]:
        """
        Returns the live ticker data for Tier 2 pre-filtering.
        Reads exclusively from KlineCache — zero exchange calls.
        Returns None if no live data available.
        """
        ticker = self._cache.get_ticker(symbol)
        if ticker and ticker.get("is_fresh"):
            return ticker
        return None

    def get_klines_for_nexus(self, symbol: str, interval: str = "15m", limit: int = 50) -> list:
        """
        Returns OHLCV klines for Nexus-15 analysis.

        Priority:
          1. KlineCache (SQLite) — always preferred (written by WS from any exchange)
          2. Multi-source REST fetch if cache has < 25 candles

        Returns [] if insufficient data and all REST sources fail.
        """
        # 1. Check cache first
        klines = self._cache.get_klines(symbol, interval, limit)
        if len(klines) >= 25:
            return klines

        # 2. On-demand multi-source REST fetch
        if len(klines) > 0:
            logger.debug(
                f"[Fetcher] {symbol} has {len(klines)} klines in cache "
                f"(need 25+). Fetching via multi-source REST."
            )
        else:
            logger.info(f"[Fetcher] {symbol} has no cache history. Fetching via multi-source REST.")

        # Check if Binance-specific limiter blocks us
        # (MultiSourceFetcher handles per-exchange circuit breakers internally)
        fetched = self._multi_fetcher.fetch_klines(symbol, interval, limit)

        if fetched:
            # Persist to cache so subsequent calls are instant
            rest_klines = [{
                "open_time": k["open_time"],
                "open":      k["open"],
                "high":      k["high"],
                "low":       k["low"],
                "close":     k["close"],
                "volume":    k["volume"],
                "is_final":  True,
            } for k in fetched]
            self._cache.bulk_upsert_klines(symbol, interval, rest_klines)
            logger.info(
                f"[Fetcher] {symbol}: fetched {len(fetched)} klines via "
                f"multi-source REST and saved to cache."
            )
            return self._cache.get_klines(symbol, interval, limit)

        # Return whatever we had (partial is better than nothing)
        if klines:
            logger.debug(
                f"[Fetcher] Returning {len(klines)} partial klines for {symbol} "
                f"(all REST sources failed)."
            )
        return klines

    def get_rate_limiter_status(self) -> dict:
        """Exposes rate limiter + circuit breaker status for /health endpoints."""
        logger.debug("[TRACE] Entering get_rate_limiter_status")
        limiter_status = self._limiter.get_status()
        cb_status      = self._multi_fetcher.get_status()
        return {
            **limiter_status,
            "circuit_breakers": cb_status,
        }
