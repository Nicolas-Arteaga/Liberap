import time
import logging
import sys
import config
from datetime import datetime

from auth_manager import AuthManager
from binance_fetcher import BinanceFetcher
from state_manager import StateManager
from signal_engine import SignalEngine
from risk_manager import RiskManager
from position_manager import PositionManager
from report_engine import ReportEngine

# ---------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VergeAgent")

class VergeAgent:
    """
    Main loop for the VERGE Autonomous Trading Agent.
    Orchestrates the components to analyze markets, make decisions, and manage positions.
    """
    def __init__(self):
        logger.info("Initializing VERGE Agent v2.0...")
        self.auth = AuthManager()
        self.fetcher = BinanceFetcher()
        self.state = StateManager()
        self.signals = SignalEngine(self.fetcher)
        self.risk = RiskManager(self.fetcher)
        self.positions = PositionManager(self.auth)
        self.report = ReportEngine()

    def run(self):
        logger.info(f"Agent started. Loop interval: {config.LOOP_INTERVAL_SECONDS} seconds.")
        
        # Test Auth before starting
        if not self.auth.get_token():
            logger.error("FATAL: Could not authenticate with ABP Backend. Stopping agent.")
            return

        while True:
            try:
                self.loop_cycle()
            except Exception as e:
                logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)
                
            logger.info(f"Sleeping for {config.LOOP_INTERVAL_SECONDS} seconds...")
            time.sleep(config.LOOP_INTERVAL_SECONDS)

    def loop_cycle(self):
        logger.info("--- Starting new analysis cycle ---")
        
        # [1] Monitor and manage open positions
        self._manage_open_positions()
        
        # Check if we can open new trades
        open_count = self.state.get_position_count()
        if open_count >= config.MAX_OPEN_POSITIONS:
            logger.info(f"Max open positions reached ({open_count}). Skipping new signals.")
            return
            
        if not self.state.can_trade_today():
            logger.info("Max daily trades limit reached. Skipping new signals.")
            return

        # [2] Gather Signals
        logger.info("Fetching SCAR active alerts...")
        scar_alerts = self.signals.get_scar_alerts()
        
        candidates = []
        
        logger.info("Scanning watchlist with Nexus-15...")
        for symbol in config.WATCHLIST:
            # Anti-churn: skip if already traded today
            if self.state.has_traded_symbol_today(symbol):
                continue
                
            # Skip if we already have an open position for this symbol
            if any(p.get("symbol") == symbol for p in self.state.get_open_positions()):
                continue

            nexus_data = self.signals.get_nexus15_prediction(symbol)
            scar_data = scar_alerts.get(symbol, {})
            
            # [3] Confluence Score
            confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data)
            
            if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                candidates.append(confluence)

        if not candidates:
            logger.info("No candidates met the minimum confluence score.")
            return

        # Sort candidates by confluence score descending
        candidates.sort(key=lambda x: x["confluence_score"], reverse=True)
        top_candidate = candidates[0]
        
        logger.info(f"Top candidate selected: {top_candidate['symbol']} with score {top_candidate['confluence_score']}")

        # [4] Risk Validation and Execution
        self._execute_trade(top_candidate)

    def _execute_trade(self, candidate: dict):
        symbol = candidate["symbol"]
        
        balance = self.positions.get_virtual_balance()
        pos_details = self.risk.calculate_position(symbol, candidate, available_balance=balance)
        
        if not pos_details:
            return
            
        logger.info(f"Attempting to open {candidate['trade_direction']} on {symbol}. Margin: {pos_details['margin']}")
        
        # [5] Open Trade via ABP
        trade_result = self.positions.open_trade(pos_details)
        
        if trade_result:
            trade_id = trade_result.get("id")
            
            # Save to local state for monitoring
            local_pos = {
                "trade_id": trade_id,
                "symbol": symbol,
                "opened_at": datetime.utcnow().isoformat(),
                # Merge metrics for reporting later
                **candidate,
                **pos_details
            }
            
            self.state.add_position(local_pos)
            self.state.record_trade_action(symbol)
            self.report.log_trade_opened(local_pos)

    def _manage_open_positions(self):
        """
        Iterates over local open positions, checks their current price,
        and triggers close if TP, SL, or timeout is reached.
        """
        positions = self.state.get_open_positions()
        if not positions:
            return
            
        logger.info(f"Monitoring {len(positions)} open positions...")
        
        for pos in positions:
            symbol = pos["symbol"]
            trade_id = pos["trade_id"]
            side = pos["side"] # 0 = Long, 1 = Short
            tp = pos["tp_price"]
            sl = pos["sl_price"]
            
            current_price = self.fetcher.get_current_price(symbol)
            if current_price <= 0:
                continue
                
            should_close = False
            close_reason = ""
            
            # Check TP/SL
            if side == 0: # LONG
                if current_price >= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price <= sl:
                    should_close, close_reason = True, "Stop Loss reached"
            else: # SHORT
                if current_price <= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price >= sl:
                    should_close, close_reason = True, "Stop Loss reached"
                    
            # Check Max Duration
            opened_at = datetime.fromisoformat(pos["opened_at"])
            hours_open = (datetime.utcnow() - opened_at).total_seconds() / 3600.0
            if hours_open >= config.MAX_POSITION_DURATION_HOURS:
                should_close, close_reason = True, "Max duration exceeded (48h)"
                
            if should_close:
                logger.info(f"Action required for {symbol}: {close_reason} @ {current_price}")
                success = self.positions.close_trade(trade_id)
                
                if success:
                    # To get final stats (RealizedPnL), we could fetch the history, 
                    # but for now we just use the current price to estimate or we can trust the backend.
                    # As a quick workaround, we inject the closePrice into a fake dict to pass to the report
                    fake_backend_trade_data = {
                        "closePrice": current_price,
                        # Rough estimate for PnL
                        "realizedPnl": pos["margin"] * (current_price - pos["entry_price"]) / pos["entry_price"] * (1 if side == 0 else -1) * pos["leverage"],
                        # We don't know Win/Loss exact enum here without fetching, but we estimate:
                        "status": 1 if close_reason == "Take Profit reached" else 2
                    }
                    self.report.log_trade_closed(pos, fake_backend_trade_data)
                    self.state.remove_position(trade_id)


if __name__ == "__main__":
    agent = VergeAgent()
    agent.run()
