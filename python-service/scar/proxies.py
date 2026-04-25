"""
SCAR Proxy Signals — Degraded mode implementations for signals 1 & 2.
These use Binance public REST APIs as a proxy for on-chain withdrawal data.
When BSCScan/Etherscan API keys are available, replace with scar/onchain.py.
"""
import requests
import logging
from typing import Tuple, Optional

logger = logging.getLogger("SCAR_PROXIES")

BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_API  = "https://api.binance.com"

_session = requests.Session()
_session.headers.update({"Accept": "application/json"})


def _get(url: str, params: dict = None, timeout: int = 8) -> Optional[dict]:
    try:
        r = _session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("SCAR proxy request failed [%s]: %s", url, e)
        return None


# ── Signal 1 Proxy: Whale Withdrawal Detection ─────────────────────────────
def detect_whale_withdrawal_proxy(symbol: str) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, confidence_value).
    Uses Futures/Spot volume ratio + OI accumulation as proxy for exchange withdrawal.
    Triggered when futures liquidity dominates spot (sign the spot book is drying).
    """
    base = symbol.replace("USDT", "").replace("BUSD", "").strip()

    # 1. Futures vs Spot 24h volume ratio
    try:
        fut_ticker = _get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", {"symbol": symbol})
        spot_ticker = _get(f"{BINANCE_API}/api/v3/ticker/24hr", {"symbol": symbol})

        if fut_ticker and spot_ticker:
            fut_vol_usd = float(fut_ticker.get("quoteVolume", 0))
            spot_vol_usd = float(spot_ticker.get("quoteVolume", 0))

            if spot_vol_usd > 0:
                ratio = fut_vol_usd / spot_vol_usd
                if ratio > 3.0:
                    return True, f"futures/spot_ratio={ratio:.1f}x (spot book thinning)", ratio
    except Exception as e:
        logger.debug("Signal1 vol ratio error for %s: %s", symbol, e)

    # 2. OI change (growing OI + stable price = accumulation pressure)
    try:
        oi_data = _get(f"{BINANCE_FAPI}/fapi/v1/openInterest", {"symbol": symbol})
        ticker_data = _get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", {"symbol": symbol})

        if oi_data and ticker_data:
            oi = float(oi_data.get("openInterest", 0))
            price_change_pct = abs(float(ticker_data.get("priceChangePercent", 100)))
            # High OI but price barely moved → silent accumulation
            if oi > 0 and price_change_pct < 5.0:
                # Use volume as OI proxy signal strength
                vol_usd = float(ticker_data.get("quoteVolume", 0))
                if vol_usd > 500_000:
                    return True, f"oi_accumulation: price_chg={price_change_pct:.1f}%, vol=${vol_usd/1e6:.1f}M", vol_usd
    except Exception as e:
        logger.debug("Signal1 OI error for %s: %s", symbol, e)

    return False, None, 0.0


# ── Signal 2 Proxy: Supply Drying Detection ────────────────────────────────
def detect_supply_drying_proxy(symbol: str) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, confidence_value).
    Uses order book depth analysis as proxy for supply reduction on exchanges.
    """
    try:
        depth = _get(f"{BINANCE_API}/api/v3/depth", {"symbol": symbol, "limit": 100})
        if not depth:
            return False, None, 0.0

        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        if not bids or not asks:
            return False, None, 0.0

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2.0

        # 1. Spread check (>0.5% indicates thin book)
        spread_pct = (best_ask - best_bid) / mid_price if mid_price > 0 else 0
        if spread_pct > 0.005:
            return True, f"wide_spread={spread_pct*100:.2f}%", spread_pct

        # 2. Bid-side depth ratio: vol within 2% vs vol within 10% of price
        def sum_depth(levels, max_pct: float) -> float:
            total = 0.0
            for price_str, qty_str in levels:
                price = float(price_str)
                qty   = float(qty_str)
                if abs(price - mid_price) / mid_price <= max_pct:
                    total += price * qty
            return total

        near_vol  = sum_depth(bids, 0.02)   # within 2%
        total_vol = sum_depth(bids, 0.10)   # within 10%

        if total_vol > 0:
            ratio = near_vol / total_vol
            if ratio < 0.15:  # Less than 15% liquidity is near the market
                return True, f"thin_near_book: {ratio*100:.1f}% of depth within 2%", ratio

    except Exception as e:
        logger.debug("Signal2 depth error for %s: %s", symbol, e)

    return False, None, 0.0


# ── Signal 3: Price Stability Check ────────────────────────────────────────
def detect_price_stable(symbol: str, range_threshold: float = 0.15) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, range_value).
    Checks if price has been in ±15% range for 7+ days using Binance klines.
    """
    try:
        klines = _get(
            f"{BINANCE_API}/api/v3/klines",
            {"symbol": symbol, "interval": "1d", "limit": 8}
        )
        if not klines or len(klines) < 7:
            # Fallback: try futures endpoint
            klines = _get(
                f"{BINANCE_FAPI}/fapi/v1/klines",
                {"symbol": symbol, "interval": "1d", "limit": 8}
            )

        if not klines or len(klines) < 7:
            return False, "insufficient_data", 0.0

        closes = [float(k[4]) for k in klines[:-1]]  # last 7 days (exclude today)
        highs  = [float(k[2]) for k in klines[:-1]]
        lows   = [float(k[3]) for k in klines[:-1]]

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


# ── Signal 4: Negative Funding Rate ────────────────────────────────────────
def detect_negative_funding(symbol: str, threshold: float = -0.0001,
                            external_rate: Optional[float] = None) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, avg_funding).
    Uses Binance Futures funding rate history (last 3 periods = ~24h).
    Can accept an externally provided rate to avoid duplicate API calls.
    """
    avg_rate = external_rate

    if avg_rate is None:
        try:
            history = _get(
                f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                {"symbol": symbol, "limit": 3}
            )
            if history and len(history) > 0:
                rates = [float(x["fundingRate"]) for x in history]
                avg_rate = sum(rates) / len(rates)
        except Exception as e:
            logger.debug("Signal4 funding error for %s: %s", symbol, e)
            return False, None, 0.0

    if avg_rate is not None and avg_rate < threshold:
        return True, f"avg_funding_3d={avg_rate*100:.4f}% (threshold={threshold*100:.4f}%)", avg_rate

    return False, None, avg_rate or 0.0


# ── Signal 5: Silence Detection (no large moves for 24-48h after activity) ─
def detect_silence(symbol: str, history_days: int = 7) -> Tuple[bool, Optional[str], float]:
    """
    Returns (triggered, reason, hours_since_last_spike).
    Detects if volume has gone 'silent' after a period of high activity.
    Proxy: volume dropped below 50% of previous 7-day average in last 24h.
    """
    try:
        klines = _get(
            f"{BINANCE_API}/api/v3/klines",
            {"symbol": symbol, "interval": "1d", "limit": history_days + 2}
        )
        if not klines or len(klines) < 4:
            klines = _get(
                f"{BINANCE_FAPI}/fapi/v1/klines",
                {"symbol": symbol, "interval": "1d", "limit": history_days + 2}
            )

        if not klines or len(klines) < 4:
            return False, None, 0.0

        volumes = [float(k[5]) for k in klines]
        # Previous days (excluding today and last day)
        prev_vols = volumes[:-2]
        avg_vol   = sum(prev_vols) / len(prev_vols) if prev_vols else 0

        # Was there a spike in the previous session?
        prev_day_vol = volumes[-2]
        today_vol    = volumes[-1]

        had_spike = prev_day_vol > avg_vol * 1.5
        now_silent = today_vol < avg_vol * 0.6

        if had_spike and now_silent:
            return True, f"volume_silenced: prev={prev_day_vol/avg_vol:.1f}x avg, today={today_vol/avg_vol:.1f}x", today_vol / (avg_vol + 1)

    except Exception as e:
        logger.debug("Signal5 silence error for %s: %s", symbol, e)

    return False, None, 0.0
