"""
BinanceFetcher - Market Data Provider
======================================
Prioridad de datos:
  1. WebSocket Server local (http://localhost:8001) - SIN rate limits
  2. Binance REST API - Fallback con proteccion anti-ban

El WebSocket Server debe estar corriendo en una terminal separada:
    python market_ws_server.py
"""

import requests
import logging
import time

logger = logging.getLogger("BinanceFetcher")

WS_SERVER_URL = "http://localhost:8001"


class BinanceFetcher:
    """
    Fetches raw market data, prioritizing the local WebSocket cache server
    to avoid Binance REST API rate limits.
    """
    BINANCE_FAPI = "https://fapi.binance.com"
    BINANCE_API  = "https://api.binance.com"

    def __init__(self):
        self.session = requests.Session()
        self.ws_available = None      # None = no chequeado aun
        self.last_ws_check = 0
        self.last_request_time = 0
        self.min_delay = 1.0

    # ─────────────────────────────────────────────────────────────
    # WebSocket Server Local
    # ─────────────────────────────────────────────────────────────

    def _is_ws_server_up(self) -> bool:
        """
        Considera el servidor disponible si tiene historial cargado,
        independientemente de si el WS esta conectado en este instante.
        Re-chequea cada 15s.
        """
        now = time.time()
        if self.ws_available is None or (now - self.last_ws_check) > 15:
            try:
                r = self.session.get(f"{WS_SERVER_URL}/health", timeout=1)
                if r.status_code == 200:
                    data = r.json()
                    # Disponible si tiene historial cargado O si el WS esta conectado
                    has_history = data.get("symbols_history", 0) > 0
                    is_connected = data.get("connected", False)
                    self.ws_available = has_history or is_connected
                else:
                    self.ws_available = False
            except Exception:
                self.ws_available = False
            self.last_ws_check = now
            if self.ws_available:
                logger.debug("[WS] Servidor local disponible.")
            else:
                logger.warning("[WS] Servidor local NO disponible. Usando REST como fallback.")
        return self.ws_available

    def _get_candle_from_ws(self, symbol: str) -> dict | None:
        """Obtiene la ultima vela cacheada del servidor WebSocket local."""
        try:
            r = self.session.get(f"{WS_SERVER_URL}/market/candle/{symbol}", timeout=1)
            if r.status_code == 200:
                return r.json()
        except Exception:
            self.ws_available = False  # Marcar como caido para forzar re-chequeo
        return None

    # ─────────────────────────────────────────────────────────────
    # REST Fallback con proteccion anti-ban
    # ─────────────────────────────────────────────────────────────

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def _make_rest_request(self, method, url, **kwargs):
        """REST request con retry ante rate limits."""
        for attempt in range(3):
            self._wait_for_rate_limit()
            try:
                response = self.session.request(method, url, **kwargs)
                if response.status_code in (429, 418):
                    wait_time = int(response.headers.get("Retry-After", 15))
                    logger.warning(f"[REST] Rate limit Binance. Esperando {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return response
            except Exception as e:
                if attempt == 2:
                    raise e
                time.sleep(1)
        return None

    # ─────────────────────────────────────────────────────────────
    # Interfaz publica
    # ─────────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float:
        """
        Obtiene el precio actual del simbolo.
        - Si WS server esta activo: usa dato en tiempo real. Si el simbolo
          todavia no esta cacheado (seed fallido), espera hasta 5s y devuelve 0
          (el agente saltea ese simbolo en este ciclo, sin tocar REST).
        - Si WS server no esta disponible: usa REST de Binance como fallback.
        """
        if self._is_ws_server_up():
            # Intentar obtener del cache WS
            candle = self._get_candle_from_ws(symbol)
            if candle:
                return float(candle.get("close", 0))

            # El simbolo no esta cacheado todavia (seed fallido, esperando WS)
            # Esperar hasta 5s para que llegue el primer update
            logger.debug(f"[WS] {symbol} no en cache. Esperando hasta 5s por dato en vivo...")
            for _ in range(10):
                time.sleep(0.5)
                candle = self._get_candle_from_ws(symbol)
                if candle:
                    return float(candle.get("close", 0))

            # Si en 5s no llego, saltear (no usar REST, el ban es peor)
            logger.warning(f"[WS] {symbol} sin dato en vivo aun. Saltando este ciclo.")
            return 0.0

        # WS no disponible: usar REST de Binance
        logger.warning(f"[REST] Fallback REST para precio de {symbol}")
        url = f"{self.BINANCE_FAPI}/fapi/v1/premiumIndex"
        try:
            response = self._make_rest_request("GET", url, params={"symbol": symbol}, timeout=5)
            if response and response.status_code == 200:
                return float(response.json().get("markPrice", 0))
        except Exception as e:
            logger.error(f"[REST] Error precio {symbol}: {e}")
        return 0.0

    def get_klines_for_nexus(self, symbol: str, interval: str = "15m", limit: int = 50) -> list:
        """
        Obtiene velas OHLCV para alimentar a Nexus-15.
        1. Si WS server esta up: usa historial del cache local (SIN rate limit).
           Si el simbolo no tiene historial todavia (seed fallido), devuelve []
           para saltear ese simbolo. NUNCA cae a REST mientras WS esta up.
        2. Solo usa REST si el WS server esta completamente caido.
        """
        if self._is_ws_server_up():
            try:
                r = self.session.get(
                    f"{WS_SERVER_URL}/market/candles/{symbol}",
                    timeout=2
                )
                if r.status_code == 200:
                    candles = r.json()
                    return [{
                        "timestamp": c["timestamp"],
                        "open":   float(c["open"]),
                        "high":   float(c["high"]),
                        "low":    float(c["low"]),
                        "close":  float(c["close"]),
                        "volume": float(c["volume"])
                    } for c in candles[-limit:]]
                else:
                    # 404 = seed fallo para este simbolo, WS aun no tiene historial.
                    # Saltear silenciosamente — NO ir a REST (evita el ban).
                    logger.debug(f"[WS] {symbol} sin historial todavia (HTTP {r.status_code}). Saltando.")
                    return []
            except Exception as e:
                self.ws_available = False
                logger.warning(f"[WS] Error consultando historial para {symbol}: {e}")
                return []

        # WS completamente caido: usar REST de Binance como ultimo recurso
        logger.warning(f"[REST] WS server caido. Usando REST para {symbol}.")
        return self._fetch_klines_rest(symbol, interval, limit)

    def _fetch_klines_rest(self, symbol: str, interval: str, limit: int) -> list:
        """Obtiene velas historicas directamente de Binance REST."""
        url = f"{self.BINANCE_FAPI}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            response = self._make_rest_request("GET", url, params=params, timeout=10)
            if response and response.status_code == 200:
                return [{
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k[0] / 1000.0)),
                    "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                    "close": float(k[4]), "volume": float(k[5])
                } for k in response.json()]
            else:
                if response:
                    logger.warning(f"[REST] Klines para {symbol}: {response.text}")
        except Exception as e:
            logger.error(f"[REST] Error klines {symbol}: {e}")
        return []
