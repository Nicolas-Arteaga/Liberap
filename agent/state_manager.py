import json
import os
import config
import logging
from datetime import datetime

logger = logging.getLogger("StateManager")

class StateManager:
    """
    Manages local persistent state for the agent using JSON files.
    This tracks open positions locally (in addition to the DB) and daily trade limits.
    """
    
    def __init__(self):
        self.positions_file = config.POSITIONS_FILE
        self.daily_stats_file = config.DAILY_STATS_FILE
        
        self._ensure_files()

    def _ensure_files(self):
        if not os.path.exists(self.positions_file):
            self._save_json(self.positions_file, [])
            
        if not os.path.exists(self.daily_stats_file):
            self._reset_daily_stats()

    def _load_json(self, filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading state file {filepath}: {e}")
            return [] if 'positions' in filepath else {}

    def _save_json(self, filepath, data):
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error writing state file {filepath}: {e}")

    # --- Daily Stats (Anti-Churn & Rate Limiting) ---

    def _reset_daily_stats(self):
        data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "trades_count": 0,
            "symbols_traded_today": []
        }
        self._save_json(self.daily_stats_file, data)
        return data

    def get_daily_stats(self):
        stats = self._load_json(self.daily_stats_file)
        today = datetime.now().strftime("%Y-%m-%d")
        if stats.get("date") != today:
            return self._reset_daily_stats()
        return stats

    def record_trade_action(self, symbol: str):
        """Records that a trade was opened today to enforce limits."""
        stats = self.get_daily_stats()
        stats["trades_count"] += 1
        if symbol not in stats["symbols_traded_today"]:
            stats["symbols_traded_today"].append(symbol)
        self._save_json(self.daily_stats_file, stats)

    def can_trade_today(self) -> bool:
        """Check if we haven't hit the daily maximum trades limit."""
        stats = self.get_daily_stats()
        return stats["trades_count"] < config.MAX_TRADES_PER_DAY

    def has_traded_symbol_today(self, symbol: str) -> bool:
        """Anti-churn: check if we already traded this symbol today."""
        stats = self.get_daily_stats()
        return symbol in stats.get("symbols_traded_today", [])

    # --- Open Positions Management ---

    def get_open_positions(self) -> list:
        return self._load_json(self.positions_file)

    def add_position(self, position: dict):
        """Adds a position to the local state."""
        positions = self.get_open_positions()
        # Prevent duplicates
        if not any(p.get("trade_id") == position.get("trade_id") for p in positions):
            positions.append(position)
            self._save_json(self.positions_file, positions)
            
    def remove_position(self, trade_id: str):
        """Removes a position from the local state after it's closed."""
        positions = self.get_open_positions()
        filtered = [p for p in positions if p.get("trade_id") != trade_id]
        if len(filtered) != len(positions):
            self._save_json(self.positions_file, filtered)

    def get_position_count(self) -> int:
        return len(self.get_open_positions())

    def update_position_tpsl(self, trade_id: str, tp_price: float, sl_price: float):
        """Updates TP/SL for an existing position in the local state."""
        positions = self.get_open_positions()
        updated = False
        for p in positions:
            if p.get("trade_id") == trade_id:
                p["tp_price"] = tp_price
                p["sl_price"] = sl_price
                updated = True
                break
        if updated:
            self._save_json(self.positions_file, positions)
