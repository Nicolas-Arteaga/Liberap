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

    msg_count = {"total": 0, "written": 0, "parse_none": 0, "errors": 0}
    last_report = [time.time()]

    while True:
        try:
            url = exc.ws_url_builder(symbols)
            def on_open(ws):
                set_exchange_status(exchange_name, "CONNECTED")
                agent_log(f"🔌 {exchange_name.upper()} Websocket conectado. URL={url[:120]}")
                # BUG REAL: acá nunca se llamaba a exc.subscribe_fn — el socket
                # abría bien (por eso /health decía "CONNECTED") pero para
                # bybit/okx/bitget (que necesitan un mensaje explícito de
                # suscripción, a diferencia de binance que va todo en la URL)
                # nunca se pedían los streams, así que jamás llegaba un
                # mensaje real y el caché quedaba congelado para siempre.
                try:
                    exc.subscribe_fn(ws, symbols)
                    agent_log(f"📡 {exchange_name.upper()} suscripto a {len(symbols)} símbolos.")
                except Exception as e:
                    agent_log(f"❌ {exchange_name.upper()} subscribe_fn falló: {type(e).__name__}: {e}")
            def on_message(ws, msg):
                msg_count["total"] += 1
                try:
                    data = pyjson.loads(msg)
                    parsed = exc.message_parser(data)
                    if parsed:
                        cache.upsert_live_price(
                            parsed["symbol"], parsed["close"], parsed["open"],
                            parsed["high"], parsed["low"], parsed["volume"], exchange_name
                        )
                        msg_count["written"] += 1
                    else:
                        msg_count["parse_none"] += 1
                except Exception as e:
                    msg_count["errors"] += 1
                    # Loguea la excepción real la primera vez que pasa en esta
                    # ventana de reporte — antes esto era `except: pass` y por
                    # eso nunca se supo por qué las escrituras se frenaron.
                    if msg_count["errors"] <= 3:
                        agent_log(f"⚠️ {exchange_name.upper()} on_message error: {type(e).__name__}: {e} | raw={msg[:200]}")
                # Reporte periódico (cada ~60s) para confirmar en los logs que
                # los mensajes siguen llegando y escribiéndose, sin inundar.
                if time.time() - last_report[0] > 60:
                    agent_log(f"📊 {exchange_name.upper()} msgs/60s: total={msg_count['total']} "
                              f"written={msg_count['written']} parse_none={msg_count['parse_none']} "
                              f"errors={msg_count['errors']}")
                    msg_count.update(total=0, written=0, parse_none=0, errors=0)
                    last_report[0] = time.time()
            def on_error(ws, err):
                set_exchange_status(exchange_name, "ERROR")
                agent_log(f"❌ {exchange_name.upper()} Websocket error: {type(err).__name__}: {err}")
            def on_close(ws, code, msg):
                set_exchange_status(exchange_name, "DISCONNECTED")
                agent_log(f"🔌 {exchange_name.upper()} Websocket cerrado. code={code} msg={msg}")

            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
            ws.run_forever()
            time.sleep(5)
        except Exception as e:
            set_exchange_status(exchange_name, "DISCONNECTED")
            agent_log(f"❌ {exchange_name.upper()} ws_loop crash: {type(e).__name__}: {e}")
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
