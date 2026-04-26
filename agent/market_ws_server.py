"""
VERGE Market WebSocket Server v2.0
====================================
- UNA sola conexion WebSocket para todos los simbolos
- Acumula historial de velas cerradas (hasta 100 por simbolo)
- HTTP local en puerto 8001:
    GET /health                     -> estado del servidor
    GET /market/candle/{symbol}     -> ultima vela (en tiempo real)
    GET /market/candles/{symbol}    -> historial de hasta 100 velas cerradas
- Reconexion automatica con backoff exponencial
- En startup: siembra el historial con una llamada REST por simbolo
"""

import json
import time
import logging
import threading
import requests
import websocket
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("MarketWS")

# ─────────────────────────────────────────────────────────────
# Cache global
# ─────────────────────────────────────────────────────────────
# Ultima vela (puede estar abierta, se actualiza cada 2s)
live_candle: dict = {}   # { "BTCUSDT": { candle_dict } }

# Historial de velas CERRADAS (solo isFinal=True)
history: dict = {}       # { "BTCUSDT": deque([candle1, candle2, ...], maxlen=100) }

ws_connected: bool = False
ws_reconnect_count: int = 0
BINANCE_FAPI = "https://fapi.binance.com"


# ─────────────────────────────────────────────────────────────
# Seed inicial: pedir historial REST una sola vez al arrancar
# ─────────────────────────────────────────────────────────────
def seed_history_from_rest():
    """Llama a Binance REST UNA VEZ al inicio para sembrar el historial de cada simbolo."""
    logger.info("[Seed] Sembrando historial inicial desde REST (una sola vez)...")
    session = requests.Session()

    for symbol in config.WATCHLIST:
        try:
            url = f"{BINANCE_FAPI}/fapi/v1/klines"
            params = {"symbol": symbol, "interval": "15m", "limit": 100}
            r = session.get(url, params=params, timeout=10)

            if r.status_code == 200:
                candles = []
                for k in r.json():
                    candles.append({
                        "symbol": symbol,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k[0] / 1000.0)),
                        "open":   float(k[1]),
                        "high":   float(k[2]),
                        "low":    float(k[3]),
                        "close":  float(k[4]),
                        "volume": float(k[5]),
                        "is_final": True
                    })
                history[symbol] = deque(candles, maxlen=100)
                # Ultima vela como live
                if candles:
                    live_candle[symbol] = candles[-1]
                logger.info(f"[Seed] {symbol}: {len(candles)} velas cargadas.")
            else:
                logger.warning(f"[Seed] No se pudo cargar {symbol}: {r.status_code} {r.text[:80]}")

            time.sleep(0.3)  # 300ms entre symbols para no agotar el rate limit en el seed

        except Exception as e:
            logger.error(f"[Seed] Error con {symbol}: {e}")

    logger.info(f"[Seed] Listo. {len(history)} simbolos con historial.")


# ─────────────────────────────────────────────────────────────
# Servidor HTTP
# ─────────────────────────────────────────────────────────────
class CandleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        # GET /health
        if path == "/health":
            self._respond(200, {
                "connected": ws_connected,
                "symbols_live": len(live_candle),
                "symbols_history": len(history),
                "reconnects": ws_reconnect_count
            })
            return

        # GET /market/candle/{symbol}  -> ultima vela en tiempo real
        if path.startswith("/market/candle/"):
            symbol = path.split("/market/candle/")[-1].upper()
            data = live_candle.get(symbol)
            if data:
                self._respond(200, data)
            else:
                self._respond(404, {"error": f"No live data for {symbol}"})
            return

        # GET /market/candles/{symbol} -> historial completo (hasta 100 velas)
        if path.startswith("/market/candles/"):
            symbol = path.split("/market/candles/")[-1].upper()
            hist = history.get(symbol)
            if hist:
                self._respond(200, list(hist))
            else:
                self._respond(404, {"error": f"No history for {symbol}"})
            return

        self._respond(404, {"error": "Not found"})

    def _respond(self, status: int, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP


# ─────────────────────────────────────────────────────────────
# WebSocket Client
# ─────────────────────────────────────────────────────────────
def build_ws_url() -> str:
    streams = "/".join(f"{s.lower()}@kline_15m" for s in config.WATCHLIST)
    return f"wss://fstream.binance.com/stream?streams={streams}"


def on_message(ws, message):
    try:
        data = json.loads(message)
        stream_data = data.get("data", {})
        if stream_data.get("e") != "kline":
            return

        k = stream_data["k"]
        symbol = k["s"].upper()

        candle = {
            "symbol": symbol,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k["t"] / 1000.0)),
            "open":     float(k["o"]),
            "high":     float(k["h"]),
            "low":      float(k["l"]),
            "close":    float(k["c"]),
            "volume":   float(k["v"]),
            "is_final": k.get("x", False),
            "received_at": time.time()
        }

        # Siempre actualizar la vela en tiempo real
        live_candle[symbol] = candle

        # Solo agregar al historial cuando la vela CIERRA
        if candle["is_final"]:
            if symbol not in history:
                history[symbol] = deque(maxlen=100)
            history[symbol].append(candle)
            logger.info(f"[WS] Vela cerrada: {symbol} C={candle['close']} V={candle['volume']:.0f}")

    except Exception as e:
        logger.error(f"[WS] Error procesando mensaje: {e}")


def on_error(ws, error):
    logger.error(f"[WS] Error: {error}")


def on_close(ws, close_status_code, close_msg):
    global ws_connected
    ws_connected = False
    logger.warning(f"[WS] Conexion cerrada. Codigo={close_status_code}")


def on_open(ws):
    global ws_connected
    ws_connected = True
    logger.info(f"[WS] Conexion activa. Monitoreando {len(config.WATCHLIST)} simbolos en tiempo real.")


def run_websocket():
    global ws_reconnect_count
    backoff = 1
    while True:
        try:
            url = build_ws_url()
            logger.info(f"[WS] Conectando... (intento #{ws_reconnect_count + 1})")
            ws = websocket.WebSocketApp(
                url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            logger.error(f"[WS] Excepcion: {e}")

        ws_reconnect_count += 1
        logger.warning(f"[WS] Reconectando en {backoff}s...")
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  VERGE Market WebSocket Server v2.0")
    logger.info(f"  Simbolos: {len(config.WATCHLIST)}")
    logger.info(f"  HTTP: http://localhost:8001")
    logger.info("=" * 60)

    # PASO 1: Sembrar historial desde REST (UNICA llamada REST, al inicio)
    seed_history_from_rest()

    # PASO 2: Iniciar WebSocket en hilo separado
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    time.sleep(2)  # Dar tiempo para que conecte

    # PASO 3: Abrir servidor HTTP
    logger.info("[HTTP] Servidor listo en http://localhost:8001")
    server = HTTPServer(("localhost", 8001), CandleHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Servidor detenido.")
