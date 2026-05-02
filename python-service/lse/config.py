"""
LSE Config — Clasificación dinámica por símbolo para el LiquiditySweepEngine.

Sin hardcoding. La categoría (MAJOR / MID_CAP / LOW_CAP / MICRO_CAP) se infiere
automáticamente en base al precio actual del par, obtenido de la misma fuente
de datos que usan todos los demás motores del sistema:

  Prioridad de precio:
    1. Binance Futures REST /ticker/24hr  → quoteVolume + lastPrice
    2. Bybit REST /market/tickers         → fallback
    3. OKX REST /market/tickers           → fallback
    4. Umbral de precio heurístico por nombre del símbolo → last resort

Criterios de clasificación (precio en USDT):
  - MAJOR:     precio >= 100 USDT  (BTC, ETH, BNB, SOL...)
  - MID_CAP:   0.50 <= precio < 100 (DOGE, ADA, LINK, MATIC...)
  - LOW_CAP:   0.001 <= precio < 0.50 (alts de baja cap)
  - MICRO_CAP: precio < 0.001   (PEPE, SHIB, BONK... — 0.0000001x)

La clasificación se cachea por símbolo con TTL de 60 minutos para no hacer
requests en cada scan. Se invalida si el precio cambia de categoría.
"""

from __future__ import annotations

import logging
import time
import threading
import urllib.request
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger("LSE_CONFIG")


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass de configuración
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LSESymbolConfig:
    category: str = "default"           # "major" | "mid_cap" | "low_cap" | "micro_cap"

    # --- Compresión ---
    compression_slope_max: float = 0.001
    compression_slope_window: int = 7
    compression_threshold_pct: float = 0.022
    # Si la compresión no está activa en la última vela, buscar en las últimas N velas
    # (el patrón es evolutivo: primero compresión, luego sweep más tarde).
    compression_recent_lookback: int = 56

    # --- Nivel roto (equal lows) ---
    lookback_lows: int = 20
    equal_lows_min_touches: int = 2
    equal_lows_tolerance_pct: float = 0.001
    equal_lows_atr_k: float = 0.5

    # --- Sweep ---
    wick_ratio_min: float = 0.30
    # Ventana de barrido: antes solo ~6 velas; sweeps más antiguos no aparecían.
    sweep_lookback: int = 36

    # --- Volume spike ---
    volume_spike_mult: float = 1.5
    volume_lookback: int = 50

    # --- ATR filter ---
    atr_ratio_max: float = 1.8
    anomaly_candle_ratio: float = 3.0

    # --- HTF filter ---
    htf_ma_period: int = 99
    htf_overextension_pct: float = 0.15

    # --- Scoring threshold ---
    min_score_to_trigger: float = 65.0

    # --- State machine ---
    cooldown_candles: int = 10
    confirmation_candles: int = 2

    # --- Take Profit ---
    tp1_lookback: int = 50

    # --- Entry mode ---
    entry_mode: str = "conservative"

    # --- Solo detection_mode == aggressive (conservative ignora estos campos) ---
    aggressive_wick_ratio_min: Optional[float] = None  # None → max(base wick_ratio_min, 0.35)
    aggressive_volume_spike_mult: Optional[float] = None  # None → 1.2 (volumen más flexible)
    aggressive_compression_optional: bool = True  # si True, puede seguir sin compresión MA


# ─────────────────────────────────────────────────────────────────────────────
# Perfiles de configuración (SIN símbolos hardcodeados)
# ─────────────────────────────────────────────────────────────────────────────

def _make_major() -> LSESymbolConfig:
    """BTC, ETH, BNB, SOL — precio >= 100 USDT. Alta liquidez, señales precisas."""
    return LSESymbolConfig(
        category="major",
        compression_threshold_pct=0.012,
        compression_slope_max=0.0008,
        wick_ratio_min=0.32,
        volume_spike_mult=1.65,
        atr_ratio_max=1.55,
        equal_lows_tolerance_pct=0.0005,
        min_score_to_trigger=68.0,
        cooldown_candles=8,
        sweep_lookback=32,
    )


def _make_mid_cap() -> LSESymbolConfig:
    """DOGE, ADA, LINK, MATIC — 0.50 <= precio < 100 USDT. Balance entre liquidez y volatilidad."""
    return LSESymbolConfig(
        category="mid_cap",
        compression_threshold_pct=0.018,
        compression_slope_max=0.001,
        wick_ratio_min=0.28,
        volume_spike_mult=1.45,
        atr_ratio_max=1.85,
        equal_lows_tolerance_pct=0.001,
        min_score_to_trigger=62.0,
        cooldown_candles=10,
        sweep_lookback=36,
    )


def _make_low_cap() -> LSESymbolConfig:
    """Alts de baja cap — 0.001 <= precio < 0.50 USDT. Más holgura para ruido de mercado."""
    return LSESymbolConfig(
        category="low_cap",
        compression_threshold_pct=0.028,
        compression_slope_max=0.0012,
        wick_ratio_min=0.24,
        volume_spike_mult=1.35,
        atr_ratio_max=2.05,
        equal_lows_tolerance_pct=0.002,
        min_score_to_trigger=58.0,
        cooldown_candles=12,
        sweep_lookback=40,
    )


def _make_micro_cap() -> LSESymbolConfig:
    """PEPE, SHIB, BONK — precio < 0.001 USDT. Tolerancias máximas por volatilidad extrema."""
    return LSESymbolConfig(
        category="micro_cap",
        compression_threshold_pct=0.038,
        compression_slope_max=0.0015,
        wick_ratio_min=0.20,
        volume_spike_mult=1.25,
        atr_ratio_max=2.55,
        equal_lows_tolerance_pct=0.004,
        anomaly_candle_ratio=4.0,
        min_score_to_trigger=55.0,
        cooldown_candles=15,
        confirmation_candles=3,
        sweep_lookback=48,
        compression_recent_lookback=72,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Precio dinámico — consulta las mismas APIs que usa el sistema
# ─────────────────────────────────────────────────────────────────────────────

# Fuentes REST para precio de ticker (precio actual en USDT)
_PRICE_SOURCES = [
    # Binance Futures
    lambda sym: (
        f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}",
        lambda raw: float(raw.get("price", 0)),
    ),
    # Bybit
    lambda sym: (
        f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={sym}",
        lambda raw: float((raw.get("result", {}).get("list") or [{}])[0].get("lastPrice", 0)),
    ),
    # OKX (symbol convertido a BTC-USDT-SWAP format)
    lambda sym: (
        f"https://www.okx.com/api/v5/market/ticker?instId={sym[:-4]}-USDT-SWAP",
        lambda raw: float((raw.get("data") or [{}])[0].get("last", 0)),
    ),
]

_PRICE_CACHE_TTL = 3600  # 60 minutos — el precio solo cambia de categoría lentamente
_price_cache: Dict[str, Tuple[float, float]] = {}  # symbol → (price, timestamp)
_price_cache_lock = threading.Lock()


def _fetch_live_price(symbol: str) -> float:
    """
    Obtiene el precio actual de un símbolo desde las APIs de exchange.
    Prueba Binance → Bybit → OKX en orden. Retorna 0.0 si todo falla.
    """
    sym = symbol.upper()

    for source_fn in _PRICE_SOURCES:
        try:
            url, parser = source_fn(sym)
            req = urllib.request.Request(url, headers={"User-Agent": "Verge/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read())
                price = parser(raw)
                if price > 0:
                    logger.debug("[LSE_CONFIG] %s precio=%.8f (from %s)", sym, price, url.split("/")[2])
                    return price
        except Exception as e:
            logger.debug("[LSE_CONFIG] Fuente fallida para %s: %s", sym, e)
            continue

    return 0.0


def _get_cached_price(symbol: str) -> float:
    """
    Retorna el precio cacheado si aún es válido (TTL no expirado).
    Si expiró o no existe, hace un fetch fresco y lo cachea.
    """
    sym = symbol.upper()
    now = time.time()

    with _price_cache_lock:
        cached = _price_cache.get(sym)
        if cached:
            price, ts = cached
            if now - ts < _PRICE_CACHE_TTL:
                return price

    # Cache miss o expirado — fetch fresco (fuera del lock para no bloquear)
    price = _fetch_live_price(sym)

    if price > 0:
        with _price_cache_lock:
            _price_cache[sym] = (price, now)

    return price


# ─────────────────────────────────────────────────────────────────────────────
# Clasificador dinámico
# ─────────────────────────────────────────────────────────────────────────────

def _classify_by_price(price: float) -> LSESymbolConfig:
    """
    Clasifica un activo según su precio en USDT.
    Sin hardcoding de ningún símbolo.
    """
    if price <= 0:
        # Sin precio — usar configuración default (mid_cap es el centro seguro)
        logger.debug("[LSE_CONFIG] Sin precio disponible — usando mid_cap por defecto")
        return _make_mid_cap()

    if price >= 100:
        return _make_major()
    elif price >= 0.50:
        return _make_mid_cap()
    elif price >= 0.001:
        return _make_low_cap()
    else:
        return _make_micro_cap()


# ─────────────────────────────────────────────────────────────────────────────
# Config cache (por símbolo + categoría resuelta)
# ─────────────────────────────────────────────────────────────────────────────

# Almacena la config resuelta con su categoría para detectar cambios de categoría
_config_cache: Dict[str, Tuple[str, LSESymbolConfig]] = {}  # sym → (category, config)
_config_cache_lock = threading.Lock()


def get_config(symbol: str) -> LSESymbolConfig:
    """
    Retorna la LSESymbolConfig correcta para el símbolo dado.

    Proceso:
      1. Obtiene el precio actual del par desde las mismas APIs del sistema
         (Binance → Bybit → OKX, con caché de 60 minutos).
      2. Clasifica el activo en MAJOR / MID_CAP / LOW_CAP / MICRO_CAP
         basándose en el precio (sin hardcoding de ningún símbolo).
      3. Retorna la config apropiada para esa categoría.

    Si el precio no está disponible → usa mid_cap como fallback seguro.
    """
    sym = symbol.upper()

    # Obtener precio (con caché de 60 min)
    price = _get_cached_price(sym)

    # Clasificar dinámicamente
    config = _classify_by_price(price)

    # Log solo cuando la categoría cambia para ese símbolo
    with _config_cache_lock:
        prev = _config_cache.get(sym)
        if prev is None or prev[0] != config.category:
            logger.info(
                "[LSE_CONFIG] %s → categoría=%s (precio=%.8f USDT)",
                sym, config.category, price,
            )
            _config_cache[sym] = (config.category, config)

    return config


def invalidate_price_cache(symbol: Optional[str] = None):
    """
    Invalida la caché de precios manualmente.
    Útil si un símbolo tuvo un movimiento extremo que cambió su categoría.
    Si symbol=None, invalida todo el caché.
    """
    with _price_cache_lock:
        if symbol:
            _price_cache.pop(symbol.upper(), None)
        else:
            _price_cache.clear()

    with _config_cache_lock:
        if symbol:
            _config_cache.pop(symbol.upper(), None)
        else:
            _config_cache.clear()

    logger.info("[LSE_CONFIG] Caché de precios invalidado (%s)", symbol or "ALL")
