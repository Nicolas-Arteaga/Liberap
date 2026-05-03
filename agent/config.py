import os
import json
import time

# ==========================================
# VERGE AUTONOMOUS TRADING AGENT CONFIGURATION
# ==========================================

# 1. API Endpoints
PYTHON_SERVICE_URL = os.getenv("PYTHON_SERVICE_URL", "http://localhost:8005")
ABP_BACKEND_URL = os.getenv("ABP_BACKEND_URL", "https://localhost:44396")

# LiquiditySweepEngine (python-service /lse/scan y /lse/scan-batch)
LSE_ENABLED = os.getenv("LSE_ENABLED", "true").lower() in ("1", "true", "yes")
LSE_MIN_SCORE = float(os.getenv("LSE_MIN_SCORE", "65"))
LSE_DETECTION_MODE = os.getenv("LSE_DETECTION_MODE", "conservative")  # conservative | aggressive
LSE_DUAL_SCAN = os.getenv("LSE_DUAL_SCAN", "true").lower() in ("1", "true", "yes")
LSE_ENTRY_MODE = os.getenv("LSE_ENTRY_MODE", "conservative")  # conservative | aggressive (timing entrada)
# UI/LSE pueden tardar 1–3+ min; el agente antes usaba 10s y cortaba todas las respuestas.
LSE_HTTP_TIMEOUT_SEC = int(os.getenv("LSE_HTTP_TIMEOUT_SEC", "360"))
# Cuántos pares con historial 1h completo entran al batch TOP-K.
# Por defecto escanea todo el universo elegible para decidir con contexto completo.
LSE_MAX_SYMBOLS_PER_CYCLE = int(os.getenv("LSE_MAX_SYMBOLS_PER_CYCLE", "200"))
LSE_BATCH_TOP_K = int(os.getenv("LSE_BATCH_TOP_K", "10"))
# Si True: no abrir operación nueva si LSE no completó scan-batch HTTP 200 con suficientes símbolos procesados.
LSE_REQUIRE_SCAN_BEFORE_ENTRY = os.getenv(
    "LSE_REQUIRE_SCAN_BEFORE_ENTRY", "true"
).lower() in ("1", "true", "yes")
LSE_MIN_SYMBOLS_PROCESSED_GATE = int(os.getenv("LSE_MIN_SYMBOLS_PROCESSED_GATE", "1"))
LSE_REQUIRE_ALL_QUEUED_PROCESSED = os.getenv(
    "LSE_REQUIRE_ALL_QUEUED_PROCESSED", "true"
).lower() in ("1", "true", "yes")

# 2. ABP Agent Credentials
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "agent@verge.internal")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "1q2w3E*")
CLIENT_ID = os.getenv("CLIENT_ID", "Verge_App")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

# 3. Risk & Capital Management
VIRTUAL_CAPITAL_BASE = 10000.0
RISK_PER_TRADE_PCT = 0.015
# LSE / sizing por riesgo respecto al stop estructural (no margen fijo % equity)
EQUITY_RISK_PCT_FOR_STOP = float(os.getenv("EQUITY_RISK_PCT_FOR_STOP", "0.01"))
MIN_RR_DEFAULT = float(os.getenv("MIN_RR_DEFAULT", "1.5"))
MIN_RR_NEXUS = float(os.getenv("MIN_RR_NEXUS", str(MIN_RR_DEFAULT)))
MIN_RR_AGGRESSIVE_LSE = float(os.getenv("MIN_RR_AGGRESSIVE_LSE", "2.0"))
MIN_STOP_ATR_MULT = float(os.getenv("MIN_STOP_ATR_MULT", "0.5"))
MIN_STOP_PCT_OF_PRICE = float(os.getenv("MIN_STOP_PCT_OF_PRICE", "0.002"))
MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("MAX_ENTRY_SLIPPAGE_PCT", "0.002"))
MAX_MARGIN_PER_TRADE_USD = float(os.getenv("MAX_MARGIN_PER_TRADE_USD", "150"))
MAX_NOTIONAL_PER_TRADE_USD = float(os.getenv("MAX_NOTIONAL_PER_TRADE_USD", "50000"))
TICK_SIZE_MIN_RELATIVE_OF_PRICE = float(os.getenv("TICK_SIZE_MIN_RELATIVE_OF_PRICE", "1e-7"))
TICK_SIZE_MIN_ABSOLUTE = float(os.getenv("TICK_SIZE_MIN_ABSOLUTE", "1e-10"))
LSE_BLOCK_REASONING_SUBSTRING = os.getenv("LSE_BLOCK_REASONING_SUBSTRING", "R:R bajo")
LSE_FOLLOW_THROUGH_ENABLED = os.getenv("LSE_FOLLOW_THROUGH_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
LSE_FOLLOW_THROUGH_CANDLES = int(os.getenv("LSE_FOLLOW_THROUGH_CANDLES", "2"))
# Mínimo recorrido absoluto hasta TP2 (evita RR “válido” pero setup microscópico)
MIN_TP_DISTANCE_ATR_MULT = float(os.getenv("MIN_TP_DISTANCE_ATR_MULT", "0.8"))
MIN_TP_DISTANCE_PCT_OF_PRICE = float(os.getenv("MIN_TP_DISTANCE_PCT_OF_PRICE", "0.003"))
# Cooldown por símbolo tras trade LSE (0 = desactivado). Duración ≈ N × duración de vela del TF.
LSE_SYMBOL_COOLDOWN_CANDLES = int(os.getenv("LSE_SYMBOL_COOLDOWN_CANDLES", "5"))
# Tras N pérdidas seguidas (cualquier cierre que no sea TP), pausa nuevas entradas LSE.
AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES = int(os.getenv("AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES", "3"))
AGENT_KILL_SWITCH_PAUSE_MINUTES = float(os.getenv("AGENT_KILL_SWITCH_PAUSE_MINUTES", "120"))
# Cuántos candidatos rankeados probar en serie hasta ejecutar uno válido (fallback).
AGENT_MAX_CANDIDATES_PER_CYCLE = int(os.getenv("AGENT_MAX_CANDIDATES_PER_CYCLE", "10"))
# Si > 0: solo los ranks 1..N pueden ejecutar candidatos no-LSE (evita rank 9 Nexus "por descarte").
AGENT_MAX_RANK_FOR_NEXUS_FALLBACK = int(os.getenv("AGENT_MAX_RANK_FOR_NEXUS_FALLBACK", "0"))

MAX_OPEN_POSITIONS = 3
MAX_TRADES_PER_DAY = 100
MAX_POSITION_DURATION_HOURS = 48
DEFAULT_LEVERAGE = 1

# 4. Intelligence Thresholds
MIN_NEXUS_CONFIDENCE = 70.0
MIN_SCAR_SCORE = 4
MIN_CONFLUENCE_SCORE = 35.0

# 5. Take Profit / Stop Loss
TP_MULTIPLIER = 1.5
SL_MULTIPLIER = 0.8

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
POSITIONS_FILE    = os.path.join(DATA_DIR, "positions.json")
DAILY_STATS_FILE  = os.path.join(DATA_DIR, "daily_stats.json")
TRADES_LOG_FILE   = os.path.join(DATA_DIR, "trades.csv")
TRADE_METRICS_JSONL = os.path.join(DATA_DIR, "trade_metrics.jsonl")
LSE_SYMBOL_COOLDOWN_FILE = os.path.join(DATA_DIR, "lse_symbol_cooldown.json")
AGENT_LOSS_STREAK_FILE = os.path.join(DATA_DIR, "agent_loss_streak.json")
AUTO_TUNER_OVERRIDES_FILE = os.path.join(DATA_DIR, "auto_tuner_overrides.json")
AUTO_TUNER_RECOMMENDATIONS_FILE = os.path.join(DATA_DIR, "auto_tuner_recommendations.json")
WATCHLIST_CACHE   = os.path.join(DATA_DIR, "watchlist_cache.json")


def timeframe_to_seconds(tf: str) -> float:
    """Duración aproximada de una vela (para cooldown por N velas)."""
    s = (tf or "1h").strip().lower()
    sec = {
        "1m": 60.0,
        "3m": 180.0,
        "5m": 300.0,
        "15m": 900.0,
        "30m": 1800.0,
        "1h": 3600.0,
        "2h": 7200.0,
        "4h": 14400.0,
        "1d": 86400.0,
    }
    return float(sec.get(s, 3600.0))

os.makedirs(DATA_DIR, exist_ok=True)


def _merge_auto_tuner_overrides() -> None:
    """
    Aplica agent/data/auto_tuner_overrides.json si existe (generado por auto_tuner.py --apply).
    Solo claves permitidas; requiere sample_size >= min_trades en el JSON.
    """
    global MIN_RR_DEFAULT, MIN_RR_NEXUS, MIN_RR_AGGRESSIVE_LSE
    global MIN_TP_DISTANCE_ATR_MULT, MIN_TP_DISTANCE_PCT_OF_PRICE
    global MIN_STOP_ATR_MULT, MIN_STOP_PCT_OF_PRICE, MAX_ENTRY_SLIPPAGE_PCT
    global AGENT_MAX_RANK_FOR_NEXUS_FALLBACK

    path = AUTO_TUNER_OVERRIDES_FILE
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Config] auto_tuner_overrides read failed: {e}")
        return

    min_need = int(data.get("min_trades_required", 30))
    n = int(data.get("sample_size", 0))
    if n < min_need:
        print(
            f"[Config] auto_tuner overrides ignorados: sample_size={n} < {min_need}"
        )
        return

    o = data.get("overrides") or {}
    if not isinstance(o, dict) or not o:
        return

    allowed = {
        "MIN_RR_DEFAULT": float,
        "MIN_RR_NEXUS": float,
        "MIN_RR_AGGRESSIVE_LSE": float,
        "MIN_TP_DISTANCE_ATR_MULT": float,
        "MIN_TP_DISTANCE_PCT_OF_PRICE": float,
        "MIN_STOP_ATR_MULT": float,
        "MIN_STOP_PCT_OF_PRICE": float,
        "MAX_ENTRY_SLIPPAGE_PCT": float,
        "AGENT_MAX_RANK_FOR_NEXUS_FALLBACK": int,
    }
    applied = []
    for key, caster in allowed.items():
        if key not in o:
            continue
        try:
            val = caster(o[key])
        except (TypeError, ValueError):
            continue
        if key == "MIN_RR_DEFAULT":
            MIN_RR_DEFAULT = val
        elif key == "MIN_RR_NEXUS":
            MIN_RR_NEXUS = val
        elif key == "MIN_RR_AGGRESSIVE_LSE":
            MIN_RR_AGGRESSIVE_LSE = val
        elif key == "MIN_TP_DISTANCE_ATR_MULT":
            MIN_TP_DISTANCE_ATR_MULT = val
        elif key == "MIN_TP_DISTANCE_PCT_OF_PRICE":
            MIN_TP_DISTANCE_PCT_OF_PRICE = val
        elif key == "MIN_STOP_ATR_MULT":
            MIN_STOP_ATR_MULT = val
        elif key == "MIN_STOP_PCT_OF_PRICE":
            MIN_STOP_PCT_OF_PRICE = val
        elif key == "MAX_ENTRY_SLIPPAGE_PCT":
            MAX_ENTRY_SLIPPAGE_PCT = val
        elif key == "AGENT_MAX_RANK_FOR_NEXUS_FALLBACK":
            AGENT_MAX_RANK_FOR_NEXUS_FALLBACK = val
        applied.append(f"{key}={val}")

    if applied:
        print(f"[Config] Auto-tuner overrides activos ({data.get('generated_at_utc', '?')}): {', '.join(applied)}")


_merge_auto_tuner_overrides()

# 6. Agent Loop Interval
LOOP_INTERVAL_SECONDS = 300

# 7. Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", None)
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", None)

# ==========================================
# TIER SYSTEM
# ==========================================
TIER2_MIN_VOLATILITY_PCT = 0.3   # Min price move % to pass Tier 2 pre-filter
TIER3_ROTATE_PER_CYCLE   = 10    # Symbols to rotate per cycle in Tier 3 (10 = ~50min full coverage)

# Tier sizes
_TIER1_SIZE  = 30
_TIER2_SIZE  = 70
_TOTAL_LIMIT = 200

# Watchlist cache TTL: refresh from Binance every 6 hours
_CACHE_TTL_SECONDS = 6 * 3600

# Static fallback used only when Binance AND cache are both unavailable
_FALLBACK_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT", "FILUSDT",
    "AAVEUSDT", "SHIBUSDT", "MATICUSDT", "NEARUSDT", "APTUSDT",
    "OPUSDT", "ARBUSDT", "INJUSDT", "SUIUSDT", "TIAUSDT",
    "WIFUSDT", "JUPUSDT", "FETUSDT", "RENDERUSDT", "ONDOUSDT",
]


def _load_open_position_symbols() -> list:
    """Returns symbols in local open positions. Always placed at front of T1."""
    try:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
                return [p["symbol"] for p in positions if p.get("symbol")]
    except Exception as e:
        print(f"[Config] Warning: Could not read positions ({e})")
    return []


def _load_cached_watchlist() -> list | None:
    """
    Loads the watchlist from disk cache if it exists and is fresh (< TTL).
    Returns None if cache is missing or stale.
    """
    try:
        if os.path.exists(WATCHLIST_CACHE):
            with open(WATCHLIST_CACHE, "r") as f:
                data = json.load(f)
            age = time.time() - data.get("timestamp", 0)
            symbols = data.get("symbols", [])
            if age < _CACHE_TTL_SECONDS and len(symbols) >= 30:
                print(f"[Config] Watchlist loaded from cache ({len(symbols)} symbols, age={int(age/60)}min).")
                return symbols
    except Exception as e:
        print(f"[Config] Cache read error: {e}")
    return None


def _save_cached_watchlist(symbols: list):
    """Saves the watchlist to disk for future startups."""
    try:
        with open(WATCHLIST_CACHE, "w") as f:
            json.dump({"timestamp": time.time(), "symbols": symbols}, f)
        print(f"[Config] Watchlist cached to disk ({len(symbols)} symbols).")
    except Exception as e:
        print(f"[Config] Cache write error: {e}")


def _fetch_watchlist_multi(limit: int) -> list | None:
    """
    Fetches the top-N USDT futures symbols using the multi-exchange chain:
      Binance → Bybit → OKX
    Returns None only if ALL sources fail — caller uses static fallback.
    """
    # Lazy import to avoid circular dependency at module load time
    try:
        from multi_source_fetcher import get_multi_fetcher
        symbols = get_multi_fetcher().fetch_watchlist(limit=limit)
        if symbols:
            print(f"[Config] Watchlist fetched: {len(symbols)} symbols via multi-exchange chain.")
            return symbols
        print("[Config] All exchanges failed for watchlist — using cache/fallback.")
        return None
    except Exception as e:
        print(f"[Config] Multi-exchange watchlist fetch failed ({e}) — using cache/fallback.")
        return None


def _build_tiered_watchlist() -> dict:
    """
    Builds the tiered watchlist with this priority:
      1. Disk cache (if fresh < 6h)     → zero REST calls
      2. Binance REST (if cache stale)  → 1 REST call, then save to cache
      3. Hardcoded fallback             → if both fail (ban active)

    Open positions are ALWAYS prepended to T1 regardless of source.
    """
    open_pos = _load_open_position_symbols()

    # --- Determine base symbol list (cache → REST → fallback) ---
    base_symbols = _load_cached_watchlist()

    if base_symbols is None:
        # Cache miss or stale: try multi-exchange chain (Binance → Bybit → OKX)
        base_symbols = _fetch_watchlist_multi(_TOTAL_LIMIT)
        if base_symbols:
            _save_cached_watchlist(base_symbols)
        else:
            # All exchanges failed — use static fallback
            base_symbols = list(_FALLBACK_SYMBOLS)
            print(f"[Config] WARNING: Using static fallback ({len(base_symbols)} symbols). "
                  f"All exchanges unavailable. Cache will be refreshed on next successful startup.")

    # --- Merge: open positions FIRST, then base_symbols without duplicates ---
    ordered = list(open_pos)
    for s in base_symbols:
        if s not in ordered:
            ordered.append(s)

    # --- Slice into tiers ---
    tier1 = ordered[:_TIER1_SIZE]
    tier2 = ordered[_TIER1_SIZE: _TIER1_SIZE + _TIER2_SIZE]
    tier3 = ordered[_TIER1_SIZE + _TIER2_SIZE:]

    print(f"[Config] Tiers: T1={len(tier1)} | T2={len(tier2)} | T3={len(tier3)} | Total={len(ordered)}")
    if open_pos:
        print(f"[Config] Open positions guaranteed in T1: {open_pos}")

    return {
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "all":   ordered,
    }


# Build on import — uses cache when possible (0 REST calls after first run)
TIERED_WATCHLIST = _build_tiered_watchlist()

# Convenience aliases
WATCHLIST       = TIERED_WATCHLIST["all"]
WATCHLIST_TIER1 = TIERED_WATCHLIST["tier1"]
WATCHLIST_TIER2 = TIERED_WATCHLIST["tier2"]
WATCHLIST_TIER3 = TIERED_WATCHLIST["tier3"]


# ─────────────────────────────────────────────────────────────
# SYMBOL DISTRIBUTION (Load Balancing)
# ─────────────────────────────────────────────────────────────

def get_symbols_for_exchange(exchange_name: str) -> list:
    """
    Returns symbols assigned to a specific exchange.
    RESILIENCE UPDATE: 
      - TIER 1 (and Open Positions) are monitored by ALL exchanges for redundancy (HA).
      - TIER 2 & 3 are distributed among exchanges to balance load.
    """
    if not WATCHLIST:
        return []

    # 1. Start with TIER 1 (High Priority - Monitored by everyone)
    symbols = list(WATCHLIST_TIER1)

    # 2. Distribute TIER 2 & 3 (Lower Priority - Distributed)
    distributed_syms = WATCHLIST_TIER2 + WATCHLIST_TIER3
    
    mapping = {
        "binance": 0,
        "bybit":   1,
        "okx":     2,
        "bitget":  3,
    }

    if exchange_name not in mapping:
        return symbols # return at least T1 if unknown

    idx = mapping[exchange_name]
    num_exchanges = len(mapping)

    chunk_size = len(distributed_syms) // num_exchanges
    start = idx * chunk_size
    end = (idx + 1) * chunk_size if idx < num_exchanges - 1 else len(distributed_syms)

    # Add the distributed slice
    symbols.extend(distributed_syms[start:end])

    return list(set(symbols)) # Unique symbols just in case


def get_primary_exchange_for_symbol(symbol: str) -> str:
    """Returns which exchange is 'responsible' for this symbol's live data."""
    all_syms = WATCHLIST
    if symbol not in all_syms:
        return "binance"  # default fallback

    num_exchanges = 4
    try:
        s_idx = all_syms.index(symbol)
        chunk_size = len(all_syms) // num_exchanges
        e_idx = min(s_idx // chunk_size, num_exchanges - 1)
        return ["binance", "bybit", "okx", "bitget"][e_idx]
    except ValueError:
        return "binance"
