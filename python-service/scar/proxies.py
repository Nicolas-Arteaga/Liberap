"""
SCAR Proxy Signals — Multi-Exchange implementation.
====================================================
Uses Binance public REST APIs as primary source.
Falls back to Bybit if Binance returns an error (ban / rate limit).

Signal routing:
  Signal 1 (Whale Withdrawal): Binance FAPI 24hr + OI → Bybit tickers + OI
  Signal 2 (Supply Drying):    Binance order book → Bybit order book
  Signal 3 (Price Stability):  Binance klines (1d) → Bybit klines (1d)
  Signal 4 (Funding Rate):     Binance funding rate → Bybit funding rate
  Signal 5 (Silence):          Binance klines (1d) → Bybit klines (1d)
  get_current_price:            Binance spot → Bybit futures → 0.0
"""
import requests
import logging
from typing import Tuple, Optional

logger = logging.getLogger("SCAR_PROXIES")

# ── Exchange base URLs ────────────────────────────────────────────────────────
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_API  = "https://api.binance.com"
BYBIT_API    = "https://api.bybit.com"
OKX_API      = "https://www.okx.com"

# URL of the local Market Data Service (market_ws_server.py)
MARKET_WS_URL = "http://127.0.0.1:8001"


# ─────────────────────────────────────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, timeout: int = 8) -> Optional[dict]:
    """Single GET with graceful error handling. Returns None on any failure."""
    try:
        r = _session.get(url, params=params, timeout=timeout)
        if r.status_code == 400:
            logger.debug("SCAR proxy: bad request [%s] (400)", url)
            return None
        if r.status_code in (418, 429):
            logger.warning("SCAR proxy: rate-limited/banned [%s] (HTTP %s)", url, r.status_code)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("SCAR proxy request failed [%s]: %s", url, e)
        return None


def _get_first(*calls) -> Optional[dict]:
    """
    Tries each (url, params) tuple in order.
    Returns the first successful JSON response, or None if all fail.
    Usage: _get_first((url1, params1), (url2, params2))
    """
    for url, params in calls:
        result = _get(url, params)
        if result is not None:
            return result
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Price helper (used by SCAR scheduler internally)
# ─────────────────────────────────────────────────────────────────────────────

def get_current_price(symbol: str) -> float:
    """
    Spot/mark price for a symbol.
    Chain: Local Cache (WS Server) → Binance spot → Bybit futures → 0.0
    """
    # 1. Try Local Market WS Cache (Phase 3: Shared Source of Truth)
    data = _get(f"{MARKET_WS_URL}/market/candle/{symbol}")
    if data and "close" in data:
        return float(data["close"])

    # 2. Binance spot (Legacy fallback)
    data = _get(f"{BINANCE_API}/api/v3/ticker/price", {"symbol": symbol})
    if data and "price" in data:
        return float(data["price"])

    # 3. Bybit futures fallback
    data = _get(f"{BYBIT_API}/v5/market/tickers",
                {"category": "linear", "symbol": symbol})
    try:
        price = float(data["result"]["list"][0]["lastPrice"])
        if price > 0:
            return price
    except Exception:
        pass

    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Signal 1 — Whale Withdrawal Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_whale_withdrawal_proxy(symbol: str) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, confidence_value).
    Uses Futures/Spot volume ratio + OI accumulation as proxy for exchange withdrawal.
    Primary: Binance. Fallback: Bybit.
    """
    # ── Attempt 1: Binance futures/spot volume ratio ─────────────────────────
    try:
        fut_ticker  = _get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", {"symbol": symbol})
        spot_ticker = _get(f"{BINANCE_API}/api/v3/ticker/24hr",   {"symbol": symbol})

        if fut_ticker and spot_ticker:
            fut_vol_usd  = float(fut_ticker.get("quoteVolume", 0))
            spot_vol_usd = float(spot_ticker.get("quoteVolume", 0))
            if spot_vol_usd > 0:
                ratio = fut_vol_usd / spot_vol_usd
                if ratio > 3.0:
                    return True, f"futures/spot_ratio={ratio:.1f}x (spot book thinning)", ratio
    except Exception as e:
        logger.debug("Signal1 Binance vol ratio error for %s: %s", symbol, e)

    # ── Fallback: Bybit volume + OI ──────────────────────────────────────────
    try:
        bybit_ticker = _get(f"{BYBIT_API}/v5/market/tickers",
                            {"category": "linear", "symbol": symbol})
        if bybit_ticker:
            t = bybit_ticker.get("result", {}).get("list", [{}])[0]
            turnover = float(t.get("turnover24h", 0))
            if turnover > 0:
                logger.debug("Signal1: Using Bybit ticker for %s", symbol)
                # Use turnover as a proxy signal (high volume may indicate whale activity)
                if turnover > 500_000_000:  # $500M threshold
                    return True, f"bybit_high_turnover=${turnover/1e6:.0f}M (whale activity)", turnover
    except Exception as e:
        logger.debug("Signal1 Bybit fallback error for %s: %s", symbol, e)

    # ── Attempt 2: Binance OI accumulation ───────────────────────────────────
    try:
        oi_data     = _get(f"{BINANCE_FAPI}/fapi/v1/openInterest", {"symbol": symbol})
        ticker_data = _get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr",  {"symbol": symbol})

        if oi_data and ticker_data:
            oi               = float(oi_data.get("openInterest", 0))
            price_change_pct = abs(float(ticker_data.get("priceChangePercent", 100)))
            if oi > 0 and price_change_pct < 5.0:
                vol_usd = float(ticker_data.get("quoteVolume", 0))
                if vol_usd > 500_000:
                    return True, f"oi_accumulation: price_chg={price_change_pct:.1f}%, vol=${vol_usd/1e6:.1f}M", vol_usd
    except Exception as e:
        logger.debug("Signal1 OI error for %s: %s", symbol, e)

    return False, None, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Signal 2 — Supply Drying Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_supply_drying_proxy(symbol: str) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, confidence_value).
    Uses order book depth analysis as proxy for supply reduction.
    Primary: Binance. Fallback: Bybit.
    """
    depth = _get_first(
        (f"{BINANCE_API}/api/v3/depth",         {"symbol": symbol, "limit": 100}),
        (f"{BYBIT_API}/v5/market/orderbook",    {"category": "linear", "symbol": symbol, "limit": 50}),
    )

    if not depth:
        return False, None, 0.0

    # Normalize Bybit order book format to Binance format
    # Bybit returns: {"result": {"b": [[price,qty],...], "a": [[price,qty],...]}}
    bids = depth.get("bids") or depth.get("result", {}).get("b", [])
    asks = depth.get("asks") or depth.get("result", {}).get("a", [])

    if not bids or not asks:
        return False, None, 0.0

    try:
        best_bid  = float(bids[0][0])
        best_ask  = float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2.0

        # 1. Spread check (>0.5% indicates thin book)
        spread_pct = (best_ask - best_bid) / mid_price if mid_price > 0 else 0
        if spread_pct > 0.005:
            return True, f"wide_spread={spread_pct*100:.2f}%", spread_pct

        # 2. Bid-side depth ratio: vol within 2% vs vol within 10% of price
        def sum_depth(levels, max_pct: float) -> float:
            total = 0.0
            for level in levels:
                price = float(level[0])
                qty   = float(level[1])
                if abs(price - mid_price) / mid_price <= max_pct:
                    total += price * qty
            return total

        near_vol  = sum_depth(bids, 0.02)
        total_vol = sum_depth(bids, 0.10)

        if total_vol > 0:
            ratio = near_vol / total_vol
            if ratio < 0.15:
                return True, f"thin_near_book: {ratio*100:.1f}% of depth within 2%", ratio

    except Exception as e:
        logger.debug("Signal2 depth analysis error for %s: %s", symbol, e)

    return False, None, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Signal 3 — Price Stability Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_price_stable(symbol: str, range_threshold: float = 0.15) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, range_value).
    Checks if price has been in ±15% range for 7+ days using daily klines.
    Chain: Local Cache → Binance → Bybit.
    """
    # 1. Try Local Market WS Cache first (Zero external REST)
    # Note: market_ws_server currently caches 15m klines. 
    # For daily stability, we might still need external or build it from 15m.
    # For now, we try to get it from cache if possible, otherwise fallback.
    
    # Try to get daily klines from any source
    klines = _get_first(
        (f"{MARKET_WS_URL}/market/candles/{symbol}", {"limit": 100}), # 100 x 15m = ~24h
        (f"{BINANCE_API}/api/v3/klines",
            {"symbol": symbol, "interval": "1d", "limit": 8}),
        (f"{BINANCE_FAPI}/fapi/v1/klines",
            {"symbol": symbol, "interval": "1d", "limit": 8}),
        (f"{BYBIT_API}/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "D", "limit": 8}),
    )

    if not klines or not isinstance(klines, (list, dict)):
        return False, "insufficient_data", 0.0

    # Normalize Bybit kline format
    # Bybit: {"result": {"list": [[ts, open, high, low, close, vol, turnover], ...]}, ...}
    raw = klines
    if isinstance(klines, dict):
        raw = list(reversed(klines.get("result", {}).get("list", [])))

    if not raw or len(raw) < 7:
        return False, "insufficient_data", 0.0

    try:
        closes = [float(k[4]) for k in raw[:-1]]
        highs  = [float(k[2]) for k in raw[:-1]]
        lows   = [float(k[3]) for k in raw[:-1]]

        price_max = max(highs)
        price_min = min(lows)
        price_avg = sum(closes) / len(closes)

        if price_avg == 0:
            return False, None, 0.0

        price_range = (price_max - price_min) / price_avg
        if price_range <= range_threshold:
            return True, f"price_range_7d={price_range*100:.1f}% (threshold={range_threshold*100:.0f}%)", price_range

    except Exception as e:
        logger.debug("Signal3 stability error for %s: %s", symbol, e)

    return False, None, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Signal 4 — Negative Funding Rate
# ─────────────────────────────────────────────────────────────────────────────

def detect_negative_funding(symbol: str, threshold: float = -0.0001,
                            external_rate: Optional[float] = None) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, avg_funding).
    Uses funding rate history (last 3 periods = ~24h).
    Primary: Binance. Fallback: Bybit.
    """
    avg_rate = external_rate

    if avg_rate is None:
        # Try Binance first
        history = _get(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                       {"symbol": symbol, "limit": 3})
        if history and len(history) > 0:
            try:
                rates    = [float(x["fundingRate"]) for x in history]
                avg_rate = sum(rates) / len(rates)
            except Exception as e:
                logger.debug("Signal4 Binance funding parse error for %s: %s", symbol, e)

        # Bybit fallback if Binance failed
        if avg_rate is None:
            bybit_history = _get(f"{BYBIT_API}/v5/market/funding/history",
                                 {"category": "linear", "symbol": symbol, "limit": 3})
            if bybit_history:
                try:
                    records = bybit_history.get("result", {}).get("list", [])
                    if records:
                        rates    = [float(x["fundingRate"]) for x in records]
                        avg_rate = sum(rates) / len(rates)
                        logger.debug("Signal4: Using Bybit funding rate for %s: %.6f", symbol, avg_rate)
                except Exception as e:
                    logger.debug("Signal4 Bybit funding parse error for %s: %s", symbol, e)

    if avg_rate is not None and avg_rate < threshold:
        return True, f"avg_funding_3d={avg_rate*100:.4f}% (threshold={threshold*100:.4f}%)", avg_rate

    return False, None, avg_rate or 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Signal 5 — Silence Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_silence(symbol: str, history_days: int = 7) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, hours_since_last_spike).
    Detects if volume has gone 'silent' after a period of high activity.
    Primary: Binance. Fallback: Bybit.
    """
    limit = history_days + 2

    klines = _get_first(
        (f"{BINANCE_API}/api/v3/klines",
            {"symbol": symbol, "interval": "1d", "limit": limit}),
        (f"{BINANCE_FAPI}/fapi/v1/klines",
            {"symbol": symbol, "interval": "1d", "limit": limit}),
        (f"{BYBIT_API}/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "D", "limit": limit}),
    )

    if not klines:
        return False, None, 0.0

    # Normalize Bybit format
    raw = klines
    if isinstance(klines, dict):
        raw = list(reversed(klines.get("result", {}).get("list", [])))

    if not raw or len(raw) < 4:
        return False, None, 0.0

    try:
        volumes      = [float(k[5]) for k in raw]
        prev_vols    = volumes[:-2]
        avg_vol      = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        prev_day_vol = volumes[-2]
        today_vol    = volumes[-1]

        had_spike  = prev_day_vol > avg_vol * 1.5
        now_silent = today_vol < avg_vol * 0.6

        if had_spike and now_silent:
            ratio = today_vol / (avg_vol + 1)
            return True, f"volume_silenced: prev={prev_day_vol/avg_vol:.1f}x avg, today={today_vol/avg_vol:.1f}x", ratio

    except Exception as e:
        logger.debug("Signal5 silence error for %s: %s", symbol, e)

    return False, None, 0.0
