"""
OpenInterestCollector — Captura histórica de Open Interest (TRACK A, post-H9 2026-09-02)
======================================================================================
ESTO ES DATA COLLECTION, NO ESTRATEGIA. Nada de producción lee `open_interest`
todavía. El objetivo es acumular una serie limpia desde ahora para poder testear
más adelante si el OI contiene información incremental (hipótesis futura, aún sin
definir).

Mismo patrón robusto que `funding_rates.py`: REST de baja frecuencia + circuit
breaker compartido de Binance (si está en cuarentena por un 418, no golpea la API
y reintenta el próximo ciclo). Sin WebSocket: el OI histórico de Binance sólo se
publica en buckets de 5m, un WS sería sobre-ingeniería.

────────────────────────────────────────────────────────────────────────────────
FUENTE
  GET https://fapi.binance.com/futures/data/openInterestHist
      ?symbol=<S>&period=5m&limit=<N>[&startTime=<ms>&endTime=<ms>]
  Respuesta: [{"symbol","sumOpenInterest","sumOpenInterestValue","timestamp"}, ...]
    - sumOpenInterest       -> OI en unidades base (coin/contratos)   -> col open_interest
    - sumOpenInterestValue  -> OI en notional USDT                    -> col open_interest_value
    - timestamp             -> ms UTC, alineado al bucket de 5m
  Sin auth. RETENCIÓN DE LA FUENTE: SÓLO LOS ÚLTIMOS ~30 DÍAS. Por eso este
  collector tiene que correr de forma continua desde ya — lo que no capturemos
  ahora se pierde para siempre.

  Snapshot en vivo (no usado por defecto, disponible como fallback):
  GET /fapi/v1/openInterest?symbol=<S>  -> {"openInterest","symbol","time"}  (weight 1)

FRECUENCIA
  - Backfill inicial: pagina hacia atrás hasta ~30 días (BACKFILL_DAYS), limit 500
    por request (~41 h de datos 5m c/u), ~15 requests/símbolo. Idempotente: volver
    a correrlo sólo rellena huecos.
  - Régimen permanente: cada POLL_INTERVAL_S (300 s) trae los últimos RECENT_LIMIT
    buckets (1 h) por símbolo — captura el bucket nuevo + tapa huecos cortos.

RATE LIMITS
  Los endpoints /futures/data/* de Binance tienen límite POR IP (no el
  X-MBX-USED-WEIGHT de /fapi/*). Doc oficial: ~1000 req / 5 min por IP. Acá se
  usa MUY por debajo: SLEEP_BETWEEN_CALLS_S=0.35 → ~30 símbolos en ~11 s por ciclo
  de 5 min. El circuit breaker de Binance frena todo ante un 418/429.

RETENCIÓN LOCAL
  prune_old_open_interest(keep_days=400) — a propósito alto: el punto es acumular
  historia. 5m × 100 símbolos × 400 d ≈ 11.5 M filas, manejable con el índice.

DETECCIÓN DE HUECOS / CALIDAD
  cache.open_interest_gaps(symbol) devuelve rows/expected/missing/coverage_pct.
  El loop loguea la cobertura peor cada ciclo. Un símbolo con coverage < 95 %
  sostenido = revisar (símbolo delisted, o la fuente no lo tiene).

NORMALIZACIÓN
  Se guarda el dato CRUDO tal cual lo da el exchange (base + notional USDT).
  Los derivados —ΔOI, %ΔOI, OI/volumen, z-score— se calculan al LEER, de forma
  causal, y NUNCA se persisten. Así un bug de cálculo no contamina la serie ni
  introduce lookahead retroactivo.

LOOKAHEAD / TIMESTAMPS — cómo se garantiza que el collector no los rompe
  1. El collector SÓLO escribe buckets ya cerrados que la API ya publicó. No
     inventa timestamps: usa el `timestamp` que devuelve Binance, verificado
     alineado a 300000 ms (assert en _parse). Un registro con timestamp no
     alineado se descarta y se loguea (posible cambio de esquema de la fuente).
  2. El collector nunca escribe un bucket con timestamp > now. _parse filtra
     `ts <= now_ms - PERIOD_MS` (el bucket actual todavía se está formando en la
     fuente; se toma recién cuando cerró).
  3. La lectura causal es responsabilidad del consumidor: usar
     `cache.get_open_interest_history(symbol, before_ms=t)` (devuelve sólo
     timestamp <= t) y, para no usar el bucket que aún se formaba en `t`, pedir
     `before_ms = t - PERIOD_MS`. Documentado también en kline_cache.py.
  4. `updated_at` (wall-clock de escritura) se guarda aparte SÓLO para auditar el
     lag de captura; nunca se usa como eje temporal.

AMPLIAR A OTROS EXCHANGES (bybit/okx/bitget) — deliberadamente NO hecho en v1
  El esquema ya tiene la columna `exchange`. Sumar bybit = agregar un
  `fetch_bybit_oi_history()` (GET /v5/market/open-interest, category=linear,
  intervalTime=5min) y llamarlo en el loop con exchange="bybit". Prioridad
  ahora: cobertura + calidad + persistencia de UNA fuente (Binance Futures, que
  es donde opera el agente), no 4 a medias.
────────────────────────────────────────────────────────────────────────────────
"""
import os
import json
import time
import logging

logger = logging.getLogger("OpenInterest")

# ── Universo de research (EX-ANTE, ver research/universe/build_oi_universe.py) ──
# Se lee de research/universe/oi_universe.json. Si no existe, fallback a
# WATCHLIST_TIER1 + BTC/ETH/SOL forzados. NUNCA se seleccionan simbolos por
# resultados de H13 — el archivo lo genera un script con criterio de liquidez.
_UNIVERSE_JSON = os.path.join(os.path.dirname(__file__), "..", "research", "universe", "oi_universe.json")
TIER0 = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def load_research_universe(fallback_watchlist=None) -> list:
    try:
        with open(_UNIVERSE_JSON) as f:
            u = json.load(f).get("universe") or []
        if u:
            # Tier 0 siempre primero y siempre presente
            seen = set()
            out = [s for s in TIER0 + list(u) if not (s in seen or seen.add(s))]
            return out
    except Exception as e:
        logger.warning("[OI] no pude leer %s (%s) — uso fallback", _UNIVERSE_JSON, type(e).__name__)
    fb = list(fallback_watchlist or [])
    seen = set()
    return [s for s in TIER0 + fb if not (s in seen or seen.add(s))]

OI_REST_URL          = "https://fapi.binance.com/futures/data/openInterestHist"
PERIOD               = "5m"
PERIOD_MS            = 300_000
# Tope de la fuente = 30 d. Se puede ACOTAR por env para un reinicio suave
# (menos requests de golpe cuando el agente live comparte IP): OI_BACKFILL_DAYS=7.
# 0 = saltear el backfill (los simbolos nuevos se llenan solo hacia adelante).
BACKFILL_DAYS        = int(os.getenv("OI_BACKFILL_DAYS", "30"))
BACKFILL_PAGE_LIMIT  = 500          # máximo del endpoint
RECENT_LIMIT         = 12           # 1 h de buckets por ciclo en régimen permanente
POLL_INTERVAL_S      = 300
SLEEP_BETWEEN_CALLS_S = 0.35
PRUNE_EVERY_CYCLES   = 288          # ~1 vez por día
HTTP_TIMEOUT_S       = 8.0


def _parse(raw: list, now_ms: int) -> list:
    """Cruda -> [{timestamp, open_interest, open_interest_value}]. Descarta:
       - registros mal formados,
       - timestamps no alineados a PERIOD_MS (posible cambio de esquema),
       - el bucket que todavía se está formando (ts > now_ms - PERIOD_MS)."""
    out = []
    for r in (raw or []):
        try:
            ts = int(r["timestamp"])
            if ts % PERIOD_MS != 0:
                logger.warning("[OI] timestamp no alineado a %dms: %s — descartado", PERIOD_MS, ts)
                continue
            if ts > now_ms - PERIOD_MS:
                continue  # bucket en formación
            oi = float(r["sumOpenInterest"])
            oiv = r.get("sumOpenInterestValue")
            out.append({
                "timestamp": ts,
                "open_interest": oi,
                "open_interest_value": (float(oiv) if oiv not in (None, "") else None),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _get(session, params: dict):
    """Un GET. Devuelve (list|None). None = fallo real (429/418/5xx/timeout) para
    que el caller avise al circuit breaker. [] = respuesta OK sin datos."""
    try:
        resp = session.get(OI_REST_URL, params=params, timeout=HTTP_TIMEOUT_S)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        logger.debug("[OI] HTTP %s para %s", resp.status_code, params.get("symbol"))
        return None
    except Exception as e:
        logger.debug("[OI] fetch %s falló: %s", params.get("symbol"), type(e).__name__)
        return None


def fetch_recent(session, symbol: str, limit: int = RECENT_LIMIT):
    now_ms = int(time.time() * 1000)
    raw = _get(session, {"symbol": symbol, "period": PERIOD, "limit": limit})
    return None if raw is None else _parse(raw, now_ms)


def backfill_symbol(session, cache, symbol: str, breaker) -> int:
    """Pagina hacia atrás hasta BACKFILL_DAYS. Idempotente (upsert). Devuelve
    filas escritas. Se corta ante breaker abierto o fallo."""
    now_ms = int(time.time() * 1000)
    end_ms = now_ms
    floor_ms = now_ms - BACKFILL_DAYS * 86_400_000
    written = 0
    for _ in range(20):  # 20 páginas de 500 × 5m ≈ 34.7 días — cubre el tope de 30
        if not breaker.is_available:
            break
        start_ms = max(floor_ms, end_ms - BACKFILL_PAGE_LIMIT * PERIOD_MS)
        raw = _get(session, {"symbol": symbol, "period": PERIOD,
                             "startTime": start_ms, "endTime": end_ms,
                             "limit": BACKFILL_PAGE_LIMIT})
        if raw is None:
            breaker.record_failure()
            break
        breaker.record_success()
        recs = _parse(raw, now_ms)
        if not recs:
            break
        cache.bulk_upsert_open_interest(symbol, recs, exchange="binance", period=PERIOD)
        written += len(recs)
        oldest = min(r["timestamp"] for r in recs)
        if oldest <= floor_ms + PERIOD_MS:
            break
        end_ms = oldest - PERIOD_MS
        time.sleep(SLEEP_BETWEEN_CALLS_S)
    return written


def run_oi_capture(agent_log=print):
    """Loop principal — pensado para su propio thread daemon o proceso standalone."""
    import requests
    import config
    from kline_cache import get_cache
    try:
        from circuit_breaker import get_breaker
        breaker = get_breaker("binance")
    except Exception:
        from circuit_breaker import get_breakers
        breaker = get_breakers()["binance"]

    cache = get_cache()
    session = requests.Session()
    session.headers.update({"User-Agent": "verge-oi-collector/1"})

    # ── Backfill inicial (una vez por arranque; idempotente) ──
    try:
        config.refresh_watchlist()
    except Exception as e:
        agent_log(f"⚠️ OI: refresh_watchlist falló ({type(e).__name__}), uso watchlist actual.")
    symbols = load_research_universe(getattr(config, 'WATCHLIST_TIER1', []))
    if BACKFILL_DAYS <= 0:
        agent_log(f"📊 OI collector: backfill DESACTIVADO (OI_BACKFILL_DAYS={BACKFILL_DAYS}); "
                  f"{len(symbols)} símbolos se llenan hacia adelante.")
    else:
        agent_log(f"📊 OI collector: backfill inicial de {len(symbols)} símbolos (hasta {BACKFILL_DAYS}d)...")
        total_bf = 0
        for sym in symbols:
            if not breaker.is_available:
                agent_log("📊 OI: breaker abierto durante backfill — se completa en régimen permanente.")
                break
            total_bf += backfill_symbol(session, cache, sym, breaker)
            time.sleep(SLEEP_BETWEEN_CALLS_S)
        agent_log(f"📊 OI: backfill inicial listo — {total_bf} filas.")

    cycle = 0
    while True:
        cycle += 1
        try:
            try:
                config.refresh_watchlist()
            except Exception:
                pass
            symbols = load_research_universe(getattr(config, 'WATCHLIST_TIER1', []))
            fetched = skipped = failed = 0
            worst = None
            for sym in symbols:
                if not breaker.is_available:
                    skipped += 1
                    continue
                recs = fetch_recent(session, sym)
                if recs is None:
                    breaker.record_failure()
                    failed += 1
                    continue
                breaker.record_success()
                if recs:
                    cache.bulk_upsert_open_interest(sym, recs, exchange="binance", period=PERIOD)
                    fetched += 1
                g = cache.open_interest_gaps(sym, period_ms=PERIOD_MS)
                if g["coverage_pct"] is not None and (worst is None or g["coverage_pct"] < worst[1]):
                    worst = (sym, g["coverage_pct"], g["rows"])
                time.sleep(SLEEP_BETWEEN_CALLS_S)

            msg = (f"📊 OI ciclo {cycle}: {fetched} actualizados, {skipped} saltados "
                   f"(breaker), {failed} fallidos")
            if worst:
                msg += f" | peor cobertura: {worst[0]} {worst[1]:.1f}% ({worst[2]} filas)"
            agent_log(msg)

            if cycle % PRUNE_EVERY_CYCLES == 0:
                cache.prune_old_open_interest(keep_days=400)
        except Exception as e:
            agent_log(f"❌ OI loop crash: {type(e).__name__}: {e}")

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    # usar logger.info (con flush) y NO print — print a un archivo redirigido queda
    # block-buffered y no se ve el progreso hasta que muere el proceso.
    run_oi_capture(agent_log=logger.info)
