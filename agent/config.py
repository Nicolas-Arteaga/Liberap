import os
import json
import time

# ==========================================
# VERGE AUTONOMOUS TRADING AGENT CONFIGURATION
# ==========================================

# 1. API Endpoints
PYTHON_SERVICE_URL = os.getenv("PYTHON_SERVICE_URL", "http://localhost:8005")
ABP_BACKEND_URL = os.getenv("ABP_BACKEND_URL", "https://localhost:44396")

# Redis Signal Bridge — sincroniza el agente con las señales en tiempo real del backend C#.
# El backend publica en 'verge:superscore' cada vez que detecta un score >= 40 en CUALQUIER símbolo.
# El agente escucha ese canal y puede operar TRUTHUSDT, SHIBUSDT, o cualquier token que explote,
# aunque no esté en el watchlist hardcodeado.
# REDIS_URL: apuntar al mismo Redis que usa docker-compose (servicio 'redis')
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Score mínimo del backend C# para que el bridge inyecte el símbolo como candidato.
# Default: mismo que MIN_CONFLUENCE_SCORE para consistencia.
BRIDGE_MIN_SCORE = float(os.getenv("BRIDGE_MIN_SCORE", "45.0"))

# LiquiditySweepEngine (python-service /lse/scan y /lse/scan-batch)
LSE_ENABLED = os.getenv("LSE_ENABLED", "true").lower() in ("1", "true", "yes")
LSE_MIN_SCORE = float(os.getenv("LSE_MIN_SCORE", "65"))
LSE_DETECTION_MODE = os.getenv("LSE_DETECTION_MODE", "conservative")  # conservative | aggressive
LSE_DUAL_SCAN = os.getenv("LSE_DUAL_SCAN", "true").lower() in ("1", "true", "yes")
LSE_ENTRY_MODE = os.getenv("LSE_ENTRY_MODE", "aggressive")  # conservative | aggressive (timing entrada)
# UI/LSE pueden tardar 1–3+ min; el agente antes usaba 10s y cortaba todas las respuestas.
LSE_HTTP_TIMEOUT_SEC = int(os.getenv("LSE_HTTP_TIMEOUT_SEC", "360"))
# Cuántos pares con historial 1h completo entran al batch TOP-K.
# Por defecto escanea todo el universo elegible para decidir con contexto completo.
LSE_MAX_SYMBOLS_PER_CYCLE = int(os.getenv("LSE_MAX_SYMBOLS_PER_CYCLE", "450"))
LSE_BATCH_TOP_K = int(os.getenv("LSE_BATCH_TOP_K", "10"))
# Cuántos candidatos LSE distintos (por símbolo, mejor score) inyectar al ranking tras scan-batch.
# Permite fallback rank 2..N si el #1 cae en lse_warning_block / validate_lse_setup.
LSE_MAX_INJECTED_CANDIDATES = int(os.getenv("LSE_MAX_INJECTED_CANDIDATES", "10"))
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
MIN_RR_DEFAULT = float(os.getenv("MIN_RR_DEFAULT", "2.5"))
MIN_RR_NEXUS = float(os.getenv("MIN_RR_NEXUS", str(MIN_RR_DEFAULT)))
MIN_RR_AGGRESSIVE_LSE = float(os.getenv("MIN_RR_AGGRESSIVE_LSE", "1.2"))
LSE_MIN_RR = 3.0  # Sube el requisito mínimo de R:R para LSE (contratendencia)
MIN_STOP_ATR_MULT = float(os.getenv("MIN_STOP_ATR_MULT", "0.5"))
MIN_STOP_PCT_OF_PRICE = float(os.getenv("MIN_STOP_PCT_OF_PRICE", "0.002"))
MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("MAX_ENTRY_SLIPPAGE_PCT", "0.002"))
LSE_MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("LSE_MAX_ENTRY_SLIPPAGE_PCT", "0.20"))
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
AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES = int(os.getenv("AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES", "4"))
AGENT_KILL_SWITCH_PAUSE_MINUTES = float(os.getenv("AGENT_KILL_SWITCH_PAUSE_MINUTES", "120"))
# Cuántos candidatos rankeados probar en serie hasta ejecutar uno válido (fallback).
AGENT_MAX_CANDIDATES_PER_CYCLE = int(os.getenv("AGENT_MAX_CANDIDATES_PER_CYCLE", "10"))
# Si > 0: solo los ranks 1..N pueden ejecutar candidatos no-LSE (evita rank 9 Nexus "por descarte").
AGENT_MAX_RANK_FOR_NEXUS_FALLBACK = int(os.getenv("AGENT_MAX_RANK_FOR_NEXUS_FALLBACK", "0"))

MAX_OPEN_POSITIONS = 3              # 3 posiciones simultáneas para scalping
MIN_ENTRY_NEXUS  = float(os.getenv("MIN_ENTRY_NEXUS",  "76.0"))  # Nexus mínimo para abrir slot libre (Antes 70.0)
MIN_UPGRADE_NEXUS = float(os.getenv("MIN_UPGRADE_NEXUS", "80.0"))  # Nexus mínimo para reemplazar la peor posición
MAX_TRADES_PER_DAY = 100
MAX_POSITION_DURATION_HOURS = 48
MAX_TRADE_DURATION_CANDLES = int(os.getenv("MAX_TRADE_DURATION_CANDLES", "8"))
DEFAULT_LEVERAGE = 1

# 4. Intelligence Thresholds
MIN_NEXUS_CONFIDENCE = 76.0          # (Antes 75.0) — Exige más certeza, capturando ganadores PLAY y FIDA
MIN_SCAR_SCORE = 4
MIN_CONFLUENCE_SCORE = 60.0          # (Antes 55.0) — Evita picoteo sangrante de baja confluencia (<60)
LSE_WARNING_OVERRIDE_SCORE = float(os.getenv("LSE_WARNING_OVERRIDE_SCORE", "85.0"))
MIN_ESTIMATED_RANGE_PCT = float(os.getenv("MIN_ESTIMATED_RANGE_PCT", "0.8"))  # calibración LSE inicial — subir progresivamente según resultados

# --- CALIBRACIÓN DE VOLATILIDAD Y SEGURIDAD MÁXIMA ---
MAX_ESTIMATED_RANGE_PCT = 15.0         # Deja respirar a bombas reales (FIDA/PLAY) hasta 15% en 15m
MAX_STOP_LOSS_PCT = 9.0               # Máximo stop porcentual absoluto de 9% para evitar pérdidas catastróficas
CLONE_MAX_STOP_LOSS_PCT = 5.0         # Techo absoluto para Scalping Clone (usa SL 2x, necesita límite más estricto)
MAX_RSI_LONG_LIMIT = 75.0             # Nadie compra con RSI > 75. Evita comprar el clímax del pump.
TIER3_MIN_CONFLUENCE_SCORE = 65.0     # Exclusivo Tier 3: exige confluencia perfecta para entrar

# --- REGLA sniper DE ALTA VOLATILIDAD ---
HIGH_VOLATILITY_RANGE_THRESHOLD = 7.0  # Rango >= 7% activa la regla Sniper
HIGH_VOLATILITY_MIN_CONFLUENCE = 90.0   # Requiere confluencia extrema de 90+ para monedas explosivas

# ==========================================
# BTC TRIPLE LAYER DEFENSE - MACRO RISK SYSTEM
# ==========================================

# --- Capa 1: BTC Macro Filter (Régimen + Flash Crash) ---
BTC_DUMP_THRESHOLD_5M = float(os.getenv("BTC_DUMP_THRESHOLD_5M", "-0.8"))   # % caída 5m para DUMPING
BTC_DUMP_THRESHOLD_15M = float(os.getenv("BTC_DUMP_THRESHOLD_15M", "-1.5")) # % caída 15m para DUMPING
BTC_PUMP_THRESHOLD_5M = float(os.getenv("BTC_PUMP_THRESHOLD_5M", "0.8"))    # % subida 5m para BULLISH
BTC_REGIME_CACHE_SEC = int(os.getenv("BTC_REGIME_CACHE_SEC", "60"))        # Caché de régimen (segundos)
BTC_FLASH_CRASH_PCT_1H = float(os.getenv("BTC_FLASH_CRASH_PCT_1H", "-3.0")) # % caída 1h para flash crash
BTC_FLASH_CRASH_PAUSE_M = int(os.getenv("BTC_FLASH_CRASH_PAUSE_M", "120"))  # Pausa tras flash crash (minutos)

# --- Capa 2: Bloqueo Inteligente + Decouple + Macro Exit ---
BTC_EXIT_DUMP_5M = float(os.getenv("BTC_EXIT_DUMP_5M", "-0.7"))              # % dump 5m para trigger salida
BTC_EXIT_DUMP_15M = float(os.getenv("BTC_EXIT_DUMP_15M", "-1.5"))            # % dump 15m para trigger salida
BTC_MIN_ROI_TO_PROTECT = float(os.getenv("BTC_MIN_ROI_TO_PROTECT", "10.0"))  # % ROI mínimo sobre margin para activar
BTC_DECOUPLE_MIN_VOLUME_RATIO = float(os.getenv("BTC_DECOUPLE_MIN_VOLUME_RATIO", "2.5"))  # VolumeRatio mínimo para excepción
BTC_DECOUPLE_MIN_NEXUS = float(os.getenv("BTC_DECOUPLE_MIN_NEXUS", "80.0"))  # Nexus mínimo para excepción decouple

# --- Capa 3: Correlación Rolling y Penalización Nexus ---
BTC_CORR_WINDOW_CANDLES = int(os.getenv("BTC_CORR_WINDOW_CANDLES", "20"))     # Ventana de velas para correlación
BTC_CORR_CACHE_MINUTES = int(os.getenv("BTC_CORR_CACHE_MINUTES", "5"))        # Caché de correlación (minutos)
BTC_CORR_HIGH_THRESHOLD = float(os.getenv("BTC_CORR_HIGH_THRESHOLD", "0.8")) # Umbral alta correlación
BTC_CORR_MED_THRESHOLD = float(os.getenv("BTC_CORR_MED_THRESHOLD", "0.6"))   # Umbral media correlación
BTC_CORR_LOW_THRESHOLD = float(os.getenv("BTC_CORR_LOW_THRESHOLD", "0.4"))   # Umbral baja correlación
BTC_CORR_PENALTY_HIGH = float(os.getenv("BTC_CORR_PENALTY_HIGH", "0.60"))    # Penalización alta correlación
BTC_CORR_PENALTY_MED = float(os.getenv("BTC_CORR_PENALTY_MED", "0.75"))      # Penalización media correlación
BTC_CORR_PENALTY_LOW = float(os.getenv("BTC_CORR_PENALTY_LOW", "0.88"))      # Penalización baja correlación

# 5. Take Profit / Stop Loss — Fat Tail Strategy (asimétrica)
# SL amplio: 0.8× el rango estimado para que el ruido de 15m no active el stop.
# TP agresivo: 3.0× deja correr al 15% de trades ganadores hasta su potencial real.
# TP_MULTIPLIER = 3.5 (Aumenta para exprimir los ganadores masivos)
TP_MULTIPLIER = 3.5                  
SL_MULTIPLIER = 0.6                  
# Topes máximos de multiplicador TP por tipo de setup Nexus.
# TF puede correr hasta 3× el SL. MR tiene menos recorrido histórico, cap más conservador.
TP_MULT_TREND_FOLLOWING_MAX = float(os.getenv("TP_MULT_TREND_FOLLOWING_MAX", "3.2"))
TP_MULT_MEAN_REVERSION_MAX = float(os.getenv("TP_MULT_MEAN_REVERSION_MAX", "2.0"))

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
_TOTAL_LIMIT = 400

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


def _fetch_top_volatile_symbols(limit: int = 150) -> list:
    """
    Fetches the top volatile symbols from Binance Futures based on absolute 24h price change %.
    This matches exactly the behavior of the UI dashboard Top LSE Scan list.
    """
    try:
        import requests
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            pairs = [x for x in data if str(x.get("symbol", "")).endswith("USDT")]
            # Sort by absolute price change percent descending
            pairs.sort(key=lambda x: abs(float(x.get("priceChangePercent", 0.0))), reverse=True)
            res = [x["symbol"] for x in pairs[:limit]]
            print(f"[Config] Volatile symbols fetched: {len(res)} symbols (top volatile).")
            return res
    except Exception as e:
        print(f"[Config] Error fetching volatile symbols: {e}")
    return []


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

    # --- Fetch volatile symbols and merge them right after open positions ---
    volatile_symbols = _fetch_top_volatile_symbols(150)

    # --- Merge: open positions FIRST, then top volatile, then base_symbols without duplicates ---
    ordered = list(open_pos)
    for s in volatile_symbols:
        if s not in ordered:
            ordered.append(s)
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


def refresh_watchlist():
    """
    Refreshes the watchlist dynamically by re-building the tiered watchlist.
    Ensures newly opened positions or volatile tokens are immediately monitored.
    """
    global TIERED_WATCHLIST, WATCHLIST, WATCHLIST_TIER1, WATCHLIST_TIER2, WATCHLIST_TIER3
    try:
        new_watchlist = _build_tiered_watchlist()
        if new_watchlist and new_watchlist.get("all"):
            TIERED_WATCHLIST = new_watchlist
            WATCHLIST = new_watchlist["all"]
            WATCHLIST_TIER1 = new_watchlist["tier1"]
            WATCHLIST_TIER2 = new_watchlist["tier2"]
            WATCHLIST_TIER3 = new_watchlist["tier3"]
            print(f"[Config] Watchlist refreshed dynamically: T1={len(WATCHLIST_TIER1)} | T2={len(WATCHLIST_TIER2)} | T3={len(WATCHLIST_TIER3)}")
    except Exception as e:
        print(f"[Config] Error refreshing watchlist dynamically: {e}")


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
