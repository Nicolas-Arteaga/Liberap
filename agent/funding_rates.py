"""
FundingRates — Captura de Funding Rate (Binance Futures)
=========================================================
A diferencia de order book (orderbook_ws.py, WS persistente porque necesita
resolución de milisegundos), el funding rate solo cambia una vez cada ~8h
por símbolo — un WS dedicado sería sobre-ingeniería. Se usa REST de muy baja
frecuencia (una pasada por TIER1 cada FUNDING_POLL_INTERVAL_S), reusando el
circuit breaker compartido para no repetir el problema de baneo de esta
sesión (ver circuit_breaker.py).

Nota (2026-07-17): se intentó primero el WS de markPrice (`<symbol>@markPrice`,
que trae funding en vivo) para reusar la misma infraestructura que order
book, pero se verificó en vivo contra fstream.binance.com que este entorno
solo recibe mensajes del canal @depth — markPrice/kline/aggTrade/ticker se
conectan (handshake OK) pero nunca entregan datos, probablemente resabio de
los baneos 418 de sesiones anteriores. REST de baja frecuencia es la opción
robusta disponible ahora; si el WS se normaliza más adelante, migrar es
directo (mismo cache de destino).

Endpoint: GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=X&limit=30
Respuesta: [{"symbol":"BTCUSDT","fundingTime":1597370400000,"fundingRate":"-0.00072700",...}, ...]
"""

import time
import logging

logger = logging.getLogger("FundingRates")

FUNDING_MIN_PERIODS = 30            # spec: al menos 30 períodos históricos
FUNDING_POLL_INTERVAL_S = 2 * 3600  # cada 2h alcanza de sobra (funding real cambia cada 8h)
FUNDING_REST_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def parse_funding_response(raw: list) -> list:
    """
    Convierte la respuesta cruda de Binance a records {funding_time, funding_rate}.
    Filtra entradas mal formadas en vez de fallar todo el batch.
    """
    result = []
    for r in (raw or []):
        try:
            result.append({
                "funding_time": int(r["fundingTime"]),
                "funding_rate": float(r["fundingRate"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return result


def fetch_funding_history(symbol: str, limit: int = FUNDING_MIN_PERIODS, timeout: float = 8.0):
    """
    Un solo REST call. Devuelve lista de records o [] si falla — nunca
    lanza, el caller decide qué hacer con una lista vacía (reintenta en el
    próximo ciclo, no bloquea el resto de símbolos).
    """
    import requests
    try:
        resp = requests.get(FUNDING_REST_URL, params={"symbol": symbol, "limit": limit}, timeout=timeout)
        if resp.status_code == 200:
            return parse_funding_response(resp.json())
        return None  # señal de fallo real (429/418/5xx) — distinto de "sin datos"
    except Exception as e:
        logger.debug(f"[FundingRates] {symbol}: fetch falló ({type(e).__name__}: {e})")
        return None


def funding_pressure_hint(symbol: str):
    """
    Heurística simple — NO un modelo entrenado. Este proyecto ya tiene un
    antecedente de "parece una señal real pero no lo es" (XGBoost de
    Nexus-15 nunca entrenado, quedaba en g6=0.5 fijo sin decirlo; ver
    memoria verge_2026_2040) — esto está escrito para no repetirlo: combina
    el signo del OFI en vivo con el signo del funding vigente para señalar
    si la presión de order flow va en la MISMA dirección que el funding
    (probable continuación) o en contra (probable reversión de esa presión).
    No es una predicción numérica del próximo funding — eso requeriría un
    modelo real (spec: "estimar la dirección probable", no el valor).
    Devuelve None si falta OFI o funding para el símbolo.
    """
    from kline_cache import get_cache
    cache = get_cache()
    ofi_row = cache.get_latest_ofi(symbol)
    funding_row = cache.get_latest_funding(symbol)
    if ofi_row is None or funding_row is None:
        return None
    ofi = ofi_row["ofi"]
    funding = funding_row["funding_rate"]
    aligned = None if (abs(ofi) < 0.05 or abs(funding) < 1e-6) else ((ofi > 0) == (funding > 0))
    return {"ofi": ofi, "funding_rate": funding, "aligned_with_funding": aligned}


def run_funding_capture(agent_log=print):
    """
    Loop principal — pensado para correr en su propio thread daemon. Cada
    FUNDING_POLL_INTERVAL_S, re-backfillea los últimos FUNDING_MIN_PERIODS
    períodos para cada símbolo de config.WATCHLIST_TIER1 (idempotente vía
    upsert, así que repetir no duplica). Usa el circuit breaker de binance
    ya existente — si está abierto (baneo/cuarentena), no golpea la API y
    reintenta en el próximo ciclo.
    """
    import config
    from kline_cache import get_cache
    from circuit_breaker import get_breaker

    cache = get_cache()
    breaker = get_breaker("binance")

    while True:
        try:
            try:
                config.refresh_watchlist()
            except Exception as e:
                agent_log(f"⚠️ FundingRates: refresh_watchlist falló ({type(e).__name__}: {e}), sigo con el watchlist actual.")
            symbols = list(config.WATCHLIST_TIER1)

            fetched, skipped, failed = 0, 0, 0
            for symbol in symbols:
                if not breaker.is_available:
                    skipped += 1
                    continue
                records = fetch_funding_history(symbol)
                if records is None:
                    breaker.record_failure()
                    failed += 1
                    continue
                breaker.record_success()
                if records:
                    cache.bulk_upsert_funding(symbol, records)
                    fetched += 1
                time.sleep(0.2)  # separa las llamadas — 30 símbolos en ~6s, nada agresivo

            agent_log(f"💰 FundingRates: ciclo completo — {fetched} símbolos actualizados, "
                      f"{skipped} saltados (breaker abierto), {failed} fallidos.")
        except Exception as e:
            agent_log(f"❌ FundingRates loop crash: {type(e).__name__}: {e}")

        time.sleep(FUNDING_POLL_INTERVAL_S)
