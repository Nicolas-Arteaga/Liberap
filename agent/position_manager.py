import requests
import logging
import config
from typing import Dict, Any, Optional

logger = logging.getLogger("PositionManager")

class PositionManager:
    """
    Communicates with the ABP backend to open and close simulated trades.
    Requires a valid JWT token from AuthManager.
    """
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.base_url = config.ABP_BACKEND_URL

    def open_trade(self, position_data: dict) -> Optional[Dict[str, Any]]:
        """
        Sends the OpenTradeInputDto to the ABP SimulatedTradeAppService.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            logger.error("Cannot open trade: No valid auth token.")
            return None

        url = f"{self.base_url}/api/app/simulated-trade/open-trade"
        
        # Matching Verge.Trading.DTOs.OpenTradeInputDto
        payload = {
            "symbol": position_data["symbol"],
            "side": position_data["side"],
            "amount": position_data["margin"], 
            "leverage": position_data["leverage"],
            "tpPrice": position_data.get("tp_price"),
            "slPrice": position_data.get("sl_price"),
            "tradingSignalId": position_data.get("tradingSignalId")
        }
        
        try:
            logger.info(f" Sending Open Trade command to ABP: {payload['symbol']} (Side: {payload['side']}, Margin: {payload['amount']})")
            # verify=False for localhost dev certs
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=30)
            
            if response.status_code == 200:
                trade_result = response.json()
                logger.info(f" Trade successfully opened! Trade ID: {trade_result.get('id')}")
                return trade_result
            else:
                logger.error(f" Failed to open trade. Server returned {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f" Connection error while opening trade: {e}")
            return None

    def close_trade(self, trade_id: str) -> bool:
        """
        Sends the command to close a trade by ID to the ABP backend.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            logger.error("Cannot close trade: No valid auth token.")
            return False

        url = f"{self.base_url}/api/app/simulated-trade/close-trade/{trade_id}"
        
        try:
            logger.info(f" Sending Close Trade command for ID {trade_id}")
            response = requests.post(url, headers=headers, verify=False, timeout=30)
            
            if response.status_code == 200:
                logger.info(f" Trade {trade_id} successfully closed!")
                return True
            else:
                logger.error(f" Failed to close trade {trade_id}. Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f" Connection error while closing trade {trade_id}: {e}")
            return False

    def update_tp_sl(self, trade_id: str, tp_sl_data: dict) -> bool:
        """
        Updates TP/SL for an existing trade in the backend.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return False

        url = f"{self.base_url}/api/app/simulated-trade/tp-sl/{trade_id}"
        try:
            logger.info(f" Updating TP/SL for ID {trade_id}: {tp_sl_data}")
            response = requests.put(url, json=tp_sl_data, headers=headers, verify=False, timeout=30)
            if response.status_code not in [200, 204]:
                logger.error(f" Backend rejected TP/SL update. Status: {response.status_code}, Body: {response.text}")
            return response.status_code == 200 or response.status_code == 204
        except Exception as e:
            logger.error(f" Connection error while updating TP/SL: {e}")
            return False

    def get_active_trades(self) -> list:
        """
        Retrieves active trades from the backend to sync state if needed.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return []

        url = f"{self.base_url}/api/app/simulated-trade/active-trades"
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=30)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching active trades: {e}")
            
        return []
        
    def get_virtual_balance(self) -> float:
        """
        Retrieves the current virtual balance of the agent's account.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return config.VIRTUAL_CAPITAL_BASE

        url = f"{self.base_url}/api/app/simulated-trade/virtual-balance"
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=30)
            if response.status_code == 200:
                return float(response.text)
        except Exception as e:
            logger.warning(f"Error fetching virtual balance, using default: {e}")
            
        return config.VIRTUAL_CAPITAL_BASE
