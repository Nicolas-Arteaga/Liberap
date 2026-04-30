"""
ExchangeRegistry — Multi-Exchange Configuration
================================================
Defines WS endpoints, REST endpoints, symbol converters, and message parsers
for each supported exchange.

Canonical symbol format: "BTCUSDT" (Binance-style, no hyphens, no separators).

To add a new exchange:
  1. Write symbol converters (to/from canonical)
  2. Write WS URL builder and subscribe function
  3. Write message parser
  4. Write REST kline params + parser
  5. Add an ExchangeConfig entry in EXCHANGES dict
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any

logger = logging.getLogger("ExchangeRegistry")


# ─────────────────────────────────────────────────────────────
# Symbol converters
# ─────────────────────────────────────────────────────────────

def _to_okx(symbol: str) -> str:
    """BTCUSDT → BTC-USDT-SWAP"""
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}-USDT-SWAP"
    return symbol


def _from_okx(symbol: str) -> str:
    """BTC-USDT-SWAP → BTCUSDT"""
    if symbol.endswith("-USDT-SWAP"):
        return symbol[:-10] + "USDT"
    return symbol


def _identity(symbol: str) -> str:
    """Binance, Bybit, Bitget all use BTCUSDT format for USDT-M futures."""
    return symbol


# ─────────────────────────────────────────────────────────────
# WebSocket message parsers
# Each returns a normalized dict or None if message is irrelevant
# ─────────────────────────────────────────────────────────────

def _parse_binance(data: dict) -> Optional[dict]:
    """Combined stream: {data: {e: 'kline', k: {...}}}"""
    inner = data.get("data", {})
    if inner.get("e") != "kline":
        return None
    k = inner["k"]
    return {
        "symbol":    k["s"].upper(),
        "open":      float(k["o"]),
        "high":      float(k["h"]),
        "low":       float(k["l"]),
        "close":     float(k["c"]),
        "volume":    float(k["v"]),
        "open_time": int(k["t"]),
        "is_final":  bool(k.get("x", False)),
    }


def _parse_bybit(data: dict) -> Optional[dict]:
    """
    Bybit v5: {topic: "kline.15.BTCUSDT", data: [{start, open, high, low, close, volume, confirm}]}
    """
    topic = data.get("topic", "")
    if not topic.startswith("kline."):
        return None
    parts = topic.split(".")          # ["kline", "15", "BTCUSDT"]
    if len(parts) < 3:
        return None
    symbol = parts[2]                 # Already canonical
    recs = data.get("data", [])
    if not recs:
        return None
    k = recs[0]
    return {
        "symbol":    symbol,
        "open":      float(k.get("open",   0)),
        "high":      float(k.get("high",   0)),
        "low":       float(k.get("low",    0)),
        "close":     float(k.get("close",  0)),
        "volume":    float(k.get("volume", 0)),
        "open_time": int(k.get("start",    0)),
        "is_final":  bool(k.get("confirm", False)),
    }


def _parse_okx(data: dict) -> Optional[dict]:
    """
    OKX v5: {arg: {channel:"candle15m", instId:"BTC-USDT-SWAP"}, data: [[ts,o,h,l,c,vol,...,confirm]]}
    """
    if data.get("event"):
        return None    # Subscription confirmation — ignore
    arg = data.get("arg", {})
    if not arg.get("channel", "").startswith("candle"):
        return None
    symbol   = _from_okx(arg.get("instId", ""))
    recs     = data.get("data", [])
    if not recs:
        return None
    k        = recs[0]
    is_final = len(k) > 8 and k[8] == "1"
    return {
        "symbol":    symbol,
        "open":      float(k[1]),
        "high":      float(k[2]),
        "low":       float(k[3]),
        "close":     float(k[4]),
        "volume":    float(k[5]),
        "open_time": int(k[0]),
        "is_final":  is_final,
    }


def _parse_bitget(data: dict) -> Optional[dict]:
    """
    Bitget v2: {arg:{channel:"candle15m",instId:"BTCUSDT"}, data:[[ts,o,h,l,c,vol]]}
    """
    if data.get("event"):
        return None
    arg = data.get("arg", {})
    if not arg.get("channel", "").startswith("candle"):
        return None
    symbol = arg.get("instId", "")
    recs   = data.get("data", [])
    if not recs:
        return None
    k = recs[0]
    return {
        "symbol":    symbol,
        "open":      float(k[1]),
        "high":      float(k[2]),
        "low":       float(k[3]),
        "close":     float(k[4]),
        "volume":    float(k[5]) if len(k) > 5 else 0.0,
        "open_time": int(k[0]),
        "is_final":  False,   # Bitget doesn't expose a reliable confirm flag here
    }


# ─────────────────────────────────────────────────────────────
# WS subscribe helpers
# ─────────────────────────────────────────────────────────────

def _subscribe_bybit(ws, symbols: List[str]):
    topics = [f"kline.15.{s}" for s in symbols]
    for i in range(0, len(topics), 10):
        ws.send(json.dumps({"op": "subscribe", "args": topics[i:i+10]}))
        time.sleep(0.05)


def _subscribe_okx(ws, symbols: List[str]):
    args = [{"channel": "candle15m", "instId": _to_okx(s)} for s in symbols]
    for i in range(0, len(args), 100):
        ws.send(json.dumps({"op": "subscribe", "args": args[i:i+100]}))
        time.sleep(0.1)


def _subscribe_bitget(ws, symbols: List[str]):
    args = [{"instType": "USDT-FUTURES", "channel": "candle15m", "instId": s} for s in symbols]
    for i in range(0, len(args), 50):
        ws.send(json.dumps({"op": "subscribe", "args": args[i:i+50]}))
        time.sleep(0.1)


# ─────────────────────────────────────────────────────────────
# REST kline parsers (return list of normalized kline dicts)
# ─────────────────────────────────────────────────────────────

def _rest_parse_binance(raw) -> list:
    result = []
    for k in (raw or []):
        try:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]), "high": float(k[2]),
                "low":   float(k[3]), "close": float(k[4]),
                "volume": float(k[5]), "is_final": True,
            })
        except Exception:
            pass
    return result


def _rest_parse_bybit(raw) -> list:
    result = []
    records = raw.get("result", {}).get("list", []) if isinstance(raw, dict) else []
    for k in reversed(records):   # Bybit returns newest first
        try:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]), "high": float(k[2]),
                "low":   float(k[3]), "close": float(k[4]),
                "volume": float(k[5]), "is_final": True,
            })
        except Exception:
            pass
    return result


def _rest_parse_okx(raw) -> list:
    result = []
    records = raw.get("data", []) if isinstance(raw, dict) else []
    for k in reversed(records):   # OKX returns newest first
        try:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]), "high": float(k[2]),
                "low":   float(k[3]), "close": float(k[4]),
                "volume": float(k[5]), "is_final": True,
            })
        except Exception:
            pass
    return result


def _rest_parse_bitget(raw) -> list:
    result = []
    records = raw.get("data", []) if isinstance(raw, dict) else []
    for k in records:
        try:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]), "high": float(k[2]),
                "low":   float(k[3]), "close": float(k[4]),
                "volume": float(k[5]) if len(k) > 5 else 0.0,
                "is_final": True,
            })
        except Exception:
            pass
    return result


# ─────────────────────────────────────────────────────────────
# Watchlist parsers (return list of canonical symbols sorted by volume)
# ─────────────────────────────────────────────────────────────

def _wl_parse_binance(raw) -> list:
    pairs = [x for x in (raw or []) if str(x.get("symbol", "")).endswith("USDT")]
    pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
    return [x["symbol"] for x in pairs]


def _wl_parse_bybit(raw) -> list:
    tickers = raw.get("result", {}).get("list", []) if isinstance(raw, dict) else []
    usdt = [x for x in tickers if str(x.get("symbol", "")).endswith("USDT")]
    usdt.sort(key=lambda x: float(x.get("turnover24h", 0)), reverse=True)
    return [x["symbol"] for x in usdt]


def _wl_parse_okx(raw) -> list:
    tickers = raw.get("data", []) if isinstance(raw, dict) else []
    swaps = [x for x in tickers if str(x.get("instId", "")).endswith("-USDT-SWAP")]
    swaps.sort(key=lambda x: float(x.get("volCcy24h", 0)), reverse=True)
    return [_from_okx(x["instId"]) for x in swaps]


# ─────────────────────────────────────────────────────────────
# Exchange Configuration
# ─────────────────────────────────────────────────────────────

@dataclass
class ExchangeConfig:
    name: str
    priority: int           # 1 = highest priority (Binance), higher = lower priority

    # WebSocket
    ws_url_builder: Callable    # fn(symbols: list) -> str
    subscribe_fn: Callable       # fn(ws, symbols: list) — sends subscription msg (no-op for Binance)
    message_parser: Callable     # fn(dict) -> normalized_dict | None

    # REST — klines
    rest_kline_url: str
    rest_kline_params: Callable  # fn(symbol, interval, limit) -> dict
    rest_kline_parser: Callable  # fn(raw_response) -> list[dict]

    # Symbol normalization
    to_exchange: Callable        # fn(canonical_symbol) -> exchange_symbol
    from_exchange: Callable      # fn(exchange_symbol) -> canonical_symbol

    # API Keys (Loaded from .env)
    api_key:    Optional[str] = None
    api_secret: Optional[str] = None

    # Heartbeat
    ping_payload: Optional[str] = None  # e.g., "ping" for OKX

    # REST — watchlist (optional)
    rest_watchlist_url: Optional[str] = None
    rest_watchlist_parser: Optional[Callable] = None

    # REST interval map (canonical interval → exchange interval string)
    interval_map: Dict[str, str] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Exchange Registry
# ─────────────────────────────────────────────────────────────

import os

EXCHANGES: Dict[str, ExchangeConfig] = {

    "binance": ExchangeConfig(
        name="binance",
        priority=1,
        api_key=os.getenv("BINANCE_API_KEY"),
        api_secret=os.getenv("BINANCE_API_SECRET"),
        ws_url_builder=lambda syms: "wss://fstream.binance.com/stream?streams=" + "/".join(
            f"{s.lower()}@kline_15m" for s in syms
        ),
        subscribe_fn=lambda ws, syms: None,   # URL-based, no message needed
        message_parser=_parse_binance,
        rest_kline_url="https://fapi.binance.com/fapi/v1/klines",
        rest_kline_params=lambda sym, ivl, lim: {
            "symbol": sym, "interval": ivl, "limit": lim
        },
        rest_kline_parser=_rest_parse_binance,
        to_exchange=_identity,
        from_exchange=_identity,
        rest_watchlist_url="https://fapi.binance.com/fapi/v1/ticker/24hr",
        rest_watchlist_parser=_wl_parse_binance,
        interval_map={"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"},
    ),

    "bybit": ExchangeConfig(
        name="bybit",
        priority=2,
        api_key=os.getenv("BYBIT_API_KEY"),
        api_secret=os.getenv("BYBIT_API_SECRET"),
        ws_url_builder=lambda syms: "wss://stream.bybit.com/v5/public/linear",
        subscribe_fn=_subscribe_bybit,
        message_parser=_parse_bybit,
        rest_kline_url="https://api.bybit.com/v5/market/kline",
        rest_kline_params=lambda sym, ivl, lim: {
            "category": "linear", "symbol": sym,
            "interval": {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}.get(ivl, "15"),
            "limit": lim
        },
        rest_kline_parser=_rest_parse_bybit,
        to_exchange=_identity,
        from_exchange=_identity,
        rest_watchlist_url="https://api.bybit.com/v5/market/tickers?category=linear",
        rest_watchlist_parser=_wl_parse_bybit,
        interval_map={"15m": "15", "1h": "60", "4h": "240", "1d": "D"},
    ),

    "okx": ExchangeConfig(
        name="okx",
        priority=3,
        api_key=os.getenv("OKX_API_KEY"),
        api_secret=os.getenv("OKX_API_SECRET"),
        ping_payload="ping",
        ws_url_builder=lambda syms: "wss://ws.okx.com:8443/ws/v5/public",
        subscribe_fn=_subscribe_okx,
        message_parser=_parse_okx,
        rest_kline_url="https://www.okx.com/api/v5/market/candles",
        rest_kline_params=lambda sym, ivl, lim: {
            "instId": _to_okx(sym),
            "bar": {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1Dutc"}.get(ivl, "15m"),
            "limit": lim
        },
        rest_kline_parser=_rest_parse_okx,
        to_exchange=_to_okx,
        from_exchange=_from_okx,
        rest_watchlist_url="https://www.okx.com/api/v5/market/tickers?instType=SWAP",
        rest_watchlist_parser=_wl_parse_okx,
        interval_map={"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1Dutc"},
    ),

    "bitget": ExchangeConfig(
        name="bitget",
        priority=4,
        api_key=os.getenv("BITGET_API_KEY"),
        api_secret=os.getenv("BITGET_API_SECRET"),
        ping_payload="ping",
        ws_url_builder=lambda syms: "wss://ws.bitget.com/v2/ws/public",
        subscribe_fn=_subscribe_bitget,
        message_parser=_parse_bitget,
        rest_kline_url="https://api.bitget.com/api/v2/mix/market/candles",
        rest_kline_params=lambda sym, ivl, lim: {
            "symbol": sym, "productType": "USDT-FUTURES",
            "granularity": {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1Dutc"}.get(ivl, "15m"),
            "limit": lim
        },
        rest_kline_parser=_rest_parse_bitget,
        to_exchange=_identity,
        from_exchange=_identity,
        rest_watchlist_url="https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES",
        rest_watchlist_parser=None,  # Bitget watchlist format varies — skip for now
        interval_map={"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1Dutc"},
    ),

    "pyth": ExchangeConfig(
        name="pyth",
        priority=5,
        ws_url_builder=lambda syms: "https://hermes.pyth.network", # Dummy URL
        subscribe_fn=lambda ws, syms: None,
        message_parser=lambda data: None,
        rest_kline_url="https://hermes.pyth.network/v2/updates/price/latest",
        rest_kline_params=lambda sym, ivl, lim: {}, # Pyth uses IDs, handled specially
        rest_kline_parser=lambda raw: [],
        to_exchange=_identity,
        from_exchange=_identity,
        interval_map={},
    ),
}

# Ordered by priority (most reliable first)
EXCHANGE_PRIORITY_LIST = sorted(EXCHANGES.values(), key=lambda x: x.priority)
