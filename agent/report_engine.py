import csv
import os
import config
import logging
import requests
from datetime import datetime

logger = logging.getLogger("ReportEngine")

class ReportEngine:
    """
    Handles generating CSV logs and sending Telegram notifications.
    """
    def __init__(self):
        self.csv_file = config.TRADES_LOG_FILE
        self._ensure_csv_exists()

    def _ensure_csv_exists(self):
        if not os.path.exists(self.csv_file):
            try:
                with open(self.csv_file, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    # date, symbol, source, scar_score, nexus_confidence, confluence, direction, entry, tp, sl, exit_price, pnl_pct, result, duration_h, entry_reason, nexus_group, tier
                    writer.writerow([
                        "date", "symbol", "source", "scar_score", "nexus_confidence", 
                        "confluence", "direction", "entry", "tp", "sl", 
                        "exit_price", "pnl_usd", "result", "duration_h",
                        "entry_reason", "nexus_group", "tier"
                    ])
            except Exception as e:
                logger.error(f"Failed to create CSV file: {e}")

    def log_trade_closed(self, local_pos_data: dict, backend_trade_data: dict):
        """
        Logs a closed trade to the CSV file for post-mortem analysis.
        """
        try:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            symbol = local_pos_data.get("symbol")
            
            scar_score = local_pos_data.get("scar_score", 0)
            nexus_conf = local_pos_data.get("nexus_confidence", 0)
            
            source = "SCAR+Nexus" if (scar_score >= 4 and nexus_conf > 0) else ("SCAR" if scar_score >= 4 else "Nexus")
            
            confluence = local_pos_data.get("confluence_score", 0)
            direction = local_pos_data.get("trade_direction", "UNKNOWN")
            
            entry = local_pos_data.get("entry_price", 0)
            tp = local_pos_data.get("tp_price", 0)
            sl = local_pos_data.get("sl_price", 0)
            
            exit_price = backend_trade_data.get("closePrice", 0)
            pnl_usd = backend_trade_data.get("realizedPnl", 0)
            
            result = backend_trade_data.get("status", 0) # TradeStatus enum
            status_str = "WIN" if result == 1 else ("LOSS" if result == 2 else "UNKNOWN")
            
            # Calculate duration in hours
            opened_at_str = local_pos_data.get("opened_at")
            duration_h = 0.0
            if opened_at_str:
                opened_at = datetime.fromisoformat(opened_at_str)
                duration_h = round((datetime.utcnow() - opened_at).total_seconds() / 3600.0, 1)

            entry_reason = local_pos_data.get("entry_reason", "")
            nexus_group = local_pos_data.get("nexus_group", "")
            tier = local_pos_data.get("tier", "N/A")

            with open(self.csv_file, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([
                    date_str, symbol, source, scar_score, nexus_conf,
                    confluence, direction, entry, tp, sl,
                    exit_price, round(pnl_usd, 2), status_str, duration_h,
                    entry_reason, nexus_group, tier
                ])
                
            logger.info(f" Trade log saved to CSV for {symbol}. PnL: ${pnl_usd:.2f}")
            
            # Send Telegram if enabled
            self._send_telegram(f" *Trade Closed*: {symbol}\nStatus: {status_str}\nPnL: ${pnl_usd:.2f}\nDuration: {duration_h}h")
            
        except Exception as e:
            logger.error(f"Failed to log trade to CSV: {e}")

    def log_trade_opened(self, pos_data: dict):
        """Send telegram notification when trade is opened."""
        msg = (f" *New Trade Opened*: {pos_data['symbol']}\n"
               f"Direction: {pos_data['trade_direction']}\n"
               f"Entry: {pos_data['entry_price']}\n"
               f"TP: {pos_data['tp_price']} | SL: {pos_data['sl_price']}\n"
               f"Confluence: {pos_data['confluence_score']} (SCAR: {pos_data.get('scar_score')})")
        self._send_telegram(msg)

    def _send_telegram(self, message: str):
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            return
            
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
