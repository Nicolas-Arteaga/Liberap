import config
import logging
from typing import Dict, Any

logger = logging.getLogger("RiskManager")

class RiskManager:
    """
    Handles position sizing and Take Profit / Stop Loss calculations.
    """
    
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def calculate_position(self, symbol: str, signal_data: dict, available_balance: float = None) -> Dict[str, Any]:
        """
        Calculates the margin (capital to risk) and dynamic TP/SL levels.
        """
        # 1. Determine Margin (Cost)
        balance = available_balance if available_balance is not None else config.VIRTUAL_CAPITAL_BASE
        margin = balance * config.RISK_PER_TRADE_PCT
        
        # 2. Get Current Price
        entry_price = self.fetcher.get_current_price(symbol)
        if entry_price <= 0:
            logger.error(f"Cannot calculate position for {symbol}, invalid entry price: {entry_price}")
            return None
            
        # 3. Calculate TP and SL based on ATR (Estimated Range from Nexus-15)
        # estimated_range_pct is returned as a percentage (e.g., 2.5 means 2.5%)
        range_pct = signal_data.get("estimated_range_pct", 2.0) / 100.0
        
        tp_distance = range_pct * config.TP_MULTIPLIER
        sl_distance = range_pct * config.SL_MULTIPLIER
        
        side = signal_data.get("side") # 0 = Long, 1 = Short
        
        if side == 0: # LONG
            tp_price = entry_price * (1 + tp_distance)
            sl_price = entry_price * (1 - sl_distance)
        else: # SHORT
            tp_price = entry_price * (1 - tp_distance)
            sl_price = entry_price * (1 + sl_distance)
            
        result = {
            "symbol": symbol,
            "side": side,
            "margin": round(margin, 2),
            "leverage": config.DEFAULT_LEVERAGE,
            "entry_price": entry_price,
            "tp_price": round(tp_price, 4),
            "sl_price": round(sl_price, 4),
            "range_pct_used": round(range_pct * 100, 2)
        }
        
        return result
