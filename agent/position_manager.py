import requests
import logging
import hashlib
import hmac
import time
import os
import config
from typing import Dict, Any, Optional

logger = logging.getLogger("PositionManager")

# ──────────────────────────────────────────────────────────────
# Binance Futures Direct Client (bypasses C# backend)
# ──────────────────────────────────────────────────────────────
class BinanceDirectClient:
    """Signs and sends requests directly to Binance Futures REST API."""

    def __init__(self):
        use_testnet_str = os.getenv("BINANCE_USE_TESTNET", "false")
        self.use_testnet = use_testnet_str.lower() in ("1", "true", "yes")
        if self.use_testnet:
            self.api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY", "")
            self.api_secret = os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET", "")
            self.base_url = "https://testnet.binancefuture.com"
            version = "3.4"
        else:
            self.api_key = os.getenv("BINANCE_MAINNET_API_KEY") or os.getenv("BINANCE_API_KEY", "")
            self.api_secret = os.getenv("BINANCE_MAINNET_API_SECRET") or os.getenv("BINANCE_API_SECRET", "")
            self.base_url = "https://fapi.binance.com"
            version = "3.3"
        self._precision_cache: dict = {}
        logger.info(f"[BinanceDirect] PositionManager v{version} loaded - closePosition=true with fallbacks ({'TESTNET' if self.use_testnet else 'MAINNET'})")

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def get_symbol_precision(self, symbol: str):
        """Returns (qty_precision, price_precision) for a symbol."""
        if symbol in self._precision_cache:
            return self._precision_cache[symbol]
        
        # 1. Safe defaults initialized at start to prevent UnboundLocalError / NameError
        qty_p, price_p = 3, 4
        fallback_used = True
        
        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                symbols_list = resp.json().get("symbols", [])
                for s in symbols_list:
                    if s.get("symbol") == symbol:
                        qty_p = s.get("quantityPrecision", 3)
                        price_p = s.get("pricePrecision", 4)
                        self._precision_cache[symbol] = (qty_p, price_p)
                        logger.info(f"[BinanceDirect] Precision for {symbol} fetched from API: qty={qty_p}, price={price_p}")
                        fallback_used = False
                        return qty_p, price_p
                logger.warning(f"[BinanceDirect] Symbol {symbol} not found in exchangeInfo.")
            else:
                logger.warning(f"[BinanceDirect] exchangeInfo returned HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"[BinanceDirect] Error fetching precision from exchangeInfo for {symbol}: {e}")
            
        if fallback_used:
            logger.warning(
                f"[BinanceDirect] ⚠️ Using fallback precision for {symbol}: qty={qty_p}, price={price_p}. "
                f"Reason: Symbol not found or API request failed."
            )
            
        return qty_p, price_p

    def place_order(self, symbol: str, side: str, order_type: str, **kwargs) -> dict:
        """Low-level order placement. Returns {success, orderId, error, raw_response}."""
        url = f"{self.base_url}/fapi/v1/order"
        params = {"symbol": symbol, "side": side, "type": order_type}
        params.update(kwargs)
        params = self._sign(params)
        try:
            resp = requests.post(url, params=params, headers=self._headers(), timeout=15)
            data = resp.json()
            if resp.status_code == 200:
                return {"success": True, "orderId": data.get("orderId"), "raw_response": data}
            else:
                err_msg = data.get("msg", str(data))
                logger.error(f"[BinanceDirect] HTTP {resp.status_code} Error placing order ({side} {order_type} on {symbol}): {err_msg}")
                return {"success": False, "error": err_msg, "raw_response": data}
        except Exception as e:
            logger.error(f"[BinanceDirect] Exception placing order ({side} {order_type} on {symbol}): {e}")
            return {"success": False, "error": str(e), "raw_response": None}

    def place_algo_order(self, symbol: str, side: str, order_type: str, **kwargs) -> dict:
        """Place TP/SL using Binance Algo Orders API (New Dec 2025 Standard). Returns {success, algoId, error, raw_response}."""
        url = f"{self.base_url}/fapi/v1/algoOrder"
        params = {
            "symbol": symbol,
            "side": side,
            "algoType": "CONDITIONAL",
            "type": order_type,  # e.g. "STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT"
        }
        params.update(kwargs)
        params = self._sign(params)
        try:
            resp = requests.post(url, params=params, headers=self._headers(), timeout=15)
            data = resp.json()
            if resp.status_code == 200:
                return {"success": True, "algoId": data.get("algoId"), "raw_response": data}
            else:
                err_msg = data.get("msg", str(data))
                logger.error(f"[BinanceDirect] Algo HTTP {resp.status_code} Error placing {order_type} on {symbol}: {err_msg}")
                return {"success": False, "error": err_msg, "raw_response": data}
        except Exception as e:
            logger.error(f"[BinanceDirect] Algo Exception placing {order_type} on {symbol}: {e}")
            return {"success": False, "error": str(e), "raw_response": None}

    def open_position(self, symbol: str, side: str, quantity: float,
                      tp_price: float = None, sl_price: float = None) -> bool:
        """Opens a market entry + TP + SL directly on Binance Futures."""
        env_str = "TESTNET" if self.use_testnet else "MAINNET"
        logger.info("[BinanceDirect] ========== open_position START ==========")
        logger.info(f"[BinanceDirect] ENVIRONMENT: {env_str} ({self.base_url})")
        logger.info(f"[BinanceDirect] Parameters: symbol={symbol}, side={side}, qty={quantity}, TP={tp_price}, SL={sl_price}")
        
        if not self.api_key or not self.api_secret:
            logger.error("[BinanceDirect] No API keys configured.")
            return False
            
        qty_p, price_p = self.get_symbol_precision(symbol)
        qty = round(quantity, qty_p)
        opposite = "SELL" if side == "BUY" else "BUY"
        logger.info(f"[BinanceDirect] Precision: qty_p={qty_p}, price_p={price_p}, rounded_qty={qty}, opposite={opposite}")

        # 0. Set Leverage to 1x (Spot-like mode for both Mainnet and Testnet)
        try:
            leverage_url = f"{self.base_url}/fapi/v1/leverage"
            lev_params = self._sign({"symbol": symbol, "leverage": 1})
            lev_resp = requests.post(leverage_url, params=lev_params, headers=self._headers(), timeout=10)
            if lev_resp.status_code == 200:
                logger.info(f"[BinanceDirect] Auto-adjusted leverage to 1x. Response: {lev_resp.text}")
            else:
                logger.warning(f"[BinanceDirect] Leverage adjustment returned code {lev_resp.status_code}: {lev_resp.text}")
        except Exception as e:
            logger.warning(f"[BinanceDirect] Failed to auto-adjust leverage: {e}")

        # 1. Entry Market Order
        logger.info(f"[BinanceDirect] Step 1/3: Entry {side} {qty} {symbol} @ MARKET (env={env_str})")
        r = self.place_order(symbol, side, "MARKET", quantity=qty)
        if not r["success"]:
            # If entry fails, retry with 1x leverage (already set, but ensure it)
            try:
                logger.info("[BinanceDirect] Entry failed. Retrying with 1x leverage...")
                lev_params = self._sign({"symbol": symbol, "leverage": 1})
                requests.post(f"{self.base_url}/fapi/v1/leverage", params=lev_params, headers=self._headers(), timeout=10)
                r = self.place_order(symbol, side, "MARKET", quantity=qty)
            except Exception as e:
                logger.error(f"[BinanceDirect] Fallback leverage adjustment exception: {e}")
        
        if not r["success"]:
            logger.error(f"[BinanceDirect] Entry failed: {r.get('error')}. Raw response: {r.get('raw_response')}")
            logger.info("[BinanceDirect] ========== open_position FAILED at Entry ==========")
            return False
            
        logger.info(f"[BinanceDirect] ✅ Entry OK — orderId={r['orderId']}")
        logger.info(f"[BinanceDirect] Entry Raw Response: {r.get('raw_response')}")

        # Small pause to let Binance register the position before placing TP/SL
        import time as _time
        logger.info("[BinanceDirect] Waiting 0.5s for position to register...")
        _time.sleep(0.5)

        # 2. Take Profit Cascade Retry (using Algo Order API)
        if tp_price and tp_price > 0:
            tp = round(tp_price, price_p)
            logger.info(f"[BinanceDirect] Step 2/3: Placing TP at {tp} for {symbol}")
            
            # Option 1: TAKE_PROFIT_MARKET with closePosition=true via Algo API
            r2 = self.place_algo_order(
                symbol, opposite, "TAKE_PROFIT_MARKET",
                triggerPrice=tp,
                closePosition="true",
                workingType="MARK_PRICE",
                timeInForce="GTC"
            )
            if r2["success"]:
                logger.info(f"[BinanceDirect] ✅ Option 1 TP OK (Algo) — algoId={r2.get('algoId')}. Raw: {r2.get('raw_response')}")
            else:
                logger.warning(f"[BinanceDirect] ⚠️ Option 1 TP failed: {r2.get('error')}. Trying Option 2 (reduceOnly + quantity)...")
                
                # Option 2: TAKE_PROFIT_MARKET with quantity and reduceOnly=true via Algo API
                r2_alt = self.place_algo_order(
                    symbol, opposite, "TAKE_PROFIT_MARKET",
                    triggerPrice=tp,
                    quantity=qty,
                    reduceOnly="true",
                    workingType="MARK_PRICE",
                    timeInForce="GTC"
                )
                if r2_alt["success"]:
                    logger.info(f"[BinanceDirect] ✅ Option 2 TP OK (Algo) — algoId={r2_alt.get('algoId')}. Raw: {r2_alt.get('raw_response')}")
                else:
                    logger.warning(f"[BinanceDirect] ⚠️ Option 2 TP failed: {r2_alt.get('error')}. Trying Option 3 (LIMIT order on standard API)...")
                    
                    # Option 3: Limit order on standard API
                    r2_limit = self.place_order(
                        symbol, opposite, "LIMIT",
                        price=tp,
                        quantity=qty,
                        reduceOnly="true",
                        timeInForce="GTC"
                    )
                    if r2_limit["success"]:
                        logger.info(f"[BinanceDirect] ✅ Option 3 TP Limit OK — orderId={r2_limit.get('orderId')}. Raw: {r2_limit.get('raw_response')}")
                    else:
                        logger.error(f"[BinanceDirect] ❌ All TP options failed. Final error: {r2_limit.get('error')}")
        else:
            logger.info(f"[BinanceDirect] Step 2/3: SKIPPED — tp_price={tp_price}")

        # 3. Stop Loss Cascade Retry (using Algo Order API)
        if sl_price and sl_price > 0:
            sl = round(sl_price, price_p)
            logger.info(f"[BinanceDirect] Step 3/3: Placing SL at {sl} for {symbol}")
            
            # Option 1: STOP_MARKET with closePosition=true via Algo API
            r3 = self.place_algo_order(
                symbol, opposite, "STOP_MARKET",
                triggerPrice=sl,
                closePosition="true",
                workingType="MARK_PRICE",
                timeInForce="GTC"
            )
            if r3["success"]:
                logger.info(f"[BinanceDirect] ✅ Option 1 SL OK (Algo) — algoId={r3.get('algoId')}. Raw: {r3.get('raw_response')}")
            else:
                logger.warning(f"[BinanceDirect] ⚠️ Option 1 SL failed: {r3.get('error')}. Trying Option 2 (reduceOnly + quantity)...")
                
                # Option 2: STOP_MARKET with quantity and reduceOnly=true via Algo API
                r3_alt = self.place_algo_order(
                    symbol, opposite, "STOP_MARKET",
                    triggerPrice=sl,
                    quantity=qty,
                    reduceOnly="true",
                    workingType="MARK_PRICE",
                    timeInForce="GTC"
                )
                if r3_alt["success"]:
                    logger.info(f"[BinanceDirect] ✅ Option 2 SL OK (Algo) — algoId={r3_alt.get('algoId')}. Raw: {r3_alt.get('raw_response')}")
                else:
                    logger.warning(f"[BinanceDirect] ⚠️ Option 2 SL failed: {r3_alt.get('error')}. Trying Option 3 (STOP Limit order via Algo API)...")
                    
                    # Option 3: STOP Limit order via Algo API
                    r3_limit = self.place_algo_order(
                        symbol, opposite, "STOP",
                        price=sl,
                        triggerPrice=sl,
                        quantity=qty,
                        reduceOnly="true",
                        timeInForce="GTC"
                    )
                    if r3_limit["success"]:
                        logger.info(f"[BinanceDirect] ✅ Option 3 SL Limit OK (Algo) — algoId={r3_limit.get('algoId')}. Raw: {r3_limit.get('raw_response')}")
                    else:
                        logger.error(f"[BinanceDirect] ❌ All SL options failed. Final error: {r3_limit.get('error')}")
        else:
            logger.info(f"[BinanceDirect] Step 3/3: SKIPPED — sl_price={sl_price}")

        logger.info("[BinanceDirect] ========== open_position END ==========")
        return True

    def close_position(self, symbol: str) -> bool:
        """Cancels open TP/SL orders and closes the active position at market."""
        if not self.api_key or not self.api_secret:
            logger.error("[BinanceDirect] No API keys configured.")
            return False

        # 1. Cancel all open orders for this symbol
        url_cancel = f"{self.base_url}/fapi/v1/allOpenOrders"
        params = self._sign({"symbol": symbol})
        try:
            resp = requests.delete(url_cancel, params=params, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                logger.info(f"[BinanceDirect] Cancelled all open orders for {symbol}")
            else:
                logger.warning(f"[BinanceDirect] Cancel orders returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"[BinanceDirect] Error cancelling orders: {e}")

        # 2. Get position to determine size and direction
        url_pos = f"{self.base_url}/fapi/v2/positionRisk"
        params2 = self._sign({"symbol": symbol})
        try:
            resp2 = requests.get(url_pos, params=params2, headers=self._headers(), timeout=15)
            positions = resp2.json() if resp2.status_code == 200 else []
            for p in positions:
                qty = float(p.get("positionAmt", 0))
                if qty != 0:
                    close_side = "SELL" if qty > 0 else "BUY"
                    abs_qty = abs(qty)
                    qty_p, _ = self.get_symbol_precision(symbol)
                    abs_qty = round(abs_qty, qty_p)
                    logger.info(f"[BinanceDirect] Closing {abs_qty} {symbol} with {close_side} MARKET")
                    r = self.place_order(symbol, close_side, "MARKET",
                                        quantity=abs_qty, reduceOnly="true")
                    if r["success"]:
                        logger.info(f"[BinanceDirect] Position closed OK — orderId={r['orderId']}")
                        return True
                    else:
                        logger.error(f"[BinanceDirect] Close failed: {r['error']}")
                        return False
            logger.warning(f"[BinanceDirect] No active position found for {symbol} to close.")
            return True
        except Exception as e:
            logger.error(f"[BinanceDirect] Error closing position: {e}")
            return False


_binance_direct = None

def get_binance_direct() -> BinanceDirectClient:
    global _binance_direct
    if _binance_direct is None:
        _binance_direct = BinanceDirectClient()
    return _binance_direct

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
            "tradingSignalId": position_data.get("tradingSignalId"),
            "agentDecisionJson": position_data.get("agent_decision_json"),
            "strategyProfileId": position_data.get("strategy_profile_id"),
            "ma7DistancePctAtEntry": position_data.get("ma7_distance_pct"),  # Sniper filter validation
        }
        
        try:
            logger.info(f" Sending Open Trade command to ABP: {payload['symbol']} (Side: {payload['side']}, Margin: {payload['amount']})")
            # verify=False for localhost dev certs
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=30)
            
            if response.status_code == 200:
                trade_result = response.json()
                logger.info(f" Trade successfully opened! Trade ID: {trade_result.get('id')}")
                return trade_result
            elif response.status_code == 204:
                logger.warning(f" ⚠️ Trade skipped by backend: {payload['symbol']} is temporarily unavailable or filtered.")
                return None
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

    def update_max_favorable_price(self, trade_id: str, max_favorable_price: float) -> bool:
        """
        AI-GRADE AUDIT: Update max favorable price (MFE) for a trade.
        LONG: highest price seen. SHORT: lowest price seen.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            logger.error("Cannot update MFE: No valid auth token.")
            return False

        url = f"{self.base_url}/api/app/simulated-trade/update-max-favorable-price/{trade_id}"
        payload = {"maxFavorablePrice": max_favorable_price}
        
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            if response.status_code == 200:
                logger.debug(f" MFE updated for trade {trade_id}: {max_favorable_price}")
                return True
            else:
                logger.warning(f" Failed to update MFE for {trade_id}. Status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f" Connection error updating MFE: {e}")
            return False

    def update_trade_exit_info(self, trade_id: str, exit_reason: str, btc_price_at_close: float = None) -> bool:
        """
        AI-GRADE AUDIT: Update exit reason and BTC price at close.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            logger.error("Cannot update exit info: No valid auth token.")
            return False

        url = f"{self.base_url}/api/app/simulated-trade/update-exit-info/{trade_id}"
        payload = {
            "exitReason": exit_reason,
            "btcPriceAtClose": btc_price_at_close,
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            if response.status_code == 200:
                logger.debug(f" Exit info updated for trade {trade_id}: {exit_reason}")
                return True
            else:
                logger.warning(f" Failed to update exit info for {trade_id}. Status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f" Connection error updating exit info: {e}")
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

    def update_max_adverse_price(self, trade_id: str, max_adverse_price: float) -> bool:
        """
        Records the farthest adverse price reached for a trade.
        For LONG: the lowest price seen. For SHORT: the highest price seen.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            logger.error(" Cannot update MaxAdversePrice: No valid auth token.")
            return False

        url = f"{self.base_url}/api/app/simulated-trade/max-adverse-price/{trade_id}"
        payload = {
            "maxAdversePrice": max_adverse_price
        }
        try:
            logger.info(f" Recording MaxAdversePrice for {trade_id}: {max_adverse_price}")
            logger.info(f" PUT URL: {url}")
            logger.info(f" Payload: {payload}")
            response = requests.put(url, json=payload, headers=headers, verify=False, timeout=15)
            logger.info(f" Response status: {response.status_code}")
            logger.info(f" Response body: {response.text}")
            if response.status_code not in [200, 204]:
                logger.error(f" Backend rejected MaxAdversePrice update. Status: {response.status_code}, Body: {response.text}")
            return response.status_code == 200 or response.status_code == 204
        except Exception as e:
            logger.error(f" Connection error updating MaxAdversePrice: {e}")
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
            
        return None
        
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

    def broadcast_signal(self, signal_data: dict) -> bool:
        """
        Pushes a real-time signal/score to the ABP backend to be broadcasted via SignalR.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return False

        url = f"{self.base_url}/api/app/agent/broadcast-signal"
        try:
            # We don't need to log every single broadcast to avoid spamming the console
            response = requests.post(url, json=signal_data, headers=headers, verify=False, timeout=5)
            return response.status_code in [200, 204]
        except Exception:
            return False

    def broadcast_signals(self, signals: list) -> bool:
        """
        Pushes a batch of signals/scores to the ABP backend to be broadcasted via SignalR.
        This avoids spamming 100+ HTTP requests per cycle.
        Falls back to per-signal sending if the batch endpoint isn't available.
        """
        if not signals:
            return True

        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return False

        url = f"{self.base_url}/api/app/agent/broadcast-signals"
        try:
            response = requests.post(url, json=signals, headers=headers, verify=False, timeout=15)
            if response.status_code in [200, 204]:
                return True

            # Fallback: batch endpoint not available / rejected → send individually
            ok = True
            for s in signals:
                ok = self.broadcast_signal(s) and ok
            return ok
        except Exception:
            ok = True
            for s in signals:
                ok = self.broadcast_signal(s) and ok
            return ok

    def get_strategy_profiles(self) -> list:
        """
        Retrieves all active strategy profiles for the current user.
        """
        headers = self.auth_manager.get_auth_headers()
        if not headers:
            return []

        url = f"{self.base_url}/api/app/strategy-profile"
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=30)
            if response.status_code == 200:
                profiles = response.json()
                return [p for p in profiles if p.get("isActive")]
        except Exception as e:
            logger.error(f"Error fetching strategy profiles: {e}")
            
        return []

    def open_binance_trade(self, symbol: str, side: int, quantity: float,
                           tp_price: float = None, sl_price: float = None) -> bool:
        """
        Places entry + TP + SL directly on Binance Futures REST API.
        Bypasses the C# backend entirely — no restart needed.
        """
        side_str = "BUY" if side == 0 else "SELL"
        logger.info(f"[BinanceDirect] open_binance_trade: {symbol} {side_str} qty={quantity} TP={tp_price} SL={sl_price}")
        return get_binance_direct().open_position(
            symbol=symbol,
            side=side_str,
            quantity=quantity,
            tp_price=tp_price,
            sl_price=sl_price
        )

    def close_binance_trade(self, symbol: str) -> bool:
        """
        Cancels TP/SL orders and closes the position directly via Binance Futures REST API.
        Bypasses the C# backend entirely — no restart needed.
        """
        logger.info(f"[BinanceDirect] close_binance_trade: {symbol}")
        return get_binance_direct().close_position(symbol=symbol)
