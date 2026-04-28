import time
import logging
import sys
import config
from datetime import datetime

# ---------------------------------------------------------
# Fix Unicode en Windows (cp1252 no soporta emojis en consola)
# ---------------------------------------------------------
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

# Silenciar InsecureRequestWarning de urllib3 (requests HTTPS a localhost sin cert)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from auth_manager import AuthManager
from binance_fetcher import BinanceFetcher
from state_manager import StateManager
from signal_engine import SignalEngine
from risk_manager import RiskManager
from position_manager import PositionManager
from report_engine import ReportEngine
from circuit_breaker import get_breakers

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
    Main loop for the VERGE Autonomous Trading Agent (Phase 3 Architecture).
    Features:
      - RateLimiter awareness (Auto-Degraded Mode)
      - SQLite KlineCache integration (Zero-REST reads)
      - Dynamic Tiers (Pre-filtering to save Nexus-15 compute)
    """
    def __init__(self):
        logger.info("Initializing VERGE Agent v4.0 [Professional Architecture]...")
        self.auth      = AuthManager()
        self.fetcher   = BinanceFetcher()
        self.state     = StateManager()
        self.signals   = SignalEngine(self.fetcher)
        self.risk      = RiskManager(self.fetcher)
        self.positions = PositionManager(self.auth)
        self.report    = ReportEngine()

        self._tier3_index = 0

        logger.info(
            f"Watchlist: T1={len(config.WATCHLIST_TIER1)} | "
            f"T2={len(config.WATCHLIST_TIER2)} | "
            f"T3={len(config.WATCHLIST_TIER3)} | "
            f"Total={len(config.WATCHLIST)}"
        )

    def run(self):
        logger.info(f"Agent started. Loop interval: {config.LOOP_INTERVAL_SECONDS}s.")

        if not self.auth.get_token():
            logger.error("FATAL: Could not authenticate with ABP Backend. Stopping.")
            return

        self._repair_existing_positions()

        while True:
            try:
                self.loop_cycle()
            except Exception as e:
                logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)

            logger.info(f"Sleeping {config.LOOP_INTERVAL_SECONDS}s...")
            time.sleep(config.LOOP_INTERVAL_SECONDS)

    # ─────────────────────────────────────────────────────────
    # Main cycle
    # ─────────────────────────────────────────────────────────
    def loop_cycle(self):
        logger.info("--- Starting new analysis cycle ---")

        # 0. Check system health across ALL exchanges
        # Degraded mode only activates when EVERY exchange is unavailable.
        # A Binance ban alone is NOT enough to degrade — Bybit/OKX keep running.
        breakers     = get_breakers()
        available    = [name for name, cb in breakers.items() if cb.is_available]
        all_down     = len(available) == 0
        is_degraded  = all_down

        if available:
            logger.info(f"[MultiExchange] Active sources: {available}")
        else:
            logger.warning("[MultiExchange] ALL exchange sources unavailable — running on cache only.")

        # Log individual Binance ban status (informational only — not blocking)
        rl_status = self.fetcher.get_rate_limiter_status()
        if rl_status.get("degraded", False):
            rem = rl_status.get("degraded_remaining_s", 0)
            logger.warning(
                f"⚠️  Binance IP ban active ({rem}s remaining). "
                f"WS data continues via: {[x for x in available if x != 'binance'] or 'cache'}"
            )

        if is_degraded:
            logger.warning(
                "⚠️ FULL SYSTEM DEGRADED — all exchanges unavailable. "
                "Running on SQLite cache only. Skipping new signal search."
            )

        # 1. Monitor open positions (always runs, uses cached live prices)
        self._manage_open_positions()

        # 2. Check trade limits
        open_count = self.state.get_position_count()
        if open_count >= config.MAX_OPEN_POSITIONS:
            logger.info(f"Max open positions ({open_count}/{config.MAX_OPEN_POSITIONS}). Skipping new signals.")
            return

        if not self.state.can_trade_today():
            logger.info("Max daily trades reached. Skipping new signals.")
            return

        # 3. Gather global signals (SCAR proxy — lightweight)
        logger.info("Fetching SCAR alerts...")
        scar_alerts = self.signals.get_scar_alerts()

        candidates = []

        # 4. TIER 1 — Full analysis, every cycle
        logger.info(f"[T1] Scanning {len(config.WATCHLIST_TIER1)} priority symbols...")
        candidates += self._scan_tier1(scar_alerts, is_degraded=is_degraded)

        # 5. TIER 2 — Pre-filter first, Nexus-15 only if interesting
        if not is_degraded and len(candidates) < 3:
            logger.info(f"[T2] Pre-filtering {len(config.WATCHLIST_TIER2)} secondary symbols...")
            candidates += self._scan_tier2(scar_alerts)
        elif is_degraded:
            logger.info("[T2] Skipped (System Degraded).")

        # 6. TIER 3 — Rotate N symbols per cycle (lightweight scan)
        if not is_degraded and len(candidates) < 3:
            t3_batch = self._get_tier3_batch()
            if t3_batch:
                logger.info(f"[T3] Scanning {len(t3_batch)} rotational symbols...")
                candidates += self._scan_tier1(scar_alerts, symbols=t3_batch, is_degraded=is_degraded)
        elif is_degraded:
            logger.info("[T3] Skipped (System Degraded).")

        if not candidates:
            logger.info("No candidates met the minimum confluence score.")
            return

        # Sort by confluence score
        candidates.sort(key=lambda x: x["confluence_score"], reverse=True)
        top = candidates[0]
        logger.info(
            f"🎯 TOP CANDIDATE: {top['symbol']} | Score={top['confluence_score']} | "
            f"Dir={top['trade_direction']} | Nexus={top['nexus_confidence']}% | SCAR={top['scar_score']}"
        )

        self._execute_trade(top)

    # ─────────────────────────────────────────────────────────
    # Tier scanning methods
    # ─────────────────────────────────────────────────────────
    def _scan_tier1(self, scar_alerts: dict, symbols: list = None, is_degraded: bool = False) -> list:
        """
        Full analysis for Tier 1 symbols.
        If degraded, only analyzes symbols that already have enough history in cache.
        """
        targets = symbols if symbols is not None else config.WATCHLIST_TIER1
        candidates = []

        for symbol in targets:
            if self._should_skip(symbol):
                continue

            # In degraded mode, don't even try if we know we lack cache history
            # (to avoid spamming logs or risking REST calls)
            if is_degraded:
                ticker = self.fetcher.get_ticker(symbol)
                if not ticker or not ticker.get("has_history", False):
                    continue

            nexus_data = self.signals.get_nexus15_prediction(symbol)
            if not nexus_data:
                continue

            scar_data = scar_alerts.get(symbol, {})
            confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data)

            if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                candidates.append(confluence)

        return candidates

    def _scan_tier2(self, scar_alerts: dict) -> list:
        """
        Pre-filter scan: checks local SQLite cache (via get_ticker) for volatility/volume.
        Only runs heavy Nexus-15 on symbols that pass the filter.
        """
        candidates = []
        nexus_calls = 0
        filtered_in = 0

        for symbol in config.WATCHLIST_TIER2:
            if self._should_skip(symbol):
                continue

            # Quick pre-filter via cache (zero Binance calls)
            ticker = self.fetcher.get_ticker(symbol)
            if not ticker or not ticker.get("is_fresh"):
                continue

            change_pct  = abs(ticker.get("change_pct", 0))
            has_history = ticker.get("has_history", False)

            # Rule: Must have > X% move AND history in cache
            if change_pct < config.TIER2_MIN_VOLATILITY_PCT or not has_history:
                continue

            filtered_in += 1
            nexus_data = self.signals.get_nexus15_prediction(symbol)
            if nexus_data:
                nexus_calls += 1
                scar_data = scar_alerts.get(symbol, {})
                confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data)

                if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                    candidates.append(confluence)

        logger.info(f"[T2] Pre-filter passed: {filtered_in}/{len(config.WATCHLIST_TIER2)} | Nexus-15 calls: {nexus_calls}")
        return candidates

    def _get_tier3_batch(self) -> list:
        """Returns the next batch of Tier 3 symbols to analyze this cycle."""
        tier3 = config.WATCHLIST_TIER3
        if not tier3:
            return []

        n = config.TIER3_ROTATE_PER_CYCLE
        start = self._tier3_index % len(tier3)
        batch = (tier3 + tier3)[start: start + n]
        self._tier3_index = (start + n) % len(tier3)
        return batch

    def _should_skip(self, symbol: str) -> bool:
        if self.state.has_traded_symbol_today(symbol):
            return True
        if any(p.get("symbol") == symbol for p in self.state.get_open_positions()):
            return True
        return False

    # ─────────────────────────────────────────────────────────
    # Trade execution
    # ─────────────────────────────────────────────────────────
    def _get_tier_for_symbol(self, symbol: str) -> str:
        if symbol in config.WATCHLIST_TIER1: return "T1"
        if symbol in config.WATCHLIST_TIER2: return "T2"
        if symbol in config.WATCHLIST_TIER3: return "T3"
        return "N/A"

    def _execute_trade(self, candidate: dict):
        symbol = candidate["symbol"]
        balance = self.positions.get_virtual_balance()
        pos_details = self.risk.calculate_position(symbol, candidate, available_balance=balance)

        if not pos_details:
            return
        
        # Generate Entry Reason
        scar_score = candidate.get("scar_score", 0)
        nexus_conf = candidate.get("nexus_confidence", 0)
        direction = candidate.get("trade_direction", "UNKNOWN")
        confluence = candidate.get("confluence_score", 0)

        nexus_group = "Momentum Burst" if nexus_conf > 80 else ("Trend Following" if nexus_conf > 60 else "Mean Reversion")

        reason_parts = []
        if nexus_conf > 0:
            reason_parts.append(f"Señal '{nexus_group}' en marco de 15m (Nexus: {nexus_conf}%).")
        if scar_score >= 4:
            reason_parts.append(f"Flujo de liquidez de ballenas detectado (SCAR: {scar_score}/5).")
        if confluence >= config.MIN_CONFLUENCE_SCORE and scar_score >= 4:
            reason_parts.append("Alineación confirmada entre SCAR y Nexus-15.")

        entry_reason = " ".join(reason_parts) if reason_parts else "Señal de momentum validada por el motor de riesgo."

        logger.info(f"Opening {candidate['trade_direction']} on {symbol}. Margin: {pos_details['margin']}")
        trade_result = self.positions.open_trade(pos_details)

        if trade_result:
            trade_id = trade_result.get("id")
            local_pos = {
                "trade_id": trade_id,
                "symbol": symbol,
                "opened_at": datetime.utcnow().isoformat(),
                "entry_reason": entry_reason,
                "nexus_group": nexus_group,
                "tier": self._get_tier_for_symbol(symbol),
                **candidate,
                **pos_details,
            }
            self.state.add_position(local_pos)
            self.state.record_trade_action(symbol)
            self.report.log_trade_opened(local_pos)

    # ─────────────────────────────────────────────────────────
    # Position management
    # ─────────────────────────────────────────────────────────
    def _manage_open_positions(self):
        """
        Monitors open positions and closes them if TP/SL/timeout is reached.
        Prices are ALWAYS fetched from local cache.
        """
        positions = self.state.get_open_positions()
        if not positions:
            return

        logger.info(f"Monitoring {len(positions)} open positions...")

        for pos in positions:
            symbol   = pos["symbol"]
            trade_id = pos["trade_id"]
            side     = pos["side"]
            tp       = pos["tp_price"]
            sl       = pos["sl_price"]

            current_price = self.fetcher.get_current_price(symbol)
            if current_price <= 0:
                continue

            should_close = False
            close_reason = ""

            if side == 0:  # LONG
                if current_price >= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price <= sl:
                    should_close, close_reason = True, "Stop Loss reached"
            else:  # SHORT
                if current_price <= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price >= sl:
                    should_close, close_reason = True, "Stop Loss reached"

            opened_at = datetime.fromisoformat(pos["opened_at"])
            hours_open = (datetime.utcnow() - opened_at).total_seconds() / 3600.0
            if hours_open >= config.MAX_POSITION_DURATION_HOURS:
                should_close, close_reason = True, "Max duration exceeded"

            if not should_close:
                active_backend_trades = self.positions.get_active_trades()
                backend_ids = [t["id"] for t in active_backend_trades]
                if trade_id not in backend_ids:
                    logger.info(f"Position {symbol} ({trade_id}) closed by server. Syncing state.")
                    self.state.remove_position(trade_id)
                    continue

            if should_close:
                logger.info(f"Closing {symbol}: {close_reason} @ {current_price}")
                success = self.positions.close_trade(trade_id)

                if success:
                    realized_pnl = pos["margin"] * (current_price - pos["entry_price"]) / pos["entry_price"] * (1 if side == 0 else -1) * pos["leverage"]
                    fake_data = {
                        "closePrice": current_price,
                        "realizedPnl": realized_pnl,
                        "status": 1 if "Take Profit" in close_reason else 2,
                    }
                    self.report.log_trade_closed(pos, fake_data)
                    self.state.remove_position(trade_id)

    def _repair_existing_positions(self):
        """Ensures all backend positions have TP/SL."""
        logger.info("Verifying TP/SL on active positions...")
        active_trades = self.positions.get_active_trades()

        for trade in active_trades:
            symbol   = trade["symbol"]
            trade_id = trade["id"]
            tp       = trade.get("tpPrice")
            sl       = trade.get("slPrice")

            if tp is None or sl is None or tp == 0 or sl == 0:
                logger.info(f"Repairing TP/SL for {symbol} ({trade_id})...")
                fake_signal = {"side": trade["side"], "estimated_range_pct": 2.0}
                recalc = self.risk.calculate_position(symbol, fake_signal, available_balance=10000)
                
                if recalc:
                    entry = float(trade["entryPrice"])
                    range_pct = 0.02
                    tp_dist = range_pct * config.TP_MULTIPLIER
                    sl_dist = range_pct * config.SL_MULTIPLIER

                    if trade["side"] == 0:
                        tp_val = entry * (1 + tp_dist)
                        sl_val = entry * (1 - sl_dist)
                    else:
                        tp_val = entry * (1 - tp_dist)
                        sl_val = entry * (1 + sl_dist)

                    payload = {"tpPrice": round(tp_val, 4), "slPrice": round(sl_val, 4)}
                    success = self.positions.update_tp_sl(trade_id, payload)

                    if success:
                        self.state.update_position_tpsl(trade_id, payload["tpPrice"], payload["slPrice"])


if __name__ == "__main__":
    agent = VergeAgent()
    agent.run()
