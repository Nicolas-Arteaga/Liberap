"""
Caché corta en memoria, compartida entre TODOS los analyzers de este
proceso (FVG, ADN Compression, Arrow Peak, Strike15m, Staircase).

No reemplaza al caché persistente de market-ws (agent/kline_cache.py,
alimentado por WebSocket) — es un colchón liviano y sin persistencia
pensado para absorber ráfagas de scans concurrentes o consecutivos sobre
los mismos símbolos. Si dos herramientas (o dos pasos de una cascada)
piden el mismo symbol+interval dentro de la ventana de TTL, la segunda
usa lo que ya se pidió en vez de volver a golpear Binance.

Este colchón fue lo que faltó el 2026-07-11: 5+ scanners pidiendo velas
de los mismos símbolos volátiles en la misma ventana de segundos,
multiplicando el tráfico real hacia Binance y disparando el bloqueo 418.
"""
import time
import threading
import logging

logger = logging.getLogger("SHARED_KLINE_CACHE")

TTL_SECONDS = 15

_lock = threading.Lock()
_cache: dict = {}  # (symbol, interval, limit) -> (timestamp, data)


def get_or_fetch(symbol: str, interval: str, limit: int, fetch_fn):
    """
    fetch_fn: callable sin argumentos que hace el fetch real (incluyendo
    cualquier fallback futures->spot que ya tenga el analyzer) y devuelve
    la lista de klines, o None/[] en error. Solo se cachean resultados
    no vacíos — un símbolo que falló ahora puede andar en el próximo pedido.
    """
    key = (symbol, interval, limit)
    now = time.time()

    with _lock:
        cached = _cache.get(key)
        if cached and (now - cached[0]) < TTL_SECONDS:
            return cached[1]

    data = fetch_fn()

    if data:
        with _lock:
            _cache[key] = (now, data)
    return data
