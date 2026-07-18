"""
WhaleTracker — On-chain whale tracking, 100% gratis (sin proveedor pago)
=========================================================================
Reemplaza el widget de "ballenas" del dashboard, que hasta ahora era
keyword-matching sobre texto de alertas (si el mensaje decía "ballena" o
"whale", devolvía un score fijo de 65 — nunca dato real, ver PROGRESS_LOG
2026-07-15/16 y memoria verge_2026_2040).

Cobertura REAL, honesta (spec 4.3: nunca inventar el dato si la fuente no
está disponible):

- **BTCUSDT**: SIEMPRE activo. WS público de blockchain.info
  (`wss://ws.blockchain.info/inv`), gratis, sin cuenta ni API key —
  verificado en vivo (60 mensajes/8s). Transacciones on-chain reales por
  encima de WHALE_THRESHOLD_BTC se registran como eventos ballena.

- **Tokens ERC-20**: opt-in vía ETHERSCAN_API_KEY (variable de entorno, free
  tier de Etherscan — 3 req/s, 100k/día, activado 2026-07-17). Etherscan dio
  de baja su API V1 (keyless); la V2 exige una cuenta/API key gratuita que
  el usuario generó él mismo. Si la variable no está seteada, esta fuente
  queda simplemente inactiva — get_whale_activity() devuelve None para
  esos símbolos (spec 4.5: badge de "no disponible", nunca un score falso).

  Diseño: en vez de mapear símbolo→contrato (frágil, habría que mantener a
  mano decenas de direcciones de contrato), se monitorea UNA wallet caliente
  de Binance verificada en vivo (`0xF977814e90dA44bFA03b6295A0616a897441aceC`
  — balance real ~740k ETH al verificar, movimientos diarios de docenas de
  tokens distintos) vía `tokentx` SIN filtro de contrato: cualquier token
  que se mueva por esa wallet y cuyo symbol coincida con algo del watchlist
  (ej. "PENDLE" → "PENDLEUSDT") se registra. Una sola consulta cubre
  potencialmente decenas de símbolos del watchlist, no una consulta por
  símbolo — evita golpear la API de más. Limitación conocida: `tokenSymbol`
  es metadata del contrato, no verificado por Etherscan — un token scam
  podría reusar un symbol conocido; el riesgo se acepta igual que las demás
  señales de este epic (features/filtros opcionales, nunca la única fuente
  de una decisión).

No hay proveedor de pago en ningún camino de este módulo.
"""

import os
import time
import logging

logger = logging.getLogger("WhaleTracker")

WHALE_THRESHOLD_BTC = 10.0  # transferencia on-chain >= 10 BTC (~ varios cientos de miles de USD)
PRUNE_INTERVAL_S = 3600

# Wallet caliente de Binance verificada en vivo (2026-07-17) — ver nota arriba.
MONITORED_ERC20_WALLET = "0xF977814e90dA44bFA03b6295A0616a897441aceC"
ERC20_POLL_INTERVAL_S = 15 * 60  # 15 min — de sobra, muy por debajo del free tier de Etherscan
STABLECOIN_SYMBOLS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDE"}  # no tiene sentido "USDTUSDT"


def _tx_total_btc(tx: dict) -> float:
    """Suma los outputs de una tx de blockchain.info (satoshis -> BTC)."""
    outputs = tx.get("out") or []
    total_sat = sum(int(o.get("value", 0)) for o in outputs)
    return total_sat / 1e8


def run_btc_whale_capture(agent_log=print):
    """
    Loop principal — pensado para correr en su propio thread daemon. WS
    público (sin auth) de blockchain.info, se reconecta solo, mismo patrón
    de reconexión que orderbook_ws.py/market_ws_server.py.
    """
    import websocket
    import json as pyjson
    from kline_cache import get_cache

    cache = get_cache()
    last_prune = [0.0]

    while True:
        try:
            stats = {"txs": 0, "whales": 0}
            last_report = [time.time()]

            def on_open(ws):
                ws.send(pyjson.dumps({"op": "unconfirmed_sub"}))
                agent_log("🐋 WhaleTracker (BTC) conectado a blockchain.info.")

            def on_message(ws, msg):
                stats["txs"] += 1
                try:
                    data = pyjson.loads(msg)
                    tx = data.get("x") or {}
                    total_btc = _tx_total_btc(tx)
                    if total_btc >= WHALE_THRESHOLD_BTC:
                        cache.insert_whale_event("BTCUSDT", total_btc, "onchain_btc", tx.get("hash"))
                        stats["whales"] += 1
                except Exception as e:
                    if stats["txs"] <= 3:
                        agent_log(f"⚠️ WhaleTracker on_message error: {type(e).__name__}: {e}")

                now = time.time()
                if now - last_report[0] > 300:
                    agent_log(f"🐋 WhaleTracker: {stats['txs']} txs vistas / 5min, {stats['whales']} ballenas (>={WHALE_THRESHOLD_BTC} BTC).")
                    stats.update(txs=0, whales=0)
                    last_report[0] = now
                if now - last_prune[0] > PRUNE_INTERVAL_S:
                    try:
                        cache.prune_old_whale_events()
                    except Exception:
                        pass
                    last_prune[0] = now

            def on_error(ws, err):
                agent_log(f"❌ WhaleTracker WS error: {type(err).__name__}: {err}")

            def on_close(ws, code, msg):
                agent_log(f"🔌 WhaleTracker WS cerrado. code={code} msg={msg}")

            ws = websocket.WebSocketApp(
                "wss://ws.blockchain.info/inv",
                on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            ws.run_forever()
            time.sleep(5)
        except Exception as e:
            agent_log(f"❌ WhaleTracker loop crash: {type(e).__name__}: {e}")
            time.sleep(5)


def fetch_erc20_transfers(wallet: str, api_key: str, offset: int = 30, timeout: float = 10.0):
    """
    Un solo REST call a Etherscan V2 (`tokentx`, sin contractaddress) —
    trae los últimos `offset` movimientos de TODOS los tokens de la wallet
    monitoreada. Devuelve None si falla (nunca lanza), [] si no hay nada.
    """
    import requests
    try:
        resp = requests.get("https://api.etherscan.io/v2/api", params={
            "chainid": 1, "module": "account", "action": "tokentx",
            "address": wallet, "page": 1, "offset": offset, "sort": "desc",
            "apikey": api_key,
        }, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return data["result"]
        if data.get("message") == "No transactions found":
            return []
        return None  # error real (rate limit, key inválida, etc.)
    except Exception as e:
        logger.debug(f"[WhaleTracker] ERC20 fetch falló: {type(e).__name__}: {e}")
        return None


def run_erc20_whale_capture(agent_log=print):
    """
    Loop principal — thread daemon separado del de BTC. No-op silencioso
    (loguea una sola vez y no reintenta el REST) si ETHERSCAN_API_KEY no
    está configurada — spec 4.3, nunca fallar ruidosamente por una fuente
    opcional ausente.
    """
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        agent_log("🐋 WhaleTracker (ERC-20): ETHERSCAN_API_KEY no configurada — fuente inactiva (BTCUSDT sigue cubierto vía blockchain.info).")
        return

    import config
    from kline_cache import get_cache
    cache = get_cache()

    agent_log("🐋 WhaleTracker (ERC-20) activo — monitoreando wallet Binance vía Etherscan.")
    while True:
        try:
            watchlist = set(getattr(config, "WATCHLIST", []))
            records = fetch_erc20_transfers(MONITORED_ERC20_WALLET, api_key)
            matched, skipped = 0, 0
            if records:
                for tx in records:
                    tx_hash = tx.get("hash")
                    if cache.has_whale_tx(tx_hash):
                        continue
                    token_symbol = (tx.get("tokenSymbol") or "").upper()
                    if not token_symbol or token_symbol in STABLECOIN_SYMBOLS:
                        continue
                    candidate_symbol = f"{token_symbol}USDT"
                    if candidate_symbol not in watchlist:
                        skipped += 1
                        continue
                    try:
                        decimals = int(tx.get("tokenDecimal", 18) or 18)
                        amount = float(tx.get("value", 0)) / (10 ** decimals)
                    except (TypeError, ValueError):
                        continue
                    cache.insert_whale_event(candidate_symbol, amount, "onchain_erc20", tx_hash)
                    matched += 1
            elif records is None:
                agent_log("⚠️ WhaleTracker (ERC-20): fetch falló este ciclo (rate limit/red) — reintento en el próximo.")

            if matched or skipped:
                agent_log(f"🐋 WhaleTracker (ERC-20): {matched} eventos nuevos registrados, {skipped} tokens fuera del watchlist.")
            try:
                cache.prune_old_whale_events()
            except Exception:
                pass
        except Exception as e:
            agent_log(f"❌ WhaleTracker (ERC-20) loop crash: {type(e).__name__}: {e}")

        time.sleep(ERC20_POLL_INTERVAL_S)
