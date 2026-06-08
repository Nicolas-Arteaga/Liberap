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

        # 2. Multi-source REST fallback
        logger.info(f"[Fetcher] Cache miss for {symbol} price. Trying multi-source REST...")
        fetched = self._multi_fetcher.fetch_klines(symbol, "15m", limit=1)
        if fetched:
            return float(fetched[-1]["close"])

        # 3. Last kline close from cache (Fallback only if REST fails to avoid stale prices)
        logger.warning(f"[Fetcher] REST failed for {symbol}. Falling back to potentially stale cache kline.")
        klines = self._cache.get_klines(symbol, "15m", limit=1)
        if klines:
            return float(klines[-1]["close"])

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

    def get_klines_for_nexus(self, symbol: str, interval: str = "15m", limit: int = 300) -> list:
        """
        Returns OHLCV klines for Nexus-15 (15m) and Nexus-5 (5m) analysis.

        Priority:
          1. KlineCache (SQLite) — always preferred (written by WS from any exchange)
          2. Multi-source REST fetch if cache stale or has < 100 candles

        NOTE for 5m: Uses Binance Futures directly to guarantee correct interval data.
             Other exchanges (Bybit/OKX/Bitget) may return different intervals if "5m"
             is not in their primary rotation. Binance supports up to 1500 candles at 5m.

        Returns [] if insufficient data and all REST sources fail.
        """

        # 1. Check cache first
        klines = self._cache.get_klines(symbol, interval, limit)
        is_fresh = False
        if len(klines) >= 100:  # Need at least 100 candles for a meaningful score
            last_open = klines[-1]["open_time"]
            age_mins = (time.time() - (last_open / 1000.0)) / 60.0
            # Tolerance: 10 min for 5m candles, 35 min for 15m candles
            max_age = 10 if interval == "5m" else 35
            if age_mins <= max_age:
                is_fresh = True

        if is_fresh:
            return klines

        # 2. On-demand REST fetch
        if len(klines) > 0:
            logger.debug(
                f"[Fetcher] {symbol} {interval}: {len(klines)} klines in cache "
                f"(need 100+). Fetching via REST."
            )
        else:
            logger.info(f"[Fetcher] {symbol} {interval}: no cache history. Fetching via REST.")

        # For 5m candles, always use Binance Futures directly to guarantee correct interval.
        # Other exchanges default to 15m when "5m" is not explicitly supported.
        if interval == "5m":
            from exchange_registry import EXCHANGES
            binance_exc = EXCHANGES.get("binance")
            if binance_exc:
                fetched = self._do_fetch_binance_direct(binance_exc, symbol, interval, limit)
            else:
                fetched = self._multi_fetcher.fetch_klines(symbol, interval, limit)
        else:
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

    def get_klines_for_lse(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 150,
        min_cache: int = 120,
    ) -> list:
        """
        OHLCV para LSE (1h / 4h). Igual que Nexus: primero SQLite, si falta historial → REST multi-exchange.

        Sin esto, LSE veía siempre lista vacía: el agente llamaba get_klines() que no existía en esta clase.
        """
        klines = self._cache.get_klines(symbol, interval, limit)
        is_fresh = False
        if len(klines) >= min_cache:
            last_open = klines[-1]["open_time"]
            age_mins = (time.time() - (last_open / 1000.0)) / 60.0
            if interval == "1h" and age_mins <= 125:
                is_fresh = True
            elif interval != "1h":
                is_fresh = True

        if is_fresh:
            return klines

        if len(klines) > 0:
            logger.debug(
                f"[Fetcher/LSE] {symbol} {interval}: {len(klines)} velas en caché "
                f"(se piden ≥{min_cache}). Backfill REST."
            )
        else:
            logger.info(
                f"[Fetcher/LSE] {symbol} {interval}: sin historial en caché. Backfill REST."
            )

        fetched = self._multi_fetcher.fetch_klines(symbol, interval, limit)
        if fetched:
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
                f"[Fetcher/LSE] {symbol} {interval}: {len(fetched)} velas guardadas vía REST."
            )
            return self._cache.get_klines(symbol, interval, limit)

        if klines:
            logger.debug(
                f"[Fetcher/LSE] {symbol} {interval}: REST falló; devolviendo {len(klines)} parciales."
            )
        return klines

    def _do_fetch_binance_direct(self, binance_exc, symbol: str, interval: str, limit: int) -> list:
        """
        Calls Binance Futures REST API directly for klines.
        Used for 5m candles to bypass the load-balancer that may route to
        exchanges with no native 5m support.

        Returns normalized kline list, or [] on any failure.
        """
        import requests
        try:
            params = binance_exc.rest_kline_params(symbol, interval, limit)
            resp = requests.get(
                binance_exc.rest_kline_url,
                params=params,
                timeout=10
            )
            if resp.status_code == 200:
                klines = binance_exc.rest_kline_parser(resp.json())
                if klines:
                    logger.info(
                        f"[Fetcher] {symbol} {interval}: fetched {len(klines)} klines "
                        f"via Binance direct REST and saved to cache."
                    )
                    return klines
                logger.debug(f"[Fetcher/Direct] Binance returned empty klines for {symbol} {interval}")
            elif resp.status_code == 429:
                logger.warning(f"[Fetcher/Direct] Binance rate-limited (429) for {symbol}")
            elif resp.status_code == 418:
                logger.critical(f"[Fetcher/Direct] Binance IP ban (418) for {symbol}")
            else:
                logger.warning(f"[Fetcher/Direct] Binance HTTP {resp.status_code} for {symbol}")
        except Exception as e:
            logger.error(f"[Fetcher/Direct] Exception fetching {symbol} {interval} from Binance: {e}")
        return []

    def get_rate_limiter_status(self) -> dict:
        """Exposes rate limiter + circuit breaker status for /health endpoints."""
        logger.debug("[TRACE] Entering get_rate_limiter_status")
        limiter_status = self._limiter.get_status()
        cb_status      = self._multi_fetcher.get_status()
        return {
            **limiter_status,
            "circuit_breakers": cb_status,
        }
