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
MAX_TRADES_PER_DAY = 5
MAX_POSITION_DURATION_HOURS = 48        # Force close if open longer than 48h
DEFAULT_LEVERAGE = 1                    # 1x = sin apalancamiento (cambialo cuando quieras escalar)

# 4. Intelligence Thresholds
MIN_NEXUS_CONFIDENCE = 70.0             # Minimum confidence from Nexus-15 to consider standalone
MIN_SCAR_SCORE = 4                      # Minimum SCAR score to consider standalone
MIN_CONFLUENCE_SCORE = 35.0             # 70% Nexus solo = 35pts → entra. SCAR4+Nexus50 = 65pts → entra.

# 5. Take Profit / Stop Loss Multipliers (Based on ATR / Estimated Range)
TP_MULTIPLIER = 1.5                     # TP = Entry ± (Range * TP_MULTIPLIER)
SL_MULTIPLIER = 0.8                     # SL = Entry ∓ (Range * SL_MULTIPLIER)

# 6. Watchlist (Pairs to scan with Nexus-15 every 5 minutes)
WATCHLIST = [
    # Blue chips
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "NEARUSDT",
    # Nexus-15 TOP 5 activos
    "RAYSOLUSDT", "SPACEUSDT", "SONICUSDT", "ENSOUSDT",
    "WCTUSDT", "SPKUSDT", "DYMUSDT", "IOUSDT",
    "ZBTUSDT", "VELVETUSDT", "AIOUSDT", "MIRAUSDT"
]

# 7. Agent Loop Interval
LOOP_INTERVAL_SECONDS = 300             # 5 minutes

# 8. Notifications (Optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", None)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", None)

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")
DAILY_STATS_FILE = os.path.join(DATA_DIR, "daily_stats.json")
TRADES_LOG_FILE = os.path.join(DATA_DIR, "trades.csv")

os.makedirs(DATA_DIR, exist_ok=True)
