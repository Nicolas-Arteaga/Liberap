print(">>> INICIANDO VERGE MARKET WS (V1.3 Docker-Native)", flush=True)
import os
import sys
import time
import json
import asyncio
import threading
from datetime import datetime
from urllib.parse import urlparse

# Verge Modules
import config

# --- GLOBAL STATE ---
_log_buffer = []
_exchange_status = {}
_status_lock = threading.Lock()
START_TIME = datetime.now()

def set_exchange_status(name, status):
    with _status_lock:
        _exchange_status[name] = {
            "connected": (status == "CONNECTED"),
            "status": status,
            "last_update": datetime.now().isoformat()
        }

def agent_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_buffer.append(line)
    if len(_log_buffer) > 10000:
        del _log_buffer[0]

# --- PURE ASYNC HTTP SERVER (no threads, no locks, no deadlock) ---
def _build_response(path):
    if path == '/health':
        with _status_lock:
            exc_copy = dict(_exchange_status)
        return {"status": "ok", "exchanges": exc_copy, "timestamp": datetime.now().isoformat()}
    elif path == '/logs':
        return {"logs": list(_log_buffer[-500:])}
    elif path.startswith('/market/candle/'):
        symbol = path.split('/')[-1].upper()
        try:
            from kline_cache import get_cache
            ticker = get_cache().get_ticker(symbol)
            return ticker if ticker else None
        except:
            return None
    elif path == '/market/tickers':
        try:
            from kline_cache import get_cache
            return get_cache().get_all_tickers()
        except:
            return {}
    elif path.startswith('/audit/'):
        if '/summary' in path:
            return {"balance": 10000, "winRate": 0, "trades": 0, "pnlTotal": 0}
        elif '/stats' in path:
            return {"daily_pnl": 0, "weekly_pnl": 0}
        elif '/trades' in path or '/top-symbols' in path or '/open' in path:
            return []
    return None

async def handle_request(reader, writer):
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
        agent_log(f"DEBUG: GET {path}")

        data = _build_response(path)
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
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def run_server():
    server = await asyncio.start_server(handle_request, '0.0.0.0', 8001)
    agent_log("🌐 Servidor API listo en puerto 8001 (0.0.0.0)")
    async with server:
        await server.serve_forever()

# --- WEBSOCKET LOOPS (run in threads) ---
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
                        cache.upsert_live_price(
                            parsed["symbol"], parsed["close"], parsed["open"],
                            parsed["high"], parsed["low"], parsed["volume"], exchange_name
                        )
                except:
                    pass
            def on_error(ws, err):
                set_exchange_status(exchange_name, "ERROR")
            def on_close(ws, code, msg):
                set_exchange_status(exchange_name, "DISCONNECTED")

            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
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
    asyncio.run(run_server())
