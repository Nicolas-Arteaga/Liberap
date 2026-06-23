import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .schemas import Strike15mRequest, Strike15mResponse, Strike15mItem
import logging

logger = logging.getLogger("STRIKE15M")


class Strike15mAnalyzer:
    """STRIKE 15m Analyzer - Detects high-power ignition candles on MA99"""
    
    def __init__(self):
        self.timeout = 5  # seconds for API requests
    
    def analyze(self, req: Strike15mRequest) -> Strike15mResponse:
        """
        Scan multiple symbols for STRIKE 15m patterns.
        Returns top 5 coins with highest force scores meeting MA99 proximity criteria.
        """
        logger.info(f"[STRIKE15m] Scanning {len(req.symbols)} symbols concurrently...")
        
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
                        logger.info(f"[STRIKE15m] {symbol}: Score={item.force_score:.1f}/10, MA99 Dist={item.ma99_distance_pct:.2f}%")
                except Exception as e:
                    logger.warning(f"[STRIKE15m] Error analyzing {symbol}: {e}")
        
        # Sort by force score (descending) and take top 5
        qualified_items.sort(key=lambda x: x.force_score, reverse=True)
        top_5 = qualified_items[:5]
        
        logger.info(f"[STRIKE15m] Scan complete: {len(qualified_items)} qualified, top 5 returned")
        
        return Strike15mResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _analyze_symbol(self, symbol: str) -> Optional[Strike15mItem]:
        """
        Analyze a single symbol for STRIKE 15m pattern.
        Returns Strike15mItem if criteria met, None otherwise.
        """
        # Fetch 15m klines (need at least 120 candles for MA99 and ATR calculations)
        candles = self._fetch_15m_klines(symbol, limit=150)
        if not candles or len(candles) < 120:
            logger.info(f"[STRIKE15m] {symbol}: Insufficient candles ({len(candles) if candles else 0})")
            return None
        
        df = pd.DataFrame(candles)
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Calculate MA99 (Exponential Moving Average)
        df['ma99'] = df['close'].ewm(span=99, adjust=False).mean()
        
        # Calculate ATR 20 (Average True Range)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift())
        df['tr3'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr_20'] = df['tr'].rolling(window=20).mean()
        
        # Get current (latest) candle data
        current = df.iloc[-1]
        ma99_value = current['ma99']
        atr_20 = current['atr_20']
        
        if pd.isna(ma99_value) or pd.isna(atr_20) or atr_20 == 0:
            return None
        
        current_price = current['close']
        candle_open = current['open']
        volume_15m = current['volume']
        
        # Calculate Force Score (Ley de Nico)
        # Cuerpo_Actual = Abs(Precio_Actual - Apertura_Vela_15m)
        # Score_Fuerza = (Cuerpo_Actual / ATR_20_15m) * 3.33
        cuerpo_actual = abs(current_price - candle_open)
        force_score = (cuerpo_actual / atr_20) * 3.33
        
        # Calculate MA99 distance percentage
        # Distance between MA99 and price (or candle open) must be <= 1.0%
        dist_price = (abs(current_price - ma99_value) / ma99_value) * 100
        dist_open = (abs(candle_open - ma99_value) / ma99_value) * 100
        ma99_distance_pct = min(dist_price, dist_open)
        
        # Filter: MA99 distance must be <= 1.0%
        if ma99_distance_pct > 1.0:
            logger.info(f"[STRIKE15m] {symbol}: MA99 distance too high ({ma99_distance_pct:.2f}% > 1.0%)")
            return None
        
        # Check for perfect shot (Score 10/10 and 0% MA99 distance)
        is_perfect_shot = (force_score >= 10.0) and (ma99_distance_pct < 0.1)
        
        return Strike15mItem(
            symbol=symbol,
            force_score=min(10.0, force_score),  # Cap at 10.0
            ma99_distance_pct=ma99_distance_pct,
            volume_15m=volume_15m,
            current_price=current_price,
            ma99_value=ma99_value,
            candle_open=candle_open,
            atr_20_15m=atr_20,
            is_perfect_shot=is_perfect_shot
        )
    
    def _fetch_15m_klines(self, symbol: str, limit: int = 150) -> Optional[List[List]]:
        """
        Fetch 15m klines from Binance Futures API.
        Returns list of [timestamp, open, high, low, close, volume] or None on error.
        """
        # Clean symbol format
        clean_symbol = symbol.replace('/', '').replace('-', '').upper()
        
        # Try Binance Futures first
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={clean_symbol}&interval=15m&limit={limit}"
        
        try:
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                # Return only the columns we need: timestamp, open, high, low, close, volume
                return [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
        except Exception as e:
            logger.info(f"[STRIKE15m] Binance Futures failed for {symbol}: {e}")
        
        # Fallback to Binance Spot
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}&interval=15m&limit={limit}"
        try:
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
        except Exception as e:
            logger.info(f"[STRIKE15m] Binance Spot failed for {symbol}: {e}")
        
        return None
