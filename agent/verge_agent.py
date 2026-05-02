import time
import logging
import sys
import json
import copy
import config
import requests
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
LSE_REQUIRE_SCAN_BEFORE_ENTRY = getattr(config, "LSE_REQUIRE_SCAN_BEFORE_ENTRY", True)
LSE_MIN_SYMBOLS_PROCESSED_GATE = int(getattr(config, "LSE_MIN_SYMBOLS_PROCESSED_GATE", 1))
LSE_REQUIRE_ALL_QUEUED_PROCESSED = getattr(config, "LSE_REQUIRE_ALL_QUEUED_PROCESSED", True)

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
    ) -> str:
        snap = {
            "schema_version": 1,
            "captured_at_utc": datetime.utcnow().isoformat() + "Z",
            "agent_meta": {
                "entry_reason": entry_reason,
                "nexus_group": nexus_group,
                "tier": tier,
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

        # 2. LSE — LiquiditySweepEngine (antes de Nexus). Candidato LSE compite en el ranking final;
        #    si LSE_REQUIRE_SCAN_BEFORE_ENTRY, no se opera si el batch no terminó bien (mismo ciclo, misma decisión).
        lse_candidate = None
        lse_meta: dict = {}
        if LSE_ENABLED:
            logger.info("[Step 2/6] Running LSE (Liquidity Sweep Engine)...")
            lse_candidate, lse_meta = self._run_lse_scan()
            if lse_candidate:
                logger.info(
                    "[Step 2/6] LSE candidate ready: %s | Score=%.1f | mode=%s",
                    lse_candidate.get("symbol"),
                    float(lse_candidate.get("confluence_score", 0.0)),
                    lse_candidate.get("lse_detection_mode"),
                )
            else:
                logger.info("[Step 2/6] LSE: no signal this cycle.")

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
                    candidates.append(enriched)
                    logger.info(
                        f"✅ CANDIDATE: {symbol} | Score={confluence['confluence_score']:.1f} | "
                        f"Dir={confluence['trade_direction']} | Nexus={confluence['nexus_confidence']}%"
                    )
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

        if lse_candidate:
            candidates.append(lse_candidate)
            logger.info(
                "[Step 5/6] Added LSE candidate into final ranking: %s | Score=%.1f",
                lse_candidate.get("symbol"),
                float(lse_candidate.get("confluence_score", 0.0)),
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

        if LSE_ENABLED and LSE_REQUIRE_SCAN_BEFORE_ENTRY:
            sp = int(lse_meta.get("symbols_processed") or 0)
            queued = int(lse_meta.get("items_queued") or 0)
            ok = bool(lse_meta.get("batch_http_ok"))
            called = bool(lse_meta.get("batch_called"))
            min_symbols_ok = sp >= LSE_MIN_SYMBOLS_PROCESSED_GATE
            full_scan_ok = (not LSE_REQUIRE_ALL_QUEUED_PROCESSED) or (queued > 0 and sp >= queued)
            if not (called and ok and min_symbols_ok and full_scan_ok):
                logger.warning(
                    "[GATE] Entrada cancelada: LSE no completó un scan válido en este ciclo "
                    "(batch_called=%s, http_ok=%s, symbols_processed=%s, queued=%s, min_required=%s, full_scan_required=%s). "
                    "Sin LSE completo no se opera.",
                    called,
                    ok,
                    sp,
                    queued,
                    LSE_MIN_SYMBOLS_PROCESSED_GATE,
                    LSE_REQUIRE_ALL_QUEUED_PROCESSED,
                )
                return

        self._execute_trade(top)


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
                "sweep_low", "reclaim_close", "sub_scores", "reasoning",
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
    ) -> tuple[dict | None, dict]:
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
        for sc, symbol, sig, dm in hits:
            if sc >= LSE_MIN_SCORE:
                logger.info(
                    "🚨 [LSE] TOP candidate %s | Score=%.1f | detection_mode=%s | Entry=%.6f",
                    symbol,
                    sc,
                    dm,
                    float(sig.get("entry_price") or 0),
                )
                return self._lse_row_to_candidate(symbol, sig, dm), meta_ok

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

        return None, meta_ok

    def _run_lse_scan(self) -> tuple[dict | None, dict]:
        """
        TOP-K LSE vía POST /lse/scan-batch. Velas 1h/4h con backfill REST si la caché no alcanza.

        Retorna (candidato | None, meta) para el candado LSE_REQUIRE_SCAN_BEFORE_ENTRY.
        """
        empty = {
            "batch_called": False,
            "batch_http_ok": False,
            "symbols_processed": 0,
            "items_queued": 0,
            "reason": None,
        }

        open_count = self.state.get_position_count()
        if open_count >= config.MAX_OPEN_POSITIONS:
            logger.debug("[LSE] Max positions open — skip LSE scan.")
            return None, {**empty, "reason": "max_positions"}

        if not self.state.can_trade_today():
            logger.debug("[LSE] Daily trade limit reached — skip LSE scan.")
            return None, {**empty, "reason": "daily_limit"}

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
            return None, {
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
                return None, {
                    **empty,
                    "batch_called": True,
                    "items_queued": len(batch_items),
                    "symbols_processed": sym_proc,
                    "reason": "timeout",
                }
            except Exception as e:
                logger.warning("[LSE] scan-batch request failed chunk=%d/%d: %s", idx, len(chunks), e)
                return None, {
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
                return None, {
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

        for row in signals:
            sig = row.get("signal") or {}
            score = float(sig.get("score", 0.0))
            dm = row.get("detection_mode", LSE_DETECTION_MODE)
            sym = row.get("symbol", "")
            if score >= LSE_MIN_SCORE:
                logger.info(
                    "🚨 [LSE] TOP candidate %s | Score=%.1f | detection_mode=%s | Entry=%.6f",
                    sym,
                    score,
                    dm,
                    float(sig.get("entry_price") or 0),
                )
                return self._lse_row_to_candidate(sym, sig, dm), meta_ok

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

        return None, meta_ok



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

        audit_json = self._build_agent_decision_snapshot(
            candidate, pos_details, entry_reason, nexus_group, self._get_tier_for_symbol(symbol),
        )
        pos_details["agent_decision_json"] = audit_json

        logger.info(f"Opening {candidate['trade_direction']} on {symbol}. Margin: {pos_details['margin']}")
        trade_result = self.positions.open_trade(pos_details)
        pos_details.pop("agent_decision_json", None)

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
        """Ensures all backend positions have TP/SL and syncs local state."""
        logger.info("Verifying TP/SL and syncing active positions...")
        active_trades = self.positions.get_active_trades()
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
    agent = VergeAgent()
    agent.run()
