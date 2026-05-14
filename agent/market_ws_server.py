print(">>> INICIANDO VERGE MARKET WS (V1.3 Docker-Native)", flush=True)
import os
import sys
import time
import json
import logging
import threading
from datetime import datetime
from urllib.parse import urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Verge Modules
import config

# --- GLOBAL STATE ---
_log_buffer = []
_log_lock = threading.Lock()
_exchange_status = {} # { "binance": "CONNECTED", ... }
_status_lock = threading.Lock()

def set_exchange_status(name, status):
    with _status_lock:
        _exchange_status[name] = status

def agent_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with _log_lock:
        _log_buffer.append(line)
        if len(_log_buffer) > 500: _log_buffer.pop(0)

# --- HTTP HANDLER ---
class FastCandleHandler(BaseHTTPRequestHandler):
    def _json(self, status: int, data: dict):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        except: pass

    def do_GET(self):
        agent_log(f"DEBUG: GET {self.path}")
        path = urlparse(self.path).path.rstrip("/")
        if path == "/health" or path == "":
            with _status_lock:
                health_data = {
                    "status": "healthy",
                    "service": "market-ws",
                    "uptime": str(datetime.now() - START_TIME),
                    "exchanges": _exchange_status
                }
            self._json(200, health_data)
        elif path == "/logs":
            with _log_lock:
                self._json(200, {"logs": list(_log_buffer)})
        elif path.startswith("/market/candle/"):
            symbol = path.split("/")[-1].upper()
            try:
                from kline_cache import get_cache
                ticker = get_cache().get_ticker(symbol)
                if ticker: self._json(200, ticker)
                else: self._json(404, {"error": "not found"})
            except: self.send_error(500)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        agent_log(f"HTTP: {format % args}")

# --- STARTUP LOGIC ---
START_TIME = datetime.now()

def ws_loop(exchange_name):
    import websocket
    import json as pyjson
    from exchange_registry import EXCHANGES
    from kline_cache import get_cache
    
    exc = EXCHANGES[exchange_name]
    symbols = config.get_symbols_for_exchange(exchange_name)
    cache = get_cache()

    while True:
        try:
            url = exc.ws_url_builder(symbols)
            def on_open(ws):
                set_exchange_status(exchange_name, "CONNECTED")
                agent_log(f"🔌 {exchange_name.upper()} Websocket conectado.")

            def on_message(ws, msg):
                try:
                    data = pyjson.loads(msg)
                    parsed = exc.message_parser(data)
                    if parsed:
                        cache.upsert_live_price(parsed["symbol"], parsed["close"], parsed["open"], parsed["high"], parsed["low"], parsed["volume"], exchange_name)
                except: pass

            def on_error(ws, err):
                set_exchange_status(exchange_name, "ERROR")

            def on_close(ws, close_status_code, close_msg):
                set_exchange_status(exchange_name, "DISCONNECTED")

            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
            ws.run_forever()
            time.sleep(5)
        except:
            set_exchange_status(exchange_name, "DISCONNECTED")
            time.sleep(5)

def main_startup():
    try:
        agent_log("Cargando módulos de trading...")
        from exchange_registry import EXCHANGES
        from kline_cache import get_cache

        cache = get_cache()
        agent_log("✅ Módulos base inicializados.")

        for exc_name in EXCHANGES:
            if exc_name == "pyth": 
                set_exchange_status("pyth", "CONNECTED")
                continue
            set_exchange_status(exc_name, "CONNECTING")
            threading.Thread(target=ws_loop, args=(exc_name,), daemon=True).start()
            agent_log(f"🚀 Canal {exc_name.upper()} iniciado.")
            time.sleep(0.3)

        agent_log("💎 Sistema Market-WS totalmente operativo.")
    except Exception as e:
        agent_log(f"❌ ERROR CRITICO EN STARTUP: {e}")

if __name__ == "__main__":
    threading.Thread(target=main_startup, daemon=True).start()
    agent_log(f"🌐 Servidor API listo en puerto 8001 (0.0.0.0)")
    server_address = ('0.0.0.0', 8001)
    httpd = HTTPServer(server_address, FastCandleHandler)
    httpd.serve_forever()
