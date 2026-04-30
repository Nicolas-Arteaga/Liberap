import os
import json
import time

# ==========================================
# VERGE AUTONOMOUS TRADING AGENT CONFIGURATION
# ==========================================

# 1. API Endpoints
PYTHON_SERVICE_URL = os.getenv("PYTHON_SERVICE_URL", "http://localhost:8005")
ABP_BACKEND_URL = os.getenv("ABP_BACKEND_URL", "https://localhost:44396")

# 2. ABP Agent Credentials
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "agent@verge.internal")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "1q2w3E*")
CLIENT_ID = os.getenv("CLIENT_ID", "Verge_App")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

# 3. Risk & Capital Management
VIRTUAL_CAPITAL_BASE = 10000.0
RISK_PER_TRADE_PCT = 0.015
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
WATCHLIST_CACHE   = os.path.join(DATA_DIR, "watchlist_cache.json")

os.makedirs(DATA_DIR, exist_ok=True)

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
    Returns a subset of the WATCHLIST assigned to a specific exchange.
    Ensures 200 symbols are balanced (approx 50 per exchange).
    Priority exchanges (Binance/Bybit) get T1 symbols first.
    """
    all_syms = WATCHLIST
    if not all_syms:
        return []

    # Map exchange names to their index for distribution
    # Order matches EXCHANGES priority in registry
    mapping = {
        "binance": 0,
        "bybit":   1,
        "okx":     2,
        "bitget":  3,
    }

    if exchange_name not in mapping:
        return []

    idx = mapping[exchange_name]
    num_exchanges = len(mapping)

    # Distribute symbols: each exchange takes its slice
    # Example: 200 symbols / 4 = 50 each
    chunk_size = len(all_syms) // num_exchanges
    start = idx * chunk_size
    # Last exchange takes any remainder
    end = (idx + 1) * chunk_size if idx < num_exchanges - 1 else len(all_syms)

    subset = all_syms[start:end]

    # Special rule: Pyth doesn't have a WS thread (it's REST/Oracle),
    # so we don't assign it symbols for WS monitoring here.

    return subset


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
