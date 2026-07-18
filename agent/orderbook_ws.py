"""
OrderbookWS — Order Book Imbalance (OFI) Capture
=================================================
Captura profundidad de order book (Binance Futures, partial depth stream)
para el subconjunto de mayor volumen del watchlist, calcula Order Flow
Imbalance (OFI) normalizado [-1.0, 1.0] y lo persiste vía kline_cache.py
(misma DB SQLite que klines/live_prices — sin storage paralelo, ver
openspec/changes/market-data-expansion/design.md).

Solo Binance: es la única fuente de profundidad de order book gratuita
entre los exchanges ya conectados en este proyecto.

Stream (combined): wss://fstream.binance.com/stream?streams=<symbol>@depth20/...
Payload real verificado en vivo contra fstream.binance.com (el ejemplo de la
doc pública, con "bids"/"asks", resultó ser el de spot — futures usa "b"/"a"
y sí trae el símbolo en "s", a diferencia de lo que documentaba spot):
  {"stream": "btcusdt@depth20",
   "data": {"e": "depthUpdate", "E": .., "T": .., "s": "BTCUSDT", "ps": "BTCUSDT",
            "U": .., "u": .., "pu": ..,
            "b": [[price, qty], ...], "a": [[price, qty], ...]}}
"""

import time
import logging

logger = logging.getLogger("OrderbookWS")

OFI_LEVELS = 20                    # niveles de profundidad por lado (Binance permite 5/10/20)
OFI_WRITE_THROTTLE_S = 30          # cadencia de escritura a SQLite por símbolo — alineado a la
                                    # granularidad real de uso (scans cada 5 min), no al tick de 250ms
WATCHLIST_REFRESH_INTERVAL_S = 30 * 60  # recalcular watchlist y reconectar (auto-resubscribe)


def compute_ofi(bids, asks, levels: int = OFI_LEVELS):
    """
    Order Flow Imbalance normalizado en [-1.0, 1.0] sobre los primeros
    `levels` niveles de bids/asks. Positivo = presión compradora.

    Devuelve None (nunca un score inventado) si no hay suficientes niveles
    o el volumen total es cero — spec: "datos insuficientes para calcular OFI".

    Retorna (ofi, bid_volume, ask_volume) o None.
    """
    if not bids or not asks or len(bids) < levels or len(asks) < levels:
        return None
    try:
        bid_volume = sum(float(b[1]) for b in bids[:levels])
        ask_volume = sum(float(a[1]) for a in asks[:levels])
    except (TypeError, ValueError, IndexError):
        return None
    total = bid_volume + ask_volume
    if total <= 0:
        return None
    ofi = (bid_volume - ask_volume) / total
    return round(ofi, 6), round(bid_volume, 8), round(ask_volume, 8)


def parse_partial_depth_message(raw: dict):
    """
    Extrae symbol/bids/asks de un frame del combined stream. Verificado en
    vivo contra fstream.binance.com: el payload real trae "s" (símbolo) y
    "b"/"a" (bids/asks) — no "bids"/"asks" como muestra el ejemplo de la doc
    pública (ese es el de spot, no el de futures). Devuelve None si el
    frame no es un depth update reconocible.
    """
    data = raw.get("data") or {}
    symbol = data.get("s")
    bids = data.get("b")
    asks = data.get("a")
    if not symbol or bids is None or asks is None:
        return None
    return {"symbol": symbol, "bids": bids, "asks": asks}


def run_orderbook_stream(agent_log=print, set_status=None):
    """
    Loop principal — pensado para correr en su propio thread daemon (ver
    market_ws_server.py::main_startup). Se reconecta solo, mismo patrón que
    ws_loop() en ese archivo, pero además recalcula el watchlist cada
    WATCHLIST_REFRESH_INTERVAL_S y fuerza una reconexión: eso es lo que
    cumple "un símbolo nuevo del watchlist se suscribe automáticamente en
    el próximo ciclo, sin reinicio manual" (los streams de klines de
    market_ws_server.py NO hacen esto — su watchlist queda fijo toda la
    vida del container; acá sí, porque el spec de order book lo exige).
    """
    import websocket
    import json as pyjson
    import config
    from kline_cache import get_cache

    cache = get_cache()

    while True:
        try:
            try:
                config.refresh_watchlist()
            except Exception as e:
                agent_log(f"⚠️ Orderbook WS: refresh_watchlist falló ({type(e).__name__}: {e}), sigo con el watchlist actual.")
            symbols = list(config.WATCHLIST_TIER1)
            if not symbols:
                agent_log("⚠️ Orderbook WS: watchlist vacío, reintento en 5s.")
                time.sleep(5)
                continue

            streams = "/".join(f"{s.lower()}@depth{OFI_LEVELS}" for s in symbols)
            url = f"wss://fstream.binance.com/stream?streams={streams}"

            stats = {"msgs": 0, "written": 0, "insufficient": 0, "errors": 0}
            last_report = [time.time()]
            connected_at = [time.time()]
            last_write = {}

            def on_open(ws):
                if set_status:
                    set_status("orderbook", "CONNECTED")
                agent_log(f"📖 Orderbook WS conectado ({len(symbols)} símbolos, depth{OFI_LEVELS}).")

            def on_message(ws, msg):
                stats["msgs"] += 1
                now = time.time()
                try:
                    raw = pyjson.loads(msg)
                    parsed = parse_partial_depth_message(raw)
                    if parsed:
                        result = compute_ofi(parsed["bids"], parsed["asks"])
                        if result is None:
                            stats["insufficient"] += 1
                        else:
                            symbol = parsed["symbol"]
                            if now - last_write.get(symbol, 0) >= OFI_WRITE_THROTTLE_S:
                                ofi, bid_vol, ask_vol = result
                                cache.upsert_ofi(symbol, ofi, bid_vol, ask_vol, OFI_LEVELS)
                                last_write[symbol] = now
                                stats["written"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    if stats["errors"] <= 3:
                        agent_log(f"⚠️ Orderbook WS on_message error: {type(e).__name__}: {e} | raw={msg[:200]}")

                if now - last_report[0] > 60:
                    agent_log(f"📊 Orderbook WS msgs/60s: total={stats['msgs']} written={stats['written']} "
                              f"insufficient={stats['insufficient']} errors={stats['errors']}")
                    stats.update(msgs=0, written=0, insufficient=0, errors=0)
                    last_report[0] = now

                # Reconexión periódica → recoge cambios de watchlist (ver docstring)
                if now - connected_at[0] > WATCHLIST_REFRESH_INTERVAL_S:
                    ws.close()

            def on_error(ws, err):
                if set_status:
                    set_status("orderbook", "ERROR")
                agent_log(f"❌ Orderbook WS error: {type(err).__name__}: {err}")

            def on_close(ws, code, msg):
                if set_status:
                    set_status("orderbook", "DISCONNECTED")
                agent_log(f"🔌 Orderbook WS cerrado. code={code} msg={msg}")

            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
            ws.run_forever()
            try:
                cache.prune_old_ofi()
            except Exception as e:
                agent_log(f"⚠️ Orderbook WS: prune_old_ofi falló ({type(e).__name__}: {e}).")
            time.sleep(5)
        except Exception as e:
            if set_status:
                set_status("orderbook", "DISCONNECTED")
            agent_log(f"❌ Orderbook WS loop crash: {type(e).__name__}: {e}")
            time.sleep(5)
