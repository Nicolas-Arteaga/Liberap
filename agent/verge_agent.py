import time
import logging
from typing import Optional
import sys
import json
import copy
import config
import requests
import asyncio
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
from btc_macro_filter import BTCMacroFilter
from btc_correlation import BTCCorrelation

# LSE: LiquiditySweepEngine — runs BEFORE Nexus-15 to catch sweeps early
# The LSE Python service endpoint is part of the same python-service container.

# ── AGENT VERSION — Cambiar en cada release para identificar en logs ─────
AGENT_VERSION = "v12.0-BERSERKER"
AGENT_BUILD_DATE = "2026-06-21"
AGENT_CHANGES = [
    "FIX v12.0: BERSERKER — Eliminación Total de Trabas Contables",
    "FIX v12.0: BERSERKER — Balance check DESACTIVADO. Nunca consulta saldo antes de disparar.",
    "FIX v12.0: BERSERKER — Fixed Bullet $150 USDT sin filtro de balance. El exchange rebota si quiere.",
    "FIX v12.0: BERSERKER — THE TRIAD contable eliminado. Solo queda límite de 3 slots por estrategia.",
    "FIX v12.0: BERSERKER — virtual_balance / binance_balance removidos del flujo de decisión.",
    "FIX v13.0: TOTAL-SWEEP — Sinfonia Final: NEXUS-5 Bottom Sniper + Volume Radar + Ley de Nico G>R",
    "FIX v11.6: THE PURGE — Selección quirúrgica de víctima: Prioridad 1 = Margen roto (< 140 USDT)",
    "FIX v11.6: THE PURGE — Selección quirúrgica de víctima: Prioridad 2 = PnL más negativo de la estrategia",
    "FIX v11.6: THE PURGE — Fixed Bullet 150k: Balance < 150 USDT = prohibir abrir (no más $0.01 ni $109)",
    "FIX v11.6: THE PURGE — Log [PURGE v11.6] con razón de sacrificio (Margen Roto / PnL Negativo)",
    "FIX v11.5: MASTER-SNIPER — Prohibir cierre de posiciones ganadoras (PnL > 0.1%) para Upgrade",
    "FIX v11.5: MASTER-SNIPER — Bajar GOLDEN_UTURN_MAX_DISTANCE a 3.0% (precio pegado a MA99)",
    "FIX v11.5: MASTER-SNIPER — Slope-Guard infalible (-5.0) para bloquear toboganes",
    "FIX v11.5: MASTER-SNIPER — Corregir error get_balance_info en log de balance",
    "FIX v11.3: TOTAL OBEDIENCE — Validador manda sobre ejecución (is_valid False = cancelar trade)",
    "FIX v11.3: BALANCE CHECK — Log de margen disponible en cada ciclo",
    "FIX v11.3: TOTAL OBEDIENCE — Hook es la última palabra (Score 99 NO puede pisar veto)",
    "FIX v11.2: SURGICAL-FIX — Hard-Hook activo (close_above_ma7 False = return inmediato)",
    "FIX v11.2: SURGICAL-FIX — Slope-Guard calibrado (ma99_long_slope < -0.10 = bloqueo)",
    "FIX v11.2: FULL AMMO — Restaurados 3 slots de $150 USDT por estrategia (poder de fuego total)",
    "FIX v11.1: THE BARRIER — Veto de volatilidad solo para Momentum Burst (NO Golden U-Turn)",
    "FIX v11.0: THE BARRIER — Bypass Score=99 no ignora BearTrend + Wait en Golden U-Turn",
    "FIX v10.8: THE TRIAD — Límite estricto de 3 posiciones por estrategia (MAX_OPEN_POSITIONS=3)",
    "FIX v10.8: THE TRIAD — Validación de margen mínimo (150 USDT) en RiskManager",
    "FIX v10.8: THE TRIAD — MAX_TRADES_PER_DAY=50 (suficiente para 3 estrategias)",
    "FIX v10.8: THE TRIAD — Restaurado mínimo Nexus a 76% (seguridad total)",
    "FIX v10.7: Final Dictionary — Eliminado risk_usd del diccionario de retorno (NameError definitivo)",
    "FIX v10.6: Final Cleanup — Eliminadas referencias a risk_usd en logs (NameError)",
    "FIX v10.5: Final Fix — Corregido NameError en risk_manager.py (sl_distance -> sl_distance_price)",
    "FIX v10.4: Unlimited — Eliminado límite diario de trades (MAX_TRADES_PER_DAY = 999999)",
    "FIX v10.3: Fixed Bullet — Margen fijo de $150 USDT para TODOS los trades (Nexus y LSE)",
    "FIX v10.2: Syntax Fix — Corregido NameError en _calculate_ma99_slope_angle (ma99_values -> ma_values)",
    "FIX v10.2: MA7 History — Agregado cálculo de ma7_history en verge_agent.py para slope MA7",
    "FIX v10.1: The Surgical Hook — Cierre > MA7 y Slope MA7 > -1° para Golden U-Turn",
    "FIX v10.1: Veto Zombi — MIN_VOLUME_RATIO_20 = 0.15 (mata a CRDOUSDT, permite a UBUSDT)",
    "FIX v10.1: TP_MULTIPLIER 4.5x para Golden U-Turn (si VolRatio > 2.0) o 10% fijo mínimo",
    "FIX v9.8: Diamond Hands — Desactiva cierres prematuros (BTC Exit, Cosecha, Zombie) para Golden U-Turn",
    "FIX v9.8: Trailing Profit Inteligente — Activa al +10%, trailing 5% desde máximo para moonshots",
    "FIX v9.8: Margen agresivo — Forza 100% del margen ($150) para Golden U-Turn",
    "FIX v9.6: Big Fish — Golden SL max(low20, 3%) + TP mínimo 10%",
    "FIX v9.5: Dual Sniper — Golden VIP primero, Nexus-15 estándar después (65% min)",
    "FIX v9.5: Dist MA99 hasta 15%, MA7 proximidad ±2% (sin exigir cierre encima)",
    "FIX v9.5: Tier 2 Gravity Scan con volumen $100k, perfiles DB cap minNexus=65%",
    "FIX v9.4: Piso de Cemento — ángulo MA99 ±0.5° en ventana 12 velas",
    "FIX v9.4: SL = low 5 velas con buffer 0.1% bajo el piso",
    "FIX v9.3: Pase VIP Golden U-Turn — bypass MIN_ENTRY_NEXUS (76%) y MIN_UPGRADE_NEXUS",
    "FIX v9.3: Golden ignora gate Nexus-15 en _execute_trade (10% vs 76% resuelto)",
    "FIX v9.2: RiskManager atr_signal UnboundLocalError — Golden U-Turn ya no crashea al abrir",
    "FIX v9.2: Inyección directa Score=99 + prioridad absoluta sobre Nexus-15",
    "NEW: Golden U-Turn v9.0 — Structural Pivot Hunter (MA99 horizontal tras caída)",
    "NEW: Gravity Check Step 3.5 (MA99 ±1.5°, drop ≥3% en 100 velas 15m)",
    "NEW: Bypass Golden Rule — anula VETO RSI, MA7, volumen, ranging",
    "NEW: [STRAT: GOLDEN-U-TURN] tag + SL custom (low 5 velas)",
    "v9.1: structural_analytics en audit JSON + tool_used marking",
]

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

# Standard Scalping — sentinel GUID for the legacy hardcoded profile (not stored in DB)
STANDARD_PROFILE_ID = "00000000-0000-0000-0000-000000000000"
# Scalping Clone — sentinel GUID for the hardcoded clone profile (not stored in DB)
CLONE_PROFILE_ID = "00000000-0000-0000-0000-000000000001"
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
        logger.info("=" * 70)
        logger.info(f"  VERGE AGENT {AGENT_VERSION}  |  Build: {AGENT_BUILD_DATE}")
        logger.info("=" * 70)
        for change in AGENT_CHANGES:
            logger.info(f"  >> {change}")
        logger.info("=" * 70)
        logger.info(f"  BTC Defense Config:")
        logger.info(f"    BTC_DUMP_THRESHOLD_5M  = {getattr(config, 'BTC_DUMP_THRESHOLD_5M', '?')}%")
        logger.info(f"    BTC_DUMP_THRESHOLD_15M = {getattr(config, 'BTC_DUMP_THRESHOLD_15M', '?')}%")
        logger.info(f"    BTC_DUMP_THRESHOLD_1H  = {getattr(config, 'BTC_DUMP_THRESHOLD_1H', '?')}% (NUEVO)")
        logger.info(f"    BTC_BLEED_1H_THRESHOLD = {getattr(config, 'BTC_BLEED_1H_THRESHOLD', '?')}% (VETO DURO)")
        logger.info(f"    BTC_CORR_HARD_BLOCK    = {getattr(config, 'BTC_CORR_HARD_BLOCK_THRESHOLD', '?')} (VETO DURO)")
        logger.info(f"    BTC_FLASH_CRASH_PCT_1H = {getattr(config, 'BTC_FLASH_CRASH_PCT_1H', '?')}%")
        logger.info("=" * 70)
        logger.info("Initializing VERGE Agent...")
        self.auth      = AuthManager()
        self.fetcher   = BinanceFetcher()
        self.state     = StateManager()
        self.signals   = SignalEngine(self.fetcher)
        self.risk      = RiskManager(self.fetcher)
        self.positions = PositionManager(self.auth)
        self.report    = ReportEngine()
        self.btc_filter = BTCMacroFilter(self.fetcher)
        self.btc_corr   = BTCCorrelation(self.fetcher, self.btc_filter)
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
        cycle_rejected: Optional[list] = None,
    ) -> str:
        # ── BTC Context for AgentDecisionJson ──
        btc_regime = self.btc_filter.get_regime()
        pct_5m = self.btc_filter.get_dump_pct(5)
        pct_15m = self.btc_filter.get_dump_pct(15)
        pct_1h = self.btc_filter.get_dump_pct(60)
        symbol = candidate.get("symbol", "")
        corr = self.btc_corr.get_correlation(symbol) if symbol else 0.0
        penalty = self.btc_corr.get_score_penalty(symbol, btc_regime) if symbol else 1.0
        is_flash_crash = self.btc_filter.is_flash_crash()
        
        btc_context = {
            "regime": btc_regime,
            "pct_5m": pct_5m,
            "pct_15m": pct_15m,
            "pct_1h": pct_1h,
            "correlation": corr,
            "penalty": penalty,
            "flash_crash": is_flash_crash,
        }
        
        # ── AI-GRADE AUDIT: Temporal Context ──
        now_utc = datetime.utcnow()
        hour_utc = now_utc.hour
        day_of_week = now_utc.strftime("%A")

        # Determine trading session
        if 0 <= hour_utc < 8:
            session = "ASIA"
        elif 8 <= hour_utc < 13:
            session = "LONDON"
        elif 13 <= hour_utc < 21:
            session = "NY_OPEN"
        elif 21 <= hour_utc < 24:
            session = "NY_CLOSE"
        else:
            session = "WEEKEND"

        temporal_context = {
            "hour_utc": hour_utc,
            "day_of_week": day_of_week,
            "session": session,
            "is_weekend": day_of_week in ["Saturday", "Sunday"],
        }

        # ── NEXUS-5 Timing Context ──
        nexus5_context = {
            "phase": candidate.get("nexus5_phase"),
            "confidence": candidate.get("nexus5_confidence"),
            "timing_note": candidate.get("nexus5_timing_note"),
            "boost_applied": candidate.get("nexus5_boost"),
            "is_reversal": candidate.get("nexus5_reversal"),
        }

        # ── v9.1 STRUCTURAL ANALYTICS: Golden U-Turn calibration data ──
        # Exposes the full geometry of the Structural Pivot for post-trade analysis.
        gu_audit = candidate.get("agent_audit_context", {}).get("golden_uturn", {})
        is_golden = bool(candidate.get("golden_uturn_mode") or gu_audit.get("detected", False))
        tool_used = "Structural_U-Turn_v9.1" if is_golden else "Standard_Pipeline_v9.0"

        structural_analytics = {}
        if is_golden:
            structural_analytics = {
                "tool_used": tool_used,
                "ma99_angle_at_entry": gu_audit.get("angle"),
                "ma99_drop_magnitude_pct": gu_audit.get("drop_pct"),
                "ma99_drop_duration_candles": int(getattr(config, "GOLDEN_UTURN_LOOKBACK_CANDLES", 60)),
                "price_to_ma99_distance_pct": gu_audit.get("price_to_ma99_distance_pct"),
                "ma99_raw_values": {
                    "current": gu_audit.get("ma99_now"),
                    "ago_60_candles": gu_audit.get("ma99_ago"),
                },
                "volume_ignition_ratio_1m": gu_audit.get("volume_ignition_ratio_1m"),
                "atr_volatility_at_entry": gu_audit.get("atr_volatility_pct"),
                "consecutive_flat_candles": gu_audit.get("consecutive_flat_candles"),
                "sl_strategy": "5-candle_low",
                "tp_multiplier": getattr(config, "TP_MULTIPLIER", 3.5),
            }

        # ── v12.1: Compression snapshot at entry (computed from klines + Nexus-15 features) ──
        nexus_features = candidate.get("agent_audit_context", {}).get("nexus15", {}).get("features", {})
        compression_snapshot_at_entry = self._compute_compression_snapshot(symbol, nexus_features)

        # ── v12.1: Structural distances (from candidate data) ──
        structural_distances = {
            "distance_to_ma7_pct": candidate.get("distance_to_ma7_pct"),
            "distance_to_ma50_pct": candidate.get("distance_to_ma50_pct"),
            "distance_to_ma99_pct": candidate.get("distance_to_ma99_pct"),
            "swing_high_50": candidate.get("swing_high_50"),
            "swing_low_50": candidate.get("swing_low_50"),
        }
        # Calculate distance to swing high/low if available
        cur_px = candidate.get("price_at_signal") or candidate.get("current_price")
        swing_hi = candidate.get("swing_high_50")
        swing_lo = candidate.get("swing_low_50")
        if cur_px and swing_hi:
            structural_distances["distance_to_swing_high_pct"] = round(
                ((float(swing_hi) - float(cur_px)) / float(cur_px)) * 100, 4
            )
        if cur_px and swing_lo:
            structural_distances["distance_to_swing_low_pct"] = round(
                ((float(cur_px) - float(swing_lo)) / float(cur_px)) * 100, 4
            )

        # ── v12.1: Spread/liquidez (2.4) — desde orderbook si está disponible ──
        try:
            if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'get_orderbook_snapshot'):
                _ob = self.fetcher.get_orderbook_snapshot(symbol)
                if _ob and _ob.get("spread_pct") is not None:
                    structural_distances["bid_ask_spread_pct"] = float(_ob["spread_pct"])
                    structural_distances["orderbook_depth_5_usdt"] = float(_ob.get("depth_5_usdt", 0) or 0)
                    structural_distances["orderbook_imbalance"] = float(_ob.get("imbalance", 0) or 0)
        except Exception as _ob_ex:
            logger.debug(f"[AUDIT] Spread capture for {symbol}: {_ob_ex}")

        snap = {
            "schema_version": 3,
            "agent_version": "v12.1",
            "experiment": "post_sl_fix_may_2026",
            "captured_at_utc": datetime.utcnow().isoformat() + "Z",
            "agent_meta": {
                "entry_reason": entry_reason,
                "nexus_group": nexus_group,
                "tier": tier,
                "setup_validation": setup_skip or "ok",
                "setup_metrics": self._json_safe_for_audit(copy.deepcopy(setup_metrics or {})),
                "tool_used": tool_used,
            },
            "btc_context": btc_context,
            "temporal_context": temporal_context,
            "nexus5_context": nexus5_context,
            "structural_analytics": structural_analytics,
            "compression_snapshot_at_entry": compression_snapshot_at_entry,
            "structural_distances": structural_distances,
            "cycle_candidates_rejected": cycle_rejected or [],
            "human_label": "",
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

    def _capture_market_context(self, symbol: str, candidate: dict) -> dict:
        """
        AI-GRADE AUDIT: Capture market context snapshot at trade entry.
        Logs order book, OI, funding, volume, volatility, and liquidations.
        This data is NOT used for trading decisions - only for post-trade AI analysis.
        """
        try:
            context = {
                "captured_at_utc": datetime.utcnow().isoformat() + "Z",
                "symbol": symbol,
            }
            
            # Order Book metrics (si está disponible)
            try:
                if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'get_orderbook_snapshot'):
                    ob = self.fetcher.get_orderbook_snapshot(symbol)
                    if ob:
                        context["orderbook"] = {
                            "bid_ask_spread_pct": ob.get("spread_pct"),
                            "depth_5_pct_usdt": ob.get("depth_5_usdt"),
                            "imbalance": ob.get("imbalance"),  # (bids - asks) / (bids + asks)
                        }
            except Exception as e:
                logger.debug(f"[AUDIT] Order book capture failed for {symbol}: {e}")
            
            # Open Interest (si está disponible)
            try:
                if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'get_open_interest'):
                    oi_data = self.fetcher.get_open_interest(symbol)
                    if oi_data:
                        context["open_interest"] = {
                            "oi_usdt": oi_data.get("oi_usdt"),
                            "oi_change_1h_pct": oi_data.get("change_1h_pct"),
                            "oi_change_4h_pct": oi_data.get("change_4h_pct"),
                        }
            except Exception as e:
                logger.debug(f"[AUDIT] OI capture failed for {symbol}: {e}")
            
            # Funding Rate
            try:
                if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'get_funding_rate'):
                    funding = self.fetcher.get_funding_rate(symbol)
                    if funding is not None:
                        context["funding"] = {
                            "current_rate": funding,
                            "trend": "unknown",  # Requiere histórico
                        }
            except Exception as e:
                logger.debug(f"[AUDIT] Funding rate capture failed for {symbol}: {e}")
            
            # Volume
            try:
                if hasattr(self, 'fetcher') and hasattr(self.fetcher, 'get_volume_24h'):
                    vol = self.fetcher.get_volume_24h(symbol)
                    if vol:
                        context["volume"] = {
                            "volume_24h_usdt": vol.get("volume_usdt"),
                            "volume_ratio": vol.get("ratio_vs_avg"),
                        }
            except Exception as e:
                logger.debug(f"[AUDIT] Volume capture failed for {symbol}: {e}")
            
            # Volatility (ATR)
            try:
                if "atr_14" in candidate:
                    context["volatility"] = {
                        "atr_14": candidate.get("atr_14"),
                    }
            except Exception as e:
                logger.debug(f"[AUDIT] Volatility capture failed for {symbol}: {e}")
            
            return context
            
        except Exception as e:
            logger.warning(f"[AUDIT] Market context capture failed for {symbol}: {e}")
            return {"error": str(e)}

    def _compute_compression_snapshot(self, symbol: str, nexus_features: dict) -> dict:
        """
        v12.1 — Compute real compression metrics from 15m klines + Nexus-15 features.
        Maps to the 9 fields from the original compression snapshot spec.
        Never crashes the audit pipeline.
        """
        result = {
            # Nexus-15 native features (always available)
            "candle_body_ratio": float(nexus_features.get("candle_body_ratio", 0) or 0),
            "upper_wick_ratio": float(nexus_features.get("upper_wick_ratio", 0) or 0),
            "lower_wick_ratio": float(nexus_features.get("lower_wick_ratio", 0) or 0),
            "volume_ratio_20": float(nexus_features.get("volume_ratio_20", 0) or 0),
            "rsi_14": float(nexus_features.get("rsi_14", 50) or 50),
            "atr_percent": float(nexus_features.get("atr_percent", 0) or 0),
            "trend_structure": int(nexus_features.get("trend_structure", 0) or 0),
            "wyckoff_phase": str(nexus_features.get("wyckoff_phase", "") or ""),
            "bos_detected": bool(nexus_features.get("bos_detected", False)),
            "order_block_detected": bool(nexus_features.get("order_block_detected", False)),
            "explosion_bullish": bool(nexus_features.get("explosion_bullish", False)),
            "explosion_bearish": bool(nexus_features.get("explosion_bearish", False)),
            # Computed from klines (may be None if data unavailable)
            "caida_pct": None,
            "cement_duration": None,
            "cement_valid": None,
            "noise_pct": None,
            "slope_ema50_deg": None,
            "near_bottom": None,
            "ma99_cluster_dist_pct": None,
            "u_shape_count": None,
            "klines_used": 0,
        }

        try:
            klines = self.fetcher.get_klines_for_nexus(symbol, interval="15m", limit=150)
            if not klines or len(klines) < 50:
                return result

            closes = [float(k.get("close", 0)) for k in klines]
            highs = [float(k.get("high", 0)) for k in klines]
            lows = [float(k.get("low", 0)) for k in klines]
            n = len(closes)
            result["klines_used"] = n

            # ── MA99 / MA50 ──
            def _sma(arr, period, idx):
                start = max(0, idx - period + 1)
                window = arr[start:idx + 1]
                return sum(window) / len(window) if window else 0.0

            ma99_vals = [_sma(closes, 99, i) for i in range(n)]
            ma50_vals = [_sma(closes, 50, i) for i in range(n)]
            current_price = closes[-1]
            ma99_now = ma99_vals[-1]
            ma50_now = ma50_vals[-1]

            # ── 1. caída_pct: MA99 drop from recent 100-bar peak ──
            if len(ma99_vals) >= 20:
                ma99_lookback = ma99_vals[-min(100, len(ma99_vals)):]
                ma99_peak = max(ma99_lookback)
                if ma99_peak > 0:
                    result["caida_pct"] = round(((ma99_peak - ma99_now) / ma99_peak) * 100, 4)

            # ── 2. cement_duration: consecutive candles where price ≈ MA50 (±0.5%) ──
            cement = 0
            for i in range(n - 1, -1, -1):
                if ma50_vals[i] > 0:
                    dist_pct = abs((closes[i] - ma50_vals[i]) / ma50_vals[i]) * 100
                    if dist_pct <= 0.5:
                        cement += 1
                    else:
                        break
                else:
                    break
            result["cement_duration"] = cement
            result["cement_valid"] = cement >= 6

            # ── 3. noise_pct: (max_high - min_low) / price over last 20 candles ──
            lookback = min(20, n)
            recent_highs = highs[-lookback:]
            recent_lows = lows[-lookback:]
            if current_price > 0 and recent_highs and recent_lows:
                noise_range = max(recent_highs) - min(recent_lows)
                result["noise_pct"] = round((noise_range / current_price) * 100, 4)

            # ── 4. slope_ema50_deg: angle of MA50 over last 10 bars ──
            if n >= 10 and ma50_vals[-1] > 0 and ma50_vals[-10] > 0:
                slope_raw = (ma50_vals[-1] - ma50_vals[-10]) / ma50_vals[-10]
                import math
                result["slope_ema50_deg"] = round(math.degrees(math.atan(slope_raw * 100)), 4)

            # ── 5. near_bottom: price within 2% of 50-bar low ──
            if recent_lows:
                low_50 = min(recent_lows)
                if low_50 > 0:
                    result["near_bottom"] = bool(current_price <= low_50 * 1.02)

            # ── 6. ma99_cluster_dist_pct: |price - MA99| / MA99 * 100 ──
            if ma99_now > 0:
                result["ma99_cluster_dist_pct"] = round(
                    abs((current_price - ma99_now) / ma99_now) * 100, 4
                )

            # ── 7. u_shape_count: count of local minima in last 50 candles ──
            if n >= 10:
                u_count = 0
                window = closes[-min(50, n):]
                for i in range(2, len(window) - 2):
                    if (window[i] <= window[i - 1] and window[i] <= window[i - 2]
                            and window[i] <= window[i + 1] and window[i] <= window[i + 2]):
                        u_count += 1
                result["u_shape_count"] = u_count

        except Exception as ex:
            logger.debug(f"[COMPRESSION-SNAP] {symbol}: compute error (non-fatal): {ex}")

        return result

    def _determine_exit_reason(self, close_reason: str, side: int, current_price: float, tp: float, sl: float, entry_price: float) -> str:
        """
        AI-GRADE AUDIT: Classify why a trade was closed.
        Returns standardized exit reason for post-trade analysis.
        """
        # Normalize close_reason
        reason_lower = close_reason.lower()
        
        # TP hit
        if "take profit" in reason_lower or "tp" in reason_lower:
            return "tp_hit"
        
        # SL hit
        if "stop loss" in reason_lower or "sl" in reason_lower:
            return "sl_hit"
        
        # BTC dump exit
        if "btc" in reason_lower and ("dump" in reason_lower or "exit" in reason_lower):
            return "btc_dump"
        
        # Cosecha Inteligente (trailing stop)
        if "cosecha" in reason_lower or "trailing" in reason_lower:
            return "trailing_stop"
        
        # Timeout
        if "timeout" in reason_lower or "duration" in reason_lower or "zombie" in reason_lower:
            return "timeout"
        
        # LSE follow-through exit
        if "lse" in reason_lower or "follow" in reason_lower:
            return "lse_exit"
        
        # Regime change
        if "regime" in reason_lower:
            return "regime_change"
        
        # Default: classify based on price action
        if entry_price > 0:
            if side == 0:  # LONG
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price
            
            if pnl_pct > 0:
                return "manual_profit"  # Closed in profit manually
            else:
                return "manual_loss"  # Closed in loss manually
        
        return "unknown"

    def run(self):
        logger.info(f"Agent started. Loop interval: {config.LOOP_INTERVAL_SECONDS}s.")
        logger.info("[CONFIG] Agent Version: risk_v7.1 (Performance Optimization + Hybrid Sniper Synergy)")

        if not self.auth.get_token():
            logger.error("FATAL: Could not authenticate with ABP Backend. Stopping.")
            return

        self._repair_existing_positions()

        while True:
            cycle_start_time = time.time()
            try:
                self.loop_cycle()
            except Exception as e:
                logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)

            # ── SYNC v7.1: Calcular sleep dinámico basado en tiempo de análisis ─────────
            cycle_duration = time.time() - cycle_start_time
            loop_interval = config.LOOP_INTERVAL_SECONDS
            
            if cycle_duration < loop_interval:
                sleep_time = loop_interval - cycle_duration
                logger.info(f"Sleeping {sleep_time:.1f}s... (cycle took {cycle_duration:.1f}s)")
                time.sleep(sleep_time)
            else:
                logger.warning(
                    f"⚠️ Cycle took {cycle_duration:.1f}s (> {loop_interval}s). "
                    f"Starting next cycle immediately (performance bottleneck detected)."
                )

    # ─────────────────────────────────────────────────────────
    # Main cycle
    # ─────────────────────────────────────────────────────────
    def loop_cycle(self):
        logger.debug("[TRACE] Entering loop_cycle")
        
        # ── BTC FLASH CRASH PAUSE (Capa B) ──
        # Pausar el agente si BTC cayó más de 3% en 1h (flash crash)
        if self.btc_filter.is_flash_crash():
            logger.warning("[BTC-FLASH] Flash crash detectado — agente pausado 2 horas")
            self.report.record_btc_flash_crash()
            time.sleep(config.BTC_FLASH_CRASH_PAUSE_M * 60)
            return
        
        # ── PENDING SNIPERS TRAPS MANAGEMENT (Sniper Mode) ──
        try:
            self._manage_pending_snipers()
        except Exception as e:
            logger.error(f"[SNIPER] Error managing pending snipers: {e}", exc_info=True)
            
        try:
            config.refresh_watchlist()
        except Exception as e:
            logger.error(f"Failed to refresh watchlist: {e}")
        logger.info("--- Starting new analysis cycle ---")
        use_testnet_str = os.getenv("BINANCE_USE_TESTNET", "false")
        use_testnet = use_testnet_str.lower() in ("1", "true", "yes")
        version = "3.4" if use_testnet else "3.3"
        env_str = "TESTNET" if use_testnet else "MAINNET"
        logger.info(f"[VERSION] PositionManager v{version} - TP/SL via closePosition=true with fallbacks ({env_str})")
        
        # ── v12.0-BERSERKER: Balance check ELIMINADO. El bot NO consulta saldo. ──
        # Fixed Bullet: siempre $150 USDT por trade. Que el exchange rebote si quiere.
        available_balance = 999_999.0  # Dummy infinito — nunca se usa para bloquear
        logger.info(
            f"[BERSERKER v12.0] Balance check DESACTIVADO. Bala fija $150 USDT. "
            f"Slots={config.MAX_OPEN_POSITIONS} por estrategia. SIN PREGUNTAR."
        )

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
        db_profiles = [p for p in db_profiles if p.get("name") not in ("Standard Scalping", "Scalping Clone")]
        _profile_nexus_cap = float(getattr(config, "PROFILE_MIN_NEXUS_CONFIDENCE", 76.0))
        for p in db_profiles:
            raw_nexus = float(p.get("minNexusConfidence") or _profile_nexus_cap)
            if raw_nexus > _profile_nexus_cap:
                p["minNexusConfidence"] = _profile_nexus_cap
                logger.info(
                    f"[v10.8] Perfil '{p.get('name')}' minNexus capped {raw_nexus}% → {_profile_nexus_cap}%"
                )
        
        # Define the virtual legacy profile for "Standard Scalping" (Sniper Mode)
        legacy_profile = {
            "id": STANDARD_PROFILE_ID,
            "name": "Standard Scalping",
            "minConfluenceScore": config.MIN_CONFLUENCE_SCORE,
            "minNexusConfidence": _profile_nexus_cap,
            "tpMultiplier": getattr(config, "TP_MULTIPLIER", 2.0),
            "slMultiplier": getattr(config, "SL_MULTIPLIER", 1.0),
            "marginPerTrade": getattr(config, "MAX_MARGIN_PER_TRADE_USD", 150),
            "maxOpenPositions": config.MAX_OPEN_POSITIONS,
            "maxMa7DistancePct": 1.2,          # EL SECRETO: Filtro de proximidad a la media (evita FOMO)
            "maxNexusSignalAgeSeconds": 60,    # Solo señales frescas (60s)
            "nexusMaxPriceDriftPct": 0.002,    # Máximo movimiento de 0.2% desde la señal
            "allowLong": True,
            "allowShort": True,
            "allowedSources": ["nexus", "scar", "redis_bridge", "golden_uturn", "total_sweep"],
            "isActive": True
        }

        # Define the virtual clone profile for "Scalping Clone" (Sniper Mode + Tank SL)
        self.clone_profile = {
            "id": CLONE_PROFILE_ID,
            "name": "Scalping Clone",
            "minConfluenceScore": config.MIN_CONFLUENCE_SCORE,
            "minNexusConfidence": _profile_nexus_cap,
            "tpMultiplier": getattr(config, "TP_MULTIPLIER", 2.0),
            "slMultiplier": getattr(config, "SL_MULTIPLIER", 1.0) * 2,  # 2x Standard Scalping SL (Tanque)
            "marginPerTrade": getattr(config, "MAX_MARGIN_PER_TRADE_USD", 150),
            "maxOpenPositions": config.MAX_OPEN_POSITIONS,
            "maxMa7DistancePct": 1.2,          # COPIADO: El Clone ahora también espera el pullback
            "maxNexusSignalAgeSeconds": 60,    # COPIADO: Evita entrar en datos viejos
            "nexusMaxPriceDriftPct": 0.002,    # COPIADO: Máximo 0.2% drift
            "allowLong": True,
            "allowShort": True,
            "allowedSources": ["nexus", "scar", "redis_bridge", "golden_uturn", "total_sweep"],
            "isActive": True
        }

        # The active profiles list includes Standard Scalping + Scalping Clone + any DB profile
        # Each profile evaluates candidates independently with its own slot limit
        self.active_profiles = [legacy_profile, self.clone_profile] + db_profiles
        
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

        # 3.5 NEXUS-5 Timing Scan — 5m Phase 1/2 detection for entry timing
        #     OPTIMIZACIÓN v7.2: Pre-filtrado con ticker24h para reducir scope
        #     Solo analiza símbolos con volumen >= $500k en 24h para evitar HTTP 429
        #     Usa ThreadPoolExecutor para paralelizar descargas
        nexus5_cache = {}
        NEXUS5_ENABLED = getattr(config, "NEXUS5_ENABLED", True)
        if NEXUS5_ENABLED:
            all_targets_n5 = config.WATCHLIST
            
            # ── PRE-FILTRADO v9.5: T1 siempre | T2 >= $100k | resto >= $500k ───────────
            MIN_VOLUME_TIER2_USD = int(getattr(config, "GOLDEN_UTURN_MIN_VOLUME_TIER2_USD", 100_000))
            MIN_VOLUME_DEFAULT_USD = int(getattr(config, "GOLDEN_UTURN_MIN_VOLUME_DEFAULT_USD", 500_000))
            filtered_targets_n5 = []
            
            logger.info(
                f"[Step 3.5/6] Pre-filtrando {len(all_targets_n5)} símbolos "
                f"(T1=bypass | T2>=${MIN_VOLUME_TIER2_USD/1000:.0f}k | otros>=${MIN_VOLUME_DEFAULT_USD/1000:.0f}k)..."
            )
            
            tier1_symbols = config.WATCHLIST_TIER1 if hasattr(config, "WATCHLIST_TIER1") else []
            tier2_symbols = set(config.WATCHLIST_TIER2 if hasattr(config, "WATCHLIST_TIER2") else [])
            logger.info(f"[Step 3.5/6] BYPASS: {len(tier1_symbols)} TIER 1 symbols will be analyzed regardless of volume filter")
            
            def _volume_threshold_for(symbol: str) -> int:
                if symbol in tier1_symbols:
                    return 0
                if symbol in tier2_symbols:
                    return MIN_VOLUME_TIER2_USD
                return MIN_VOLUME_DEFAULT_USD
            
            # ── DEBUG v7.5: Auditoría de volumen para detectar error de unidades ─────────
            debug_count = 0
            for symbol in all_targets_n5:
                try:
                    ticker = self.fetcher.get_ticker(symbol)
                    if ticker:
                        # FIX v7.5: Binance usa "quoteVolume" (con V mayúscula) para volumen en USDT
                        # Intentar quoteVolume primero, luego quote_volume, luego volume
                        quote_volume = float(ticker.get("quoteVolume", ticker.get("quote_volume", ticker.get("volume", 0))) or 0)
                        
                        # Log de auditoría para los primeros 10 símbolos (aumentado de 5)
                        vol_threshold = _volume_threshold_for(symbol)
                        if debug_count < 10:
                            logger.info(
                                f"[Step 3.5/6] DEBUG VOLUME: {symbol} | volume_raw={quote_volume} | "
                                f"volume_formatted=${quote_volume:,.2f} | threshold=${vol_threshold:,.2f} | "
                                f"ticker_keys={list(ticker.keys())}"
                            )
                            debug_count += 1
                        
                        if vol_threshold == 0 or quote_volume >= vol_threshold:
                            filtered_targets_n5.append(symbol)
                            if vol_threshold == 0:
                                logger.debug(f"[Step 3.5/6] BYPASS: {symbol} (TIER 1) added regardless of volume")
                    else:
                        # FIX v7.5: Si ticker es None, intentar obtenerlo directamente del MSF
                        logger.debug(f"[Step 3.5/6] DEBUG: {symbol} ticker is None, trying MSF directly...")
                        try:
                            # Intentar obtener ticker 24h directamente del MSF
                            ticker_24h = self.fetcher._msf.get_ticker_24h(symbol) if hasattr(self.fetcher, '_msf') else None
                            if ticker_24h:
                                # FIX v7.5: Binance usa "quoteVolume" (con V mayúscula)
                                quote_volume = float(ticker_24h.get("quoteVolume", ticker_24h.get("quote_volume", ticker_24h.get("volume", 0))) or 0)
                                vol_threshold = _volume_threshold_for(symbol)
                                logger.info(
                                    f"[Step 3.5/6] DEBUG MSF: {symbol} | volume_raw={quote_volume} | "
                                    f"volume_formatted=${quote_volume:,.2f} | threshold=${vol_threshold:,.2f}"
                                )
                                if vol_threshold == 0 or quote_volume >= vol_threshold:
                                    filtered_targets_n5.append(symbol)
                        except Exception as msf_e:
                            logger.debug(f"[Step 3.5/6] MSF failed for {symbol}: {msf_e}")
                except Exception as e:
                    logger.debug(f"[Step 3.5/6] Error getting ticker for {symbol}: {e}")
                    pass  # Silently skip ticker errors
            
            # ── FIX v7.4: Agregar TIER 1 explícitamente si no fueron agregados ────────────
            for symbol in tier1_symbols:
                if symbol not in filtered_targets_n5:
                    filtered_targets_n5.append(symbol)
                    logger.info(f"[Step 3.5/6] BYPASS v7.4: {symbol} (TIER 1) FORCE-ADDED (no ticker or volume filter failed)")
            
            logger.info(
                f"[Step 3.5/6] Pre-filtrado completado: {len(filtered_targets_n5)}/{len(all_targets_n5)} "
                f"símbolos pasaron filtro v9.5 (T2=${MIN_VOLUME_TIER2_USD/1000:.0f}k)"
            )
            
            if len(filtered_targets_n5) == 0:
                logger.warning(
                    "[Step 3.5/6] ⚠️ WARNING: Volume filter vacío. NEXUS-5 / Gravity Check skipped."
                )
            
            # ── PARALELIZACIÓN v7.1: ThreadPoolExecutor para descargas ─────────────────
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import threading
            
            logger.info(f"[Step 3.5/6] Escaneando {len(filtered_targets_n5)} símbolos con NEXUS-5 (5m timing) [PARALELIZADO v7.1]...")
            n5_ok = 0
            n5_fail = 0
            n5_golden = 0  # Golden U-Turn v9.0 counter
            lock = threading.Lock()
            
            def fetch_n5_symbol(symbol):
                nonlocal n5_ok, n5_fail, n5_golden
                # ── NEXUS-5: timing prediction (independent) ──
                try:
                    n5 = self.signals.get_nexus5_prediction(symbol, limit=500)
                    if n5:
                        with lock:
                            nexus5_cache[symbol] = n5
                            n5_ok += 1
                    else:
                        with lock:
                            n5_fail += 1
                except Exception:
                    with lock:
                        n5_fail += 1

                # ── GOLDEN U-TURN v9.1: Gravity Check (INDEPENDIENTE de Nexus-5) ──
                # Corre SIEMPRE, incluso si Nexus-5 falla. Esta es la REGLA DE ORO.
                if getattr(config, "GOLDEN_UTURN_ENABLED", True):
                    try:
                        gu = self._check_golden_uturn(symbol)
                        if gu["passed"]:
                            # ── FIX v11.5: Slope Guard Infalible usando ma99_long_slope de Nexus-5 ──
                            # Si la MA99 sigue cayendo fuerte (< -5.0), bloquear el trade (tobogán total)
                            n5_data = nexus5_cache.get(symbol, {})
                            ma99_long_slope = n5_data.get("ma99_long_slope")
                            if ma99_long_slope is not None and ma99_long_slope < -5.0:
                                logger.warning(
                                    f"[SLOPE-GUARD v11.5] {symbol} RECHAZADO: MA99 slope={ma99_long_slope:.6f} < -5.0 (tobogán total)"
                                )
                                # No agregar al cache de golden_uturn si falla el Slope-Guard
                            else:
                                with lock:
                                    if symbol not in nexus5_cache:
                                        nexus5_cache[symbol] = {"symbol": symbol}
                                    nexus5_cache[symbol]["golden_uturn"] = True
                                    nexus5_cache[symbol]["golden_uturn_angle"] = gu["angle"]
                                    nexus5_cache[symbol]["golden_uturn_drop_pct"] = gu["drop_pct"]
                                    nexus5_cache[symbol]["golden_uturn_sl_5low"] = gu["sl_5low"]
                                    # v9.1 audit metrics
                                    nexus5_cache[symbol]["gu_price_to_ma99_distance_pct"] = gu["price_to_ma99_distance_pct"]
                                    nexus5_cache[symbol]["gu_ma99_now"] = gu["ma99_now"]
                                    nexus5_cache[symbol]["gu_ma99_ago"] = gu["ma99_ago"]
                                    nexus5_cache[symbol]["gu_volume_ignition_ratio_1m"] = gu["volume_ignition_ratio_1m"]
                                    nexus5_cache[symbol]["gu_atr_volatility_pct"] = gu["atr_volatility_pct"]
                                    nexus5_cache[symbol]["gu_consecutive_flat_candles"] = gu["consecutive_flat_candles"]
                                    nexus5_cache[symbol]["gu_ma7_now"] = gu["ma7_now"]
                                    nexus5_cache[symbol]["gu_close_above_ma7"] = gu["close_above_ma7"]
                                    n5_golden += 1
                                logger.info(
                                    f"[GRAVITY-CHECK] {symbol}: MA99 Angle={gu['angle']:.2f}°, "
                                    f"Drop={gu['drop_pct']:.2f}% — GOLDEN U-TURN!"
                                )
                        elif gu.get("reject_reason"):
                            logger.info(
                                f"[GRAVITY-CHECK] {symbol}: v9.4 RECHAZADO — {gu['reject_reason']}"
                            )
                    except Exception as gu_e:
                        logger.debug(f"[GRAVITY-CHECK] {symbol}: skip - {gu_e}")
            
            # Usar max_workers=10 para paralelizar sin saturar APIs
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_n5_symbol, symbol) for symbol in filtered_targets_n5]
                for future in as_completed(futures):
                    pass  # Los contadores se actualizan dentro de fetch_n5_symbol
            
            logger.info(
                f"[Step 3.5/6] NEXUS-5: {n5_ok} analyzed, {n5_fail} skipped | "
                f"GOLDEN U-TURN: {n5_golden} symbols passed Gravity Check [v9.0]"
            )

        # 4. Scan T1+T2 watchlist symbols with Nexus-15 (OPTIMIZACIÓN v6.1)
        #    - Tier 1 (30) + Tier 2 (70) = 100 symbols only (down from 421)
        #    - Tier 3 only analyzed via Redis Bridge or Nexus TOP (on-demand)
        #    - Reduces analysis time from 20min to ~3min
        #    - Symbols with cache history: instant (SQLite read)
        #    - Symbols without cache history: on-demand REST fetch (Bybit/OKX)
        all_targets = config.WATCHLIST_TIER1 + config.WATCHLIST_TIER2  # T1+T2 only (100 symbols)

        logger.info(
            f"[Step 4/6] Scanning {len(all_targets)} symbols (T1+T2 only) with Nexus-15... [OPTIMIZED v6.1]"
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
        # ── PARALELIZACIÓN v7.3: ThreadPoolExecutor para NEXUS-15 ─────────────────
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        candidates = []
        skipped_trading = 0
        analyzed = 0
        no_data = 0
        broadcast_batch = []
        
        # Locks para thread-safety
        candidates_lock = threading.Lock()
        counters_lock = threading.Lock()
        broadcast_lock = threading.Lock()
        
        def analyze_nexus15_symbol(symbol):
            """Analiza un símbolo con NEXUS-15 de forma thread-safe."""
            nonlocal skipped_trading, analyzed, no_data
            
            try:
                if self._should_skip(symbol):
                    with counters_lock:
                        skipped_trading += 1
                    return None

                # Fetch prediction with a strict timeout (handled inside signal_engine)
                nexus_data = self.signals.get_nexus15_prediction(symbol)
                if not nexus_data:
                    with counters_lock:
                        no_data += 1
                    return None

                with counters_lock:
                    analyzed += 1
                
                scar_data  = scar_alerts.get(symbol, {})
                n5_data    = nexus5_cache.get(symbol)
                confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data, nexus5_data=n5_data, profile_id=None)

                # 🟢 BROADCAST: Batch scores to UI scanner (avoid request spam)
                with broadcast_lock:
                    broadcast_batch.append(confluence)

                is_golden_n5 = False  # v12.1: Golden U-Turn deshabilitado completamente
                passes_confluence = confluence["confluence_score"] >= config.MIN_CONFLUENCE_SCORE
                if is_golden_n5 or passes_confluence:
                    enriched = dict(confluence)
                    enriched["agent_audit_context"] = {
                        "nexus15": self._json_safe_for_audit(nexus_data),
                        "scar": self._json_safe_for_audit(scar_data) if scar_data else {},
                        "nexus5": self._json_safe_for_audit(n5_data) if n5_data else {},
                        "golden_uturn": {
                            "detected": bool(n5_data.get("golden_uturn", False)) if n5_data else False,
                            "angle": n5_data.get("golden_uturn_angle") if n5_data else None,
                            "drop_pct": n5_data.get("golden_uturn_drop_pct") if n5_data else None,
                            "sl_5low": n5_data.get("golden_uturn_sl_5low") if n5_data else None,
                            # v9.1 structural analytics for calibration
                            "price_to_ma99_distance_pct": n5_data.get("gu_price_to_ma99_distance_pct") if n5_data else None,
                            "ma99_now": n5_data.get("gu_ma99_now") if n5_data else None,
                            "ma99_ago": n5_data.get("gu_ma99_ago") if n5_data else None,
                            "volume_ignition_ratio_1m": n5_data.get("gu_volume_ignition_ratio_1m") if n5_data else None,
                            "atr_volatility_pct": n5_data.get("gu_atr_volatility_pct") if n5_data else None,
                            "consecutive_flat_candles": n5_data.get("gu_consecutive_flat_candles") if n5_data else None,
                            "ma7_now": n5_data.get("gu_ma7_now") if n5_data else None,
                            "close_above_ma7": n5_data.get("gu_close_above_ma7") if n5_data else None,
                        },
                    }

                    # Golden U-Turn v11.12: SOLO para MA Cross Momentum.
                    # Otras estrategias (Standard Scalping, MA Clone, etc.) NO usan Golden U-Turn.
                    # El audit_context golden_uturn se preserva para todos (data enrichment),
                    # pero el Score=99 y golden_uturn_mode solo se activan en MA Cross Momentum.
                    # El Score=99 se asigna en el profile execution loop cuando el profile es MA Cross Momentum.

                    # ── BONUS SMC: Aplicar bonus de calidad antes del ranking ──
                    # Usamos price_at_signal (last_close de Nexus) para validar sin latencia REST
                    px_val = enriched.get("price_at_signal") or self.fetcher.get_current_price(symbol)
                    if px_val:
                        v_ok, v_code, v_metrics = validate_pre_trade(enriched, px_val, btc_filter=self.btc_filter, btc_corr=self.btc_corr)
                        if v_ok:
                            if "smc_bonus" in v_metrics:
                                bonus = float(v_metrics["smc_bonus"])
                                enriched["confluence_score"] += bonus
                                enriched["smc_bonus_applied"] = bonus

                            with candidates_lock:
                                candidates.append(enriched)
                            
                            logger.info(
                                f"✅ CANDIDATE: {symbol} | Score={enriched['confluence_score']:.1f} | "
                                f"Dir={enriched['trade_direction']} | Nexus={enriched['nexus_confidence']}%" +
                                (f" | SMC Bonus=+{enriched['smc_bonus_applied']}" if "smc_bonus_applied" in enriched else "")
                            )
                        else:
                            logger.info(f"❌ [VETO] {symbol} rechazado en scan: {v_code}")
                return None
            except Exception as e:
                logger.error(f"⚠️ Error analyzing {symbol}: {e}")
                return None
        
        logger.info(f"[Step 4/6] Escaneando {len(all_targets)} símbolos con NEXUS-15 [PARALELIZADO v7.3]...")
        
        # Usar max_workers=10 para paralelizar sin saturar APIs
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(analyze_nexus15_symbol, symbol) for symbol in all_targets]
            for future in as_completed(futures):
                pass  # Los contadores se actualizan dentro de analyze_nexus15_symbol

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

        # ── GOLDEN U-TURN v9.1: Inyección directa (INDEPENDIENTE de Nexus-15) ──
        # Símbolos que pasaron Gravity Check en Step 3.5 entran con Score=99 sin Nexus-15.
        if getattr(config, "GOLDEN_UTURN_ENABLED", True):
            existing_syms = {c.get("symbol") for c in candidates}
            golden_injected = 0
            golden_upgraded = 0
            for symbol, n5_data in nexus5_cache.items():
                if not n5_data or not n5_data.get("golden_uturn"):
                    continue
                if self._should_skip(symbol):
                    continue

                if symbol in existing_syms:
                    for c in candidates:
                        if c.get("symbol") != symbol:
                            continue
                        c["confluence_score"] = float(getattr(config, "GOLDEN_UTURN_SCORE", 99.0))
                        c["golden_uturn_mode"] = True
                        c["source"] = "golden_uturn"
                        c["trade_direction"] = "LONG"
                        c["side"] = 0
                        sl_5low = n5_data.get("golden_uturn_sl_5low")
                        if sl_5low and float(sl_5low) > 0:
                            c["custom_sl_price"] = float(sl_5low)
                            c["golden_uturn_sl_5low"] = sl_5low
                        golden_upgraded += 1
                    continue

                gc = self._build_golden_uturn_candidate(symbol, n5_data)
                gc_px = gc.get("price_at_signal") or self.fetcher.get_current_price(symbol)
                if not gc_px or gc_px <= 0:
                    continue
                try:
                    v_ok, v_code, _ = validate_pre_trade(
                        gc, gc_px, btc_filter=self.btc_filter, btc_corr=self.btc_corr
                    )
                    if not v_ok:
                        logger.info(f"[GOLDEN-INJECT] VETO {symbol}: {v_code}")
                        continue
                except Exception as e:
                    logger.warning(f"[GOLDEN-INJECT] Error validando {symbol}: {e}")
                    continue

                candidates.append(gc)
                existing_syms.add(symbol)
                golden_injected += 1
                logger.warning(
                    f"[GOLDEN-INJECT] {symbol} | Score=99 | "
                    f"Angle={n5_data.get('golden_uturn_angle')}° | "
                    f"Drop={n5_data.get('golden_uturn_drop_pct')}% — PRIORIDAD ABSOLUTA"
                )

            if golden_injected or golden_upgraded:
                logger.info(
                    f"[GOLDEN-INJECT] {golden_injected} nuevos + {golden_upgraded} upgraded "
                    f"(total candidates={len(candidates)})"
                )

        # ── TOTAL-SWEEP v13.0: The Sinfonía Final ───────────────────────────────────────
        # NEXUS-5 Bottom Sniper > 90% → HUNTING_READY → Volume Radar → Ley de Nico G>R
        if getattr(config, "TOTAL_SWEEP_ENABLED", True):
            self.state.cleanup_expired_hunting(
                max_candles_15m=int(getattr(config, "TOTAL_SWEEP_HUNTING_DURATION_CANDLES", 6))
            )
            hunting = self.state.get_hunting_ready()
            existing_syms_ts = {c.get("symbol") for c in candidates}
            ts_injected = 0
            ts_hunting_new = 0
            ts_min_conf = float(getattr(config, "TOTAL_SWEEP_MIN_NEXUS5_CONFIDENCE", 90.0))
            ts_slope_threshold = float(getattr(config, "TOTAL_SWEEP_VOLUME_SLOPE_THRESHOLD", -5.0))

            for symbol, n5_data in nexus5_cache.items():
                if not n5_data:
                    continue
                features = n5_data.get("features", {})
                is_bs = features.get("is_bottom_sniper", False) if isinstance(features, dict) else False
                n5_conf = float(n5_data.get("ai_confidence", 0))

                # Phase 1: NEW — Activate HUNTING_READY if NEXUS-5 > threshold
                if is_bs and n5_conf >= ts_min_conf and symbol not in hunting:
                    if self._should_skip(symbol):
                        continue
                    vol_slope = self._calculate_volume_slope_15m(symbol)
                    sweep_likely = vol_slope < ts_slope_threshold
                    self.state.set_hunting_ready(symbol, {
                        "activated_at": datetime.now(timezone.utc).timestamp(),
                        "n5_confidence": n5_conf,
                        "volume_slope": round(vol_slope, 4),
                        "sweep_likely": sweep_likely,
                        "radar_mode": "SWEEP_LIKELY" if sweep_likely else "DIRECT_BOOM",
                    })
                    hunting[symbol] = {"activated_at": datetime.now(timezone.utc).timestamp(),
                                       "n5_confidence": n5_conf, "volume_slope": round(vol_slope, 4),
                                       "sweep_likely": sweep_likely}
                    ts_hunting_new += 1
                    logger.warning(
                        f"[TOTAL-SWEEP] 🎯 HUNTING_READY activated: {symbol} | "
                        f"N5={n5_conf:.1f}% | VolSlope={vol_slope:.2f} | "
                        f"Radar={'SWEEP_LIKELY' if sweep_likely else 'DIRECT_BOOM'}"
                    )

                # Phase 2: CHECK TRIGGER for symbols already in HUNTING_READY
                if symbol in hunting and symbol not in existing_syms_ts:
                    triggered, red_low, details = self._check_green_beats_red_15m(symbol)
                    if not triggered:
                        logger.info(
                            f"[TOTAL-SWEEP] {symbol}: Esperando gatillo G>R | "
                            f"prev_red={details.get('prev_red')} curr_green={details.get('curr_green')} "
                            f"prev_body={details.get('prev_body')} curr_body={details.get('curr_body')}"
                        )
                        continue

                    # GATILLO DISPARADO — Build and inject candidate
                    vol_slope = self._calculate_volume_slope_15m(symbol)
                    gc = self._build_total_sweep_candidate(symbol, n5_data, vol_slope, red_low)
                    gc_px = gc.get("price_at_signal") or self.fetcher.get_current_price(symbol)
                    if not gc_px or gc_px <= 0:
                        continue
                    try:
                        v_ok, v_code, _ = validate_pre_trade(
                            gc, gc_px, btc_filter=self.btc_filter, btc_corr=self.btc_corr
                        )
                        if not v_ok:
                            logger.info(f"[TOTAL-SWEEP] VETO {symbol}: {v_code}")
                            continue
                    except Exception as e:
                        logger.warning(f"[TOTAL-SWEEP] Error validando {symbol}: {e}")
                        continue

                    candidates.append(gc)
                    existing_syms_ts.add(symbol)
                    self.state.remove_hunting_ready(symbol)
                    ts_injected += 1
                    logger.warning(
                        f"[TOTAL-SWEEP] 🔥 TRIGGERED {symbol} | Score=99.5 | "
                        f"VolSlope={vol_slope:.2f} | SL={red_low} | "
                        f"Radar={'SWEEP_LIKELY' if vol_slope < ts_slope_threshold else 'DIRECT_BOOM'} — "
                        f"[STRAT: TOTAL-SWEEP-v13.0]"
                    )

            still_hunting = len(self.state.get_hunting_ready())
            if ts_hunting_new or ts_injected or still_hunting:
                logger.info(
                    f"[TOTAL-SWEEP] {ts_hunting_new} nuevos HUNTING + {ts_injected} TRIGGERED | "
                    f"{still_hunting} aún esperando G>R"
                )

        # Inject Nexus-15 TOP candidates (NUNCA pisan Golden U-Turn)
        for nc in nexus_top_candidates:
            existing_syms = {c["symbol"] for c in candidates}
            if nc["symbol"] in existing_syms:
                # Si ya hay Golden U-Turn, Nexus-15 TOP no puede reemplazarlo
                if any(
                    c.get("symbol") == nc["symbol"] and self._is_golden_uturn_candidate(c)
                    for c in candidates
                ):
                    logger.info(
                        f"[NEXUS-TOP] SKIP {nc['symbol']} — Golden U-Turn tiene prioridad absoluta"
                    )
                continue
            if nc["symbol"] not in existing_syms:
                # Pre-validate NEXUS-TOP candidate before injection (consistent with scan flow)
                try:
                    nc_px = nc.get("price_at_signal") or self.fetcher.get_current_price(nc["symbol"])
                    if nc_px:
                        v_ok, v_code, v_metrics = validate_pre_trade(nc, nc_px, btc_filter=self.btc_filter, btc_corr=self.btc_corr)
                        if not v_ok:
                            logger.info(f"[NEXUS-TOP] VETO {nc['symbol']}: {v_code} — descartado.")
                            continue
                except Exception as e:
                    logger.warning(f"[NEXUS-TOP] Error validando {nc['symbol']}: {e}")

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
            bridge_dir   = sig.get("direction", "").upper()  # Inicializar dirección del bridge

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

            # ── NEXUS-5 Reversal Check: Si confidence > 80%, el movimiento ya pasó. Considerar reversión. ──
            # Solo para señales de NEXUS-5 (source=nexus5_bridge o estado=NEXUS5_HOT)
            is_nexus5_signal = sig.get("source") == "nexus5_bridge" or sig.get("estado") == "NEXUS5_HOT"
            n5_confidence = float(sig.get("nexus5", 0))
            n5_phase = sig.get("phase", "")
            n5_direction = sig.get("direction", "").upper()

            if is_nexus5_signal and n5_confidence > config.NEXUS5_REVERSAL_MIN:
                # Confidence > 80% = movimiento ya pasó, considerar entrada en dirección opuesta (exhaustion)
                reversed_dir = "BEARISH" if n5_direction == "BULLISH" else "BULLISH" if n5_direction == "BEARISH" else n5_direction
                if reversed_dir != n5_direction:
                    logger.info(
                        "[BRIDGE] NEXUS-5 REVERSAL %s: %s @ %.0f%% = too late, flipping to %s (exhaustion entry)",
                        sym, n5_direction, n5_confidence, reversed_dir
                    )
                    bridge_dir = reversed_dir

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
            v_ok, v_code, v_metrics = validate_pre_trade(bridge_cand, current_px, btc_filter=self.btc_filter, btc_corr=self.btc_corr)
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

        # Golden U-Turn + TOTAL-SWEEP siempre al frente de la cola (Score=99/99.5 > Nexus-15)
        candidates.sort(
            key=lambda x: (
                0 if self._is_total_sweep_candidate(x) else (1 if self._is_golden_uturn_candidate(x) else 2),
                -float(x.get("confluence_score", 0)),
            )
        )

        # 6. For EACH active profile: rank and execute candidates
        active_trades = self.positions.get_active_trades() or []
        
        for profile in self.active_profiles:
            p_name = profile.get("name", "Unknown")
            p_id = profile.get("id")
            logger.info(f"--- Strategy Execution: {p_name} ---")

            # MA Clone: Recalculate confluence score with profile-specific logic
            ma_clone_id = "3a21db74-5d45-fcbf-f186-a284d59e97fb"
            if p_id == ma_clone_id:
                scar_alerts = self.signals.get_scar_alerts()
                nexus5_cache = {}  # v12.1: Golden U-Turn deshabilitado, nexus5 no se usa
                recalculated_candidates = []
                for c in candidates:
                    # Recalculate confluence with MA Clone profile_id
                    nexus_data = c.get("agent_audit_context", {}).get("nexus15", {})
                    scar_data = scar_alerts.get(c.get("symbol"), {})
                    n5_data = nexus5_cache.get(c.get("symbol"))
                    new_confluence = self.signals.calculate_confluence(
                        c.get("symbol"),
                        scar_data,
                        nexus_data,
                        nexus5_data=n5_data,
                        profile_id=ma_clone_id
                    )
                    # Preserve other fields
                    for k, v in c.items():
                        if k not in new_confluence:
                            new_confluence[k] = v
                    recalculated_candidates.append(new_confluence)
                candidates = recalculated_candidates

            # Filter candidates for THIS profile
            p_candidates = []
            p_rejected = []  # v12.1: Track rejected candidates for audit
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
                is_golden = self._is_golden_uturn_candidate(c)
                
                # v12.1: Golden U-Turn DESHABILITADO — nunca inyectar Score=99 ni golden_uturn_mode
                is_golden = False
                c.pop("golden_uturn_mode", None)
                logger.debug(f"[GOLDEN-OFF v12.1] {c.get('symbol')}: Golden U-Turn deshabilitado, flags limpiados")

                if c.get("source") == "LSE":
                    if not batch_ok:
                        p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": "lse_batch_not_ok"})
                        continue
                    if self.state.is_lse_symbol_cooldown_active(c.get("symbol")):
                        p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": "lse_cooldown"})
                        continue

                # v12.0 LEY DE NICO: Filtro TOP-5 para MA Cross Momentum
                # Eliminar monedas que no tengan al menos 6 velas de cemento acumuladas
                if p_id == "3a214744-f0b9-68bb-f235-438a39d39d33" or p_name == "MA Cross Momentum":
                    audit_ctx = c.get("agent_audit_context", {})
                    nexus15_ctx = audit_ctx.get("nexus15", {}) if isinstance(audit_ctx, dict) else {}
                    nexus_features = nexus15_ctx.get("features", {}) if isinstance(nexus15_ctx, dict) else {}
                    
                    # Calcular velas de cemento (similar a _check_nico_l_shape)
                    ma50_history = nexus_features.get("ma50_history", [])
                    recent_prices = nexus_features.get("close_history", [])
                    
                    if ma50_history and recent_prices:
                        min_cement_for_top5 = int(getattr(config, "NICO_L_SHAPE_MIN_CEMENT_FOR_TOP5", 6))
                        max_price_ma50_dist_pct = float(getattr(config, "NICO_L_SHAPE_MAX_PRICE_MA50_DIST_PCT", 0.5))
                        max_ma50_slope_deg = float(getattr(config, "NICO_L_SHAPE_MAX_MA50_SLOPE_DEG", 0.2))
                        reset_threshold_pct = float(getattr(config, "NICO_L_SHAPE_RESET_THRESHOLD_PCT", 1.0))
                        
                        cement_candles = 0
                        max_cement_candles = 0
                        
                        recent_ma50 = ma50_history[-20:] if len(ma50_history) >= 20 else ma50_history
                        recent_prices = recent_prices[-20:] if len(recent_prices) >= 20 else recent_prices
                        
                        for i in range(len(recent_ma50) - 1, -1, -1):
                            if i >= len(recent_prices):
                                break
                            
                            price = float(recent_prices[i])
                            ma50 = float(recent_ma50[i])
                            
                            price_ma50_dist_pct = abs((price - ma50) / ma50) * 100 if ma50 > 0 else 999
                            
                            ma50_window_start = max(0, i - 5)
                            ma50_window = recent_ma50[ma50_window_start:i+1]
                            ma50_slope = self._calculate_ma99_slope_angle(ma50_window, window=len(ma50_window))
                            
                            if price_ma50_dist_pct > reset_threshold_pct:
                                cement_candles = 0
                                continue
                            
                            if (price_ma50_dist_pct <= max_price_ma50_dist_pct and 
                                abs(ma50_slope) <= max_ma50_slope_deg):
                                cement_candles += 1
                                max_cement_candles = max(max_cement_candles, cement_candles)
                            else:
                                cement_candles = 0
                        
                        if max_cement_candles < min_cement_for_top5:
                            logger.info(
                                f"[NICO-L-SHAPE TOP-5] {p_name} SKIP {c.get('symbol')}: "
                                f"Solo {max_cement_candles} velas de cemento (necesita {min_cement_for_top5})"
                            )
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"top5_cement({max_cement_candles}<{min_cement_for_top5})"})
                            continue

                # v9.5 Dual Sniper: Golden VIP bypass total de score/nexus del perfil
                if not is_golden:
                    if c.get("confluence_score", 0) < min_score:
                        logger.info(f"[{p_name}] SKIP {c.get('symbol')}: score {c.get('confluence_score')} < {min_score}")
                        p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"score<{min_score}"})
                        continue
                    if c.get("source") != "LSE" and c.get("nexus_confidence", 0) < min_nexus:
                        logger.info(f"[{p_name}] SKIP {c.get('symbol')}: nexus {c.get('nexus_confidence')} < {min_nexus}")
                        p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"nexus<{min_nexus}"})
                        continue
                else:
                    logger.info(
                        f"[GOLDEN-VIP] {c.get('symbol')}: bypass perfil {p_name} "
                        f"(nexus={c.get('nexus_confidence', 0)}%, score={c.get('confluence_score', 0)})"
                    )
                
                allowed = profile.get("allowedSources")
                if allowed and not is_golden:
                    src = (c.get("source", "") or "").lower()
                    if src in ("nexus_top", "nexus15_ui"):
                        src = "nexus"
                    elif src == "redis_bridge":
                        src = "bridge"
                    elif src == "golden_uturn":
                        src = "golden_uturn"
                        
                    if isinstance(allowed, list):
                        if src not in [s.lower() for s in allowed]:
                            logger.info(f"[{p_name}] SKIP {c.get('symbol')}: src {src} not in {allowed}")
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"src_not_allowed({src})"})
                            continue
                    elif isinstance(allowed, str):
                        # .NET serializes as "LSE,Nexus,Bridge"
                        allowed_list = [s.strip().lower() for s in allowed.split(",")]
                        if src not in allowed_list:
                            logger.info(f"[{p_name}] SKIP {c.get('symbol')}: src {src} not in {allowed_list}")
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"src_not_allowed({src})"})
                            continue
                
                # Profile side filters
                allow_long = profile.get("allowLong", True)
                allow_short = profile.get("allowShort", True)
                cand_side = int(c.get("side", 0))
                
                if cand_side == 0 and not allow_long:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: Long not allowed")
                    p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": "long_not_allowed"})
                    continue
                if cand_side == 1 and not allow_short:
                    logger.info(f"[{p_name}] SKIP {c.get('symbol')}: Short not allowed")
                    p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": "short_not_allowed"})
                    continue

                # Fix 2: Filtros RSI y MA7 por perfil (PascalCase del DTO -> camelCase del JSON)
                # BYPASS: Golden U-Turn v9.0 — si el candidato tiene golden_uturn_mode, ignorar estos filtros.
                if not c.get("golden_uturn_mode"):
                    max_rsi_long  = profile.get("maxRsiLong")
                    min_rsi_short = profile.get("minRsiShort")
                    cand_rsi = float(c.get("rsi", 50))

                    if max_rsi_long is not None and cand_side == 0:
                        if cand_rsi > float(max_rsi_long):
                            logger.info(f"[VETO] {c['symbol']} RSI {cand_rsi} > max {max_rsi_long} for profile {p_name}")
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"rsi>{max_rsi_long}"})
                            continue

                    if min_rsi_short is not None and cand_side == 1:
                        if cand_rsi < float(min_rsi_short):
                            logger.info(f"[VETO] {c['symbol']} RSI {cand_rsi} < min {min_rsi_short} for profile {p_name}")
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"rsi<{min_rsi_short}"})
                            continue

                    # Filtro distancia MA7 por perfil
                    max_dist_ma7 = profile.get("maxMa7DistancePct")
                    if max_dist_ma7 is not None:
                        dist = abs(float(c.get("distance_to_ma7_pct", 0)))
                        if dist > float(max_dist_ma7):
                            logger.info(f"[VETO] {c['symbol']} MA7 Dist {dist:.2f}% > max {max_dist_ma7}% for profile {p_name}")
                            p_rejected.append({"symbol": c.get("symbol"), "score": c.get("confluence_score", 0), "nexus": c.get("nexus_confidence", 0), "reason": f"ma7_dist>{max_dist_ma7}"})
                            continue

                p_candidates.append(c)

            if not p_candidates:
                logger.info(f"No candidates pass profile {p_name}")
                continue

            # v9.5 Dual Sniper + v13.0 TOTAL-SWEEP: VIP motors first, Nexus-15 estándar después
            p_vip = [c for c in p_candidates if self._is_golden_uturn_candidate(c) or self._is_total_sweep_candidate(c)]
            p_standard = [c for c in p_candidates if not self._is_golden_uturn_candidate(c) and not self._is_total_sweep_candidate(c)]
            p_vip.sort(key=lambda x: x["confluence_score"], reverse=True)
            p_standard.sort(key=lambda x: x["confluence_score"], reverse=True)
            p_candidates = p_vip + p_standard
            if p_vip:
                logger.info(
                    f"[DUAL-SNIPER] {p_name}: {len(p_vip)} VIP (Golden+TOTAL-SWEEP) + {len(p_standard)} Nexus estándar"
                )
            
            # Check slot availability for this profile
            p_max_pos = int(profile.get("maxOpenPositions", config.MAX_OPEN_POSITIONS))
            # Fix: Standard Scalping usa STANDARD_PROFILE_ID; trades legacy con null también le pertenecen.
            p_id = profile.get("id")
            if p_id == STANDARD_PROFILE_ID:
                p_active_count = len([
                    t for t in active_trades
                    if t.get("strategyProfileId", t.get("strategy_profile_id")) in (STANDARD_PROFILE_ID, None)
                    and t.get("strategyProfileId", t.get("strategy_profile_id")) != CLONE_PROFILE_ID
                ])
            else:
                p_active_count = len([
                    t for t in active_trades
                    if t.get("strategyProfileId", t.get("strategy_profile_id")) == p_id
                ])
            
            if p_active_count >= p_max_pos:
                vip_waiting = [c for c in p_candidates if self._is_golden_uturn_candidate(c) or self._is_total_sweep_candidate(c)]
                if not vip_waiting:
                    logger.info(f"[LIMIT] Profile {p_name} is full ({p_active_count}/{p_max_pos}). Skipping new trades.")
                    continue
                logger.info(
                    f"[VIP-PRIORITY] Profile {p_name} lleno pero hay {len(vip_waiting)} "
                    f"VIP (Golden+TOTAL-SWEEP) — intentando upgrade/reemplazo"
                )

            # v12.1: Sort rejected candidates by score desc, take top 10 for audit
            p_rejected.sort(key=lambda x: x.get("score", 0), reverse=True)
            cycle_rejected = p_rejected[:10]

            # Try ranked candidates in order (LSE + Nexus); AGENT_MAX_CANDIDATES_PER_CYCLE enables rank 2..N fallback.
            max_try = max(1, AGENT_MAX_CANDIDATES_PER_CYCLE)
            p_ranked = p_candidates[:max_try]
            
            for idx, cand in enumerate(p_ranked):
                sym = cand.get("symbol", "")
                if self._execute_trade(cand, profile=profile, cycle_rejected=cycle_rejected):
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
            confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data, profile_id=None)

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
                confluence = self.signals.calculate_confluence(symbol, scar_data, nexus_data, profile_id=None)

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

    def _close_worst_position(self, profile_id: str = None) -> bool:
        """
        ── FIX v11.6: THE PURGE — Selección Quirúrgica de Reemplazo ──
        Encuentra la posición a sacrificar siguiendo esta prioridad:
        1. Margen Roto (< 140 USDT) - cerrar primero sin importar PnL
        2. PnL más negativo de la estrategia
        Si todas las posiciones están en profit (> 0.1%) y tienen margen correcto, el Upgrade se anula.
        """
        open_positions = self.state.get_open_positions()
        if not open_positions:
            return False

        # Filtrar para cerrar solo posiciones pertenecientes a esta estrategia específica
        open_positions = [
            p for p in open_positions
            if p.get("strategyProfileId", p.get("strategy_profile_id")) == profile_id
        ]
        if not open_positions:
            return False

        # ── PRIORIDAD 1: Buscar posiciones con margen roto (< 140 USDT) ──
        broken_margin_positions = []
        for pos in open_positions:
            margin = float(pos.get("margin", 0))
            if margin < 140.0:  # Margen roto: menos de 140 USDT
                broken_margin_positions.append(pos)
        
        if broken_margin_positions:
            # Cerrar la primera posición con margen roto (fusible)
            victim = broken_margin_positions[0]
            symbol = victim["symbol"]
            margin = float(victim.get("margin", 0))
            logger.warning(
                f"[PURGE v11.6] Seleccionada posición {symbol} para sacrificio. "
                f"Razón: Margen Roto (${margin:.2f} < 140 USDT) — Fusible activado."
            )
            success = self.positions.close_trade(victim["trade_id"])
            if success:
                self.state.remove_position(victim["trade_id"])
                return True
            return False

        # ── PRIORIDAD 2: Buscar la posición con PnL más negativo ──
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

        # ── FIX v11.5: MASTER-SNIPER — Prohibir cierre de posiciones ganadoras (Executive Override) ──
        # El bot tiene PROHIBIDO cerrar cualquier posición para un "Upgrade" si el PnL es SUPERIOR a 0.1%
        # Solo se reemplazan posiciones que estén en PÉRDIDA. Si todas están en profit, NO ABRE nada nuevo.
        if worst_pos:
            if worst_pnl > 0.001:  # 0.1% = 0.001 en decimal
                logger.warning(
                    f"[PURGE v11.6] UPGRADE ABORTADO: Todas las posiciones tienen PnL POSITIVO (> 0.1%). "
                    f"La peor posición ({worst_pos['symbol']}) tiene {worst_pnl*100:.2f}%. "
                    f"PROHIBIDO cerrar ganadores."
                )
                return False
            logger.warning(
                f"[PURGE v11.6] Seleccionada posición {worst_pos['symbol']} para sacrificio. "
                f"Razón: PnL Negativo {worst_pnl*100:.2f}%"
            )
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

    def _is_golden_uturn_candidate(self, candidate: dict) -> bool:
        """True si el candidato entró por la Regla de Oro (Golden U-Turn)."""
        if candidate.get("golden_uturn_mode") or candidate.get("source") == "golden_uturn":
            return True

    def _calculate_ma99_slope_angle(self, ma_values: list, window: int = 12) -> float:
        """
        Calcula el ángulo de inclinación de una media móvil en grados.
        Usa regresión lineal sobre los últimos 'window' valores.
        """
        if not ma_values or len(ma_values) < 2:
            return 0.0
        
        # Usar los últimos 'window' valores
        values = ma_values[-window:] if len(ma_values) >= window else ma_values
        
        n = len(values)
        if n < 2:
            return 0.0
        
        # Regresión lineal simple: y = mx + b
        x = list(range(n))
        y = values
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        
        # Calcular pendiente (m)
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0
        
        m = (n * sum_xy - sum_x * sum_y) / denominator
        
        # Convertir pendiente a ángulo en grados
        # Ángulo = atan(m) * (180 / π)
        angle_deg = math.degrees(math.atan(m))
        
        return angle_deg

    def _build_golden_uturn_candidate(self, symbol: str, n5_data: dict, nexus_data: dict = None) -> dict:
        """
        Construye candidato Golden U-Turn con Score=99, sin depender de Nexus-15.
        IF (MA99 plana AND vino de arriba) -> BUY.
        """
        price = self.fetcher.get_current_price(symbol)
        gu_score = float(getattr(config, "GOLDEN_UTURN_SCORE", 99.0))
        sl_5low = n5_data.get("golden_uturn_sl_5low")
        cand = {
            "symbol": symbol,
            "confluence_score": gu_score,
            "nexus_confidence": 0,
            "trade_direction": "LONG",
            "side": 0,
            "source": "golden_uturn",
            "golden_uturn_mode": True,
            "price_at_signal": price,
            "estimated_range_pct": float(n5_data.get("gu_atr_volatility_pct") or 5.0),
            "golden_uturn_sl_5low": sl_5low,
            "reasons": ["[GOLDEN-U-TURN] MA99 horizontal tras caída vertical — Score=99"],
            "agent_audit_context": {
                "nexus15": self._json_safe_for_audit(nexus_data) if nexus_data else {},
                "scar": {},
                "nexus5": self._json_safe_for_audit(n5_data),
                "golden_uturn": {
                    "detected": True,
                    "angle": n5_data.get("golden_uturn_angle"),
                    "drop_pct": n5_data.get("golden_uturn_drop_pct"),
                    "sl_5low": sl_5low,
                    "price_to_ma99_distance_pct": n5_data.get("gu_price_to_ma99_distance_pct"),
                    "ma99_now": n5_data.get("gu_ma99_now"),
                    "ma99_ago": n5_data.get("gu_ma99_ago"),
                    "volume_ignition_ratio_1m": n5_data.get("gu_volume_ignition_ratio_1m"),
                    "atr_volatility_pct": n5_data.get("gu_atr_volatility_pct"),
                    "consecutive_flat_candles": n5_data.get("gu_consecutive_flat_candles"),
                    "ma7_now": n5_data.get("gu_ma7_now"),
                    "close_above_ma7": n5_data.get("gu_close_above_ma7"),
                },
            },
        }
        if sl_5low and float(sl_5low) > 0 and price and float(sl_5low) < float(price):
            cand["custom_sl_price"] = float(sl_5low)
        return cand

    # ── TOTAL-SWEEP v13.0: Helper Methods ────────────────────────────────────────────

    def _calculate_volume_slope_15m(self, symbol: str) -> float:
        """
        [TOTAL-SWEEP v13.0] Radar de Intenciones del MM.
        Linear regression slope on last N 15m candles' volume.
        Returns raw slope (negative = volume dying = SWEEP_LIKELY).
        """
        lookback = int(getattr(config, "TOTAL_SWEEP_VOLUME_LOOKBACK", 15))
        try:
            klines = self.fetcher.get_klines_for_nexus(symbol, interval="15m", limit=lookback + 5)
            if not klines or len(klines) < lookback:
                return 0.0
            volumes = [float(k.get("volume", 0)) for k in klines[-lookback:]]
            n = len(volumes)
            sum_x = sum(range(n))
            sum_y = sum(volumes)
            sum_xy = sum(i * v for i, v in enumerate(volumes))
            sum_x2 = sum(i * i for i in range(n))
            denom = n * sum_x2 - sum_x * sum_x
            if denom == 0:
                return 0.0
            slope = (n * sum_xy - sum_x * sum_y) / denom
            return slope
        except Exception as e:
            logger.debug(f"[TOTAL-SWEEP] Volume slope error for {symbol}: {e}")
            return 0.0

    def _check_green_beats_red_15m(self, symbol: str) -> tuple:
        """
        [TOTAL-SWEEP v13.0] Ley de Nico — Universal Trigger on 15m.
        Previous candle (n-1) = RED, Current candle (n) = GREEN, Green body > Red body.
        Returns (triggered: bool, red_candle_low: float, details: dict)
        """
        try:
            klines = self.fetcher.get_klines_for_nexus(symbol, interval="15m", limit=5)
            if not klines or len(klines) < 2:
                return False, 0.0, {}
            prev = klines[-2]
            curr = klines[-1]
            prev_open, prev_close = float(prev["open"]), float(prev["close"])
            curr_open, curr_close = float(curr["open"]), float(curr["close"])
            prev_body = prev_open - prev_close
            curr_body = curr_close - curr_open
            is_prev_red = prev_body > 0
            is_curr_green = curr_body > 0
            triggered = is_prev_red and is_curr_green and curr_body > prev_body
            red_low = float(prev.get("low", 0))
            return triggered, red_low, {
                "prev_body": round(prev_body, 8),
                "curr_body": round(curr_body, 8),
                "prev_red": is_prev_red,
                "curr_green": is_curr_green,
            }
        except Exception as e:
            logger.debug(f"[TOTAL-SWEEP] Green>Red check error for {symbol}: {e}")
            return False, 0.0, {}

    def _build_total_sweep_candidate(self, symbol: str, n5_data: dict, volume_slope: float, red_candle_low: float) -> dict:
        """
        [TOTAL-SWEEP v13.0] Build bypass candidate with Score=99.5.
        SL = low of previous red candle, TP = entry + 12%.
        """
        price = self.fetcher.get_current_price(symbol)
        ts_score = float(getattr(config, "TOTAL_SWEEP_SCORE", 99.5))
        tp_min_pct = float(getattr(config, "TOTAL_SWEEP_TP_MIN_DISTANCE_PCT", 12.0))
        tp_price = price * (1 + tp_min_pct / 100) if price and price > 0 else 0
        sweep_likely = volume_slope < float(getattr(config, "TOTAL_SWEEP_VOLUME_SLOPE_THRESHOLD", -5.0))
        cand = {
            "symbol": symbol,
            "confluence_score": ts_score,
            "nexus_confidence": n5_data.get("ai_confidence", 0),
            "trade_direction": "LONG",
            "side": 0,
            "source": "total_sweep",
            "total_sweep_mode": True,
            "price_at_signal": price,
            "estimated_range_pct": tp_min_pct,
            "reasons": ["[TOTAL-SWEEP-v13.0] Bottom Sniper + Volume Radar + Ley de Nico G>R"],
            "custom_sl_price": red_candle_low if red_candle_low > 0 and (not price or red_candle_low < price) else None,
            "custom_tp_price": tp_price if tp_price > 0 else None,
            "agent_audit_context": {
                "nexus5": self._json_safe_for_audit(n5_data),
                "total_sweep": {
                    "detected": True,
                    "volume_slope": round(volume_slope, 4),
                    "sweep_likely": sweep_likely,
                    "radar_mode": "SWEEP_LIKELY" if sweep_likely else "DIRECT_BOOM",
                    "red_candle_low": red_candle_low,
                    "tp_min_pct": tp_min_pct,
                    "n5_confidence": n5_data.get("ai_confidence", 0),
                },
                "scar": {},
                "nexus15": {},
            },
        }
        return cand

    def _is_total_sweep_candidate(self, candidate: dict) -> bool:
        """True si el candidato entró por TOTAL-SWEEP v13.0."""
        return candidate.get("total_sweep_mode", False) or candidate.get("source") == "total_sweep"

    def _get_ma99_15m(self, symbol: str) -> Optional[float]:
        try:
            klines = self.fetcher.get_klines_for_nexus(symbol, interval="15m", limit=120)
            if not klines or len(klines) < 99:
                return None
            closes = [float(k["close"]) for k in klines]
            return sum(closes[-99:]) / 99.0
        except Exception as e:
            logger.error(f"[SNIPER] Error calculating MA99 for {symbol}: {e}")
            return None

    def _compute_big_fish_sl_price(self, entry_price: float, lows: list) -> float:
        """
        v9.6 Big Fish SL para LONG: el stop más amplio entre low-20velas y 3% fijo bajo entrada.
        Retorna el precio de SL (más bajo = más aire al trade).
        """
        if entry_price <= 0:
            return 0.0
        lookback = int(getattr(config, "GOLDEN_UTURN_SL_CANDLE_LOOKBACK", 20))
        min_sl_pct = float(getattr(config, "GOLDEN_UTURN_SL_MIN_DISTANCE_PCT", 3.0))
        buffer_pct = float(getattr(config, "GOLDEN_UTURN_SL_SPREAD_BUFFER_PCT", 0.1))
        recent = lows[-lookback:] if len(lows) >= lookback else lows
        raw_low = min(recent) if recent else entry_price
        struct_sl = raw_low * (1.0 - buffer_pct / 100.0)
        pct_sl = entry_price * (1.0 - min_sl_pct / 100.0)
        # Para LONG: menor precio = stop más lejos = más aire
        return min(struct_sl, pct_sl)

    def _slope_angle_degrees(self, values: list, window: int = None) -> float:
        """Ángulo de inclinación por regresión lineal sobre los últimos N valores."""
        import math
        if not values or len(values) < 2:
            return 0.0
        if window is None:
            window = int(getattr(config, "GOLDEN_UTURN_ANGLE_WINDOW", 12))
        recent = values[-window:] if len(values) >= window else values
        if len(recent) < 2 or recent[-1] <= 0:
            return 0.0
        n = len(recent)
        x_vals = list(range(n))
        sum_x = sum(x_vals)
        sum_y = sum(recent)
        sum_xy = sum(xi * yi for xi, yi in zip(x_vals, recent))
        sum_x2 = sum(xi ** 2 for xi in x_vals)
        denom = n * sum_x2 - sum_x ** 2
        if denom == 0:
            return 0.0
        slope = (n * sum_xy - sum_x * sum_y) / denom
        return math.degrees(math.atan(slope / recent[-1]))

    def _check_golden_uturn(self, symbol: str) -> dict:
        """
        GOLDEN U-TURN v9.4 — Gravity Check ("Piso de Cemento").

        Detecta si la MA99 (15m) se horizontalizó tras una caída vertical.
        
        Condiciones:
          1. MA99 angle ±0.5° en ventana de 12 velas (mesa, no frenada momentánea)
          2. MA99 hace 100 velas (15m) cayó ≥3%
          3. Precio a ≤2% de distancia de MA99 (no cuchillos cayendo)
          4. Cierre 15m por encima de MA7 (giro confirmado)
          5. SL = Low 5 velas − 0.1% buffer
        """
        interval = getattr(config, "GOLDEN_UTURN_INTERVAL", "15m")
        lookback = int(getattr(config, "GOLDEN_UTURN_LOOKBACK_CANDLES", 100))
        result = {
            "passed": False, "angle": 0.0, "drop_pct": 0.0, "sl_5low": 0.0,
            "price_to_ma99_distance_pct": 0.0,
            "ma99_now": 0.0, "ma99_ago": 0.0,
            "ma7_now": 0.0, "close_above_ma7": False,
            "reject_reason": "",
            "volume_ignition_ratio_1m": 0.0,
            "atr_volatility_pct": 0.0,
            "consecutive_flat_candles": 0,
        }
        try:
            # Necesitamos al menos 99 + lookback velas para MA99 estable + histórico
            min_candles = 99 + lookback
            klines = self.fetcher.get_klines_for_nexus(symbol, interval=interval, limit=min_candles + 10)
            if not klines or len(klines) < min_candles:
                return result

            closes = [float(k["close"]) for k in klines]
            lows = [float(k["low"]) for k in klines]

            # ── Calcular EMA-99 ──
            period = 99
            if len(closes) < period:
                return result
            multiplier = 2.0 / (period + 1)
            ema = sum(closes[:period]) / period  # SMA inicial
            for price in closes[period:]:
                ema = (price - ema) * multiplier + ema
            # Reconstruir serie EMA completa para ángulo
            ema_series = []
            ema_val = sum(closes[:period]) / period
            for i, price in enumerate(closes):
                if i < period:
                    ema_series.append(sum(closes[:i+1]) / (i + 1))
                else:
                    ema_val = (price - ema_val) * multiplier + ema_val
                    ema_series.append(ema_val)

            # ── Ángulo de MA99 (regresión sobre ventana de 12 velas — inercia real) ──
            angle_window = int(getattr(config, "GOLDEN_UTURN_ANGLE_WINDOW", 12))
            angle = self._slope_angle_degrees(ema_series, window=angle_window)
            if ema_series[-1] <= 0:
                return result
            import math

            # ── Drop%: MA99 hace N velas vs actual ──
            # lookback ya definido al inicio de la función (config: 100 velas 15m)
            lookback_idx = min(lookback, len(ema_series) - 1)
            if lookback_idx <= 0:
                return result
            ma99_now = ema_series[-1]
            ma99_ago = ema_series[-lookback_idx - 1]
            if ma99_ago <= 0 or ma99_now <= 0:
                return result
            drop_pct = ((ma99_now - ma99_ago) / ma99_ago) * 100
            last_close = closes[-1]

            # ── SL v9.6 Big Fish: max(low-20velas, 3% bajo entrada) ──
            sl_5low = self._compute_big_fish_sl_price(last_close, lows)

            # ── Evaluar condiciones v9.5 "Piso de Cemento" ──
            angle_threshold = float(getattr(config, "GOLDEN_UTURN_ANGLE_THRESHOLD", 0.5))
            min_drop = float(getattr(config, "GOLDEN_UTURN_MIN_DROP_PCT", 3.0))
            max_ma99_dist = float(getattr(config, "GOLDEN_UTURN_MAX_MA99_DISTANCE_PCT", 15.0))
            max_ma7_dist = float(getattr(config, "GOLDEN_UTURN_MAX_MA7_DISTANCE_PCT", 2.0))
            ma7_now = sum(closes[-7:]) / 7.0 if len(closes) >= 7 else 0.0
            ma7_proximity_pct = (
                abs((last_close - ma7_now) / ma7_now) * 100 if ma7_now > 0 else 999.0
            )
            close_above_ma7 = bool(ma7_now > 0 and last_close > ma7_now)
            
            # ── v10.1 The Surgical Hook: Calcular MA7 history para slope ──
            ma7_history = []
            if len(closes) >= 7:
                for i in range(len(closes) - 6, len(closes) + 1):
                    if i > 0:
                        ma7_history.append(sum(closes[max(0, i-7):i]) / 7.0)

            price_to_ma99_pct = 0.0
            if ma99_now > 0:
                price_to_ma99_pct = ((last_close - ma99_now) / ma99_now) * 100

            result["angle"] = round(angle, 4)
            result["drop_pct"] = round(drop_pct, 4)
            result["sl_5low"] = sl_5low
            result["ma7_now"] = round(ma7_now, 6)
            result["ma7_proximity_pct"] = round(ma7_proximity_pct, 4)
            result["close_above_ma7"] = close_above_ma7
            result["ma7_history"] = ma7_history  # v10.1: para cálculo de slope MA7
            result["price_to_ma99_distance_pct"] = round(price_to_ma99_pct, 4)
            result["ma99_now"] = round(ma99_now, 6)
            result["ma99_ago"] = round(ma99_ago, 6)

            is_flat = abs(angle) <= angle_threshold
            is_drop = drop_pct <= -min_drop
            is_rise = drop_pct >= min_drop
            ma99_dist_ok = abs(price_to_ma99_pct) <= max_ma99_dist
            ma7_ok = ma7_now > 0 and ma7_proximity_pct <= max_ma7_dist

            reject_reasons = []
            if is_flat and is_rise:
                reject_reasons.append(f"techo (MA99 subió {drop_pct:.2f}%)")
            if not is_flat:
                reject_reasons.append(f"ángulo {angle:.2f}° > ±{angle_threshold}°")
            if not is_drop:
                reject_reasons.append(f"caída insuficiente ({drop_pct:.2f}%)")
            if not ma99_dist_ok:
                reject_reasons.append(f"dist MA99={price_to_ma99_pct:.2f}% > ±{max_ma99_dist}%")
            if not ma7_ok:
                reject_reasons.append(
                    f"dist MA7={ma7_proximity_pct:.2f}% > ±{max_ma7_dist}% (cerca del rebote, no encima)"
                )

            result["passed"] = bool(is_flat and is_drop and not is_rise and ma99_dist_ok and ma7_ok)
            if reject_reasons and not result["passed"]:
                result["reject_reason"] = "; ".join(reject_reasons)
                logger.debug(
                    f"[GRAVITY-CHECK] {symbol}: RECHAZADO v9.4 — {result['reject_reason']}"
                )
            elif result["passed"]:
                logger.info(
                    f"[GRAVITY-CHECK] {symbol}: v9.5 OK — Angle={angle:.2f}°, "
                    f"DistMA99={price_to_ma99_pct:.2f}%, DistMA7={ma7_proximity_pct:.2f}%"
                )

            # ── AUDIT METRICS (siempre, pase o no) ──

            # ATR% from 1h klines (14-period)
            highs = [float(k["high"]) for k in klines]
            tr_list = []
            for i_tr in range(max(1, len(klines) - 14), len(klines)):
                tr = max(
                    highs[i_tr] - lows[i_tr],
                    abs(highs[i_tr] - closes[i_tr - 1]),
                    abs(lows[i_tr] - closes[i_tr - 1]),
                )
                tr_list.append(tr)
            if tr_list and last_close > 0:
                atr_avg = sum(tr_list) / len(tr_list)
                result["atr_volatility_pct"] = round((atr_avg / last_close) * 100, 4)

            # Volume ignition ratio (1m): last 1m candle volume vs 10-candle average
            try:
                klines_1m = self.fetcher.get_klines_for_nexus(symbol, interval="1m", limit=15)
                if klines_1m and len(klines_1m) >= 10:
                    vols_1m = [float(k["volume"]) for k in klines_1m]
                    avg_1m = sum(vols_1m[-10:]) / 10.0
                    if avg_1m > 0:
                        result["volume_ignition_ratio_1m"] = round(vols_1m[-1] / avg_1m, 4)
            except Exception:
                pass  # non-critical for audit; leave 0.0 on failure

            # Consecutive flat candles: MA99 dentro de ±threshold en ventanas de 12 velas
            consecutive_flat = 0
            for i_cf in range(len(ema_series) - 1, angle_window - 1, -1):
                window = ema_series[i_cf - angle_window + 1: i_cf + 1]
                if len(window) < angle_window:
                    break
                a = self._slope_angle_degrees(window, window=angle_window)
                if abs(a) <= angle_threshold:
                    consecutive_flat += 1
                else:
                    break
            result["consecutive_flat_candles"] = consecutive_flat

        except Exception as e:
            logger.debug(f"[GRAVITY-CHECK] {symbol}: Error - {e}")

        return result

    def _get_vol_ratio_5m(self, symbol: str) -> float:
        try:
            klines = self.fetcher.get_klines_for_nexus(symbol, interval="5m", limit=15)
            if not klines or len(klines) < 10:
                return 1.0
            volumes = [float(k["volume"]) for k in klines]
            current_vol = volumes[-1]
            avg_vol = sum(volumes[-10:]) / 10.0
            if avg_vol <= 0:
                return 1.0
            return current_vol / avg_vol
        except Exception as e:
            logger.error(f"[SNIPER] Error calculating vol ratio for {symbol}: {e}")
            return 1.0

    def _manage_pending_snipers(self):
        snipers = self.state.get_pending_snipers()
        if not snipers:
            return

        logger.info(f"[Step 1.5/6] Checking {len(snipers)} pending sniper traps...")
        now = time.time()
        to_remove = []

        for s in snipers:
            symbol = s["symbol"]
            created_at = s.get("created_at", now)
            trigger_price = s["trigger_price"]
            candidate = s["candidate"]
            profile = s["profile"]

            # 4 hours vanish timer check
            if now - created_at > 4 * 3600:
                logger.info(f"[SNIPER] Vanish Timer expired for {symbol}. Removing trap.")
                to_remove.append(symbol)
                continue

            current_px = self.fetcher.get_current_price(symbol)
            if current_px <= 0:
                continue

            # Check price cross
            if current_px >= trigger_price:
                # Check volume ratio
                vol_ratio = self._get_vol_ratio_5m(symbol)
                logger.info(f"[SNIPER] {symbol} crossed trigger price {trigger_price:.6f} (current: {current_px:.6f}). Checking volume: {vol_ratio:.2f}x (needed: 2.5x)")
                if vol_ratio >= 2.5:
                    logger.info(f"[SNIPER] 🔥 TRIGGERED! {symbol} volume is explosive ({vol_ratio:.2f}x >= 2.5x). Executing trade...")
                    success = self._execute_trade(candidate, profile=profile, is_triggered_sniper=True)
                    if success:
                        to_remove.append(symbol)
                    else:
                        logger.warning(f"[SNIPER] Failed to execute triggered trade for {symbol}.")
            else:
                # Still stalking
                logger.info(f"[SNIPER] Stalking {symbol}: price={current_px:.6f} trigger={trigger_price:.6f} (diff={((trigger_price - current_px)/current_px)*100:.2f}%)")

        for sym in to_remove:
            self.state.remove_pending_sniper(sym)

    def _execute_trade(self, candidate: dict, profile: dict = None, is_triggered_sniper: bool = False, cycle_rejected: list = None) -> bool:
        symbol = candidate["symbol"]
        is_golden = self._is_golden_uturn_candidate(candidate)
        is_total_sweep = self._is_total_sweep_candidate(candidate)
        if is_golden:
            gu_score = float(getattr(config, "GOLDEN_UTURN_SCORE", 99.0))
            candidate["golden_uturn_mode"] = True
            candidate["confluence_score"] = gu_score
            logger.info(
                f"[GOLDEN-VIP] {symbol}: Pase ejecutivo activo — "
                f"Nexus-15 ignorado, Score estructural={gu_score:.0f}"
            )

        confluence = candidate.get("confluence_score", 0)

        # Sniper mode check for scores > 90%
        # BYPASS: Golden U-Turn + TOTAL-SWEEP — estos entran directo, no van a sniper queue.
        if confluence > 90.0 and not is_triggered_sniper and not is_golden and not is_total_sweep:
            ma99 = self._get_ma99_15m(symbol)
            if ma99:
                trigger_price = ma99 * 1.005
                sniper_data = {
                    "symbol": symbol,
                    "trigger_price": trigger_price,
                    "ma99": ma99,
                    "created_at": datetime.now(timezone.utc).timestamp(),
                    "candidate": candidate,
                    "profile": profile
                }
                self.state.add_pending_sniper(sniper_data)
                logger.info(f"[SNIPER] 🎯 Trap set for {symbol} at {trigger_price:.6f} (0.5% above MA99={ma99:.6f}). Score={confluence:.1f}%")
                return False
            else:
                logger.warning(f"[SNIPER] Could not set trap for {symbol}: failed to calculate MA99.")

        # v12.0-BERSERKER: Balance NO se consulta. Bala fija $150.
        balance = 999_999.0
        setup_metrics: dict = {}

        market_px = self.fetcher.get_current_price(symbol)
        if market_px <= 0:
            logger.warning("[SKIP] %s invalid market price for setup validation", symbol)
            return False

        # Update staleness metric for VETO #4
        if candidate.get("scored_at"):
            candidate["scored_at_age_s"] = datetime.now(timezone.utc).timestamp() - candidate["scored_at"]

        ok, code, setup_metrics = validate_pre_trade(candidate, market_px, profile=profile, btc_filter=self.btc_filter, btc_corr=self.btc_corr)
        if not ok:
            logger.info("[SKIP] %s — %s | profile=%s | metrics=%s", code, symbol, profile.get("name") if profile else "Legacy", setup_metrics)
            return False

        setup_skip = "ok"

        pos_details = self.risk.calculate_position(symbol, candidate, available_balance=balance, profile=profile)

        if not pos_details:
            return False
        
        # ── AI-GRADE AUDIT: Capture MA7 distance for Sniper filter validation ──
        try:
            ma7_value = candidate.get("ma7", 0)
            entry_price = float(pos_details.get("entry_price", market_px))
            if ma7_value > 0 and entry_price > 0:
                ma7_distance_pct = abs(entry_price - ma7_value) / ma7_value * 100.0
                pos_details["ma7_distance_pct"] = round(ma7_distance_pct, 4)
                logger.debug(f"[AUDIT] {symbol} MA7 distance: {ma7_distance_pct:.2f}% (MA7={ma7_value}, Entry={entry_price})")
            else:
                pos_details["ma7_distance_pct"] = None
        except Exception as e:
            logger.warning(f"[AUDIT] Failed to calculate MA7 distance for {symbol}: {e}")
            pos_details["ma7_distance_pct"] = None
        
        # ── AI-GRADE AUDIT: Capture Market Context Snapshot ──
        try:
            market_context = self._capture_market_context(symbol, candidate)
            pos_details["market_context"] = market_context
        except Exception as e:
            logger.warning(f"[AUDIT] Failed to capture market context for {symbol}: {e}")
            pos_details["market_context"] = {}
        
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

        # ── GOLDEN U-TURN v9.0: Tag strategy + Custom SL ────────────────────────
        if candidate.get("golden_uturn_mode"):
            gu_ctx = candidate.get("agent_audit_context", {}).get("golden_uturn", {})
            gu_drop = gu_ctx.get("drop_pct", "?")
            gu_angle = gu_ctx.get("angle", "?")
            gu_sl = gu_ctx.get("sl_5low", 0) or candidate.get("golden_uturn_sl_5low", 0)
            
            # Override entry_reason with Golden U-Turn tag
            entry_reason = (
                f"[STRAT: GOLDEN-U-TURN] Entrada por Sinergia Estructural: "
                f"MA99 Plana (Angle={gu_angle}°) tras caída de {gu_drop}%. "
                f"Score=99 bypass activo."
            )
            
            # Set custom SL to low of last 20 candles (v9.6 Big Fish) if not already set
            if gu_sl and gu_sl > 0 and not candidate.get("custom_sl_price"):
                candidate["custom_sl_price"] = float(gu_sl)
                sl_pct = (market_px - float(gu_sl)) / market_px * 100 if market_px > 0 else 0
                min_tp = float(getattr(config, "GOLDEN_UTURN_TP_MIN_DISTANCE_PCT", 10.0))
                logger.info(
                    f"[BIG-FISH-RISK] {symbol}: SL estirado a {sl_pct:.2f}% (mín estructural) "
                    f"para buscar TP del {min_tp:.1f}%"
                )
            
            # Log strategy tag
            logger.warning(
                f"[GOLDEN-U-TURN v9.0] {symbol} — STRATEGY TAG APPLIED | "
                f"Drop={gu_drop}% | Angle={gu_angle}° | SL={gu_sl}"
            )

        # ── TOTAL-SWEEP v13.0: Tag strategy + Custom SL/TP ────────────────────
        if candidate.get("total_sweep_mode"):
            ts_ctx = candidate.get("agent_audit_context", {}).get("total_sweep", {})
            ts_vol_slope = ts_ctx.get("volume_slope", 0)
            ts_radar = ts_ctx.get("radar_mode", "?")
            ts_red_low = ts_ctx.get("red_candle_low", 0)
            ts_n5_conf = ts_ctx.get("n5_confidence", 0)
            tp_min_pct = float(getattr(config, "TOTAL_SWEEP_TP_MIN_DISTANCE_PCT", 12.0))

            # Override entry_reason with TOTAL-SWEEP tag
            entry_reason = (
                f"[STRAT: TOTAL-SWEEP-v13.0] Bottom Sniper N5={ts_n5_conf:.1f}% + "
                f"Radar={ts_radar} (VolSlope={ts_vol_slope:.2f}) + "
                f"Ley de Nico G>R. SL=RedLow({ts_red_low}). TP>={tp_min_pct}%."
            )

            # Ensure custom SL = red candle low
            if ts_red_low and ts_red_low > 0 and not candidate.get("custom_sl_price"):
                candidate["custom_sl_price"] = float(ts_red_low)

            # Ensure custom TP = entry + min 12%
            if market_px and market_px > 0:
                tp_price = market_px * (1 + tp_min_pct / 100)
                if not candidate.get("custom_tp_price"):
                    candidate["custom_tp_price"] = tp_price

            logger.warning(
                f"[TOTAL-SWEEP-v13.0] {symbol} — STRATEGY TAG APPLIED | "
                f"N5={ts_n5_conf:.1f}% | Radar={ts_radar} | SL={ts_red_low} | TP>={tp_min_pct}%"
            )

        audit_json = self._build_agent_decision_snapshot(
            candidate,
            pos_details,
            entry_reason,
            nexus_group,
            self._get_tier_for_symbol(symbol),
            setup_metrics=setup_metrics if setup_metrics else None,
            setup_skip=setup_skip,
            cycle_rejected=cycle_rejected,
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

        # Evitar duplicar margen en el mismo símbolo dentro del mismo perfil
        # (Permite que distintos perfiles abran el mismo símbolo de forma independiente)
        p_id = profile.get("id") if profile else None
        # Para Standard Scalping: los trades legacy con strategyProfileId=null también le pertenecen
        std_ids = (STANDARD_PROFILE_ID, None) if p_id == STANDARD_PROFILE_ID else (p_id,)
        if any(
            t.get("symbol") == symbol and
            t.get("strategyProfileId", t.get("strategy_profile_id")) in std_ids
            for t in active_trades
        ):
            logger.info(f"[SKIP] Ya existe una posición activa para {symbol} en el perfil '{profile.get('name', 'Legacy') if profile else 'Standard Scalping'}'. Evitando duplicar margen.")
            return False

        # El límite se calcula por perfil para que las 5 estrategias operen de forma independiente
        p_max_pos = int(profile.get("maxOpenPositions", config.MAX_OPEN_POSITIONS)) if profile else config.MAX_OPEN_POSITIONS
        p_id = profile.get("id") if profile else None
        # Fix: Standard Scalping usa STANDARD_PROFILE_ID; trades legacy con null también le pertenecen.
        if p_id == STANDARD_PROFILE_ID:
            p_active_count = len([
                t for t in active_trades
                if t.get("strategyProfileId", t.get("strategy_profile_id")) in (STANDARD_PROFILE_ID, None)
                and t.get("strategyProfileId", t.get("strategy_profile_id")) != CLONE_PROFILE_ID
            ])
        else:
            p_active_count = len([
                t for t in active_trades
                if t.get("strategyProfileId", t.get("strategy_profile_id")) == p_id
            ])

        if p_active_count >= p_max_pos:
            if is_lse:
                # LSE nunca tiene nexus_confidence — usa confluence_score con umbral LSE_MIN_SCORE
                lse_upgrade_threshold = float(getattr(config, "LSE_MIN_SCORE", 65.0))
                can_upgrade = confluence >= lse_upgrade_threshold
                gate_desc = f"LSE Score={confluence:.1f} vs umbral={lse_upgrade_threshold}"
            else:
                # Nexus / SCAR / Bridge — Golden U-Turn VIP bypass upgrade gate
                min_upgrade_nexus = float(getattr(config, "MIN_UPGRADE_NEXUS", 80.0))
                if is_golden or is_total_sweep:
                    can_upgrade = True
                    strat_label = "TOTAL-SWEEP VIP" if is_total_sweep else "Golden U-Turn VIP"
                    gate_desc = f"{strat_label} (Score={confluence:.0f})"
                else:
                    can_upgrade = nexus_conf_pct >= min_upgrade_nexus
                    gate_desc = f"Nexus={nexus_conf_pct:.1f}% vs umbral={min_upgrade_nexus}%"

            if can_upgrade:
                logger.info(
                    f"Cupos de la estrategia llenos, candidato élite ({gate_desc}). Reemplazando peor posición..."
                )
                closed_worst = self._close_worst_position(profile_id=p_id)
                if not closed_worst:
                    logger.info("No se pudo cerrar la peor posición. Upgrade abortado.")
                    return False
            else:
                logger.info(
                    f"[LIMIT] Slots llenos. {gate_desc} — no alcanza para reemplazar posición existente."
                )
                return False

        # Slot libre: mínimo de calidad según fuente
        # Golden U-Turn VIP: la geometría MA99 reemplaza la confianza Nexus-15
        if is_lse:
            pass
        elif is_golden:
            # ── FIX B v11.0: BYPASS SCORE=99 NO PUEDE IGNORAR BEARTREND + WAIT ──
            # SPORTFUNUSDT y MYXUSDT entraron con BearTrend/Wait por Score=99 y perdieron
            nexus_audit = candidate.get("agent_audit_context", {}).get("nexus15", {})
            api_regime = nexus_audit.get("regime", "").lower()
            api_recommendation = nexus_audit.get("recommendation", "").lower()
            
            if api_regime == "beartrend" and api_recommendation == "wait":
                logger.warning(
                    f"[THE-BARRIER] {symbol} RECHAZADO: Golden U-Turn con BearTrend + Wait "
                    f"(Score=99 bypass DESACTIVADO por FIX B v11.0)"
                )
                return False
            
            logger.info(
                f"[GOLDEN-VIP] {symbol}: bypass MIN_ENTRY_NEXUS — "
                f"Nexus={nexus_conf_pct:.1f}% ignorado (pase estructural Score=99)"
            )
        elif is_total_sweep:
            # TOTAL-SWEEP v13.0: bypass MIN_ENTRY_NEXUS — NEXUS-5 Bottom Sniper replaces Nexus-15
            logger.info(
                f"[TOTAL-SWEEP-VIP] {symbol}: bypass MIN_ENTRY_NEXUS — "
                f"Nexus-5 Bottom Sniper structural (Score=99.5)"
            )
        else:
            min_entry_nexus = float(getattr(config, "MIN_ENTRY_NEXUS", 70.0))
            if nexus_conf_pct < min_entry_nexus:
                logger.info(
                    f"[SKIP] Nexus={nexus_conf_pct:.1f}% < {min_entry_nexus}% mínimo para slot libre."
                )
                return False

        # ── BTC INTELLIGENT BLOCKING (Capa C) ──
        # Bloquear LONGs cuando BTC está en DUMPING, excepto si hay desacople institucional real
        side = candidate.get("side", 0)
        btc_regime = self.btc_filter.get_regime()
        
        if side == 0:  # LONG
            # Evaluar desacople institucional real
            # Los campos pueden estar en el nivel raíz o anidados en agent_audit_context.nexus15.features
            features = candidate.get("agent_audit_context", {}).get("nexus15", {}).get("features", {})
            volume_ratio = candidate.get("volume_ratio") or features.get("volume_ratio_20", 0)
            cvd_delta = candidate.get("cvd_delta") or features.get("cvd_delta", 0)
            nexus_confidence = float(
                candidate.get("confluence_score", 0) if is_golden
                else (candidate.get("nexus_confidence", 0) or candidate.get("confluence_score", 0))
            )
            
            btc_decouple = (
                volume_ratio > config.BTC_DECOUPLE_MIN_VOLUME_RATIO and
                cvd_delta > 0 and
                nexus_confidence >= config.BTC_DECOUPLE_MIN_NEXUS
            )
            
            if btc_regime == "DUMPING":
                if is_golden or is_total_sweep:
                    strat_tag = "TOTAL-SWEEP" if is_total_sweep else "GOLDEN"
                    logger.info(
                        f"[{strat_tag}-VIP] {symbol}: bypass BTC-BLOCK en DUMPING — "
                        f"entrada estructural en suelo (Score={nexus_confidence:.0f})"
                    )
                elif btc_decouple:
                    logger.info(f"[BTC-DECOUPLE] {symbol} permitido — VR={volume_ratio:.2f} CVD={cvd_delta:+.0f} Nexus={nexus_confidence:.1f}%")
                    self.report.record_btc_decouple_allowed()
                else:
                    logger.warning(f"[BTC-BLOCK] {symbol} LONG bloqueado — DUMPING sin desacople institucional (regime={btc_regime})")
                    self.report.record_btc_trade_blocked()
                    return False
            
            # Scalping Clone: bloqueo adicional en NEUTRAL + tendencia 1h DOWN (sin excepción decouple)
            profile_name = profile.get("name", "") if profile else ""
            if profile_name == "Scalping Clone" and btc_regime in ["DUMPING", "NEUTRAL"]:
                if self.btc_filter.get_btc_trend_1h() == "DOWN" and not btc_decouple:
                    logger.warning(f"[BTC-BLOCK-CLONE] {symbol} Clone bloqueado — 1h DOWN + régimen {btc_regime}")
                    self.report.record_btc_trade_blocked()
                    return False
        elif side == 1:  # SHORT
            # SHORTs: no bloquear, el dump de BTC los favorece. Solo loggear contexto.
            logger.info(f"[BTC-INFO] {symbol} SHORT con régimen BTC={btc_regime}")

        # ── NEXUS-5 AUTO-EXECUTION GATE ────────────────────────────────────────────
        # If NEXUS5_ONLY_AUTO_EXECUTE is True: only trades from NEXUS-5 (total_sweep) execute automatically.
        # All other sources are logged as PENDING_CONFIRMATION and skipped.
        if getattr(config, "NEXUS5_ONLY_AUTO_EXECUTE", False) and not is_total_sweep:
            source_label = candidate.get("source", "unknown")
            logger.warning(
                f"[PENDING-CONFIRM] 🛑 {symbol} NO es NEXUS-5 (source={source_label}). "
                f"Trade registrado pero NO ejecutado. Confirmar manualmente."
                f" | Score={confluence:.1f} | Nexus={nexus_conf_pct:.1f}% | "
                f"Margin={pos_details.get('margin')} | Entry={market_px}"
            )
            return False

        logger.info(f"Opening {candidate['trade_direction']} on {symbol}. Margin: {pos_details['margin']}")
        trade_result = self.positions.open_trade(pos_details)
        pos_details.pop("agent_decision_json", None)

        if trade_result:
            # ── Mirror entry to Binance if real trading is enabled ──
            if getattr(config, "BINANCE_REAL_TRADING", False):
                p_id = profile.get("id") if profile else None
                p_name = profile.get("name") if profile else ""
                is_ma_cross = (p_id == "3a214744-f0b9-68bb-f235-438a39d39d33") or (p_name == "MA Cross Momentum")
                if is_ma_cross:
                    try:
                        entry_px = float(pos_details.get("entry_price", market_px))
                        margin = float(pos_details.get("margin", 150.0))
                        lev = int(pos_details.get("leverage", 1))
                        qty = (margin * lev) / entry_px
                        qty = round(qty, 3)
                        logger.info(f"[BINANCE REAL] Mirroring entry to Binance for {symbol}: Qty={qty}, Side={candidate.get('side')}, TP={pos_details.get('tp_price')}, SL={pos_details.get('sl_price')}")
                        self.positions.open_binance_trade(
                            symbol=symbol,
                            side=candidate.get("side", 0),
                            quantity=qty,
                            tp_price=pos_details.get("tp_price"),
                            sl_price=pos_details.get("sl_price")
                        )
                    except Exception as ex:
                        logger.error(f"[BINANCE REAL] Exception placing entry order for {symbol}: {ex}")

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

            # ── Auto-cloning for Standard Scalping ──
            is_standard = False
            if profile is None:
                is_standard = True
            elif profile.get("id") in (None, STANDARD_PROFILE_ID) or profile.get("name") == "Standard Scalping":
                is_standard = True

            if is_standard:
                try:
                    self._open_clone_trade(str(trade_id) if trade_id else "", candidate, pos_details, entry_reason, nexus_group)
                except Exception as ex:
                    logger.error(f"[CLONE] Failed to auto-clone trade for {symbol}: {ex}")

            return True

        return False

    def _open_clone_trade(self, orig_trade_id: str, candidate: dict, orig_pos_details: dict, entry_reason: str, nexus_group: str) -> bool:
        """
        Opens a clone trade for Scalping Clone with the exact same parameters as the
        Standard Scalping trade, EXCEPT the SL/TP are recalculated using the Scalping Clone profile
        (which uses double SL and proportional TP).
        Skips all validation filters — the trade was already validated by Standard Scalping.
        """
        symbol = candidate["symbol"]

        # ── Check clone profile slot limit ──
        clone_max = int(self.clone_profile.get("maxOpenPositions", config.MAX_OPEN_POSITIONS))
        clone_active = [
            t for t in (self.positions.get_active_trades() or [])
            if t.get("strategyProfileId", t.get("strategy_profile_id")) == CLONE_PROFILE_ID
        ]
        if len(clone_active) >= clone_max:
            logger.info(f"[CLONE] Profile Scalping Clone is full ({len(clone_active)}/{clone_max}). Skipping clone for {symbol}.")
            return False

        # v12.0-BERSERKER: Balance NO se consulta para clone. Bala fija $150.
        balance = 999_999.0
        clone_pos = self.risk.calculate_position(symbol, candidate, available_balance=balance, profile=self.clone_profile)
        if not clone_pos:
            logger.warning(f"[CLONE] Failed to calculate clone position for {symbol}. Skipping clone.")
            return False

        clone_pos.pop("agent_decision_json", None)
        clone_pos["strategy_profile_id"] = CLONE_PROFILE_ID

        # ── CLONE PROTECTION: SL ceiling check ──
        entry_price = float(clone_pos.get("entry_price", 0))
        sl_price = float(clone_pos.get("sl_price", 0))
        if entry_price > 0 and sl_price > 0:
            sl_pct = abs(entry_price - sl_price) / entry_price * 100.0
            clone_max_sl_pct = getattr(config, "CLONE_MAX_STOP_LOSS_PCT", 5.0)
            if sl_pct > clone_max_sl_pct:
                logger.warning(f"[CLONE] VETO {symbol}: SL {sl_pct:.2f}% exceeds Clone ceiling {clone_max_sl_pct}%. Skipping clone.")
                return False

        logger.info(f"[CLONE] Opening clone trade for {symbol} | entry={entry_price} | margin={clone_pos.get('margin')}x{clone_pos.get('leverage')} | SL={clone_pos.get('sl_price')} | TP={clone_pos.get('tp_price')} (Independent Scalping Clone calculation)")
        clone_result = self.positions.open_trade(clone_pos)

        if clone_result:
            clone_id = clone_result.get("id")
            clone_local = {
                "trade_id": clone_id,
                "symbol": symbol,
                "opened_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "entry_reason": f"[CLONE] {entry_reason}",
                "nexus_group": nexus_group,
                "tier": self._get_tier_for_symbol(symbol),
                **candidate,
                **clone_pos,
                "cloned_from": orig_trade_id,
                "strategy_profile_id": CLONE_PROFILE_ID,
            }
            self.state.add_position(clone_local)
            self.state.record_trade_action(symbol)
            if candidate.get("source") == "LSE":
                self.state.register_lse_symbol_cooldown(symbol, candidate.get("lse_timeframe") or "1h")
            self.report.log_trade_opened(clone_local)
            logger.info(f"[CLONE] ✅ Clone trade {clone_id} opened for {symbol}")
            return True
        else:
            logger.warning(f"[CLONE] ❌ Failed to open clone trade for {symbol}")
            return False

    # ─────────────────────────────────────────────────────────
    # Position management
    # ─────────────────────────────────────────────────────────
    def _manage_open_positions(self):
        """
        Monitors open positions and closes them if TP/SL/timeout is reached.
        Also syncs phantom positions (local records not in backend) every cycle.
        Prices are ALWAYS fetched from local cache.
        """
        positions = self.state.get_open_positions()
        if not positions:
            return

        logger.info(f"Monitoring {len(positions)} open positions...")

        # ── Fetch backend active trades ONCE before the loop (not per-position) ──
        # Critical: if this returns None (network error), skip phantom check for this cycle
        # rather than crashing mid-loop and leaving positions unmonitored.
        active_backend_trades = self.positions.get_active_trades()
        backend_ids: set = set()
        if active_backend_trades is not None:
            backend_ids = {t["id"] for t in active_backend_trades}
        else:
            logger.warning("[SYNC] Could not reach backend to verify positions — skipping phantom check this cycle.")

        for pos in positions:
            symbol   = pos["symbol"]
            trade_id = pos["trade_id"]
            side     = pos["side"]
            tp       = pos["tp_price"]
            sl       = pos["sl_price"]
            entry_price = float(pos.get("entry_price", 0))
            margin = float(pos.get("margin", 0))

            current_price = self.fetcher.get_current_price(symbol)
            if current_price <= 0:
                continue

            # ── Track max adverse price (extreme opposite price) ──
            # For LONG: track lowest price seen. For SHORT: track highest price seen.
            prev_adverse = pos.get("max_adverse_price")
            if side == 0:  # LONG
                if prev_adverse is None:
                    pos["max_adverse_price"] = pos.get("entry_price") or current_price
                    logger.info(f" [MAE] {symbol} LONG init max_adverse_price from entry={pos['max_adverse_price']}")
                elif current_price < prev_adverse:
                    pos["max_adverse_price"] = current_price
                    logger.info(f" [MAE] {symbol} LONG updated max_adverse_price: {current_price}")
            else:  # SHORT
                if prev_adverse is None:
                    pos["max_adverse_price"] = pos.get("entry_price") or current_price
                    logger.info(f" [MAE] {symbol} SHORT init max_adverse_price from entry={pos['max_adverse_price']}")
                elif current_price > prev_adverse:
                    pos["max_adverse_price"] = current_price
                    logger.info(f" [MAE] {symbol} SHORT updated max_adverse_price: {current_price}")

            # ── Track max profit price (best price seen in favor of the trade) ──
            # For LONG: highest price seen. For SHORT: lowest price seen.
            prev_profit = pos.get("max_profit_price")
            if side == 0:  # LONG
                if prev_profit is None or current_price > prev_profit:
                    pos["max_profit_price"] = current_price
            else:  # SHORT
                if prev_profit is None or current_price < prev_profit:
                    pos["max_profit_price"] = current_price

            should_close = False
            close_reason = ""
            close_tag = "[CLOSE-NORMAL]"  # Default tag

            # ── v9.8 Diamond Hands Mode: Detect Golden U-Turn trades ─────────────────
            entry_reason = pos.get("entry_reason", "")
            is_golden_uturn = "[STRAT: GOLDEN-U-TURN]" in entry_reason or pos.get("golden_uturn_mode", False)
            # ── v13.0 Diamond Hands: TOTAL-SWEEP trades get same treatment ──
            is_total_sweep_pos = "[STRAT: TOTAL-SWEEP-v13.0]" in entry_reason or pos.get("total_sweep_mode", False)
            is_diamond = is_golden_uturn or is_total_sweep_pos

            ft_exit = self._lse_follow_through_exit_reason(pos)
            if ft_exit:
                should_close, close_reason = True, ft_exit
            elif side == 0:  # LONG
                # ── BTC MACRO EXIT TRIGGER (Capa D) ──
                # v9.8 Diamond Hands: Desactivado para Golden U-Turn / TOTAL-SWEEP
                if not is_diamond:
                    dump_5m = self.btc_filter.get_dump_pct(5)
                    dump_15m = self.btc_filter.get_dump_pct(15)
                    
                    if entry_price > 0 and margin > 0:
                        roi_pct = ((current_price - entry_price) / entry_price) * 100
                        if roi_pct >= config.BTC_MIN_ROI_TO_PROTECT:
                            if dump_5m < config.BTC_EXIT_DUMP_5M or dump_15m < config.BTC_EXIT_DUMP_15M:
                                logger.warning(f"[CLOSE-BTC-EXIT] {symbol} cerrando proactivamente - ROI={roi_pct:.1f}% dump5m={dump_5m:.2f}% dump15m={dump_15m:.2f}%")
                                should_close, close_reason = True, f"BTC Macro Exit (ROI={roi_pct:.1f}%, dump5m={dump_5m:.2f}%)"
                                close_tag = "[CLOSE-BTC-EXIT]"
                                self.report.record_btc_exit_triggered(roi_pct)
                
                if not should_close:
                    if current_price >= tp:
                        should_close, close_reason = True, "Take Profit reached"
                    elif current_price <= sl:
                        should_close, close_reason = True, "Stop Loss reached"

                # ── REGLA DE LA COSECHA INTELIGENTE (Trailing Stop Proporcional) ──
                # v9.8 Diamond Hands: Desactivado para Golden U-Turn / TOTAL-SWEEP, reemplazado por Trailing Profit Inteligente
                if not should_close and entry_price > 0 and tp > entry_price:
                    if is_diamond:
                        # ── v9.8 Trailing Profit Inteligente para Golden U-Turn ──
                        # Se activa cuando el trade alcanza +10% de profit
                        # Trailing stop solo se ejecuta si el precio cae 5% desde el máximo
                        max_profit_price = pos.get("max_profit_price") or current_price
                        max_profit_pct = (max_profit_price - entry_price) / entry_price
                        
                        if max_profit_pct >= 0.10:  # +10% de profit
                            # Trailing stop: 5% desde el máximo
                            trailing_sl_price = max_profit_price * 0.95  # 5% de caída desde el máximo
                            if current_price <= trailing_sl_price:
                                logger.info(
                                    "[DIAMOND-HANDS] %s Trailing Profit activado | max_profit=%.2f%% | trailing_sl=%.8f (5%% desde máximo) | current=%.8f",
                                    symbol, max_profit_pct * 100, trailing_sl_price, current_price
                                )
                                should_close, close_reason = True, f"Diamond Hands Trailing (max_profit={max_profit_pct*100:.1f}%)"
                                close_tag = "[DIAMOND-HANDS]"
                    else:
                        # Cosecha Inteligente estándar para trades no-Golden U-Turn
                        tp_dist = tp - entry_price
                        activation_price = entry_price + (tp_dist * 0.50)  # 50% del camino al TP
                        max_profit_price = pos.get("max_profit_price") or current_price
                        max_profit_pct = (max_profit_price - entry_price) / entry_price
                        if max_profit_pct > 0 and max_profit_price >= activation_price:
                            # El buffer es el 25% del profit máximo alcanzado
                            buffer_pct = max_profit_pct * 0.25
                            # El trailing SL protege el 75% del profit máximo
                            trailing_sl_price = entry_price * (1 + max_profit_pct - buffer_pct)
                            if current_price <= trailing_sl_price:
                                profit_protected_pct = (max_profit_pct - buffer_pct) * 100
                                logger.info(
                                    "[COSECHA] %s trailing stop activado | max_profit=%.2f%% | buffer=%.2f%% | trailing_sl=%.8f | current=%.8f | profit_protegido=%.2f%%",
                                    symbol, max_profit_pct * 100, buffer_pct * 100, trailing_sl_price, current_price, profit_protected_pct
                                )
                                should_close, close_reason = True, f"Cosecha Inteligente (profit protegido={profit_protected_pct:.1f}%)"
                                close_tag = "[COSECHA]"
            else:  # SHORT
                if current_price <= tp:
                    should_close, close_reason = True, "Take Profit reached"
                elif current_price >= sl:
                    should_close, close_reason = True, "Stop Loss reached"

                # ── REGLA DE LA COSECHA INTELIGENTE (SHORT) ──
                # v9.8 Diamond Hands: Desactivado para Golden U-Turn / TOTAL-SWEEP
                if not should_close and entry_price > 0 and tp < entry_price:
                    if is_diamond:
                        # ── v9.8 Trailing Profit Inteligente para Golden U-Turn SHORT ──
                        max_profit_price = pos.get("max_profit_price") or current_price
                        max_profit_pct = (entry_price - max_profit_price) / entry_price
                        
                        if max_profit_pct >= 0.10:  # +10% de profit
                            # Trailing stop: 5% desde el máximo (para SHORT, el máximo es el precio más bajo)
                            trailing_sl_price = max_profit_price * 1.05  # 5% de subida desde el mínimo
                            if current_price >= trailing_sl_price:
                                logger.info(
                                    "[DIAMOND-HANDS] %s SHORT Trailing Profit activado | max_profit=%.2f%% | trailing_sl=%.8f (5%% desde mínimo) | current=%.8f",
                                    symbol, max_profit_pct * 100, trailing_sl_price, current_price
                                )
                                should_close, close_reason = True, f"Diamond Hands Trailing SHORT (max_profit={max_profit_pct*100:.1f}%)"
                                close_tag = "[DIAMOND-HANDS]"
                    else:
                        # Cosecha Inteligente estándar para trades no-Golden U-Turn
                        tp_dist = entry_price - tp
                        activation_price = entry_price - (tp_dist * 0.50)  # 50% del camino al TP
                        max_profit_price = pos.get("max_profit_price") or current_price
                        max_profit_pct = (entry_price - max_profit_price) / entry_price
                        if max_profit_pct > 0 and max_profit_price <= activation_price:
                            buffer_pct = max_profit_pct * 0.25
                            trailing_sl_price = entry_price * (1 - max_profit_pct + buffer_pct)
                            if current_price >= trailing_sl_price:
                                profit_protected_pct = (max_profit_pct - buffer_pct) * 100
                                logger.info(
                                    "[COSECHA] %s SHORT trailing stop activado | max_profit=%.2f%% | buffer=%.2f%% | trailing_sl=%.8f | current=%.8f | profit_protegido=%.2f%%",
                                    symbol, max_profit_pct * 100, buffer_pct * 100, trailing_sl_price, current_price, profit_protected_pct
                                )
                                should_close, close_reason = True, f"Cosecha Inteligente (profit protegido={profit_protected_pct:.1f}%)"
                                close_tag = "[COSECHA]"

            opened_at_str = pos["opened_at"].replace("Z", "+00:00")
            opened_at = datetime.fromisoformat(opened_at_str)
            if opened_at.tzinfo is not None:
                opened_at = opened_at.replace(tzinfo=None)
            hours_open = (datetime.utcnow() - opened_at).total_seconds() / 3600.0

            # ── Zombie timeout: más de MAX_TRADE_DURATION_CANDLES velas de 15m con PnL negativo ──
            # v9.8 Diamond Hands: Desactivado para Golden U-Turn (pueden durar días)
            if not should_close and not is_diamond:
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

            # ── Max duration exceeded ──
            # v9.8 Diamond Hands: Desactivado para Golden U-Turn
            if hours_open >= config.MAX_POSITION_DURATION_HOURS and not is_diamond:
                should_close, close_reason = True, "Max duration exceeded"

            if not should_close:
                # Use pre-fetched backend_ids (fetched once before the loop)
                if backend_ids and trade_id not in backend_ids:
                    logger.info(f"Position {symbol} ({trade_id}) closed by server. Syncing state.")
                    self.state.remove_position(trade_id)
                    continue

            if should_close:
                logger.info(f"{close_tag} Closing {symbol}: {close_reason} @ {current_price}")

                # ── AI-GRADE AUDIT: Determine exit_reason ──
                exit_reason = self._determine_exit_reason(close_reason, side, current_price, tp, sl, entry_price)
                
                # ── AI-GRADE AUDIT: Get BTC context at exit (full regime, not just price) ──
                btc_price_at_close = None
                btc_context_at_exit = {}
                try:
                    btc_price_at_close = self.fetcher.get_current_price("BTCUSDT")
                    btc_context_at_exit = {
                        "btc_price": btc_price_at_close,
                        "regime": self.btc_filter.get_regime(),
                        "pct_5m": round(self.btc_filter.get_dump_pct(5), 4),
                        "pct_15m": round(self.btc_filter.get_dump_pct(15), 4),
                        "pct_1h": round(self.btc_filter.get_dump_pct(60), 4),
                    }
                except Exception as e:
                    logger.debug(f"[AUDIT] Failed to get BTC context at close: {e}")
                
                # ── AI-GRADE AUDIT: Calculate MAE% and MFE% ──
                mae_pct = None
                mfe_pct = None
                max_adv = pos.get("max_adverse_price")
                max_fav = pos.get("max_profit_price")
                if entry_price > 0:
                    if max_adv is not None:
                        if side == 0:  # LONG
                            mae_pct = round(((float(max_adv) - entry_price) / entry_price) * 100, 4)
                        else:  # SHORT
                            mae_pct = round(((entry_price - float(max_adv)) / entry_price) * 100, 4)
                    if max_fav is not None:
                        if side == 0:  # LONG
                            mfe_pct = round(((float(max_fav) - entry_price) / entry_price) * 100, 4)
                        else:  # SHORT
                            mfe_pct = round(((entry_price - float(max_fav)) / entry_price) * 100, 4)
                
                # ── AI-GRADE AUDIT: Calculate candles_held (exact 15m candles) ──
                candles_held = None
                try:
                    opened_at_str = pos["opened_at"].replace("Z", "+00:00")
                    opened_at_dt = datetime.fromisoformat(opened_at_str)
                    if opened_at_dt.tzinfo is not None:
                        opened_at_dt = opened_at_dt.replace(tzinfo=None)
                    seconds_open = (datetime.utcnow() - opened_at_dt).total_seconds()
                    candles_held = round(seconds_open / 900, 1)  # 15m = 900s
                except Exception:
                    pass
                
                # ── AI-GRADE AUDIT: Build exit_audit block ──
                exit_audit = {
                    "exit_reason": exit_reason,
                    "close_reason_raw": close_reason,
                    "mae_pct": mae_pct,
                    "mfe_pct": mfe_pct,
                    "max_adverse_price": float(max_adv) if max_adv is not None else None,
                    "max_favorable_price": float(max_fav) if max_fav is not None else None,
                    "candles_held": candles_held,
                    "btc_context_at_exit": btc_context_at_exit,
                    "close_price": current_price,
                    "entry_price": entry_price,
                }
                
                logger.info(
                    f"[EXIT-AUDIT v12.1] {symbol}: exit={exit_reason} | MAE={mae_pct}% | MFE={mfe_pct}% | "
                    f"candles={candles_held} | BTC regime={btc_context_at_exit.get('regime', 'N/A')}"
                )
                
                # ── Sync max adverse price to backend before closing ──
                if max_adv is not None:
                    try:
                        self.positions.update_max_adverse_price(trade_id, float(max_adv))
                    except Exception as e:
                        logger.warning(f" [MAE] Failed to update max_adverse_price: {e}")
                
                # ── Sync max favorable price ──
                if max_fav is not None:
                    try:
                        self.positions.update_max_favorable_price(trade_id, float(max_fav))
                    except Exception as e:
                        logger.warning(f" [MFE] Failed to update max_favorable_price: {e}")
                
                # ── Sync exit_reason + full exit_audit to backend ──
                try:
                    self.positions.update_trade_exit_info(
                        trade_id, exit_reason, btc_price_at_close,
                        exit_audit_json=exit_audit
                    )
                except Exception as e:
                    logger.warning(f" [AUDIT] Failed to update exit info: {e}")

                success = self.positions.close_trade(trade_id)

                if success:
                    # ── Mirror close to Binance if real trading is enabled ──
                    if getattr(config, "BINANCE_REAL_TRADING", False):
                        p_id = pos.get("strategy_profile_id") or pos.get("strategyProfileId")
                        profile = next((p for p in self.active_profiles if p.get("id") == p_id), None)
                        p_name = profile.get("name", "") if profile else ""
                        is_ma_cross = (p_id == "3a214744-f0b9-68bb-f235-438a39d39d33") or (p_name == "MA Cross Momentum")
                        if is_ma_cross:
                            try:
                                logger.info(f"[BINANCE REAL] Mirroring close of {symbol} to Binance")
                                self.positions.close_binance_trade(symbol)
                            except Exception as ex:
                                logger.error(f"[BINANCE REAL] Exception closing position for {symbol}: {ex}")

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
        """Bidirectional sync: ensures backend positions have TP/SL and removes phantom local positions."""
        logger.info("Verifying TP/SL and syncing active positions (bidirectional)...")
        active_trades = self.positions.get_active_trades()
        if active_trades is None:
            logger.error("Failed to fetch active trades from backend during repair. Skipping.")
            return

        local_positions = self.state.get_open_positions()
        local_ids = [p.get("trade_id") for p in local_positions]
        backend_ids = {t["id"] for t in active_trades}

        # ── REVERSE SYNC: remove phantom local positions that don't exist in backend ──
        # This is the key fix: if the agent recorded a trade locally but the backend
        # never confirmed it (or already closed it), remove it from local state so
        # _should_skip() doesn't block the symbol forever.
        phantoms_removed = 0
        for local_pos in local_positions:
            tid = local_pos.get("trade_id")
            sym = local_pos.get("symbol", "?")
            if tid not in backend_ids:
                logger.warning(
                    "[REPAIR] Phantom position removed: %s (%s) — not found in backend. "
                    "Was recorded locally but never confirmed by exchange.",
                    sym, tid
                )
                self.state.remove_position(tid)
                phantoms_removed += 1
        if phantoms_removed:
            logger.warning(
                "[REPAIR] Removed %d phantom position(s). Agent unblocked for those symbols.",
                phantoms_removed
            )

        for trade in active_trades:
            symbol   = trade["symbol"]
            trade_id = trade["id"]

            # 1. Sync local state if missing
            if trade_id not in local_ids:
                logger.info(f"🔄 Syncing missing position {symbol} ({trade_id}) to local state.")
                sync_pos = {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "opened_at": trade.get("openedAt") or trade.get("opened_at") or trade.get("OpenedAt") or datetime.utcnow().isoformat(),
                    "side": trade["side"],
                    "entry_price": float(trade["entryPrice"]),
                    "tp_price": float(trade.get("tpPrice") or trade.get("tp_price") or trade.get("TpPrice") or 0),
                    "sl_price": float(trade.get("slPrice") or trade.get("sl_price") or trade.get("SlPrice") or 0),
                    "leverage": trade["leverage"],
                    "margin": float(trade["margin"])
                }
                self.state.add_position(sync_pos)

            # 2. Repair TP/SL if missing
            tp = trade.get("tpPrice") if trade.get("tpPrice") is not None else trade.get("tp_price")
            sl = trade.get("slPrice") if trade.get("slPrice") is not None else trade.get("sl_price")

            if tp is None or sl is None or tp == 0 or sl == 0:
                logger.info(f"🔧 Repairing TP/SL for {symbol} ({trade_id})...")
                entry = float(trade["entryPrice"])
                range_pct = 0.02
                tp_dist = range_pct * config.TP_MULTIPLIER
                sl_dist = range_pct * config.SL_MULTIPLIER

                if trade["side"] == 0:  # LONG
                    tp_val = entry * (1 + tp_dist)
                    sl_val = entry * (1 - sl_dist)
                else:  # SHORT
                    tp_val = entry * (1 - tp_dist)
                    sl_val = entry * (1 + sl_dist)

                payload = {"tpPrice": round(tp_val, 4), "slPrice": round(sl_val, 4)}
                success = self.positions.update_tp_sl(trade_id, payload)

                if success:
                    self.state.update_position_tpsl(trade_id, payload["tpPrice"], payload["slPrice"])


# --- HTTP SERVER FOR MANUAL CLOSURE SUPPORT ---
_agent_instance = None

def _build_agent_response(path, agent):
    """Build HTTP response for agent state queries."""
    if path.startswith('/position/') and '/max-adverse-price' in path:
        # Extract trade_id from path: /position/{trade_id}/max-adverse-price
        parts = path.split('/')
        if len(parts) >= 3:
            trade_id = parts[2]
            positions = agent.state.get_open_positions()
            pos = next((p for p in positions if p.get("trade_id") == trade_id), None)
            if pos:
                max_adv = pos.get("max_adverse_price")
                return {"tradeId": trade_id, "maxAdversePrice": max_adv}
            else:
                return {"tradeId": trade_id, "maxAdversePrice": None, "error": "Position not found"}
    return None

async def handle_agent_request(reader, writer, agent):
    """Handle HTTP requests for agent state."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            return
        # Drain remaining headers
        while True:
            hdr = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if hdr in (b'\r\n', b'\n', b''):
                break

        parts = request_line.decode(errors='replace').split()
        path = parts[1].split('?')[0] if len(parts) > 1 else '/'
        logger.info(f" [HTTP] GET {path}")

        data = _build_agent_response(path, agent)
        if data is None:
            body = b'{"error": "Not found"}'
            status_line = b"HTTP/1.1 404 Not Found\r\n"
        else:
            body = json.dumps(data).encode('utf-8')
            status_line = b"HTTP/1.1 200 OK\r\n"

        response = (
            status_line +
            b"Content-Type: application/json\r\n"
            b"Access-Control-Allow-Origin: *\r\n"
            b"Connection: close\r\n" +
            f"Content-Length: {len(body)}\r\n\r\n".encode()
        )
        writer.write(response + body)
        await writer.drain()
    except Exception as e:
        logger.error(f" [HTTP] Error handling request: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def run_agent_http_server(agent):
    """Run HTTP server for agent state queries."""
    server = await asyncio.start_server(
        lambda r, w: handle_agent_request(r, w, agent),
        '127.0.0.1', 8002
    )
    logger.info("🌐 Agent HTTP server ready on port 8002 (127.0.0.1)")
    async with server:
        await server.serve_forever()


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

        # Start HTTP server in background thread
        import threading
        http_thread = threading.Thread(
            target=lambda: asyncio.run(run_agent_http_server(agent)),
            daemon=True
        )
        http_thread.start()

        agent.run()
    except KeyboardInterrupt:
        print("\nDeteniendo agente...")
    except Exception as e:
        print(f"Error crítico: {e}")
    finally:
        if os.path.exists(LOCK_FILE):
            try: os.remove(LOCK_FILE)
            except: pass
