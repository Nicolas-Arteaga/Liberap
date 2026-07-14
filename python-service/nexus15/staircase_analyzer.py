import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .schemas import StaircaseRequest, StaircaseResponse, StaircaseItem
from shared_kline_cache import get_or_fetch
import logging

logger = logging.getLogger("ROLLERCOASTER")


class StaircaseAnalyzer:
    """ROLLERCOASTER v17.0 - High-Beta Swings Scanner (Maximum Daily Volatility with Directional Bias)"""
    
    def __init__(self):
        self.timeout = 5  # seconds for API requests
    
    def analyze(self, req: StaircaseRequest) -> StaircaseResponse:
        """
        Scan multiple symbols for ROLLERCOASTER patterns (high-beta swings).
        Returns top 5 coins with highest ADR-10 meeting directional bias criteria.
        """
        logger.info(f"[ROLLERCOASTER] Scanning {len(req.symbols)} symbols for high-beta swings (ADR-10 ≥ 8%)...")
        
        qualified_items = []
        
        # Use ThreadPoolExecutor to fetch and analyze symbols concurrently
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_to_symbol = {executor.submit(self._analyze_symbol, symbol): symbol for symbol in req.symbols}
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    item = future.result()
                    if item:
                        qualified_items.append(item)
                        logger.info(f"[ROLLERCOASTER] {symbol}: ADR-10={item.order_score:.1f}%, Trend={item.trend_1d}")
                except Exception as e:
                    logger.warning(f"[ROLLERCOASTER] Error analyzing {symbol}: {e}")
        
        # Sort by ADR-10 (descending) - highest volatility first
        qualified_items.sort(key=lambda x: x.order_score, reverse=True)
        top_5 = qualified_items[:5]
        
        logger.info(f"[ROLLERCOASTER] Scan complete: {len(qualified_items)} qualified, top 5 returned")
        
        return StaircaseResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _analyze_symbol(self, symbol: str) -> Optional[StaircaseItem]:
        """
        Analyze a single symbol for ROLLERCOASTER pattern.
        Returns StaircaseItem if criteria met, None otherwise.
        """
        # Step 1: Fetch 1D timeframe for ADR-10 calculation
        candles_1d = self._fetch_klines(symbol, interval='1d', limit=20)
        if not candles_1d or len(candles_1d) < 10:
            logger.info(f"[ROLLERCOASTER] {symbol}: Insufficient 1D candles ({len(candles_1d) if candles_1d else 0})")
            return None
        
        df_1d = pd.DataFrame(candles_1d)
        df_1d.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Step 2: Calculate ADR-10 (Average Daily Range of last 10 days)
        last_10_days = df_1d.tail(10)
        
        # Calculate daily range percentage for each day
        daily_ranges = []
        for idx, row in last_10_days.iterrows():
            range_pct = (row['high'] - row['low']) / row['low'] * 100
            daily_ranges.append(range_pct)
        
        adr_10 = np.mean(daily_ranges)
        
        # Filter: Require minimum 8% average daily volatility
        if adr_10 < 8.0:
            logger.info(f"[ROLLERCOASTER] {symbol}: ADR-10 too low ({adr_10:.1f}% < 8%)")
            return None
        
        # Step 3: Verify Directional Bias (Sesgo Macro)
        current_close = df_1d['close'].iloc[-1]
        close_10_days_ago = df_1d['close'].iloc[-10]
        
        # Calculate EMAs for directional check
        df_1d['ema20'] = df_1d['close'].ewm(span=20, adjust=False).mean()
        df_1d['ema50'] = df_1d['close'].ewm(span=50, adjust=False).mean()
        
        latest_ema20 = df_1d['ema20'].iloc[-1]
        latest_ema50 = df_1d['ema50'].iloc[-1]
        
        # Check Bullish Bias: +10% price change OR EMA20 > EMA50
        price_change_pct = (current_close - close_10_days_ago) / close_10_days_ago * 100
        is_bullish_bias = (price_change_pct >= 10.0) or (latest_ema20 > latest_ema50)
        
        # Check Bearish Bias: -10% price change OR EMA20 < EMA50
        is_bearish_bias = (price_change_pct <= -10.0) or (latest_ema20 < latest_ema50)
        
        if not (is_bullish_bias or is_bearish_bias):
            logger.info(f"[ROLLERCOASTER] {symbol}: No directional bias (price_change={price_change_pct:.1f}%)")
            return None
        
        trend_1d = "Bullish" if is_bullish_bias else "Bearish"
        
        # Step 4: Fetch 15m for current price and EMAs (for execution trigger)
        candles_15m = self._fetch_klines(symbol, interval='15m', limit=50)
        if not candles_15m or len(candles_15m) < 25:
            logger.info(f"[ROLLERCOASTER] {symbol}: Insufficient 15m candles ({len(candles_15m) if candles_15m else 0})")
            return None
        
        df_15m = pd.DataFrame(candles_15m)
        df_15m.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Calculate EMAs for 15m (for execution trigger)
        df_15m['ema25'] = df_15m['close'].ewm(span=25, adjust=False).mean()
        df_15m['ema50'] = df_15m['close'].ewm(span=50, adjust=False).mean()
        
        latest_15m = df_15m.iloc[-1]
        current_price = latest_15m['close']
        ema25_value = latest_15m['ema25']
        ema50_value = latest_15m['ema50']
        
        # Determine phase based on 15m price action
        phase = self._determine_phase(df_15m, trend_1d)
        
        # Detect if price is near EMA25/50 (execution trigger zone)
        impulse_detected = self._is_near_ema_trigger(current_price, ema25_value, ema50_value)
        
        return StaircaseItem(
            symbol=symbol,
            order_score=adr_10,  # Using ADR-10 as the score
            trend_1d=trend_1d,
            phase=phase,
            current_price=current_price,
            ema7_value=0,  # Not used in ROLLERCOASTER
            ema25_value=ema25_value,
            impulse_detected=impulse_detected
        )
    
    def _determine_phase(self, df: pd.DataFrame, trend: str) -> str:
        """
        Determine current phase based on 15m price action.
        """
        last_5 = df.tail(5)
        price_range_pct = (last_5['high'].max() - last_5['low'].min()) / last_5['close'].iloc[-1] * 100
        
        if price_range_pct < 1.5:
            return "Rest"
        elif price_range_pct < 3.0:
            return "Consolidation"
        else:
            return "Impulse"
    
    def _is_near_ema_trigger(self, price: float, ema25: float, ema50: float) -> bool:
        """
        Check if price is near EMA25 or EMA50 (within 1.5%) for execution trigger.
        """
        dist_ema25 = abs(price - ema25) / price * 100
        dist_ema50 = abs(price - ema50) / price * 100
        
        return dist_ema25 < 1.5 or dist_ema50 < 1.5
    
    def _fetch_klines(self, symbol: str, interval: str = '15m', limit: int = 150) -> Optional[List[List]]:
        """
        Fetch klines from Binance Futures API.
        Returns list of [timestamp, open, high, low, close, volume] or None on error.
        """
        clean_symbol = symbol.replace('/', '').replace('-', '').upper()

        def _do_fetch():
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={clean_symbol}&interval={interval}&limit={limit}"
            try:
                response = requests.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    return [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
            except Exception as e:
                logger.info(f"[STAIRCASE] Binance Futures failed for {symbol}: {e}")

            url = f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}&interval={interval}&limit={limit}"
            try:
                response = requests.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    return [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
            except Exception as e:
                logger.info(f"[STAIRCASE] Binance Spot failed for {symbol}: {e}")

            return None

        return get_or_fetch(clean_symbol, interval, limit, _do_fetch)
