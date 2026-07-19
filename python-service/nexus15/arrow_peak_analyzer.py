import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .schemas import ArrowPeakRequest, ArrowPeakResponse, ArrowPeakItem
from shared_kline_cache import get_or_fetch
import logging

logger = logging.getLogger("ARROW_PEAK")


class ArrowPeakAnalyzer:
    """ARROW PEAK v18.1 - Exhaustion Reversal Scanner (Fuzzy Bleeding + Debug Logging)"""
    
    # TOP 10 volume symbols for debug logging
    TOP_VOLUME_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
                         'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'TRXUSDT', 'LINKUSDT']
    
    def __init__(self):
        self.timeout = 5  # seconds for API requests
        self.rejection_log = {}  # Store rejection reasons for TOP 10
    
    def analyze(self, req: ArrowPeakRequest) -> ArrowPeakResponse:
        """
        Scan multiple symbols for ARROW PEAK patterns (exhaustion reversals).
        Returns top 5 coins organized by days of bleeding (1-7 days).
        v18.1: Fuzzy bleeding logic + rejection debug logging.
        """
        logger.info(f"[ARROW PEAK v18.1] Scanning {len(req.symbols)} symbols for exhaustion reversals...")
        
        qualified_items = []
        self.rejection_log = {}
        
        # Use ThreadPoolExecutor to fetch and analyze symbols concurrently
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_to_symbol = {executor.submit(self._analyze_symbol, symbol): symbol for symbol in req.symbols}
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    item = future.result()
                    if item:
                        qualified_items.append(item)
                        logger.info(f"[ARROW PEAK] {symbol}: {item.days_bleeding} days bleeding, prev_rise={item.prev_rise_pct:.1f}%")
                except Exception as e:
                    logger.warning(f"[ARROW PEAK] Error analyzing {symbol}: {e}")
        
        # Print rejection debug for TOP 10 volume symbols
        self._print_rejection_debug()
        
        # Group by days of bleeding and select best for each slot (1-7)
        top_5 = self._select_top_5_by_bleeding_days(qualified_items)
        
        logger.info(f"[ARROW PEAK] Scan complete: {len(qualified_items)} qualified, top 5 returned")
        
        return ArrowPeakResponse(
            top_5=top_5,
            scanned_count=len(req.symbols),
            analyzed_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _select_top_5_by_bleeding_days(self, items: List[ArrowPeakItem]) -> List[ArrowPeakItem]:
        """
        Select the best candidate for each bleeding day slot (1-3).
        Within each slot, prioritize by previous rise magnitude.
        Returns top 10 overall.
        """
        # Group by days of bleeding
        slots = {1: [], 2: [], 3: []}
        
        for item in items:
            if item.days_bleeding in slots:
                slots[item.days_bleeding].append(item)
        
        # For each slot, select the items with highest previous rise
        candidates = []
        for day in range(1, 4):
            if slots[day]:
                # Sort by previous rise (descending)
                slots[day].sort(key=lambda x: x.prev_rise_pct, reverse=True)
                # Take up to 4 candidates per slot to populate the top 10 list
                candidates.extend(slots[day][:4])
        
        # Return top 10 overall by previous rise (prioritize bigger pumps)
        candidates.sort(key=lambda x: x.prev_rise_pct, reverse=True)
        return candidates[:10]
    
    def _print_rejection_debug(self):
        """Print rejection reasons for TOP 10 volume symbols."""
        if not self.rejection_log:
            return
        
        logger.info("[DEBUG-PEAK] TOP 10 Volume Symbols Rejection Reasons:")
        for symbol, reason in self.rejection_log.items():
            logger.info(f"[DEBUG-PEAK] {symbol}: {reason}")
    
    def _analyze_symbol(self, symbol: str) -> Optional[ArrowPeakItem]:
        """
        Analyze a single symbol for ARROW PEAK pattern.
        Returns ArrowPeakItem if criteria met, None otherwise.
        """
        # Step 1: Fetch 1D timeframe for arrow pattern detection
        candles_1d = self._fetch_klines(symbol, interval='1d', limit=30)
        if not candles_1d or len(candles_1d) < 15:
            logger.info(f"[ARROW PEAK] {symbol}: Insufficient 1D candles ({len(candles_1d) if candles_1d else 0})")
            return None

        # Bug real encontrado 2026-07-19 (causó una pérdida real en BULLAUSDT):
        # Binance devuelve la vela diaria de HOY como último elemento aunque
        # todavía no cerró — se estaba contando como "día de sangrado
        # confirmado" un día parcial que más tarde, al cerrar completo,
        # terminó siendo VERDE (revirtió la caída de la mañana). Se descarta
        # acá la última vela si todavía no pasaron 24h desde que abrió.
        import time as _time
        now_ms = int(_time.time() * 1000)
        last_open_ms = int(candles_1d[-1][0])
        if last_open_ms + 24 * 3600 * 1000 > now_ms:
            candles_1d = candles_1d[:-1]
        if len(candles_1d) < 15:
            logger.info(f"[ARROW PEAK] {symbol}: Insufficient CLOSED 1D candles after descartar el día en formación")
            return None

        df_1d = pd.DataFrame(candles_1d)
        # Binance returns 12 fields, we only need first 6
        df_1d = df_1d.iloc[:, :6]
        df_1d.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        # Convert string columns to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df_1d[col] = pd.to_numeric(df_1d[col], errors='coerce')
        
        # Step 2: Identify the peak (highest point in last 10 days)
        last_10_days = df_1d.tail(10)
        peak_idx = last_10_days['high'].idxmax()
        peak_row = df_1d.loc[peak_idx]
        peak_price = peak_row['high']
        
        # Step 3: Check for a clean green arrow pump (3-5 consecutive green days with >= 20% rise)
        df_before_peak = df_1d.loc[:peak_idx]
        n_before = len(df_before_peak)
        
        is_clean_arrow = False
        prev_rise_pct = 0.0
        arrow_start_price = 0.0

        # Check sequences ending at peak (index -1) or the day before (index -2)
        for end_pos in [n_before, n_before - 1]:
            if is_clean_arrow:
                break
            for length in [5, 4, 3]:
                start_pos = end_pos - length
                if start_pos < 0:
                    continue
                sub_df = df_before_peak.iloc[start_pos:end_pos]
                # Check if all candles in this sub-sequence are green (close > open)
                if all(sub_df['close'] > sub_df['open']):
                    # Calculate rise from open of first candle to peak price
                    first_open = sub_df.iloc[0]['open']
                    rise_pct = (peak_price - first_open) / first_open * 100
                    if rise_pct >= 20.0:
                        is_clean_arrow = True
                        prev_rise_pct = rise_pct
                        arrow_start_price = float(first_open)
                        break
        
        if not is_clean_arrow:
            reason = "No clean 3-5 day green pump of >= 20%"
            logger.info(f"[ARROW PEAK] {symbol}: {reason}")
            self._log_rejection(symbol, reason)
            return None
        
        # Step 4: STRICT RED BLEEDING - All candles after peak must be red (close < open)
        peak_pos = df_1d.index.get_loc(peak_idx)
        candles_after_peak = df_1d.iloc[peak_pos+1:]
        
        if len(candles_after_peak) < 1:
            reason = "No candles after peak"
            logger.info(f"[ARROW PEAK] {symbol}: {reason}")
            self._log_rejection(symbol, reason)
            return None
        
        # Ensure all candles after peak are red
        if not all(candles_after_peak['close'] < candles_after_peak['open']):
            reason = "Not all candles after peak are red (must be consecutive red)"
            logger.info(f"[ARROW PEAK] {symbol}: {reason}")
            self._log_rejection(symbol, reason)
            return None
        
        bleeding_days = len(candles_after_peak)
        
        # Filter: Must have 1-3 bleeding days
        if bleeding_days < 1 or bleeding_days > 3:
            reason = f"Bleeding days={bleeding_days} (must be 1-3)"
            logger.info(f"[ARROW PEAK] {symbol}: {reason}")
            self._log_rejection(symbol, reason)
            return None
        
        # Step 5: Fetch 15m for MA99 distance (execution trigger)
        candles_15m = self._fetch_klines(symbol, interval='15m', limit=100)
        if not candles_15m or len(candles_15m) < 99:
            logger.info(f"[ARROW PEAK] {symbol}: Insufficient 15m candles ({len(candles_15m) if candles_15m else 0})")
            return None
        
        df_15m = pd.DataFrame(candles_15m)
        # Binance returns 12 fields, we only need first 6
        df_15m = df_15m.iloc[:, :6]
        df_15m.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        # Convert string columns to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df_15m[col] = pd.to_numeric(df_15m[col], errors='coerce')
        
        # Calculate MA99 for 15m
        df_15m['ma99'] = df_15m['close'].ewm(span=99, adjust=False).mean()
        
        latest_15m = df_15m.iloc[-1]
        current_price = latest_15m['close']
        ma99_value = latest_15m['ma99']
        
        # Calculate distance to MA99 (percentage)
        dist_ma99_pct = (current_price - ma99_value) / ma99_value * 100
        
        # 15m trigger check: Price touches MA99 + current red candle > previous green candle
        prev_15m = df_15m.iloc[-2]
        is_red_candle = latest_15m['close'] < latest_15m['open']
        prev_was_green = prev_15m['close'] > prev_15m['open']
        red_bigger_than_prev_green = is_red_candle and prev_was_green and \
                                     abs(latest_15m['close'] - latest_15m['open']) > abs(prev_15m['close'] - prev_15m['open'])
        
        touches_ma99 = abs(dist_ma99_pct) < 0.5  # Within 0.5% of MA99
        
        trigger_signal = touches_ma99 and red_bigger_than_prev_green
        
        return ArrowPeakItem(
            symbol=symbol,
            prev_rise_pct=prev_rise_pct,
            days_bleeding=bleeding_days,
            current_price=current_price,
            peak_price=peak_price,
            arrow_start_price=arrow_start_price,
            dist_ma99_pct=dist_ma99_pct,
            trigger_signal=trigger_signal
        )
    
    def _log_rejection(self, symbol: str, reason: str):
        """Log rejection reason for TOP 10 volume symbols."""
        if symbol in self.TOP_VOLUME_SYMBOLS:
            self.rejection_log[symbol] = reason
    
    def _fetch_klines(self, symbol: str, interval: str = '15m', limit: int = 150) -> Optional[List[List]]:
        """
        Fetch klines from Binance Futures API.
        Returns list of [timestamp, open, high, low, close, volume] or None on error.
        """
        clean_symbol = symbol.replace('/', '').replace('-', '').upper()

        def _do_fetch():
            try:
                url = f"https://fapi.binance.com/fapi/v1/klines"
                params = {
                    'symbol': clean_symbol,
                    'interval': interval,
                    'limit': limit
                }
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"[ARROW PEAK] Failed to fetch {symbol} from Binance Futures: {e}")

                try:
                    url = f"https://api.binance.com/api/v3/klines"
                    params = {
                        'symbol': clean_symbol,
                        'interval': interval,
                        'limit': limit
                    }
                    response = requests.get(url, params=params, timeout=self.timeout)
                    response.raise_for_status()
                    return response.json()
                except Exception as e2:
                    logger.error(f"[ARROW PEAK] Failed to fetch {symbol} from Binance Spot: {e2}")
                    return None

        return get_or_fetch(clean_symbol, interval, limit, _do_fetch)
