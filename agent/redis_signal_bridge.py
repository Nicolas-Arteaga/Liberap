"""
RedisSignalBridge — Puente entre el backend C# y el agente Python vía Redis Pub/Sub.

El backend (MarketScannerService.cs) publica en:
  verge:superscore  →  {symbol, score, direction, regime, estado, timestamp}

Este módulo:
  1. Se conecta al mismo Redis que usa el backend (mismo contenedor 'redis' en docker-compose)
  2. Escucha verge:superscore en un thread daemon separado (no bloquea el agente)
  3. Mantiene un buffer en memoria de señales recientes (TTL configurable, default 15 min)
  4. Expone get_hot_signals(min_score) para que loop_cycle las use como candidatos prioritarios

Garantías de robustez:
  - Si Redis no está disponible al arrancar → el agente continúa normalmente (modo degradado)
  - Si la conexión se cae durante el run → reconnect automático con backoff exponencial
  - Thread es daemon → muere limpiamente cuando el proceso principal termina
  - Todos los accesos al buffer son thread-safe (Lock)
  - No bloquea el loop principal bajo ninguna circunstancia
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("RedisSignalBridge")

# ─────────────────────────────────────────────
# Constantes configurables
# ─────────────────────────────────────────────
REDIS_CHANNEL         = "verge:superscore"
SIGNAL_TTL_SECONDS    = int(900)   # 15 minutos — señales más viejas se descartan
MAX_BUFFER_SIZE       = int(500)   # máx señales en memoria (evita leak)
RECONNECT_BASE_DELAY  = float(2.0) # segundos espera inicial en backoff
RECONNECT_MAX_DELAY   = float(60.0)


class RedisSignalBridge:
    """
    Subscriptor Redis que captura señales del backend C# en tiempo real
    y las pone a disposición del agente como candidatos de alta prioridad.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url       = redis_url
        self._buffer: Dict[str, dict] = {}   # symbol → señal más reciente
        self._lock            = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running         = False
        self._available       = False         # True cuando Redis responde OK
        self._stats           = {"received": 0, "errors": 0, "reconnects": 0}

    # ─────────────────────────────────────────────
    # Ciclo de vida
    # ─────────────────────────────────────────────

    def start(self) -> bool:
        """
        Arranca el thread de escucha en background.
        Retorna True si Redis está disponible, False si no (agente continúa igual).
        """
        try:
            import redis as redis_lib  # type: ignore
            self._redis_lib = redis_lib
        except ImportError:
            logger.warning(
                "[RSB] redis-py no instalado. Ejecutá: pip install redis  "
                "— el agente opera en modo sin bridge."
            )
            return False

        # Prueba rápida de conectividad antes de arrancar el thread
        try:
            test_client = self._redis_lib.from_url(
                self._redis_url, socket_connect_timeout=2, socket_timeout=2
            )
            test_client.ping()
            test_client.close()
            self._available = True
            logger.info("[RSB] ✅ Redis disponible en %s — bridge activo.", self._redis_url)
        except Exception as ex:
            logger.warning(
                "[RSB] ⚠️ Redis no disponible (%s). Bridge desactivado — agente opera normal.",
                ex,
            )
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="RedisSignalBridge",
            daemon=True,   # muere con el proceso principal, sin cleanup manual
        )
        self._thread.start()
        return True

    def stop(self):
        self._running = False

    def is_available(self) -> bool:
        return self._available

    # ─────────────────────────────────────────────
    # Thread de escucha principal
    # ─────────────────────────────────────────────

    def _listen_loop(self):
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                self._subscribe_and_listen()
                delay = RECONNECT_BASE_DELAY  # reset backoff en éxito
            except Exception as ex:
                self._stats["reconnects"] += 1
                logger.warning(
                    "[RSB] Conexión perdida: %s — reconectando en %.0fs (intento #%d)…",
                    ex, delay, self._stats["reconnects"],
                )
                time.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

        logger.info("[RSB] Thread detenido.")

    def _subscribe_and_listen(self):
        client = self._redis_lib.from_url(
            self._redis_url,
            socket_connect_timeout=5,
            socket_timeout=30,
            health_check_interval=15,
            retry_on_timeout=True,
        )
        pubsub = client.pubsub()
        pubsub.subscribe(REDIS_CHANNEL)
        logger.info("[RSB] Subscripto a '%s'. Escuchando señales del backend C#…", REDIS_CHANNEL)

        for message in pubsub.listen():
            if not self._running:
                break
            if message["type"] != "message":
                continue
            self._handle_message(message["data"])

        pubsub.unsubscribe()
        client.close()

    def _handle_message(self, raw):
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            symbol = payload.get("symbol", "").strip().upper()
            score  = float(payload.get("score", 0))
            if not symbol:
                return

            now_utc = datetime.now(timezone.utc).timestamp()
            enriched = {
                "symbol":    symbol,
                "score":     score,
                "direction": payload.get("direction", "Auto"),
                "regime":    payload.get("regime", "Unknown"),
                "estado":    payload.get("estado", "WAIT"),
                "received_at": now_utc,
                "source":    payload.get("source", "redis_bridge"),
                "nexus15":   payload.get("nexus15", score),
                "estimatedRangePercent": payload.get("estimatedRangePercent", 0.0),
                "features":  payload.get("features", {}),
                "groupScores": payload.get("groupScores", {})
            }

            with self._lock:
                self._buffer[symbol] = enriched
                # Trim si crece demasiado (FIFO por símbolo, no hace falta más)
                if len(self._buffer) > MAX_BUFFER_SIZE:
                    oldest = min(self._buffer.values(), key=lambda x: x["received_at"])
                    self._buffer.pop(oldest["symbol"], None)

            self._stats["received"] += 1
            logger.debug("[RSB] 📥 %s score=%.0f dir=%s", symbol, score, enriched["direction"])

        except Exception as ex:
            self._stats["errors"] += 1
            logger.debug("[RSB] Error procesando mensaje: %s", ex)

    # ─────────────────────────────────────────────
    # API pública para el agente
    # ─────────────────────────────────────────────

    def get_hot_signals(
        self,
        min_score: float = 45.0,
        max_age_seconds: float = SIGNAL_TTL_SECONDS,
    ) -> List[dict]:
        """
        Retorna señales recientes del backend C# que superan min_score.
        Descarta automáticamente señales más viejas que max_age_seconds.
        Thread-safe. Nunca lanza excepciones.
        """
        if not self._available:
            return []
        try:
            now = datetime.now(timezone.utc).timestamp()
            cutoff = now - max_age_seconds
            with self._lock:
                hot = [
                    s for s in self._buffer.values()
                    if s["score"] >= min_score and s["received_at"] >= cutoff
                ]
            # Ordenar de mayor a menor score
            hot.sort(key=lambda x: x["score"], reverse=True)
            return hot
        except Exception as ex:
            logger.warning("[RSB] Error en get_hot_signals: %s", ex)
            return []

    def purge_expired(self):
        """Limpia señales viejas del buffer (llamado opcionalmente cada ciclo)."""
        if not self._available:
            return
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - SIGNAL_TTL_SECONDS
            with self._lock:
                expired = [s for s, v in self._buffer.items() if v["received_at"] < cutoff]
                for s in expired:
                    del self._buffer[s]
            if expired:
                logger.debug("[RSB] Purged %d señales expiradas.", len(expired))
        except Exception:
            pass

    def stats(self) -> dict:
        return {**self._stats, "buffer_size": len(self._buffer)}
