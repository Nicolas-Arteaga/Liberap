"""
VERGE Market WebSocket Server — Phase 2: Multi-Exchange Architecture
=====================================================================
Responsibilities:
  - Maintain PARALLEL WebSocket connections to Binance, Bybit, OKX and Bitget.
  - Each exchange runs in its own daemon thread with independent reconnect logic.
  - All WS message handlers write to the SAME KlineCache (SQLite) — single source of truth.
  - The 'source' field in live_prices tracks which exchange provided the latest price.
  - HTTP server on :8001 reads exclusively from KlineCache (zero exchange calls).

WebSocket threads (4 parallel):
  Thread 1 → Binance  (primary)
  Thread 2 → Bybit    (secondary)
  Thread 3 → OKX      (tertiary)
  Thread 4 → Bitget   (quaternary)

HTTP API (served from SQLite cache):
    GET /health                     → server status, circuit breaker states
    GET /market/candle/{symbol}     → latest live kline
    GET /market/candles/{symbol}    → up to 100 closed klines
    GET /market/ticker/{symbol}     → mini-ticker for Tier 2 pre-filter
    GET /audit/*                    → trade audit endpoints
"""

import json
import time
import random
import logging
import sys
import threading
import websocket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import config
from kline_cache import get_cache
from rate_limiter import get_limiter
from audit_engine import AuditEngine
from exchange_registry import EXCHANGES
from circuit_breaker import get_breakers

cache    = get_cache()
limiter  = get_limiter()
audit    = AuditEngine()
breakers = get_breakers()

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MarketWS")

# ─────────────────────────────────────────────────────────────
# Global counters (per exchange)
# ─────────────────────────────────────────────────────────────
_ws_state: dict = {
    name: {"connected": False, "reconnects": 0, "messages": 0, "candles": 0}
    for name in EXCHANGES
}
_state_lock = threading.Lock()


def _get_global_status() -> dict:
    with _state_lock:
        return {
            name: dict(v)
            for name, v in _ws_state.items()
        }


# ─────────────────────────────────────────────────────────────
# Generic WS runner (one per exchange)
# ─────────────────────────────────────────────────────────────

def _run_exchange_ws(exchange_name: str):
    """
    Runs the WebSocket loop for a single exchange.
    Reconnects automatically with exponential backoff + jitter.
    """
    exc = EXCHANGES[exchange_name]
    cb  = breakers.get(exchange_name)
    
    # NEW: Distribute 200 symbols across 4 exchanges (50 each)
    symbols = config.get_symbols_for_exchange(exchange_name)
    if not symbols:
        logger.warning(f"[WS:{exchange_name}] No symbols assigned. Thread exiting.")
        return

    backoff = 2

    while True:
        # If circuit is OPEN (ban active) — skip until available
        if cb and not cb.is_available:
            status = cb.get_status()
            ban_rem = status.get("ban_remaining_s", 0)
            if ban_rem > 0:
                wait = min(ban_rem, 300)   # recheck every 5 min max
                logger.warning(
                    f"[WS:{exchange_name}] Circuit OPEN (ban). "
                    f"Waiting {wait}s before retry..."
                )
                time.sleep(wait)
                continue

        url = exc.ws_url_builder(symbols)

        def on_open(ws):
            with _state_lock:
                _ws_state[exchange_name]["connected"] = True
            logger.info(
                f"[WS:{exchange_name}] Connected. "
                f"Subscribing to {len(symbols)} symbols..."
            )
            exc.subscribe_fn(ws, symbols)

            # Start custom heartbeat if required
            if exc.ping_payload:
                def run_heartbeat():
                    while _ws_state.get(exchange_name, {}).get("connected"):
                        try:
                            ws.send(exc.ping_payload)
                            logger.debug(f"[WS:{exchange_name}] Heartbeat sent.")
                        except:
                            break
                        time.sleep(20) # OKX requires every 30s
                
                hb_t = threading.Thread(target=run_heartbeat, daemon=True, name=f"HB-{exchange_name}")
                hb_t.start()

        def on_message(ws, raw: str):
            if raw == "pong":
                logger.debug(f"[WS:{exchange_name}] Heartbeat received (pong).")
                return

            try:
                data = json.loads(raw)
                kline = exc.message_parser(data)
                if not kline:
                    return

                symbol   = kline["symbol"]
                is_final = kline["is_final"]

                # Write live price to cache (tagged with source exchange)
                cache.upsert_live_price(
                    symbol  = symbol,
                    close   = kline["close"],
                    open_   = kline["open"],
                    high    = kline["high"],
                    low     = kline["low"],
                    volume  = kline["volume"],
                    source  = exchange_name,
                )

                # Write kline to history
                cache.upsert_kline(symbol, "15m", {
                    "open_time": kline["open_time"],
                    "open":      kline["open"],
                    "high":      kline["high"],
                    "low":       kline["low"],
                    "close":     kline["close"],
                    "volume":    kline["volume"],
                    "is_final":  is_final,
                })

                with _state_lock:
                    _ws_state[exchange_name]["messages"] += 1
                    if is_final:
                        _ws_state[exchange_name]["candles"] += 1

                # Log Tier-1 candle closes for primary exchange only (reduce noise)
                if is_final and exchange_name == "binance" and symbol in config.WATCHLIST_TIER1:
                    cnt = cache.count_klines(symbol, "15m")
                    logger.info(
                        f"[WS:binance] T1 closed: {symbol} "
                        f"C={kline['close']} V={kline['volume']:.0f} "
                        f"history={cnt}klines"
                    )

                # Record success in circuit breaker (heartbeat)
                if cb:
                    cb.record_success()

            except Exception as e:
                logger.error(f"[WS:{exchange_name}] Message parse error: {e}")

        def on_error(ws, error):
            logger.error(f"[WS:{exchange_name}] Error: {error}")

        def on_close(ws, code, msg):
            with _state_lock:
                _ws_state[exchange_name]["connected"] = False
            logger.warning(f"[WS:{exchange_name}] Closed (code={code})")

        try:
            logger.info(
                f"[WS:{exchange_name}] Connecting "
                f"(attempt #{_ws_state[exchange_name]['reconnects'] + 1})..."
            )
            ws = websocket.WebSocketApp(
                url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)

        except Exception as e:
            logger.error(f"[WS:{exchange_name}] Exception: {e}")
            if cb:
                cb.record_failure()

        with _state_lock:
            _ws_state[exchange_name]["reconnects"] += 1

        jitter = random.uniform(0, backoff * 0.3)
        wait   = backoff + jitter
        logger.warning(f"[WS:{exchange_name}] Reconnecting in {wait:.1f}s...")
        time.sleep(wait)
        backoff = min(backoff * 2, 60)


# ─────────────────────────────────────────────────────────────
# HTTP Server — reads from SQLite cache (zero exchange calls)
# ─────────────────────────────────────────────────────────────

class CandleHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        # GET /health
        if path == "/health":
            ws_status    = _get_global_status()
            cache_stats  = cache.get_stats()
            limiter_stat = limiter.get_status()
            cb_status    = {name: cb.get_status() for name, cb in breakers.items()}
            self._json(200, {
                "exchanges":       ws_status,
                "watchlist_total": len(config.WATCHLIST),
                "tier1":           len(config.WATCHLIST_TIER1),
                "tier2":           len(config.WATCHLIST_TIER2),
                "tier3":           len(config.WATCHLIST_TIER3),
                "cache":           cache_stats,
                "rate_limiter":    limiter_stat,
                "circuit_breakers": cb_status,
            })
            return

        # GET /market/candle/{symbol}
        if path.startswith("/market/candle/"):
            symbol = path.split("/market/candle/")[-1].upper()
            ticker = cache.get_ticker(symbol)
            if ticker and ticker.get("is_fresh"):
                self._json(200, {
                    "symbol":  symbol,
                    "close":   ticker["close"],
                    "open":    ticker["open"],
                    "high":    ticker["high"],
                    "low":     ticker["low"],
                    "volume":  ticker["volume"],
                    "age_s":   ticker["age_s"],
                })
            else:
                self._json(404, {"error": f"No live data for {symbol}"})
            return

        # GET /market/candles/{symbol}?limit=N
        if path.startswith("/market/candles/"):
            symbol = path.split("/market/candles/")[-1].upper()
            qs     = parse_qs(urlparse(self.path).query)
            limit  = int(qs.get("limit", ["100"])[0])
            klines = cache.get_klines(symbol, "15m", limit)
            if klines:
                self._json(200, klines)
            else:
                self._json(404, {"error": f"No history for {symbol}"})
            return

        # GET /market/ticker/{symbol}
        if path.startswith("/market/ticker/"):
            symbol = path.split("/market/ticker/")[-1].upper()
            ticker = cache.get_ticker(symbol)
            if ticker:
                ticker["has_history"] = cache.has_history(symbol, "15m", 25)
                self._json(200, ticker)
            else:
                self._json(404, {"error": f"No ticker for {symbol}"})
            return

        # GET /market/sources — shows which exchange provided each symbol's latest price
        if path == "/market/sources":
            stats = cache.get_stats()
            self._json(200, {
                "exchanges": _get_global_status(),
                "circuit_breakers": {name: cb.get_status() for name, cb in breakers.items()},
                "cache_stats": stats,
            })
            return

        # Audit Endpoints
        if path == "/audit/summary":
            self._json(200, audit.get_summary())
            return
        if path == "/audit/stats":
            self._json(200, audit.get_strategy_stats())
            return
        if path == "/audit/trades":
            self._json(200, audit.get_recent_trades())
            return
        if path == "/audit/top-symbols":
            self._json(200, audit.get_top_symbols())
            return
        if path == "/audit/open":
            self._json(200, audit.get_open_positions())
            return

        self._json(404, {"error": "Not found"})

    def _json(self, status: int, body: dict):
        try:
            payload = json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(payload))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionAbortedError, BrokenPipeError, OSError):
            # Client disconnected before response was fully sent — ignore silently
            pass

    def log_message(self, fmt, *args):
        pass   # Silence HTTP access logs


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("=" * 65)
    logger.info("  VERGE Market Data Service — Phase 2: Multi-Exchange")
    logger.info(f"  Symbols: {len(config.WATCHLIST)} total "
                f"(T1={len(config.WATCHLIST_TIER1)}, "
                f"T2={len(config.WATCHLIST_TIER2)}, "
                f"T3={len(config.WATCHLIST_TIER3)})")
    logger.info("  WS Sources: Binance | Bybit | OKX | Bitget")
    logger.info("  Mode: WS-only — NO REST seed at startup")
    logger.info("  Cache: SQLite (data/klines.db)")
    logger.info("  HTTP:  http://localhost:8001")
    logger.info("=" * 65)

    stats = cache.get_stats()
    logger.info(
        f"[Cache] Startup: {stats['symbols_with_history']} symbols, "
        f"{stats['total_klines']} klines, {stats['live_prices']} live prices."
    )
    if stats['symbols_with_history'] > 0:
        logger.info("[Cache] Existing history loaded. Agent can analyze immediately.")
    else:
        logger.info("[Cache] No history yet. WS will accumulate data over ~15-30 min.")

    # Start one WS thread per exchange
    for exchange_name in EXCHANGES:
        if exchange_name == "pyth":
            continue # Pyth is handled by its own REST polling thread below
            
        t = threading.Thread(
            target=_run_exchange_ws,
            args=(exchange_name,),
            daemon=True,
            name=f"WS-{exchange_name}",
        )
        t.start()
        logger.info(f"[WS] Started thread for {exchange_name}")
        time.sleep(0.5)   # Stagger connections slightly

    # Start Pyth Polling thread (Decentralized Source #5)
    def _run_pyth_polling():
        import requests
        # Mapping for critical symbols
        PYTH_MAPPING = {
            "BTCUSDT": "e62df6c8b4a85fe1a67db44dc12de5bb330f8f27cf5097240a0593e9f05a9140",
            "ETHUSDT": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
            "SOLUSDT": "ef0d8b6fda2ceba41da3678a2abd3690def3a5932a37ee18f7090f8d05b11fb1",
        }
        url = "https://hermes.pyth.network/v2/updates/price/latest"
        
        while True:
            try:
                ids = list(PYTH_MAPPING.values())
                params = [('ids[]', id) for id in ids]
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("parsed", [])
                    for item in data:
                        feed_id = item.get("id")
                        # Find symbol for this feed_id
                        symbol = next((s for s, i in PYTH_MAPPING.items() if i == feed_id), None)
                        if symbol:
                            p = item.get("price", {})
                            price = float(p.get("price", 0)) * (10 ** int(p.get("expo", 0)))
                            if price > 0:
                                cache.upsert_live_price(
                                    symbol=symbol,
                                    close=price,
                                    open_=price, # Pyth doesn't give open easily here
                                    high=price,
                                    low=price,
                                    volume=0.0,
                                    source="pyth"
                                )
                                # Record success for Pyth CB
                                breakers["pyth"].record_success()
                time.sleep(10) # Pyth polling interval
            except Exception as e:
                logger.error(f"[Pyth] Polling error: {e}")
                breakers["pyth"].record_failure()
                time.sleep(30)

    t_pyth = threading.Thread(target=_run_pyth_polling, daemon=True, name="Pyth-Polling")
    t_pyth.start()
    logger.info("[Pyth] Started polling thread (decentralized backup).")

    # Start HTTP server (blocks main thread)
    logger.info("[HTTP] Server ready at http://localhost:8001")
    server = HTTPServer(("localhost", 8001), CandleHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[HTTP] Server stopped.")
