"""
LiquidationTracker — Dinámica de liquidaciones (openspec market-data-expansion, sección 3)
=============================================================================================
El stream `!forceOrder@arr`/`<symbol>@forceOrder` de Binance Futures NO
entrega mensajes en este entorno (verificado dos sesiones distintas,
2026-07-16 y 2026-07-17, con y sin actividad reciente de baneos — no es un
ban, `@depth` funciona perfecto en la misma conexión). El REST público
equivalente (`/fapi/v1/allForceOrders`) está dado de baja por Binance para
todo el mundo, no solo acá.

Se usa Bybit en su lugar: mismo tipo de dato (liquidaciones forzadas de
futuros USDT-perpetuos), gratis, sin cuenta, y el WS de Bybit YA funciona en
este entorno (se usa para klines desde antes). Topic real verificado en
vivo: `allLiquidation.<symbol>` (el topic viejo `liquidation.<symbol>` fue
dado de baja por Bybit — devuelve error "handler not found" si se usa).

Payload real (verificado en vivo):
  {"topic":"allLiquidation.BTCUSDT","type":"snapshot","ts":...,
   "data":[{"T":<ms>,"s":"BTCUSDT","S":"Sell"|"Buy","v":"<qty>","p":"<price>"}]}
  S="Sell" = se liquidó un LONG (venta forzada) | S="Buy" = se liquidó un SHORT (compra forzada)
"""

import os
import json
import time
import logging

logger = logging.getLogger("LiquidationTracker")

WATCHLIST_REFRESH_INTERVAL_S = 30 * 60  # mismo patrón que orderbook_ws.py
PRUNE_INTERVAL_S = 3600

# ── Universo de research (EX-ANTE, mismo archivo que el colector de OI) ──
# research/universe/oi_universe.json. Fallback: WATCHLIST_TIER1 + BTC/ETH/SOL.
# El universo de ~30 microcaps de TIER1 NO alcanza para H14; esto lo amplia a
# los perps liquidos + majors, definido por liquidez, NO por resultados de H13.
_UNIVERSE_JSON = os.path.join(os.path.dirname(__file__), "..", "research", "universe", "oi_universe.json")
TIER0 = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
MAX_TOPICS = 180   # Bybit v5 publico: se suscribe de a 10; 180 topics = 63 del universo + margen


def load_research_universe(fallback_watchlist=None) -> list:
    try:
        with open(_UNIVERSE_JSON) as f:
            u = json.load(f).get("universe") or []
        if u:
            seen = set()
            out = [s for s in TIER0 + list(u) if not (s in seen or seen.add(s))]
            return out[:MAX_TOPICS]
    except Exception as e:
        logger.warning("[LIQ] no pude leer %s (%s) — uso fallback", _UNIVERSE_JSON, type(e).__name__)
    fb = list(fallback_watchlist or [])
    seen = set()
    return [s for s in TIER0 + fb if not (s in seen or seen.add(s))][:MAX_TOPICS]


def parse_liquidation_message(raw: dict):
    """Devuelve lista de {symbol, side, qty, price, timestamp_ms} o [] si el frame no es de liquidaciones."""
    topic = raw.get("topic", "")
    if not topic.startswith("allLiquidation."):
        return []
    events = []
    for d in (raw.get("data") or []):
        try:
            events.append({
                "symbol": d["s"],
                "side": d["S"],
                "qty": float(d["v"]),
                "price": float(d["p"]),
                "timestamp_ms": int(d["T"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return events


def run_liquidation_capture(agent_log=print):
    """
    Loop principal — thread daemon. Se reconecta solo y recalcula el
    watchlist cada WATCHLIST_REFRESH_INTERVAL_S (mismo patrón que
    orderbook_ws.py) para no requerir reinicio manual al cambiar de símbolos.
    """
    import websocket
    import json as pyjson
    import threading
    import config
    from kline_cache import get_cache

    cache = get_cache()
    BYBIT_PING_INTERVAL_S = 20  # Bybit v5 público corta la conexión si no hay tráfico ~60s sin este ping
                                 # de aplicación ({"op":"ping"}) — a diferencia de klines (mensajes
                                 # constantes), liquidaciones pueden tener silencios largos por símbolo,
                                 # así que acá SÍ hace falta explícito (bug real encontrado 2026-07-17:
                                 # la conexión se caía cada ~60s con 0 eventos capturados).

    while True:
        try:
            try:
                config.refresh_watchlist()
            except Exception as e:
                agent_log(f"⚠️ LiquidationTracker: refresh_watchlist falló ({type(e).__name__}: {e}), sigo con el watchlist actual.")
            symbols = load_research_universe(getattr(config, "WATCHLIST_TIER1", []))
            if not symbols:
                agent_log("⚠️ LiquidationTracker: universo vacío, reintento en 5s.")
                time.sleep(5)
                continue

            stats = {"events": 0, "cascades_flagged": 0}
            last_report = [time.time()]
            connected_at = [time.time()]

            stop_ping = threading.Event()

            def _ping_loop(ws):
                while not stop_ping.wait(BYBIT_PING_INTERVAL_S):
                    try:
                        ws.send(pyjson.dumps({"op": "ping"}))
                    except Exception:
                        return

            def on_open(ws):
                topics = [f"allLiquidation.{s}" for s in symbols]
                for i in range(0, len(topics), 10):  # mismo batching de a 10 que _subscribe_bybit en exchange_registry.py
                    ws.send(pyjson.dumps({"op": "subscribe", "args": topics[i:i + 10]}))
                    time.sleep(0.05)
                threading.Thread(target=_ping_loop, args=(ws,), daemon=True).start()
                agent_log(f"💥 LiquidationTracker conectado ({len(symbols)} símbolos, Bybit allLiquidation).")
                try:
                    cache.record_liq_health("connect", symbols_subscribed=len(symbols))
                except Exception:
                    pass

            def on_message(ws, msg):
                now = time.time()
                try:
                    raw = pyjson.loads(msg)
                    for ev in parse_liquidation_message(raw):
                        # LIVE CACHE (retencion corta, la usa el agente)
                        cache.insert_liquidation(ev["symbol"], ev["side"], ev["qty"], ev["price"], ev["timestamp_ms"])
                        # RESEARCH DATASET (append-only, sobrevive al prune) — idempotente
                        try:
                            cache.insert_liquidation_research(ev["symbol"], ev["side"], ev["qty"],
                                                              ev["price"], ev["timestamp_ms"], venue="bybit")
                        except Exception as e:
                            agent_log(f"⚠️ LiquidationTracker research insert error: {type(e).__name__}: {e}")
                        stats["events"] += 1
                except Exception as e:
                    agent_log(f"⚠️ LiquidationTracker on_message error: {type(e).__name__}: {e} | raw={msg[:200]}")

                if now - last_report[0] > 300:
                    agent_log(f"💥 LiquidationTracker: {stats['events']} eventos / 5min.")
                    try:
                        cache.record_liq_health("heartbeat", symbols_subscribed=len(symbols),
                                                events_since_last=stats["events"])
                    except Exception:
                        pass
                    stats.update(events=0)
                    last_report[0] = now
                if now - connected_at[0] > WATCHLIST_REFRESH_INTERVAL_S:
                    ws.close()

            def on_error(ws, err):
                agent_log(f"❌ LiquidationTracker WS error: {type(err).__name__}: {err}")

            def on_close(ws, code, msg):
                stop_ping.set()
                agent_log(f"🔌 LiquidationTracker WS cerrado. code={code} msg={msg}")
                try:
                    cache.record_liq_health("disconnect", symbols_subscribed=len(symbols),
                                            note=f"code={code}")
                except Exception:
                    pass

            ws = websocket.WebSocketApp(
                "wss://stream.bybit.com/v5/public/linear",
                on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            ws.run_forever()
            stop_ping.set()
            try:
                cache.prune_old_liquidations()
            except Exception:
                pass
            time.sleep(5)
        except Exception as e:
            agent_log(f"❌ LiquidationTracker loop crash: {type(e).__name__}: {e}")
            time.sleep(5)
