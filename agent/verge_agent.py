import time
import logging
from typing import Optional
import sys
import json
import copy
import config
import requests
from datetime import datetime, timezone

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
from setup_validator import validate_pre_trade
from circuit_breaker import get_breakers
from redis_signal_bridge import RedisSignalBridge

# LSE: LiquiditySweepEngine — runs BEFORE Nexus-15 to catch sweeps early
# The LSE Python service endpoint is part of the same python-service container.
LSE_ENABLED = getattr(config, "LSE_ENABLED", True)
LSE_MIN_SCORE = getattr(config, "LSE_MIN_SCORE", 65.0)
LSE_SYMBOLS = getattr(config, "LSE_SYMBOLS", None)  # None = all watchlist; or list of symbols
LSE_CANDLE_LIMIT_1H = 150  # minimum to give MA99 enough history
# detection_mode: conservative | aggressive — modo del detector (equal lows vs min-low)
LSE_DETECTION_MODE = getattr(config, "LSE_DETECTION_MODE", "conservative")
if LSE_DETECTION_MODE not in ("conservative", "aggressive"):
    LSE_DETECTION_MODE = "conservative"
# Si True: por símbolo prueba aggressive y conservative (reset SM entre intentos) y elige mayor score
LSE_DUAL_SCAN = getattr(config, "LSE_DUAL_SCAN", True)
# entry_mode enviado al API: aggressive (cierre reclaim) | conservative (ruptura high)
LSE_ENTRY_MODE = getattr(config, "LSE_ENTRY_MODE", "conservative")
if LSE_ENTRY_MODE not in ("conservative", "aggressive"):
    LSE_ENTRY_MODE = "conservative"
LSE_HTTP_TIMEOUT_SEC = int(getattr(config, "LSE_HTTP_TIMEOUT_SEC", 360))
LSE_MAX_SYMBOLS_PER_CYCLE = int(getattr(config, "LSE_MAX_SYMBOLS_PER_CYCLE", 200))
LSE_BATCH_TOP_K = int(getattr(config, "LSE_BATCH_TOP_K", 10))
LSE_MAX_INJECTED_CANDIDATES = int(getattr(config, "LSE_MAX_INJECTED_CANDIDATES", 10))
LSE_REQUIRE_SCAN_BEFORE_ENTRY = getattr(config, "LSE_REQUIRE_SCAN_BEFORE_ENTRY", True)
LSE_MIN_SYMBOLS_PROCESSED_GATE = int(getattr(config, "LSE_MIN_SYMBOLS_PROCESSED_GATE", 1))
LSE_REQUIRE_ALL_QUEUED_PROCESSED = getattr(config, "LSE_REQUIRE_ALL_QUEUED_PROCESSED", True)
AGENT_MAX_CANDIDATES_PER_CYCLE = int(getattr(config, "AGENT_MAX_CANDIDATES_PER_CYCLE", 10))

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
        self.active_profiles = []

        self._tier3_index = 0
        self._last_profile_sync = 0

        # ── Redis Signal Bridge ──────────────────────────────────────────
        # Escucha el canal verge:superscore publicado por el backend C#.
        # Cuando el backend detecta TRUTHUSDT al 75%, el agente lo recibe
        # en tiempo real y lo inyecta como candidato sin importar el watchlist.
        _redis_url = getattr(config, "REDIS_URL", "redis://localhost:6379/0")
        self._bridge = RedisSignalBridge(redis_url=_redis_url)
        bridge_ok = self._bridge.start()
        if not bridge_ok:
            logger.warning(
                "[BRIDGE] Redis Signal Bridge no disponible. "
                "El agente opera normalmente pero sin señales en tiempo real del backend C#."
            )

        logger.info(
            f"Watchlist: T1={len(config.WATCHLIST_TIER1)} | "
            f"T2={len(config.WATCHLIST_TIER2)} | "
            f"T3={len(config.WATCHLIST_TIER3)} | "
            f"Total={len(config.WATCHLIST)}"
        )
        self.active_profiles = []

    @staticmethod
    def _json_safe_for_audit(obj, depth: int = 0):
        """Limit depth/size so snapshots stay persistible (PostgreSQL text)."""
        if depth > 10:
            return "[max-depth]"
        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, str):
            return obj if len(obj) < 8000 else obj[:7997] + "..."
        if isinstance(obj, dict):
            out = {}
            for i, (k, v) in enumerate(obj.items()):
                if i > 80:
                    out["_truncated_keys"] = len(obj) - 80
                    break
                sk = str(k)
                if sk in ("candles", "klines", "raw_klines", "ohlc"):
                    continue
                out[sk] = VergeAgent._json_safe_for_audit(v, depth + 1)
            return out
        if isinstance(obj, (list, tuple)):
            if len(obj) > 120:
                return [
                    VergeAgent._json_safe_for_audit(obj[0], depth + 1),
                    f"... (+{len(obj) - 1} items)",
                ]
            return [VergeAgent._json_safe_for_audit(v, depth + 1) for v in obj]
        return str(obj)

    def _build_agent_decision_snapshot(
        self,
        candidate: dict,
        pos_details: dict,
        entry_reason: str,
        nexus_group: str,
        tier: str,
        setup_metrics: Optional[dict] = None,
        setup_skip: Optional[str] = None,
    ) -> str:
        snap = {
            "schema_version": 1,
            "agent_version": "risk_v5",
            "experiment": "post_sl_fix_may_2026",
            "captured_at_utc": datetime.utcnow().isoformat() + "Z",
            "agent_meta": {
                "entry_reason": entry_reason,
                "nexus_group": nexus_group,
                "tier": tier,
                "setup_validation": setup_skip or "ok",
                "setup_metrics": self._json_safe_for_audit(copy.deepcopy(setup_metrics or {})),
            },
            "candidate": self._json_safe_for_audit(copy.deepcopy(candidate)),
            "position_sizing": self._json_safe_for_audit(copy.deepcopy(pos_details)),
        }
        try:
            return json.dumps(snap, ensure_ascii=False)
        except Exception as ex:
            logger.warning("Audit snapshot serialization failed: %s", ex)
            return json.dumps(
                {"schema_version": 1, "error": str(ex), "symbol": candidate.get("symbol")},
                ensure_ascii=False,
            )

    def run(self):
        logger.info(f"Agent started. Loop interval: {config.LOOP_INTERVAL_SECONDS}s.")
        logger.info("[CONFIG] Agent Version: risk_v4.0 (segregated metrics ON)")

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
        try:
            config.refresh_watchlist()
        except Exception as e:
            logger.error(f"Failed to refresh watchlist: {e}")
        logger.info("--- Starting new analysis cycle ---")

        # 0. Check exchange health
        breakers     = get_breakers()
        available    = [name for name, cb in breakers.items() if cb.is_available]
        is_degraded  = len(available) == 0

        if available:
            logger.info(f"[MultiExchange] Active sources: {available}")
        else:
            logger.warning("[MultiExchange] ALL exchange sources unavailable — running on cache only.")

        # 1. Sync profiles and monitor open positions
        logger.info("[Step 1/6] Syncing strategy profiles and checking positions...")
        db_profiles = self.positions.get_strategy_profiles() or []
        
        # Define the virtual legacy profile for "Standard Scalping"
        legacy_profile = {
            "id": None,
            "name": "Standard Scalping",
            "minConfluenceScore": config.MIN_CONFLUENCE_SCORE,
            "minNexusConfidence": getattr(config, "MIN_ENTRY_NEXUS", 70.0),
            "tpMultiplier": getattr(config, "TP_MULTIPLIER", 2.0),
            "slMultiplier": getattr(config, "SL_MULTIPLIER", 1.0),
            "marginPerTrade": getattr(config, "MAX_MARGIN_PER_TRADE_USD", 150),
            "maxOpenPositions": config.MAX_OPEN_POSITIONS,
            "allowLong": True,
            "allowShort": True,
            "allowedSources": ["nexus", "scar", "redis_bridge"],
            "isActive": True
        }

        # The active profiles list will ALWAYS include Standard Scalping + any DB profile
        self.active_profiles = [legacy_profile] + db_profiles
        
        logger.info(f"Active strategies this cycle: {[p['name'] for p in self.active_profiles]}")

        self._manage_open_positions()
        logger.info("[Step 1/6] Done.")

        # 2. LSE — LiquiditySweepEngine (antes de Nexus). Candidato LSE compite en el ranking final;
        #    si LSE_REQUIRE_SCAN_BEFORE_ENTRY, no se opera si el batch no terminó bien (mismo ciclo, misma decisión).
        lse_candidates: list[dict] = []
        lse_meta: dict = {}
        if LSE_ENABLED:
            logger.info("[Step 2/6] Running LSE (Liquidity Sweep Engine)...")
            lse_candidates, lse_meta = self._run_lse_scan()
            if lse_candidates:
                top = lse_candidates[0]
                logger.info(
                    "[Step 2/6] LSE: %d ranked candidate(s); top=%s | Score=%.1f | mode=%s",
                    len(lse_candidates),
                    top.get("symbol"),
                    float(top.get("confluence_score", 0.0)),
                    top.get("lse_detection_mode"),
                )
            else:
                logger.info("[Step 2/6] LSE: no signal this cycle.")

        # 2. Check daily limits (max open positions is now handled at execution time for upgrades)

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

        # 4. Fetch Nexus-15 Top candidates from the backend (same data as UI "TOP" button)
        #    The .NET backend downloads 1000 fresh candles from Binance and runs the full model.
        #    This is equivalent to clicking "TOP DE NEXUS-15" in the UI — we just automate it.
        logger.info("[Step 4/6] Fetching Nexus-15 TOP from backend...")
        nexus_top_candidates = self._fetch_nexus_top(top_n=10)
        if nexus_top_candidates:
            logger.info(
                "[Step 4/6] Nexus-15 TOP: %d candidates from backend (top: %s @ %.1f%%)",
                len(nexus_top_candidates),
                nexus_top_candidates[0].get("symbol"),
                nexus_top_candidates[0].get("nexus_confidence", 0),
            )
        else:
            logger.info("[Step 4/6] Nexus-15 TOP: no results from backend (offline or no signal).")

        # 5. Run Nexus-15 on all watchlist symbols (internal scan with local data)
        candidates = []
        skipped_trading = 0
        analyzed = 0
        no_data = 0
        broadcast_batch = []

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

                # 🟢 BROADCAST: Batch scores to UI scanner (avoid request spam)
                broadcast_batch.append(confluence)

                if confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE:
                    enriched = dict(confluence)
                    enriched["agent_audit_context"] = {
                        "nexus15": self._json_safe_for_audit(nexus_data),
                        "scar": self._json_safe_for_audit(scar_data) if scar_data else {},
                    }

                    # ── BONUS SMC: Aplicar bonus de calidad antes del ranking ──
                    # Usamos price_at_signal (last_close de Nexus) para validar sin latencia REST
                    px_val = enriched.get("price_at_signal") or self.fetcher.get_current_price(symbol)
                    if px_val:
                        v_ok, v_code, v_metrics = validate_pre_trade(enriched, px_val)
                        if v_ok:
                            if "smc_bonus" in v_metrics:
                                bonus = float(v_metrics["smc_bonus"])
                                enriched["confluence_score"] += bonus
                                enriched["smc_bonus_applied"] = bonus

                            candidates.append(enriched)
                            logger.info(
                                f"✅ CANDIDATE: {symbol} | Score={enriched['confluence_score']:.1f} | "
                                f"Dir={enriched['trade_direction']} | Nexus={enriched['nexus_confidence']}%" +
                                (f" | SMC Bonus=+{enriched['smc_bonus_applied']}" if "smc_bonus_applied" in enriched else "")
                            )
                        else:
                            logger.info(f"❌ [VETO] {symbol} rechazado en scan: {v_code}")
            except Exception as e:
                logger.error(f"⚠️ Error analyzing {symbol}: {e}")
                continue

        # Flush batch once per cycle (one HTTP request instead of ~183)
        try:
            if broadcast_batch:
                self.positions.broadcast_signals(broadcast_batch)
        except Exception as e:
            logger.warning(f"⚠️ Failed to broadcast batch signals: {e}")

        logger.info(
            f"[Step 5/6] Done: {analyzed} analyzed | "
            f"{len(candidates)} candidates | {skipped_trading} skipped | {no_data} no data"
        )

        # Inject Nexus-15 TOP candidates as high-priority entries
        for nc in nexus_top_candidates:
            # Avoid duplicate symbols already found in internal scan
            existing_syms = {c["symbol"] for c in candidates}
            if nc["symbol"] not in existing_syms:
                candidates.append(nc)
                logger.info(
                    "[NEXUS-TOP] Injected: %s | Nexus=%.1f%% | Dir=%s",
                    nc["symbol"], nc.get("nexus_confidence", 0), nc.get("trade_direction", "?")
                )

        if lse_candidates:
            for lc in lse_candidates:
                candidates.append(lc)
            top = lse_candidates[0]
            logger.info(
                "[Step 5/6] Added %d LSE candidate(s) to final ranking (top: %s @ %.1f)",
                len(lse_candidates),
                top.get("symbol"),
                float(top.get("confluence_score", 0.0)),
            )

        # ── Redis Signal Bridge: inyectar señales calientes con validación en tiempo real ──
        # Antes de inyectar cualquier señal del backend C#, el agente verifica que siga vigente:
        #   1. Edad: descarta señales más viejas que BRIDGE_MAX_AGE_SECONDS
        #   2. Precio: si el precio se movió > BRIDGE_MAX_PRICE_MOVE_PCT desde el signal → SKIP (llegamos tarde)
        #   3. Nexus-15 fresco: llama Nexus-15 on-demand sobre el símbolo y valida que la dirección coincida
        #   4. Solo si pasa todo → se inyecta al ranking
        self._bridge.purge_expired()
        bridge_min_score  = float(getattr(config, "BRIDGE_MIN_SCORE", config.MIN_CONFLUENCE_SCORE))
        bridge_max_age    = float(getattr(config, "BRIDGE_MAX_AGE_SECONDS", 480.0))   # 8 min default
        bridge_max_move   = float(getattr(config, "BRIDGE_MAX_PRICE_MOVE_PCT", 0.025)) # 2.5% default
        hot_signals = self._bridge.get_hot_signals(
            min_score=bridge_min_score,
            max_age_seconds=bridge_max_age,
        )
        existing_syms = {c.get("symbol") for c in candidates}
        injected = 0

        for sig in hot_signals:
            sym          = sig["symbol"]
            bridge_score = sig["score"]
            sig_age_s    = time.time() - sig.get("received_at", 0)

            if self._should_skip(sym):
                continue

            if sym in existing_syms:
                # Símbolo que el watchlist ya encontró: solo boost de score, sin re-validar
                for c in candidates:
                    if c.get("symbol") == sym:
                        old = c.get("confluence_score", 0)
                        c["confluence_score"] = max(old, bridge_score)
                        c["bridge_boosted"] = True
                continue

            # ── Validación 1: Precio actual vs precio al momento del signal ──────
            # Si el mercado ya se movió > bridge_max_move desde que llegó la señal,
            # significa que el movimiento ya ocurrió y entrar ahora es perseguir el precio.
            current_px = self.fetcher.get_current_price(sym)
            if current_px and current_px > 0:
                sig_price = float(sig.get("price", 0) or 0)
                if sig_price > 0:
                    move_pct = abs(current_px - sig_price) / sig_price
                    if move_pct > bridge_max_move:
                        logger.info(
                            "[BRIDGE] SKIP %s — precio ya se movió %.2f%% desde el signal "
                            "(límite=%.1f%%, age=%.0fs). Llegamos tarde.",
                            sym, move_pct * 100, bridge_max_move * 100, sig_age_s,
                        )
                        continue

            # ── Validación 2: Nexus-15 fresco — confirma dirección en tiempo real ──
            # Llama al python-service Nexus-15 sobre el símbolo AHORA, no con el caché.
            # EXCEPCIÓN: Si la señal viene de la UI (nexus15_ui), ya tiene 1000 velas procesadas, 
            # usar sus features directamente en lugar de degradar la señal con un re-cálculo local.
            if sig.get("source") == "nexus15_ui":
                nexus_fresh = {
                    "prediction": sig.get("direction", ""),
                    "ai_confidence": sig.get("nexus15", 0),
                    "features": sig.get("features", {}),
                    "group_scores": sig.get("groupScores", {}),
                }
            else:
                try:
                    # FETCH 1000 CANDLES to guarantee identical features to the .NET backend/UI.
                    # A 300-candle fallback destroys volume_ratio_20 and RSI accuracy.
                    nexus_fresh = self.signals.get_nexus15_prediction(sym, limit=1000)
                except Exception as ex:
                    logger.warning("[BRIDGE] No se pudo obtener Nexus-15 para %s: %s — descartando.", sym, ex)
                    continue

            if not nexus_fresh:
                logger.info(
                    "[BRIDGE] SKIP %s — Nexus-15 sin datos frescos (age=%.0fs).", sym, sig_age_s
                )
                continue

            nexus_dir   = str(nexus_fresh.get("prediction", "")).upper()   # BULLISH/BEARISH/NEUTRAL
            nexus_conf  = float(nexus_fresh.get("ai_confidence", 0))
            nexus_reco  = str(nexus_fresh.get("features", {}).get("nexus_recommendation", "")).lower()
            bridge_dir  = sig.get("direction", "").upper()

            # Si Nexus-15 recomienda esperar → señal caducada
            if nexus_reco in ("wait", "hold"):
                logger.info(
                    "[BRIDGE] SKIP %s — Nexus-15 fresco recomienda '%s' (bridge_dir=%s, age=%.0fs).",
                    sym, nexus_reco, bridge_dir, sig_age_s,
                )
                continue

            # Mapa de dirección normalizado
            bull_dirs = {"BULLISH", "LONG", "LONG "}
            bear_dirs = {"BEARISH", "SHORT"}
            bridge_is_bull = bridge_dir in bull_dirs
            nexus_is_bull  = nexus_dir in bull_dirs
            nexus_is_bear  = nexus_dir in bear_dirs

            direction_conflict = (bridge_is_bull and nexus_is_bear) or (not bridge_is_bull and nexus_is_bull)
            if direction_conflict:
                logger.info(
                    "[BRIDGE] SKIP %s — Nexus-15 contradice dirección bridge "
                    "(bridge=%s nexus=%s conf=%.0f%% age=%.0fs).",
                    sym, bridge_dir, nexus_dir, nexus_conf, sig_age_s,
                )
                continue

            # ── Todo OK: señal vigente y confirmada ─────────────────────────────
            # Score final = promedio ponderado bridge (40%) + Nexus-15 fresco (60%)
            final_score = bridge_score * 0.40 + nexus_conf * 0.60
            direction_map = {"LONG": 0, "BULLISH": 0, "SHORT": 1, "BEARISH": 1}
            side = direction_map.get(bridge_dir, 0)

            bridge_cand = {
                "symbol":           sym,
                "confluence_score": final_score,
                "nexus_confidence": nexus_conf,
                "trade_direction":  bridge_dir,
                "side":             side,
                "source":           "redis_bridge",
                "estimated_range_pct": sig.get("estimatedRangePercent", 0.0),
                "bridge_regime":    sig.get("regime", "Unknown"),
                "bridge_score_raw": bridge_score,
                "bridge_age_s":     round(sig_age_s, 1),
                "agent_audit_context": {
                    "nexus15": self._json_safe_for_audit(nexus_fresh),
                    "scar":    {},
                    "bridge":  sig,
                },
            }

            # ── BONUS SMC: Aplicar bonus de calidad antes del ranking (Bridge) ──
            v_ok, v_code, v_metrics = validate_pre_trade(bridge_cand, current_px)
            if v_ok:
                if "smc_bonus" in v_metrics:
                    bonus = float(v_metrics["smc_bonus"])
                    bridge_cand["confluence_score"] += bonus
                    bridge_cand["smc_bonus_applied"] = bonus
                    logger.info("[BRIDGE] %s bonus SMC detectado: +%.1f score", sym, bonus)

                candidates.append(bridge_cand)
                existing_syms.add(sym)
                injected += 1
            else:
                logger.info("[BRIDGE] %s filtrado por validación pre-ranking: %s", sym, v_code)
            logger.info(
                "[BRIDGE] ✅ VALIDADO %s | BridgeScore=%.0f | Nexus15=%.0f%% | "
                "FinalScore=%.1f | Dir=%s | Age=%.0fs",
                sym, bridge_score, nexus_conf, final_score, bridge_dir, sig_age_s,
            )

        if injected > 0:
            logger.info(
                "[BRIDGE] %d símbolo(s) inyectados y validados desde backend C# "
                "(bridge_stats=%s)", injected, self._bridge.stats()
            )

        if self.state.is_lse_kill_switch_active():
            logger.info("[KILL] LSE Kill switch active. Filtering LSE candidates.")
            candidates = [c for c in candidates if c.get("source") != "LSE"]

        # 6. For EACH active profile: rank and execute candidates
        active_trades = self.positions.get_active_trades() or []
        
        for profile in self.active_profiles:
            p_name = profile.get("name", "Unknown")
            p_id = profile.get("id")
            logger.info(f"--- Strategy Execution: {p_name} ---")

            # Filter candidates for THIS profile
            p_candidates = []
            min_score = float(profile.get("minConfluenceScore", config.MIN_CONFLUENCE_SCORE))
            min_nexus = float(profile.get("minNexusConfidence", 70.0))

            batch_ok = True
            if LSE_ENABLED and LSE_REQUIRE_SCAN_BEFORE_ENTRY:
                sp = int(lse_meta.get("symbols_processed") or 0)
                queued = int(lse_meta.get("items_queued") or 0)
                ok = bool(lse_meta.get("batch_http_ok"))
                called = bool(lse_meta.get("batch_called"))
                min_symbols_ok = sp >= LSE_MIN_SYMBOLS_PROCESSED_GATE
                full_scan_ok = (not LSE_REQUIRE_ALL_QUEUED_PROCESSED) or (queued > 0 and sp >= queued)
                batch_ok = bool(called and ok and min_symbols_ok and full_scan_ok)

            for c in candidates:
                if c.get("source") == "LSE":
                    if not batch_ok: continue
                    if self.state.is_lse_symbol_cooldown_active(c.get("symbol")): continue

                if c.get("confluence_score", 0) < min_score:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: score {c.get('confluence_score')} < {min_score}")
                    continue
                if c.get("source") != "LSE" and c.get("nexus_confidence", 0) < min_nexus:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: nexus {c.get('nexus_confidence')} < {min_nexus}")
                    continue
                
                # Check if sources are allowed
                allowed = profile.get("allowedSources")
                if allowed:
                    src = (c.get("source", "") or "").lower()
                    # Normalize agent internal sources to match .NET StrategyProfile enum values
                    if src in ("nexus_top", "nexus15_ui"):
                        src = "nexus"
                    elif src == "redis_bridge":
                        src = "bridge"
                        
                    if isinstance(allowed, list):
                        if src not in [s.lower() for s in allowed]:
                            logger.info(f"[{p_name}] SKIP {c.get('symbol')}: src {src} not in {allowed}")
                            continue
                    elif isinstance(allowed, str):
                        # .NET serializes as "LSE,Nexus,Bridge"
                        allowed_list = [s.strip().lower() for s in allowed.split(",")]
                        if src not in allowed_list:
                            logger.info(f"[{p_name}] SKIP {c.get('symbol')}: src {src} not in {allowed_list}")
                            continue
                
                # Profile side filters
                allow_long = profile.get("allowLong", True)
                allow_short = profile.get("allowShort", True)
                cand_side = int(c.get("side", 0))
                
                if cand_side == 0 and not allow_long:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: Long not allowed")
                    continue
                if cand_side == 1 and not allow_short:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: Short not allowed")
                    continue

                # Fix 2: Filtros RSI y MA7 por perfil (PascalCase del DTO -> camelCase del JSON)
                max_rsi_long  = profile.get("maxRsiLong")
                min_rsi_short = profile.get("minRsiShort")
                cand_rsi = float(c.get("rsi", 50))

                if max_rsi_long is not None and cand_side == 0:
                    if cand_rsi > float(max_rsi_long):
                        logger.info(f"[VETO] {c['symbol']} RSI {cand_rsi} > max {max_rsi_long} for profile {p_name}")
                        continue

                if min_rsi_short is not None and cand_side == 1:
                    if cand_rsi < float(min_rsi_short):
                        logger.info(f"[VETO] {c['symbol']} RSI {cand_rsi} < min {min_rsi_short} for profile {p_name}")
                        continue

                # Filtro distancia MA7 por perfil
                max_dist_ma7 = profile.get("maxMa7DistancePct")
                if max_dist_ma7 is not None:
                    dist = abs(float(c.get("distance_to_ma7_pct", 0)))
                    if dist > float(max_dist_ma7):
                        logger.info(f"[VETO] {c['symbol']} MA7 Dist {dist:.2f}% > max {max_dist_ma7}% for profile {p_name}")
                        continue

                p_candidates.append(c)

            if not p_candidates:
                logger.info(f"No candidates pass profile {p_name}")
                continue

            p_candidates.sort(key=lambda x: x["confluence_score"], reverse=True)
            
            # Check slot availability for this profile
            p_max_pos = int(profile.get("maxOpenPositions", config.MAX_OPEN_POSITIONS))
            # Fix 3: Contador robusto para camelCase (API) y snake_case (Local)
            p_active_count = len([
                t for t in active_trades 
                if t.get("strategyProfileId", t.get("strategy_profile_id")) == p_id
            ])
            
            if p_active_count >= p_max_pos:
                logger.info(f"[LIMIT] Profile {p_name} is full ({p_active_count}/{p_max_pos}). Skipping new trades.")
                continue

            # Try ranked candidates in order (LSE + Nexus); AGENT_MAX_CANDIDATES_PER_CYCLE enables rank 2..N fallback.
            max_try = max(1, AGENT_MAX_CANDIDATES_PER_CYCLE)
            p_ranked = p_candidates[:max_try]
            
            for idx, cand in enumerate(p_ranked):
                sym = cand.get("symbol", "")
                if self._execute_trade(cand, profile=profile):
                    logger.info(f"✅ Trade executed for profile {p_name} on {sym}")
                    # Update active_trades list for next profile in same cycle
                    active_trades = self.positions.get_active_trades() or []
                    break


    # ─────────────────────────────────────────────────────────
    # Nexus-15 Top Backend Injection
    # ─────────────────────────────────────────────────────────
    def _fetch_nexus_top(self, top_n: int = 10) -> list[dict]:
        """
        Calls the .NET backend's Top Nexus-15 endpoint (simulating the UI button).
        The backend performs an aggressive scan using 1000 fresh candles for each asset.
        Returns mapped candidates ready for injection into the ranking.
        """
        url = f"{config.ABP_BACKEND_URL}/api/app/nexus15/analyze-top-available?topN={top_n}"
        try:
            # We wait up to 180 seconds because the backend fetches 1000 candles from Binance sequentially
            headers = self.auth.get_auth_headers()
            r = requests.post(url, headers=headers, verify=False, timeout=180)
            if r.status_code == 200:
                results = r.json()
                candidates = []
                for res in results:
                    direction = res.get("direction", "NEUTRAL")
                    if direction not in ("BULLISH", "BEARISH"):
                        continue
                        
                    conf = res.get("aiConfidence", 0.0)
                    if conf < 60.0:  # Only inject strong signals
                        continue
                        
                    # Map to the agent's internal format
                    cand = {
                        "symbol": res.get("symbol"),
                        "confluence_score": 85.0 + (conf / 100.0 * 15.0), # Guarantee high rank (85 - 100)
                        "trade_direction": direction,
                        "side": 0 if direction == "BULLISH" else 1,
                        "nexus_confidence": conf,
                        "estimated_range_pct": res.get("estimatedRangePercent", 0.0),
                        "source": "nexus_top",
                        "price_at_signal": None, # Will be fetched dynamically
                        "agent_audit_context": {
                            "nexus15": res
                        }
                    }
                    candidates.append(cand)
                return candidates
            else:
                logger.warning(f"[NEXUS-TOP] Backend error: HTTP {r.status_code}")
                return []
        except requests.exceptions.Timeout:
            logger.warning("[NEXUS-TOP] Backend timed out after 180s (scan took too long).")
            return []
        except Exception as e:
            logger.warning(f"[NEXUS-TOP] Failed to fetch Top Nexus: {e}")
            return []


    # ─────────────────────────────────────────────────────────
    # LSE Integration
    # ─────────────────────────────────────────────────────────
    def _get_lse_candles(self, symbol: str, timeframe: str = "1h") -> list:
        """
        Velas para LSE: lee caché y hace backfill REST si hace falta (igual que Nexus con 15m).
        """
        try:
            if timeframe == "1h":
                raw = self.fetcher.get_klines_for_lse(
                    symbol, "1h", limit=LSE_CANDLE_LIMIT_1H, min_cache=120
                )
                if not raw or len(raw) < 120:
                    return []
            else:
                raw = self.fetcher.get_klines_for_lse(symbol, timeframe, limit=120, min_cache=30)
                if not raw:
                    return []

            result = []
            for k in raw:
                result.append({
                    "timestamp": str(k.get("timestamp", k.get("openTime", 0))),
                    "open":      float(k.get("open",  0)),
                    "high":      float(k.get("high",  0)),
                    "low":       float(k.get("low",   0)),
                    "close":     float(k.get("close", 0)),
                    "volume":    float(k.get("volume", 0)),
                })
            return result
        except Exception as e:
            logger.warning("[LSE] Error building candles for %s %s: %s", symbol, timeframe, e)
            return []

    def _lse_row_to_candidate(self, symbol: str, sig: dict, dm_used: str) -> dict:
        """Traduce señal LSE (dict JSON) → candidato alineado con Nexus para el ranking final."""
        lse_snap = {
            k: sig.get(k)
            for k in (
                "score", "state", "timeframe", "detection_mode", "entry_mode",
                "entry_price", "stop_loss", "take_profit_1", "take_profit_2",
                "sweep_low", "sweep_high", "reclaim_close", "sub_scores", "reasoning",
                "volume_ratio", "compression_pct", "ma7", "ma25", "ma99", "atr",
            )
        }
        return {
            "symbol":           symbol,
            "confluence_score": sig.get("score", 0.0),
            "trade_direction":  "BULLISH",
            "side":             0,
            "scar_score":       0,
            "nexus_confidence": 0,
            "nexus_direction":  "BULLISH",
            "regime":           "LSE_SPRING",
            "volume_explosion": True,
            "group_scores":     {},
            "rsi":              50,
            "estimated_range_pct": abs(
                (sig.get("take_profit_1", 0) - sig.get("entry_price", 1)) /
                max(sig.get("entry_price", 1), 1e-10) * 100
            ),
            "reasons": sig.get("reasoning", []),
            "lse_entry_price":   sig.get("entry_price"),
            "lse_stop_loss":     sig.get("stop_loss"),
            "lse_take_profit_1": sig.get("take_profit_1"),
            "lse_take_profit_2": sig.get("take_profit_2"),
            "lse_reclaim_close": sig.get("reclaim_close"),
            "lse_atr":           sig.get("atr"),
            "lse_ma99":          sig.get("ma99"),
            "lse_timeframe":     sig.get("timeframe") or "1h",
            "lse_sweep_high":    sig.get("sweep_high"),
            "lse_score":         sig.get("score"),
            "lse_detection_mode": dm_used,
            "source":            "LSE",
            "agent_audit_context": {
                "nexus15": {},
                "scar": {},
                "lse_signal": self._json_safe_for_audit(lse_snap),
            },
        }

    def _run_lse_scan_per_symbol_fallback(
        self,
        batch_items: list[dict],
        modes_order: list[str],
        base_py: str,
    ) -> tuple[list[dict], dict]:
        """
        Imágenes Docker antiguas sin /lse/scan-batch (404): misma lógica vía POST /lse/scan.
        """
        scan_url = f"{base_py}/lse/scan"
        hits: list[tuple[float, str, dict, str]] = []
        symbols_completed = 0

        for item in batch_items:
            symbol = item["symbol"]
            tf = item["timeframe"]
            c1h = item["candles_1h"]
            c4h = item["candles_4h"]
            sym_break = False
            for dm in modes_order:
                if len(modes_order) > 1:
                    try:
                        requests.post(
                            f"{base_py}/lse/reset-state/{symbol}",
                            params={"timeframe": tf},
                            timeout=3,
                        )
                    except Exception:
                        pass
                try:
                    r = requests.post(
                        scan_url,
                        json={
                            "symbol": symbol,
                            "timeframe": tf,
                            "candles_1h": c1h,
                            "candles_4h": c4h,
                            "entry_mode": LSE_ENTRY_MODE,
                            "detection_mode": dm,
                        },
                        timeout=LSE_HTTP_TIMEOUT_SEC,
                    )
                except requests.exceptions.Timeout:
                    logger.warning("[LSE] fallback timeout %s mode=%s", symbol, dm)
                    sym_break = True
                    break
                except Exception as e:
                    logger.warning("[LSE] fallback error %s: %s", symbol, e)
                    sym_break = True
                    break
                if r.status_code != 200:
                    logger.warning(
                        "[LSE] fallback HTTP %s %s: %s",
                        r.status_code,
                        symbol,
                        (r.text or "")[:200],
                    )
                    sym_break = True
                    break
                data = r.json()
                if data.get("signal_found") and data.get("signal"):
                    sig = data["signal"]
                    hits.append((float(sig.get("score", 0.0)), symbol, sig, dm))
            if not sym_break:
                symbols_completed += 1

        meta_ok = {
            "batch_called": True,
            "batch_http_ok": symbols_completed > 0,
            "symbols_processed": symbols_completed,
            "items_queued": len(batch_items),
            "reason": "fallback_per_symbol" if symbols_completed else "fallback_failed",
        }
        logger.info(
            "[LSE] Fallback (/lse/scan): symbols_completed=%d/%d | hits=%d",
            symbols_completed,
            len(batch_items),
            len(hits),
        )

        hits.sort(key=lambda x: x[0], reverse=True)
        best_by_symbol: dict[str, tuple[float, dict, str]] = {}
        for sc, symbol, sig, dm in hits:
            if sc < LSE_MIN_SCORE:
                continue
            sym_u = str(symbol or "").strip().upper()
            if not sym_u:
                continue
            prev = best_by_symbol.get(sym_u)
            if prev is None or sc > prev[0]:
                best_by_symbol[sym_u] = (sc, sig, dm)

        inject_cap = min(LSE_MAX_INJECTED_CANDIDATES, LSE_BATCH_TOP_K)
        ranked = sorted(best_by_symbol.items(), key=lambda kv: kv[1][0], reverse=True)
        out: list[dict] = []
        for sym_u, (sc, sig, dm) in ranked[:inject_cap]:
            out.append(self._lse_row_to_candidate(sym_u, sig, dm))

        if out:
            logger.info(
                "[LSE] Fallback: injecting %d LSE candidate(s) (cap=%d); top=%s @ %.1f",
                len(out),
                inject_cap,
                out[0].get("symbol"),
                float(out[0].get("confluence_score", 0.0)),
            )
            return out, meta_ok

        if hits:
            sc, symbol, _, _ = hits[0]
            logger.info(
                "[LSE] No signal ≥ LSE_MIN_SCORE (%.1f); best fallback was %s @ %.1f",
                LSE_MIN_SCORE,
                symbol,
                sc,
            )
        else:
            logger.info("[LSE] Fallback: no LSE signals this cycle.")

        return [], meta_ok

    def _run_lse_scan(self) -> tuple[list[dict], dict]:
        """
        TOP-K LSE vía POST /lse/scan-batch. Velas 1h/4h con backfill REST si la caché no alcanza.

        Retorna (lista de candidatos rankeados por score, meta) para el candado LSE_REQUIRE_SCAN_BEFORE_ENTRY.
        """
        empty = {
            "batch_called": False,
            "batch_http_ok": False,
            "symbols_processed": 0,
            "items_queued": 0,
            "reason": None,
        }

        # open_count early return removed to allow LSE candidates to trigger an upgrade

        if not self.state.can_trade_today():
            logger.debug("[LSE] Daily trade limit reached — skip LSE scan.")
            return [], {**empty, "reason": "daily_limit"}

        targets = LSE_SYMBOLS if LSE_SYMBOLS else config.WATCHLIST
        base_py = config.PYTHON_SERVICE_URL.rstrip("/")
        batch_url = f"{base_py}/lse/scan-batch"

        modes_order = (
            ["aggressive", "conservative"] if LSE_DUAL_SCAN else [LSE_DETECTION_MODE]
        )
        skipped_no_history = 0
        skipped_open_or_traded = 0
        batch_items: list[dict] = []

        for symbol in targets:
            if len(batch_items) >= LSE_MAX_SYMBOLS_PER_CYCLE:
                break
            try:
                if self._should_skip(symbol):
                    skipped_open_or_traded += 1
                    continue

                candles_1h = self._get_lse_candles(symbol, "1h")
                if len(candles_1h) < 120:
                    skipped_no_history += 1
                    continue

                candles_4h = self._get_lse_candles(symbol, "4h")
                batch_items.append({
                    "symbol": symbol,
                    "timeframe": "1h",
                    "candles_1h": candles_1h,
                    "candles_4h": candles_4h,
                })
            except Exception as e:
                logger.debug("[LSE] Error building batch item for %s: %s", symbol, e)

        logger.info(
            "[LSE] Batch prep: watchlist=%d | queued=%d | skipped(no_history)=%d | skipped(open/already_traded)=%d | timeout=%ds | top_k=%d | modes=%s",
            len(targets),
            len(batch_items),
            skipped_no_history,
            skipped_open_or_traded,
            LSE_HTTP_TIMEOUT_SEC,
            LSE_BATCH_TOP_K,
            modes_order,
        )

        if not batch_items:
            return [], {
                **empty,
                "reason": "no_batch_items",
            }

        # API contract: /lse/scan-batch acepta como máximo 50 items por request.
        batch_limit = 50
        chunks = [
            batch_items[i:i + batch_limit]
            for i in range(0, len(batch_items), batch_limit)
        ]
        signals: list[dict] = []
        sym_proc = 0

        for idx, chunk in enumerate(chunks, start=1):
            payload = {
                "items": chunk,
                "entry_mode": LSE_ENTRY_MODE,
                "detection_modes": modes_order,
                "top_k": LSE_BATCH_TOP_K,
                "preview_only": False,
            }

            try:
                resp = requests.post(batch_url, json=payload, timeout=LSE_HTTP_TIMEOUT_SEC)
            except requests.exceptions.Timeout:
                logger.warning(
                    "[LSE] scan-batch timeout chunk=%d/%d after %ss",
                    idx,
                    len(chunks),
                    LSE_HTTP_TIMEOUT_SEC,
                )
                return [], {
                    **empty,
                    "batch_called": True,
                    "items_queued": len(batch_items),
                    "symbols_processed": sym_proc,
                    "reason": "timeout",
                }
            except Exception as e:
                logger.warning("[LSE] scan-batch request failed chunk=%d/%d: %s", idx, len(chunks), e)
                return [], {
                    **empty,
                    "batch_called": True,
                    "items_queued": len(batch_items),
                    "symbols_processed": sym_proc,
                    "reason": "request_error",
                }

            if resp.status_code == 404:
                logger.warning(
                    "[LSE] scan-batch HTTP 404 (python-service sin endpoint). "
                    "Usando fallback /lse/scan por símbolo — reconstruí la imagen para /lse/scan-batch."
                )
                return self._run_lse_scan_per_symbol_fallback(
                    batch_items, modes_order, base_py
                )

            if resp.status_code != 200:
                logger.warning(
                    "[LSE] scan-batch HTTP %s (chunk %d/%d): %s",
                    resp.status_code,
                    idx,
                    len(chunks),
                    (resp.text or "")[:500],
                )
                return [], {
                    **empty,
                    "batch_called": True,
                    "items_queued": len(batch_items),
                    "symbols_processed": sym_proc,
                    "reason": f"http_{resp.status_code}",
                }

            data = resp.json()
            chunk_signals = data.get("signals") or []
            signals.extend(chunk_signals)
            sym_proc += int(data.get("symbols_processed") or 0)

        signals.sort(
            key=lambda r: float((r.get("signal") or {}).get("score", 0.0)),
            reverse=True,
        )
        meta_ok = {
            "batch_called": True,
            "batch_http_ok": True,
            "symbols_processed": sym_proc,
            "items_queued": len(batch_items),
            "reason": None,
        }
        logger.info(
            "[LSE] Batch result: chunks=%d | symbols_processed=%s | signals_returned=%d",
            len(chunks),
            sym_proc,
            len(signals),
        )

        best_by_symbol: dict[str, tuple[float, dict, str]] = {}
        for row in signals:
            sig = row.get("signal") or {}
            score = float(sig.get("score", 0.0))
            if score < LSE_MIN_SCORE:
                continue
            sym_u = str(row.get("symbol") or "").strip().upper()
            if not sym_u:
                continue
            dm = str(row.get("detection_mode") or LSE_DETECTION_MODE)
            prev = best_by_symbol.get(sym_u)
            if prev is None or score > prev[0]:
                best_by_symbol[sym_u] = (score, sig, dm)

        inject_cap = min(LSE_MAX_INJECTED_CANDIDATES, LSE_BATCH_TOP_K)
        ranked_pairs = sorted(best_by_symbol.items(), key=lambda kv: kv[1][0], reverse=True)
        lse_out: list[dict] = []
        for sym_u, (score, sig, dm) in ranked_pairs[:inject_cap]:
            lse_out.append(self._lse_row_to_candidate(sym_u, sig, dm))

        if lse_out:
            logger.info(
                "[LSE] Injected %d ranked candidate(s) (cap=%d); top=%s @ %.1f",
                len(lse_out),
                inject_cap,
                lse_out[0].get("symbol"),
                float(lse_out[0].get("confluence_score", 0.0)),
            )
            return lse_out, meta_ok

        if signals:
            best = signals[0]
            bs = best.get("signal") or {}
            logger.info(
                "[LSE] No signal ≥ LSE_MIN_SCORE (%.1f); best in batch was %s @ %.1f",
                LSE_MIN_SCORE,
                best.get("symbol"),
                float(bs.get("score", 0.0)),
            )
        else:
            logger.info("[LSE] Batch: no LSE signals this cycle.")

        return [], meta_ok



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

    @staticmethod
    def _timeframe_to_ms(tf: str) -> int:
        s = (tf or "1h").strip().lower()
        table = {
            "1m": 60_000,
            "3m": 180_000,
            "5m": 300_000,
            "15m": 900_000,
            "30m": 1_800_000,
            "1h": 3_600_000,
            "2h": 7_200_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }
        return table.get(s, 3_600_000)

    def _lse_follow_through_exit_reason(self, pos: dict) -> Optional[str]:
        """
        - fake_break_reclaim: hubo ruptura de sweep_high y dos velas seguidas cierran debajo del reclaim.
        - no_follow_through: en las primeras N velas post-apertura no se rompe sweep_high.
        """
        if not getattr(config, "LSE_FOLLOW_THROUGH_ENABLED", True):
            return None
        if pos.get("source") != "LSE" or int(pos.get("side", 0)) != 0:
            return None
        sh = pos.get("lse_sweep_high")
        if sh is None:
            return None
        try:
            sweep_high = float(sh)
        except (TypeError, ValueError):
            return None

        reclaim_raw = pos.get("lse_reclaim_close")
        reclaim_f: Optional[float] = None
        if reclaim_raw is not None:
            try:
                reclaim_f = float(reclaim_raw)
            except (TypeError, ValueError):
                reclaim_f = None

        tf = pos.get("lse_timeframe") or "1h"
        need = max(1, int(getattr(config, "LSE_FOLLOW_THROUGH_CANDLES", 2)))
        sym = pos["symbol"]
        opened_raw = pos.get("opened_at", "")
        try:
            if opened_raw.endswith("Z"):
                opened_dt = datetime.fromisoformat(opened_raw.replace("Z", "+00:00"))
            else:
                opened_dt = datetime.fromisoformat(opened_raw)
        except Exception:
            return None
        opened_ms = opened_dt.timestamp() * 1000
        tf_ms = self._timeframe_to_ms(tf)

        klines = self.fetcher.get_klines_for_lse(sym, tf, limit=max(need + 8, 20))
        if len(klines) < 2:
            return None

        now_ms = time.time() * 1000
        eligible: list = []
        for k in klines[:-1]:
            # Normalize key: REST fetcher may return 'open_time', 'openTime', or 't'
            raw_ot = k.get("open_time") or k.get("openTime") or k.get("t")
            if raw_ot is None:
                continue
            o = int(raw_ot)
            close_ts = o + tf_ms
            if close_ts > opened_ms and close_ts <= now_ms:
                eligible.append(k)

        def _get_open_time(kline):
            raw = kline.get("open_time") or kline.get("openTime") or kline.get("t") or 0
            return int(raw)

        eligible.sort(key=_get_open_time)

        if reclaim_f is not None and len(eligible) >= 3:
            for i, k in enumerate(eligible):
                if float(k["high"]) < sweep_high:
                    continue
                if i + 2 < len(eligible):
                    c1 = float(eligible[i + 1]["close"])
                    c2 = float(eligible[i + 2]["close"])
                    if c1 < reclaim_f and c2 < reclaim_f:
                        logger.info(
                            "[EXIT] fake_break_reclaim %s closes=%s,%s reclaim=%s",
                            sym,
                            c1,
                            c2,
                            reclaim_f,
                        )
                        return "fake_break_reclaim"
                break

        if len(eligible) < need:
            return None

        window = eligible[:need]
        max_h = max(float(k["high"]) for k in window)
        if max_h < sweep_high:
            logger.info(
                "[EXIT] no_follow_through %s max_high=%s sweep_high=%s (first %s candles)",
                sym,
                max_h,
                sweep_high,
                need,
            )
            return "no_follow_through"
        return None

    def _close_worst_position(self) -> bool:
        """Encuentra la peor posicion abierta (peor PnL) y la cierra para liberar cupo."""
        open_positions = self.state.get_open_positions()
        if not open_positions:
            return False

        worst_pos = None
        worst_pnl = float('inf')

        for pos in open_positions:
            symbol = pos["symbol"]
            entry_price = float(pos.get("entry_price", 0))
            side = int(pos.get("side", 0))

            current_price = self.fetcher.get_current_price(symbol)
            if current_price <= 0 or entry_price <= 0:
                continue

            if side == 0:  # LONG
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price

            if pnl_pct < worst_pnl:
                worst_pnl = pnl_pct
                worst_pos = pos

        if worst_pos:
            logger.info(f"UPGRADE: Cerrando la peor posicion ({worst_pos['symbol']}) con PnL: {worst_pnl*100:.2f}% para liberar cupo.")
            success = self.positions.close_trade(worst_pos["trade_id"])
            if success:
                # Fake data para el log del cerrado (simplificado)
                realized_pnl = worst_pos["margin"] * worst_pnl * worst_pos["leverage"]
                self.state.record_closed_trade_outcome(is_loss=True)
                self.report.log_trade_closed(worst_pos, {
                    "closePrice": current_price,
                    "realizedPnl": realized_pnl,
                    "status": 2
                })
                self.state.remove_position(worst_pos["trade_id"])
                return True
        return False

    def _execute_trade(self, candidate: dict, profile: dict = None) -> bool:
        symbol = candidate["symbol"]
        balance = self.positions.get_virtual_balance()
        setup_metrics: dict = {}

        market_px = self.fetcher.get_current_price(symbol)
        if market_px <= 0:
            logger.warning("[SKIP] %s invalid market price for setup validation", symbol)
            return False

        # Update staleness metric for VETO #4
        if candidate.get("scored_at"):
            import time
            candidate["scored_at_age_s"] = time.time() - candidate["scored_at"]

        ok, code, setup_metrics = validate_pre_trade(candidate, market_px, profile=profile)
        if not ok:
            logger.info("[SKIP] %s — %s | profile=%s | metrics=%s", code, symbol, profile.get("name") if profile else "Legacy", setup_metrics)
            return False

        setup_skip = "ok"

        pos_details = self.risk.calculate_position(symbol, candidate, available_balance=balance, profile=profile)

        if not pos_details:
            return False
        
        # Tag with strategy ID
        if profile and profile.get("id"):
            pos_details["strategy_profile_id"] = profile["id"]

        if setup_metrics:
            sz = pos_details.get("lse_sizing") or pos_details.get("nexus_sizing") or {}
            if sz:
                setup_metrics = {**setup_metrics, **sz}
        if candidate.get("source") == "LSE":
            m99 = candidate.get("lse_ma99")
            epx = candidate.get("lse_entry_price")
            if m99 is not None and epx is not None:
                try:
                    m99f = float(m99)
                    epf = float(epx)
                    if m99f > 0:
                        setup_metrics["distance_to_ma99_pct"] = round((epf - m99f) / m99f * 100, 4)
                except (TypeError, ValueError):
                    pass

        scar_score = candidate.get("scar_score", 0)
        nexus_conf = candidate.get("nexus_confidence", 0)
        confluence = candidate.get("confluence_score", 0)

        nexus_group = "Momentum Burst" if nexus_conf > 80 else ("Trend Following" if nexus_conf > 60 else "Mean Reversion")

        reason_parts = []
        if candidate.get("source") == "LSE":
            reason_parts.append(
                f"LSE spring [{candidate.get('lse_detection_mode', '')}] "
                f"score={candidate.get('lse_score', 0)} RR≈{setup_metrics.get('rr', 'n/a')}."
            )
        if nexus_conf > 0:
            reason_parts.append(f"Señal '{nexus_group}' en marco de 15m (Nexus: {nexus_conf}%).")
        if scar_score >= 4:
            reason_parts.append(f"Flujo de liquidez de ballenas detectado (SCAR: {scar_score}/5).")
        if confluence >= config.MIN_CONFLUENCE_SCORE and scar_score >= 4:
            reason_parts.append("Alineación confirmada entre SCAR y Nexus-15.")

        entry_reason = " ".join(reason_parts) if reason_parts else "Señal de momentum validada por el motor de riesgo."

        audit_json = self._build_agent_decision_snapshot(
            candidate,
            pos_details,
            entry_reason,
            nexus_group,
            self._get_tier_for_symbol(symbol),
            setup_metrics=setup_metrics if setup_metrics else None,
            setup_skip=setup_skip,
        )
        pos_details["agent_decision_json"] = audit_json

        # nexus_confidence es el % real de Nexus-15 (0 para candidatos LSE que no usan Nexus)
        nexus_conf_pct = float(candidate.get("nexus_confidence", 0))
        is_lse = candidate.get("source") == "LSE"

        # Sync con el backend para evitar desincronización de límite de posiciones
        active_trades = self.positions.get_active_trades()
        if active_trades is None:
            logger.error("[LIMIT] No se pudo conectar al backend para verificar posiciones activas. Abortando trade.")
            return False

        open_count = len(active_trades)
        if open_count >= config.MAX_OPEN_POSITIONS:
            if is_lse:
                # LSE nunca tiene nexus_confidence — usa confluence_score con umbral LSE_MIN_SCORE
                lse_upgrade_threshold = float(getattr(config, "LSE_MIN_SCORE", 65.0))
                can_upgrade = confluence >= lse_upgrade_threshold
                gate_desc = f"LSE Score={confluence:.1f} vs umbral={lse_upgrade_threshold}"
            else:
                # Nexus / SCAR / Bridge — usar nexus_confidence real
                min_upgrade_nexus = float(getattr(config, "MIN_UPGRADE_NEXUS", 80.0))
                can_upgrade = nexus_conf_pct >= min_upgrade_nexus
                gate_desc = f"Nexus={nexus_conf_pct:.1f}% vs umbral={min_upgrade_nexus}%"

            if can_upgrade:
                logger.info(
                    f"Cupos llenos, candidato élite ({gate_desc}). Reemplazando peor posición..."
                )
                closed_worst = self._close_worst_position()
                if not closed_worst:
                    logger.info("No se pudo cerrar la peor posición. Upgrade abortado.")
                    return False
            else:
                logger.info(
                    f"[LIMIT] Slots llenos. {gate_desc} — no alcanza para reemplazar posición existente."
                )
                return False

        # Slot libre: mínimo de calidad según fuente
        if is_lse:
            # LSE ya fue filtrado por LSE_MIN_SCORE antes de llegar acá — siempre OK
            pass
        else:
            min_entry_nexus = float(getattr(config, "MIN_ENTRY_NEXUS", 70.0))
            if nexus_conf_pct < min_entry_nexus:
                logger.info(
                    f"[SKIP] Nexus={nexus_conf_pct:.1f}% < {min_entry_nexus}% mínimo para slot libre."
                )
                return False

        logger.info(f"Opening {candidate['trade_direction']} on {symbol}. Margin: {pos_details['margin']}")
        trade_result = self.positions.open_trade(pos_details)
        pos_details.pop("agent_decision_json", None)

        if trade_result:
            trade_id = trade_result.get("id")
            local_pos = {
                "trade_id": trade_id,
                "symbol": symbol,
                "opened_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "entry_reason": entry_reason,
                "nexus_group": nexus_group,
                "tier": self._get_tier_for_symbol(symbol),
                **candidate,
                **pos_details,
            }
            self.state.add_position(local_pos)
            self.state.record_trade_action(symbol)
            if candidate.get("source") == "LSE":
                self.state.register_lse_symbol_cooldown(symbol, candidate.get("lse_timeframe") or "1h")
            self.report.log_trade_opened(local_pos)
            self.report.append_trade_metric_event(
                {
                    "phase": "open",
                    "trade_id": str(trade_id) if trade_id else None,
                    "symbol": symbol,
                    "source": candidate.get("source"),
                    **setup_metrics,
                    "entry_price_exec": pos_details.get("entry_price"),
                    "tp_price": pos_details.get("tp_price"),
                    "sl_price": pos_details.get("sl_price"),
                    "margin": pos_details.get("margin"),
                }
            )
            return True

        return False

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

            ft_exit = self._lse_follow_through_exit_reason(pos)
            if ft_exit:
                should_close, close_reason = True, ft_exit
            elif side == 0:  # LONG
                if current_price >= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price <= sl:
                    should_close, close_reason = True, "Stop Loss reached"
            else:  # SHORT
                if current_price <= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price >= sl:
                    should_close, close_reason = True, "Stop Loss reached"

            opened_at_str = pos["opened_at"].replace("Z", "+00:00")
            opened_at = datetime.fromisoformat(opened_at_str)
            if opened_at.tzinfo is not None:
                opened_at = opened_at.replace(tzinfo=None)
            hours_open = (datetime.utcnow() - opened_at).total_seconds() / 3600.0

            # ── Zombie timeout: más de MAX_TRADE_DURATION_CANDLES velas de 15m con PnL negativo ──
            if not should_close:
                # Buscar profile correspondiente
                p_id = pos.get("strategy_profile_id")
                profile = next((p for p in self.active_profiles if p.get("id") == p_id), None)
                
                if profile:
                    max_candles = int(profile.get("maxTradeDurationCandles", 16))
                else:
                    max_candles = int(getattr(config, "MAX_TRADE_DURATION_CANDLES", 16))

                candle_seconds = 900  # 15m en segundos
                seconds_open = (datetime.utcnow() - opened_at).total_seconds()
                candles_open = seconds_open / candle_seconds

                if candles_open >= max_candles:
                    entry_price = float(pos.get("entry_price", 0))
                    if entry_price > 0:
                        if side == 0:  # LONG
                            pnl_pct = (current_price - entry_price) / entry_price
                        else:  # SHORT
                            pnl_pct = (entry_price - current_price) / entry_price

                        if pnl_pct < 0:
                            logger.info(
                                "[EXIT] zombie_timeout %s | candles_open=%.1f | max=%d | PnL=%.2f%% | Cerrando.",
                                symbol, candles_open, max_candles, pnl_pct * 100,
                            )
                            should_close, close_reason = True, "zombie_timeout"
                        else:
                            logger.info(
                                "[EXIT] zombie_timeout omitido %s | candles_open=%.1f | PnL=%.2f%% (positivo, se deja correr)",
                                symbol, candles_open, pnl_pct * 100,
                            )

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
                    is_loss = "Take Profit" not in close_reason
                    self.state.record_closed_trade_outcome(is_loss)
                    self.report.log_trade_closed(pos, fake_data)
                    self.state.remove_position(trade_id)

    def _repair_existing_positions(self):
        """Ensures all backend positions have TP/SL and syncs local state."""
        logger.info("Verifying TP/SL and syncing active positions...")
        active_trades = self.positions.get_active_trades()
        if active_trades is None:
            logger.error("Failed to fetch active trades from backend during repair. Skipping.")
            return

        local_positions = self.state.get_open_positions()
        local_ids = [p.get("trade_id") for p in local_positions]

        for trade in active_trades:
            symbol   = trade["symbol"]
            trade_id = trade["id"]
            
            # 1. Sync local state if missing
            if trade_id not in local_ids:
                logger.info(f"🔄 Syncing missing position {symbol} ({trade_id}) to local state.")
                # Basic sync - enough for _should_skip and monitoring
                sync_pos = {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "opened_at": trade.get("openedAt", datetime.utcnow().isoformat()),
                    "side": trade["side"],
                    "entry_price": float(trade["entryPrice"]),
                    "tp_price": float(trade.get("tpPrice", 0)),
                    "sl_price": float(trade.get("slPrice", 0)),
                    "leverage": trade["leverage"],
                    "margin": float(trade["margin"])
                }
                self.state.add_position(sync_pos)

            # 2. Repair TP/SL if missing
            tp = trade.get("tpPrice")
            sl = trade.get("slPrice")

            if tp is None or sl is None or tp == 0 or sl == 0:
                logger.info(f"🔧 Repairing TP/SL for {symbol} ({trade_id})...")
                # Using a generic 2% range for repair calculation if missing
                entry = float(trade["entryPrice"])
                range_pct = 0.02
                tp_dist = range_pct * config.TP_MULTIPLIER
                sl_dist = range_pct * config.SL_MULTIPLIER

                if trade["side"] == 0: # LONG
                    tp_val = entry * (1 + tp_dist)
                    sl_val = entry * (1 - sl_dist)
                else: # SHORT
                    tp_val = entry * (1 - tp_dist)
                    sl_val = entry * (1 + sl_dist)

                payload = {"tpPrice": round(tp_val, 4), "slPrice": round(sl_val, 4)}
                success = self.positions.update_tp_sl(trade_id, payload)

                if success:
                    self.state.update_position_tpsl(trade_id, payload["tpPrice"], payload["slPrice"])


if __name__ == "__main__":
    import os
    import sys
    
    # Singleton Guard: evita que el agente corra duplicado
    LOCK_FILE = os.path.join(config.DATA_DIR, "agent.lock")
    
    if os.path.exists(LOCK_FILE):
        try:
            # Intentamos borrarlo. Si falla, es porque otra instancia lo tiene abierto.
            os.remove(LOCK_FILE)
        except Exception:
            print("\n❌ [FATAL] El agente ya está corriendo en otra ventana o proceso.")
            print("❌ Por favor, cerrá las otras ventanas de consola antes de abrir una nueva.\n")
            sys.exit(1)

    try:
        # Creamos el lock file
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        
        # Registrar limpieza al salir
        import atexit
        def cleanup():
            if os.path.exists(LOCK_FILE):
                try: os.remove(LOCK_FILE)
                except: pass
        atexit.register(cleanup)

        agent = VergeAgent()
        agent.run()
    except KeyboardInterrupt:
        print("\nDeteniendo agente...")
    except Exception as e:
        print(f"Error crítico: {e}")
    finally:
        if os.path.exists(LOCK_FILE):
            try: os.remove(LOCK_FILE)
            except: pass
