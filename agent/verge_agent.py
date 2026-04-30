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
        logger.debug("[TRACE] Entering loop_cycle")
        logger.info("--- Starting new analysis cycle ---")

        # 0. Check exchange health
        breakers     = get_breakers()
        available    = [name for name, cb in breakers.items() if cb.is_available]
        is_degraded  = len(available) == 0

        if available:
            logger.info(f"[MultiExchange] Active sources: {available}")
        else:
            logger.warning("[MultiExchange] ALL exchange sources unavailable — running on cache only.")

        # 1. Monitor open positions (always runs, uses cached live prices)
        logger.info("[Step 1/6] Checking open positions...")
        self._manage_open_positions()
        logger.info("[Step 1/6] Done.")

        # 2. Check trade limits
        open_count = self.state.get_position_count()
        if open_count >= config.MAX_OPEN_POSITIONS:
            logger.info(f"Max open positions ({open_count}/{config.MAX_OPEN_POSITIONS}). Skipping new signals.")
            return

        if not self.state.can_trade_today():
            logger.info("Max daily trades reached. Skipping new signals.")
            return

        # 3. Fetch SCAR alerts (lightweight — reads from DB, not exchanges)
        logger.info("[Step 3/6] Fetching SCAR alerts...")
        scar_alerts = self.signals.get_scar_alerts()
        logger.info(f"[Step 3/6] Received {len(scar_alerts)} alerts.")

        # 4. Scan ALL watchlist symbols with Nexus-15
        #    - Symbols with cache history: instant (SQLite read)
        #    - Symbols without cache history: on-demand REST fetch (Bybit/OKX)
        #    - Mirrors exactly what the Nexus-15 dashboard analyzes
        all_targets = config.WATCHLIST  # All 200 symbols, no exceptions

        logger.info(
            f"[Step 4/6] Scanning {len(all_targets)} symbols with Nexus-15..."
        )

        # 5. Run Nexus-15 on all watchlist symbols
        candidates = []
        skipped_trading = 0
        analyzed = 0
        no_data = 0

        for symbol in all_targets:
            try:
                if self._should_skip(symbol):
                    skipped_trading += 1
                    continue

                # Fetch prediction with a strict timeout (handled inside signal_engine)
                nexus_data = self.signals.get_nexus15_prediction(symbol)
                if not nexus_data:
                    no_data += 1
                    continue

                analyzed += 1
                scar_data  = scar_alerts.get(symbol, {})
                confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data)

                if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                    candidates.append(confluence)
                    logger.info(
                        f"✅ CANDIDATE: {symbol} | Score={confluence['confluence_score']:.1f} | "
                        f"Dir={confluence['trade_direction']} | Nexus={confluence['nexus_confidence']}%"
                    )
            except Exception as e:
                logger.error(f"⚠️ Error analyzing {symbol}: {e}")
                continue


        logger.info(
            f"[Step 5/6] Done: {analyzed} analyzed | "
            f"{len(candidates)} candidates | {skipped_trading} skipped | {no_data} no data"
        )

        if not candidates:
            logger.info("No candidates met the minimum confluence score.")
            return

        # 6. Sort by score and execute best
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
        Pre-filter scan for Tier 2 symbols.
        - If fresh live price available: apply volatility filter (change_pct > threshold)
        - If no live price but has kline history: still run Nexus-15 (skip volatility check)
        - If no live price AND no history: skip entirely
        """
        candidates = []
        nexus_calls = 0
        filtered_in = 0
        skipped_no_data = 0

        for symbol in config.WATCHLIST_TIER2:
            if self._should_skip(symbol):
                continue

            ticker = self.fetcher.get_ticker(symbol)

            if ticker and ticker.get("is_fresh"):
                # Has live price — apply volatility + history filter
                change_pct  = abs(ticker.get("change_pct", 0))
                has_history = ticker.get("has_history", False)
                if change_pct < config.TIER2_MIN_VOLATILITY_PCT or not has_history:
                    continue
            else:
                # No live price yet — check if we have kline history in cache
                # (WS may not have reached this symbol yet, but REST history exists)
                if not self.fetcher._cache.has_history(symbol):
                    skipped_no_data += 1
                    continue
                # Has history but no live price — run Nexus-15 anyway

            filtered_in += 1
            nexus_data = self.signals.get_nexus15_prediction(symbol)
            if nexus_data:
                nexus_calls += 1
                scar_data = scar_alerts.get(symbol, {})
                confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data)

                if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                    candidates.append(confluence)

        logger.info(
            f"[T2] Pre-filter passed: {filtered_in}/{len(config.WATCHLIST_TIER2)} | "
            f"Nexus-15 calls: {nexus_calls} | Skipped (no data): {skipped_no_data}"
        )
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
