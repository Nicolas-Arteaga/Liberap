import requests
import logging
import config
from typing import Dict, Any, Optional

logger = logging.getLogger("SignalEngine")

class SignalEngine:
    """
    Connects to the VERGE Python Service (Nexus-15 & SCAR).
    Calculates the Confluence Score based on both AI modules.
    """
    def __init__(self, binance_fetcher):
        self.base_url = config.PYTHON_SERVICE_URL
        self.fetcher = binance_fetcher

    def get_scar_alerts(self) -> dict:
        """
        Fetches active SCAR alerts directly from the Python service.
        Note: We use the cached alerts from DB via GET /scar/alerts to avoid 
        spamming Binance on every loop, since SCAR events develop over hours/days.
        """
        url = f"{self.base_url}/scar/alerts"
        try:
            response = requests.get(url, params={"threshold": config.MIN_SCAR_SCORE}, timeout=5)
            if response.status_code == 200:
                alerts = response.json()
                # Return dictionary for O(1) lookups: { "BTCUSDT": scar_data }
                return {a["symbol"]: a for a in alerts}
        except Exception as e:
            logger.error(f"Error fetching SCAR alerts: {e}")
        return {}

    def get_nexus15_prediction(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest Nexus-15 prediction by gathering 15m klines from Binance 
        and passing them to the local Python AI service.
        """
        klines = self.fetcher.get_klines_for_nexus(symbol)
        if not klines or len(klines) < 25:
            logger.warning(f"Not enough klines to analyze {symbol} with Nexus-15.")
            return None

        url = f"{self.base_url}/nexus15/analyze"
        payload = {
            "symbol": symbol,
            "timeframe": "15m",
            "candles": klines
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Nexus-15 error for {symbol}: {response.text}")
        except Exception as e:
            logger.error(f"Connection error to Nexus-15 for {symbol}: {e}")
            
        return None

    def calculate_confluence(self, symbol: str, scar_data: dict, nexus_data: dict) -> dict:
        """
        Calculates the confluence score between SCAR (Whale Extraction) and Nexus-15 (Price Action).
        Returns a dict with the decision metrics.
        """
        score = 0.0
        scar_score = scar_data.get("score_grial", 0) if scar_data else 0
        nexus_confidence = nexus_data.get("ai_confidence", 0) if nexus_data else 0
        nexus_direction = nexus_data.get("direction", "NEUTRAL") if nexus_data else "NEUTRAL"
        
        # 1. SCAR Contribution (max 50 points)
        if scar_data:
            score += scar_score * 10  
            
        # 2. Nexus-15 Contribution (max 50 points)
        if nexus_data:
            score += nexus_confidence * 0.5 
            
        # 3. Penalties & Alignments
        # SCAR is inherently Bullish (Whales extracting supply to pump)
        if scar_score >= 4:
            if nexus_direction == "BEARISH":
                # Contradiction: SCAR sees whale pump, but price action is strictly bearish
                score *= 0.5
                logger.info(f"[{symbol}] Confluence penalty: SCAR Bullish vs Nexus Bearish")
            elif nexus_direction == "BULLISH":
                # Strong alignment
                score += 10
                
        # Cap at 100
        score = min(100.0, score)
        
        # 4. Standalone Boosts
        # If Nexus is highly confident on its own, it overrides low confluence
        if nexus_confidence >= config.MIN_NEXUS_CONFIDENCE:
            score = max(score, config.MIN_CONFLUENCE_SCORE)
            logger.info(f"[{symbol}] Standalone Nexus-15 signal triggered (Confidence: {nexus_confidence}%)")
            
        # Determine Trade Direction based on Nexus-15 (or default to Long if SCAR dominates)
        trade_direction = nexus_direction
        if trade_direction == "NEUTRAL" and scar_score >= 4:
            trade_direction = "BULLISH" # SCAR default bias

        # Side for ABP SimulatedTrade (0=Long, 1=Short)
        side = 0 if trade_direction == "BULLISH" else 1

        result = {
            "symbol": symbol,
            "confluence_score": round(score, 2),
            "trade_direction": trade_direction,
            "side": side,
            "scar_score": scar_score,
            "nexus_confidence": nexus_confidence,
            "nexus_direction": nexus_direction,
            "estimated_range_pct": nexus_data.get("estimated_range_percent", 2.0) if nexus_data else 2.0
        }
        
        return result
