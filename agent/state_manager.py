import json
import os
import time
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

    # --- LSE symbol cooldown (evita re-entrar al mismo par en N velas) ---

    def _cooldown_path(self) -> str:
        return getattr(config, "LSE_SYMBOL_COOLDOWN_FILE", os.path.join(config.DATA_DIR, "lse_symbol_cooldown.json"))

    def _load_cooldown_map(self) -> dict:
        path = self._cooldown_path()
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Cooldown map read error: %s", e)
            return {}

    def _save_cooldown_map(self, data: dict):
        try:
            with open(self._cooldown_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Cooldown map save error: %s", e)

    def is_lse_symbol_cooldown_active(self, symbol: str) -> bool:
        data = self._load_cooldown_map()
        until = float(data.get(symbol, 0) or 0)
        now = time.time()
        if until <= 0 or now >= until:
            if symbol in data:
                del data[symbol]
                self._save_cooldown_map(data)
            return False
        return True

    def register_lse_symbol_cooldown(self, symbol: str, timeframe: str):
        n = int(getattr(config, "LSE_SYMBOL_COOLDOWN_CANDLES", 0))
        if n <= 0:
            return
        sec = float(config.timeframe_to_seconds(timeframe))
        until = time.time() + n * sec
        data = self._load_cooldown_map()
        data[symbol] = until
        self._save_cooldown_map(data)
        logger.info("LSE cooldown %s until %.0f (%s velas %s)", symbol, until, n, timeframe)

    # --- Kill-switch: racha de pérdidas → pausa LSE ---

    def _loss_streak_path(self) -> str:
        return getattr(config, "AGENT_LOSS_STREAK_FILE", os.path.join(config.DATA_DIR, "agent_loss_streak.json"))

    def _load_loss_streak(self) -> dict:
        path = self._loss_streak_path()
        if not os.path.isfile(path):
            return {"consecutive_losses": 0, "lse_paused_until": 0.0}
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return {"consecutive_losses": 0, "lse_paused_until": 0.0}
            d.setdefault("consecutive_losses", 0)
            d.setdefault("lse_paused_until", 0.0)
            return d
        except Exception as e:
            logger.warning("Loss streak read error: %s", e)
            return {"consecutive_losses": 0, "lse_paused_until": 0.0}

    def _save_loss_streak(self, d: dict):
        try:
            with open(self._loss_streak_path(), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
        except Exception as e:
            logger.warning("Loss streak save error: %s", e)

    def is_lse_kill_switch_active(self) -> bool:
        d = self._load_loss_streak()
        return time.time() < float(d.get("lse_paused_until", 0) or 0)

    def record_closed_trade_outcome(self, is_loss: bool):
        d = self._load_loss_streak()
        if is_loss:
            d["consecutive_losses"] = int(d.get("consecutive_losses", 0)) + 1
            thr = int(getattr(config, "AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES", 3))
            if d["consecutive_losses"] >= thr:
                pause_m = float(getattr(config, "AGENT_KILL_SWITCH_PAUSE_MINUTES", 120))
                d["lse_paused_until"] = time.time() + pause_m * 60.0
                d["consecutive_losses"] = 0
                logger.warning(
                    "[KILL] Pausa LSE %.0f min tras %s pérdidas consecutivas",
                    pause_m,
                    thr,
                )
        else:
            d["consecutive_losses"] = 0
        self._save_loss_streak(d)
