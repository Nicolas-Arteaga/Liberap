import os

# ==========================================
# VERGE AUTONOMOUS TRADING AGENT CONFIGURATION
# ==========================================

# 1. API Endpoints
PYTHON_SERVICE_URL = os.getenv("PYTHON_SERVICE_URL", "http://localhost:8000")
ABP_BACKEND_URL = os.getenv("ABP_BACKEND_URL", "https://localhost:44396")

# 2. ABP Agent Credentials
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "agent@verge.internal")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "1q2w3E*")
CLIENT_ID = os.getenv("CLIENT_ID", "Verge_App")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "") # Usually empty for public client in dev

# 3. Risk & Capital Management
VIRTUAL_CAPITAL_BASE = 10000.0          # Assumed initial capital if not querying DB
RISK_PER_TRADE_PCT = 0.015              # 1.5% of capital per trade
MAX_OPEN_POSITIONS = 3
MAX_TRADES_PER_DAY = 100
MAX_POSITION_DURATION_HOURS = 48        # Force close if open longer than 48h
DEFAULT_LEVERAGE = 1                    # 1x = sin apalancamiento (cambialo cuando quieras escalar)

# 4. Intelligence Thresholds
MIN_NEXUS_CONFIDENCE = 70.0             # Minimum confidence from Nexus-15 to consider standalone
MIN_SCAR_SCORE = 4                      # Minimum SCAR score to consider standalone
MIN_CONFLUENCE_SCORE = 35.0             # 70% Nexus solo = 35pts → entra. SCAR4+Nexus50 = 65pts → entra.

# 5. Take Profit / Stop Loss Multipliers (Based on ATR / Estimated Range)
TP_MULTIPLIER = 1.5                     # TP = Entry ± (Range * TP_MULTIPLIER)
SL_MULTIPLIER = 0.8                     # SL = Entry ∓ (Range * SL_MULTIPLIER)

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")
DAILY_STATS_FILE = os.path.join(DATA_DIR, "daily_stats.json")
TRADES_LOG_FILE = os.path.join(DATA_DIR, "trades.csv")

os.makedirs(DATA_DIR, exist_ok=True)

# 6. Watchlist (Dynamically populated with Top 150 USDT pairs by Volume + Open Positions)
def _get_final_watchlist(limit=150):
    symbols = []
    # 1. Fetch Top by Volume
    try:
        import requests
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10)
        if r.status_code == 200:
            usdt_pairs = [x for x in r.json() if x.get('symbol', '').endswith('USDT')]
            usdt_pairs.sort(key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
            symbols = [x['symbol'] for x in usdt_pairs[:limit]]
    except Exception as e:
        print(f"Warning: Could not fetch dynamic watchlist ({e}). Using fallback.")
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]

    # 2. Add Open Positions (CRITICAL: prevents bot from being blind to active trades)
    try:
        import json
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, 'r') as f:
                positions = json.load(f)
                for p in positions:
                    s = p.get('symbol')
                    if s and s not in symbols:
                        symbols.append(s)
    except Exception as e:
        print(f"Warning: Could not add open positions to watchlist ({e})")

    return symbols

WATCHLIST = _get_final_watchlist(150)

# 7. Agent Loop Interval
LOOP_INTERVAL_SECONDS = 300             # 5 minutes

# 8. Notifications (Optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", None)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", None)
