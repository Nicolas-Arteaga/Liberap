"""
Validación previa a ejecución: LSE (niveles estructurales) y Nexus/SCAR (rango estimado).
Devuelve métricas para auditoría / trade_analytics.
"""
from __future__ import annotations

import logging
import math
import time
import requests
from typing import Any, Dict, Tuple

import config

logger = logging.getLogger("SetupValidator")

# ── Flag de primera ejecución para confirmar código nuevo en logs ──
_VALIDATE_FIRST_CALL = True
_VALIDATE_CALL_COUNT = 0  # Contador global de validaciones
_VALIDATE_VETO_COUNT = 0  # Contador de vetos aplicados
_VALIDATE_PASS_COUNT = 0  # Contador de validaciones que pasaron

def _is_direct_injection_candidate(candidate: dict) -> bool:
    """
    True para candidatos de inyección directa (MA Slope, Arrow Peak, Total
    Sweep, Golden U-Turn): ya traen su propio score/SL/TP calculados por su
    propio detector geométrico, no son señales "Nexus con nivel de confianza"
    — los chequeos de Tier/rango estimado de esta funcion están pensados para
    ese otro paradigma (Nexus/Bridge) y no aplican acá.
    """
    return bool(
        candidate.get("ma_slope_mode")
        or candidate.get("arrow_peak_mode")
        or candidate.get("total_sweep_mode")
        or candidate.get("golden_uturn_mode")
    )


# --- 24h Ticker Cache (Thread-Safe Symmetrical Veto Provider) ---
_TICKER_CACHE: Dict[str, Dict[str, float]] = {}
_LAST_TICKER_FETCH = 0.0
_TICKER_CACHE_TTL = 300.0  # 5 minutos cache TTL

def _fetch_24h_price_change_percent(symbol: str) -> float:
    """
    Fetches the 24h price change percent for a symbol, with a global cache.
    Returns the change percent (e.g. +30.5 or -12.4).
    """
    global _TICKER_CACHE, _LAST_TICKER_FETCH
    now = time.time()
    if not _TICKER_CACHE or (now - _LAST_TICKER_FETCH) > _TICKER_CACHE_TTL:
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                new_cache = {}
                for x in data:
                    sym = x.get("symbol")
                    pct = x.get("priceChangePercent")
                    low = x.get("lowPrice")
                    if sym and pct is not None:
                        new_cache[sym] = {
                            "priceChangePercent": float(pct),
                            "lowPrice": float(low) if low else 0.0
                        }
                _TICKER_CACHE = new_cache
                _LAST_TICKER_FETCH = now
                logger.info(f"[TICKER-CACHE] Refreshed 24h ticker cache. {len(_TICKER_CACHE)} symbols cached.")
        except Exception as e:
            logger.warning(f"[TICKER-CACHE] Error refreshing 24h ticker: {e}")
            
    return _TICKER_CACHE.get(symbol, {}).get("priceChangePercent", 0.0)

def _fetch_24h_low_price(symbol: str) -> float:
    """
    Fetches the 24h low price for a symbol, with a global cache.
    Returns the low price (e.g. 0.05234).
    """
    global _TICKER_CACHE, _LAST_TICKER_FETCH
    now = time.time()
    if not _TICKER_CACHE or (now - _LAST_TICKER_FETCH) > _TICKER_CACHE_TTL:
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                new_cache = {}
                for x in data:
                    sym = x.get("symbol")
                    pct = x.get("priceChangePercent")
                    low = x.get("lowPrice")
                    if sym and pct is not None:
                        new_cache[sym] = {
                            "priceChangePercent": float(pct),
                            "lowPrice": float(low) if low else 0.0
                        }
                _TICKER_CACHE = new_cache
                _LAST_TICKER_FETCH = now
                logger.info(f"[TICKER-CACHE] Refreshed 24h ticker cache. {len(_TICKER_CACHE)} symbols cached.")
        except Exception as e:
            logger.warning(f"[TICKER-CACHE] Error refreshing 24h ticker: {e}")
            
    return _TICKER_CACHE.get(symbol, {}).get("lowPrice", 0.0)


# ── GOLDEN U-TURN DETECTOR v9.0: MA99 Lateralization After Drop ─────────────
# Detecta lateralización de MA99 tras caída confirmada.
# Bypass (Score 99) solo si MA99 horizontal (-1.5°/+1.5°) y venimos de caída >2%.
# Fast path: usa datos pre-calculados por el agente en Step 3.5 (Gravity Check).

def _calculate_ma99_slope_angle(ma_values: list, window: int = None) -> float:
    """
    Calcula el ángulo de inclinación de una MA (MA99 o MA7) en grados.
    Retorna el ángulo en grados (positivo = subiendo, negativo = bajando).
    """
    if not ma_values or len(ma_values) < 2:
        return 0.0

    if window is None:
        window = int(getattr(config, "GOLDEN_UTURN_ANGLE_WINDOW", 12))
    recent_values = ma_values[-window:] if len(ma_values) >= window else ma_values
    if len(recent_values) < 2:
        return 0.0
    
    # Calcular pendiente usando regresión lineal simple
    n = len(recent_values)
    x = list(range(n))
    y = recent_values
    
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)
    
    if n * sum_x2 - sum_x ** 2 == 0:
        return 0.0
    
    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
    
    # Convertir pendiente a ángulo en grados
    # Asumiendo que x es tiempo (velas) y y es precio
    angle = math.degrees(math.atan(slope / recent_values[-1])) if recent_values[-1] > 0 else 0.0
    
    return angle


def _is_flat_market(ma99_angle: float, threshold_deg: float = 5.0) -> bool:
    """
    Determina si el mercado está en lateralización (MA99 horizontal).
    Retorna True si el ángulo está entre -threshold_deg y +threshold_deg.
    """
    return abs(ma99_angle) <= threshold_deg


def _profile_has_veto_bypass(profile: dict) -> bool:
    """
    Determina si el profile tiene bypass de vetos #1-#8.
    
    Estrategias con bypass (solo aplican vetos #9+):
    - MA Clone (id: 3a21db74-5d45-fcbf-f186-a284d59e97fb)
    - Scalping Clone (id: 00000000-0000-0000-0000-000000000001)
    - Standard Scalping (id: 00000000-0000-0000-0000-000000000000)
    
    Estrategia sin bypass (aplica TODOS los vetos):
    - MA Cross Momentum (id: 3a214744-f0b9-68bb-f235-438a39d39d33)
    """
    if not profile:
        return False
    
    profile_id = profile.get("id", "")
    profile_name = profile.get("name", "")
    
    # IDs de estrategias con bypass
    bypass_ids = [
        "3a21db74-5d45-fcbf-f186-a284d59e97fb",  # MA Clone
        "00000000-0000-0000-0000-000000000001",  # Scalping Clone
        "00000000-0000-0000-0000-000000000000",  # Standard Scalping
    ]
    
    # MA Cross Momentum NO tiene bypass (aplica todos los vetos)
    ma_cross_id = "3a214744-f0b9-68bb-f235-438a39d39d33"
    if profile_id == ma_cross_id or profile_name == "MA Cross Momentum":
        return False
    
    return profile_id in bypass_ids


def _is_ma_cross_momentum(profile: dict) -> bool:
    """
    Determina si el profile es MA Cross Momentum.
    
    Esta estrategia aplica la LEY DE NICO v12.0 (The L-Shape).
    """
    if not profile:
        return False
    
    profile_id = profile.get("id", "")
    profile_name = profile.get("name", "")
    
    ma_cross_id = "3a214744-f0b9-68bb-f235-438a39d39d33"
    return profile_id == ma_cross_id or profile_name == "MA Cross Momentum"


def _check_nico_l_shape(
    candidate: dict,
    current_price: float,
    symbol: str = "?"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    LEY DE NICO v12.0 (The L-Shape) - Detector exclusivo para MA Cross Momentum.
    
    PASO 1 (La Caída): MA99 debe haber caído al menos 5% en las últimas 100 velas (15m).
    PASO 2 (El Cemento): Precio y MA50 pegados (<0.5%) y horizontales (±0.2°) por 12 velas consecutivas.
    PASO 3 (La Compresión): MA99 entre 1.5% y 4.0% del precio durante el cemento.
    
    GATILLO DE NICO: MA50 slope > 0.2° (primer giro positivo) y cierre > MA50.
    
    Si se cumple: Score = 100, bypass total de IA/RSI/Wait.
    """
    metrics: Dict[str, Any] = {"l_shape_detected": False}
    
    # Extraer datos estructurales del contexto de auditoría
    audit_ctx = candidate.get("agent_audit_context", {})
    nexus15_ctx = audit_ctx.get("nexus15", {}) if isinstance(audit_ctx, dict) else {}
    nexus_features = nexus15_ctx.get("features", {}) if isinstance(nexus15_ctx, dict) else {}
    
    # Obtener históricos de MA99 y MA50
    ma99_history = nexus_features.get("ma99_history", [])
    ma50_history = nexus_features.get("ma50_history", [])
    
    if not ma99_history or len(ma99_history) < 100:
        return False, "l_shape_no_ma99_history", metrics
    
    if not ma50_history or len(ma50_history) < 20:
        return False, "l_shape_no_ma50_history", metrics
    
    # ── PASO 1: La Caída (MA99 debe haber caído ≥5% en 100 velas) ──
    ma99_100_ago = float(ma99_history[-100]) if len(ma99_history) >= 100 else float(ma99_history[0])
    ma99_now = float(ma99_history[-1])
    ma99_drop_pct = ((ma99_now - ma99_100_ago) / ma99_100_ago) * 100
    
    min_drop_pct = float(getattr(config, "NICO_L_SHAPE_MIN_DROP_PCT", 5.0))
    if ma99_drop_pct > -min_drop_pct:
        logger.info(
            f"[NICO-L-SHAPE] {symbol}: FAIL Paso 1 - MA99 cayó {ma99_drop_pct:.2f}% (necesita ≥{min_drop_pct}%)"
        )
        return False, "l_shape_no_drop", metrics
    
    metrics["ma99_drop_pct"] = round(ma99_drop_pct, 2)
    logger.info(f"[NICO-L-SHAPE] {symbol}: PASS Paso 1 - MA99 cayó {ma99_drop_pct:.2f}%")
    
    # ── PASO 2: El Cemento (Precio/MA50 pegados y horizontales por 12 velas) ──
    min_cement_candles = int(getattr(config, "NICO_L_SHAPE_MIN_CEMENT_CANDLES", 12))
    max_price_ma50_dist_pct = float(getattr(config, "NICO_L_SHAPE_MAX_PRICE_MA50_DIST_PCT", 0.5))
    max_ma50_slope_deg = float(getattr(config, "NICO_L_SHAPE_MAX_MA50_SLOPE_DEG", 0.2))
    reset_threshold_pct = float(getattr(config, "NICO_L_SHAPE_RESET_THRESHOLD_PCT", 1.0))
    
    cement_candles = 0
    max_cement_candles = 0
    cement_low = float('inf')
    
    # Analizar las últimas 20 velas buscando cemento consecutivo
    recent_ma50 = ma50_history[-20:] if len(ma50_history) >= 20 else ma50_history
    recent_prices = nexus_features.get("close_history", [])
    
    if not recent_prices or len(recent_prices) < 20:
        return False, "l_shape_no_price_history", metrics
    
    recent_prices = recent_prices[-20:] if len(recent_prices) >= 20 else recent_prices
    
    for i in range(len(recent_ma50) - 1, -1, -1):
        if i >= len(recent_prices):
            break
            
        price = float(recent_prices[i])
        ma50 = float(recent_ma50[i])
        
        # Calcular distancia precio/MA50
        price_ma50_dist_pct = abs((price - ma50) / ma50) * 100 if ma50 > 0 else 999
        
        # Calcular slope de MA50 en ventana de 5 velas
        ma50_window_start = max(0, i - 5)
        ma50_window = recent_ma50[ma50_window_start:i+1]
        ma50_slope = _calculate_ma99_slope_angle(ma50_window, window=len(ma50_window))
        
        # Regla de Hierro: Reset si el precio se aleja >1%
        if price_ma50_dist_pct > reset_threshold_pct:
            cement_candles = 0
            continue
        
        # Verificar condiciones de cemento
        if (price_ma50_dist_pct <= max_price_ma50_dist_pct and 
            abs(ma50_slope) <= max_ma50_slope_deg):
            cement_candles += 1
            max_cement_candles = max(max_cement_candles, cement_candles)
            cement_low = min(cement_low, price)
        else:
            cement_candles = 0
    
    metrics["cement_candles"] = max_cement_candles
    metrics["cement_low"] = cement_low if cement_low != float('inf') else 0
    
    if max_cement_candles < min_cement_candles:
        logger.info(
            f"[NICO-L-SHAPE] {symbol}: FAIL Paso 2 - Solo {max_cement_candles} velas de cemento (necesita {min_cement_candles})"
        )
        return False, "l_shape_insufficient_cement", metrics
    
    logger.info(f"[NICO-L-SHAPE] {symbol}: PASS Paso 2 - {max_cement_candles} velas de cemento")
    
    # ── PASO 3: La Compresión (MA99 entre 1.5% y 4.0% del precio) ──
    ma99_price_dist_pct = abs((current_price - ma99_now) / ma99_now) * 100 if ma99_now > 0 else 0
    min_ma99_dist_pct = float(getattr(config, "NICO_L_SHAPE_MIN_MA99_DIST_PCT", 1.5))
    max_ma99_dist_pct = float(getattr(config, "NICO_L_SHAPE_MAX_MA99_DIST_PCT", 4.0))
    
    if not (min_ma99_dist_pct <= ma99_price_dist_pct <= max_ma99_dist_pct):
        logger.info(
            f"[NICO-L-SHAPE] {symbol}: FAIL Paso 3 - MA99 a {ma99_price_dist_pct:.2f}% del precio (necesita {min_ma99_dist_pct}%-{max_ma99_dist_pct}%)"
        )
        return False, "l_shape_ma99_not_compressed", metrics
    
    metrics["ma99_price_dist_pct"] = round(ma99_price_dist_pct, 2)
    logger.info(f"[NICO-L-SHAPE] {symbol}: PASS Paso 3 - MA99 a {ma99_price_dist_pct:.2f}% del precio")
    
    # ── GATILLO DE NICO: MA50 slope > 0.2° y cierre > MA50 ──
    ma50_now = float(ma50_history[-1])
    ma50_slope_now = _calculate_ma99_slope_angle(ma50_history[-10:], window=10)
    close_above_ma50 = current_price > ma50_now
    
    min_trigger_slope = float(getattr(config, "NICO_L_SHAPE_MIN_TRIGGER_SLOPE_DEG", 0.2))
    
    if not (ma50_slope_now > min_trigger_slope and close_above_ma50):
        logger.info(
            f"[NICO-L-SHAPE] {symbol}: WAIT Gatillo - MA50 slope={ma50_slope_now:.2f}° (necesita >{min_trigger_slope}°), "
            f"cierre>MA50={close_above_ma50}"
        )
        return False, "l_shape_waiting_trigger", metrics
    
    metrics["ma50_slope_now"] = round(ma50_slope_now, 2)
    metrics["close_above_ma50"] = close_above_ma50
    logger.info(f"[NICO-L-SHAPE] {symbol}: GATILLO ACTIVADO - MA50 slope={ma50_slope_now:.2f}°, cierre>MA50={close_above_ma50}")
    
    # ── L-SHAPE COMPLETA: Bypass Total ──
    metrics["l_shape_detected"] = True
    metrics["internal_score"] = 100.0
    metrics["l_shape_type"] = "nico_l_shape_v12"
    
    logger.warning(
        f"[NICO-L-SHAPE v12.0] {symbol} - L DE CEMENTO COMPLETA! "
        f"MA99 Drop={ma99_drop_pct:.2f}% | Cemento={max_cement_candles} velas | "
        f"MA99 Dist={ma99_price_dist_pct:.2f}% | MA50 Slope={ma50_slope_now:.2f}° | SCORE=100"
    )
    
    return True, "nico_l_shape_bypass", metrics


def _validate_golden_cement_floor(
    current_price: float,
    golden_ctx: dict,
    symbol: str = "?",
) -> Tuple[bool, str]:
    """v9.4 — Re-valida proximidad MA99 y confirmación MA7 en tiempo de ejecución."""
    if not golden_ctx:
        return False, "no_golden_context"

    max_ma99_dist = float(getattr(config, "GOLDEN_UTURN_MAX_MA99_DISTANCE_PCT", 15.0))
    max_ma7_dist = float(getattr(config, "GOLDEN_UTURN_MAX_MA7_DISTANCE_PCT", 2.0))

    dist_pct = golden_ctx.get("price_to_ma99_distance_pct")
    if dist_pct is None:
        ma99_now = float(golden_ctx.get("ma99_now", 0) or 0)
        if ma99_now > 0 and current_price > 0:
            dist_pct = ((current_price - ma99_now) / ma99_now) * 100
        else:
            dist_pct = 0.0
    else:
        dist_pct = float(dist_pct)

    if abs(dist_pct) > max_ma99_dist:
        logger.warning(
            f"[GOLDEN-v9.5] {symbol}: VETO distancia MA99={dist_pct:.2f}% > ±{max_ma99_dist}%"
        )
        return False, "golden_ma99_distance_veto"

    ma7_now = float(golden_ctx.get("ma7_now", 0) or 0)
    ma7_prox = golden_ctx.get("ma7_proximity_pct")
    if ma7_prox is None and ma7_now > 0:
        ma7_prox = abs((current_price - ma7_now) / ma7_now) * 100
    else:
        ma7_prox = float(ma7_prox or 999.0)

    if ma7_now <= 0 or ma7_prox > max_ma7_dist:
        logger.warning(
            f"[GOLDEN-v9.5] {symbol}: VETO proximidad MA7={ma7_prox:.2f}% > ±{max_ma7_dist}%"
        )
        return False, "golden_ma7_proximity_veto"

    return True, "ok"


def check_uturn_detector(
    candidate: dict,
    current_price: float
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    GOLDEN U-TURN DETECTOR v9.0: Detecta lateralización de MA99 tras una caída.
    
    Fast path: Si el agente pre-calculó golden_uturn en Step 3.5, usa esos valores directos.
    Fallback: Calcula desde nexus15 features (v8.1 legacy).
    
    Bypass (Score 99) SOLO SI:
    1. MA99 horizontal: ángulo entre -1.5° y +1.5°
    2. MA99 hace 100 velas (15m) >= 3% SUPERIOR al actual (caída confirmada)
    
    Bloqueo: Si MA99 lateraliza pero venimos de SUBIDA → BLOQUEA LONG
    """
    metrics: Dict[str, Any] = {"uturn_detected": False}
    symbol = candidate.get("symbol", "?")
    
    audit_ctx = candidate.get("agent_audit_context", {})
    
    # ── FAST PATH v9.0: Usar datos pre-calculados por el agente (Step 3.5) ──
    golden_ctx = audit_ctx.get("golden_uturn", {}) if isinstance(audit_ctx, dict) else {}
    if golden_ctx and golden_ctx.get("detected"):
        cement_ok, cement_code = _validate_golden_cement_floor(current_price, golden_ctx, symbol)
        if not cement_ok:
            metrics["cement_floor_veto"] = cement_code
            return False, cement_code, metrics

        angle = float(golden_ctx.get("angle", 0))
        drop_pct = float(golden_ctx.get("drop_pct", 0))
        sl_5low = float(golden_ctx.get("sl_5low", 0))
        
        metrics["ma99_angle"] = angle
        metrics["ma99_change_pct"] = round(drop_pct, 2)
        metrics["uturn_detected"] = True
        metrics["internal_score"] = 99.0
        metrics["uturn_type"] = "golden_uturn_floor"
        metrics["golden_uturn_sl_5low"] = sl_5low
        
        candidate["golden_uturn_mode"] = True
        if sl_5low > 0 and sl_5low < current_price:
            candidate["custom_sl_price"] = sl_5low  # v9.6: usa low de 20 velas (config GOLDEN_UTURN_SL_CANDLE_LOOKBACK)
        
        # ── v10.1 The Surgical Hook: Regla del Gancho ─────────────────────────
        # Solo para GOLDEN-U-TURN: el cierre de 15m debe ser estrictamente MAYOR a la MA7
        # La MA7 debe estar plana o subiendo (Slope MA7 > -1°)
        ma7_now = float(golden_ctx.get("ma7_now", 0))
        close_above_ma7 = float(golden_ctx.get("close_above_ma7", False))
        
        hook_pass = True
        hook_reason = ""
        
        if ma7_now > 0:
            # Verificar que el cierre sea estrictamente MAYOR a la MA7
            if not close_above_ma7:
                hook_pass = False
                hook_reason = "cierre_no_sobre_ma7"
                logger.warning(
                    f"[THE-HOOK] {symbol} - FAIL: Cierre no sobre MA7 (close={current_price:.6f}, MA7={ma7_now:.6f}) - HARD RETURN v11.2"
                )
                metrics["hook_veto"] = hook_reason
                return False, "the_hook_veto_cierre_bajo_ma7", metrics
            else:
                # Verificar slope de MA7 (usando ma7_history si está disponible)
                ma7_history = golden_ctx.get("ma7_history", [])
                if ma7_history and len(ma7_history) >= 2:
                    ma7_slope = _calculate_ma99_slope_angle(ma7_history)
                    if ma7_slope < -1.0:
                        hook_pass = False
                        hook_reason = f"ma7_slope_negativo_{ma7_slope:.2f}"
                        logger.warning(
                            f"[THE-HOOK] {symbol} - FAIL: MA7 slope={ma7_slope:.2f}° < -1° (bajando rápido)"
                        )
                    else:
                        logger.info(
                            f"[THE-HOOK] {symbol} - PASS: Cierre sobre MA7, MA7 slope={ma7_slope:.2f}° (plana/subiendo)"
                        )
                else:
                    logger.info(f"[THE-HOOK] {symbol} - PASS: Cierre sobre MA7 (sin datos de slope)")
        else:
            logger.warning(f"[THE-HOOK] {symbol} - SKIP: No hay datos de MA7")
        
        if not hook_pass:
            metrics["hook_veto"] = hook_reason
            return False, f"the_hook_veto_{hook_reason}", metrics
        
        logger.warning(
            f"[GOLDEN-U-TURN v10.1] {symbol} - PISO DE CEMENTO + THE HOOK! "
            f"MA99 Angle={angle:.2f}° | Drop={drop_pct:.2f}% | "
            f"DistMA99={golden_ctx.get('price_to_ma99_distance_pct')}% | SL={sl_5low:.6f}"
        )
        return True, "golden_uturn_bypass", metrics
    
    # ── FALLBACK PATH v8.1: Calcular desde nexus15 features ──
    nexus15_ctx = audit_ctx.get("nexus15", {}) if isinstance(audit_ctx, dict) else {}
    nexus_features = nexus15_ctx.get("features", {}) if isinstance(nexus15_ctx, dict) else {}
    
    ma99_history = []
    if isinstance(nexus_features, dict):
        ma99_history = nexus_features.get("ma99_history", [])
    
    if not ma99_history or len(ma99_history) < 2:
        ma99_current = float(nexus_features.get("ma99", 0) or 0)
        ma99_prev = float(nexus_features.get("ma99_prev", 0) or 0)
        if ma99_current > 0 and ma99_prev > 0:
            ma99_history = [ma99_prev, ma99_current]
    
    if not ma99_history or len(ma99_history) < 2:
        logger.debug(f"[U-TURN v9.0] {symbol}: No MA99 data - SKIP")
        return False, "no_ma99_data", metrics
    
    ma99_angle = _calculate_ma99_slope_angle(ma99_history)
    metrics["ma99_angle"] = ma99_angle
    
    # v9.0: ±1.5° (más estricto que v8.1 ±2°)
    angle_threshold = float(getattr(config, "GOLDEN_UTURN_ANGLE_THRESHOLD", 1.5))
    is_flat = abs(ma99_angle) <= angle_threshold
    if not is_flat:
        logger.debug(f"[U-TURN v9.0] {symbol}: MA99 Angle={ma99_angle:.2f}° not flat - FAIL")
        return False, "ma99_not_flat", metrics
    
    logger.info(f"[U-TURN v9.0] {symbol}: MA99 Angle={ma99_angle:.2f}° FLAT - PASS")
    
    lookback_candles = int(getattr(config, "GOLDEN_UTURN_LOOKBACK_CANDLES", 60))
    lookback_idx = min(lookback_candles, len(ma99_history) - 1)
    ma99_ago = float(ma99_history[-lookback_idx - 1]) if lookback_idx > 0 else 0.0
    ma99_now = float(ma99_history[-1])
    
    if ma99_ago <= 0 or ma99_now <= 0:
        return False, "ma99_insufficient_history", metrics
    
    ma99_change_pct = ((ma99_now - ma99_ago) / ma99_ago) * 100
    metrics["ma99_lookback_ago"] = ma99_ago
    metrics["ma99_now"] = ma99_now
    metrics["ma99_change_pct"] = round(ma99_change_pct, 2)
    
    # v9.0: drop >= 2% (más estricto que v8.1 1.5%)
    min_drop = float(getattr(config, "GOLDEN_UTURN_MIN_DROP_PCT", 2.0))
    
    if ma99_change_pct <= -min_drop:
        metrics["uturn_detected"] = True
        metrics["internal_score"] = 99.0
        metrics["uturn_type"] = "floor_after_drop"
        
        candidate["golden_uturn_mode"] = True
        
        logger.warning(
            f"[GOLDEN-U-TURN v9.0] {symbol} - SUELO! MA99 cayó {ma99_change_pct:.2f}% y lateraliza. Score=99."
        )
        return True, "golden_uturn_bypass", metrics
    
    if ma99_change_pct >= min_drop:
        metrics["uturn_block"] = True
        logger.warning(
            f"[U-TURN v9.0] {symbol} - TECHO! MA99 subió {ma99_change_pct:.2f}% y lateraliza. BLOCK LONG."
        )
        return False, "uturn_top_block_long", metrics
    
    logger.debug(f"[U-TURN v9.0] {symbol}: MA99 flat, change={ma99_change_pct:.2f}% - NEUTRAL")
    return False, "uturn_neutral", metrics


def _effective_tick(ref_price: float) -> float:
    rel = getattr(config, "TICK_SIZE_MIN_RELATIVE_OF_PRICE", 1e-7)
    abs_min = getattr(config, "TICK_SIZE_MIN_ABSOLUTE", 1e-10)
    return max(abs_min, abs(ref_price) * rel)


def _normalize_reasons(candidate: dict) -> list[str]:
    r = candidate.get("reasons")
    if isinstance(r, list):
        return [str(x) for x in r]
    if isinstance(r, str):
        return [r]
    return []


def lse_reasoning_blocks_trade(candidate: dict) -> bool:
    needle = getattr(config, "LSE_BLOCK_REASONING_SUBSTRING", "R:R bajo").lower()
    score = float(candidate.get("confluence_score", 0) or 0)
    lse_override_score = float(getattr(config, "LSE_WARNING_OVERRIDE_SCORE", 85.0))
    if score >= lse_override_score:
        return False
    for line in _normalize_reasons(candidate):
        if needle in line.lower():
            return True
    return False


def validate_lse_setup(
    candidate: dict, current_price: float, profile: dict = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """Reglas duras LSE (spring LONG side 0 en producción actual)."""
    global _VALIDATE_VETO_COUNT
    metrics: Dict[str, Any] = {}
    symbol = candidate.get("symbol", "UNKNOWN")  # FIX v7.6: definir symbol antes de usarlo en f-strings

    entry = candidate.get("lse_entry_price")
    sl = candidate.get("lse_stop_loss")
    tp2 = candidate.get("lse_take_profit_2")
    reclaim = candidate.get("lse_reclaim_close")
    atr = candidate.get("lse_atr")
    side = int(candidate.get("side", 0))

    if entry is None or sl is None or tp2 is None:
        return False, "missing_structural_levels", {"entry": entry, "sl": sl, "tp2": tp2}

    try:
        entry_f = float(entry)
        sl_f = float(sl)
        tp2_f = float(tp2)
        cp = float(current_price)
    except (TypeError, ValueError):
        return False, "invalid_numeric", {}

    if entry_f <= 0 or cp <= 0:
        return False, "invalid_price", {}

    if side == 0 and cp <= sl_f:
        logger.info("[SKIP] invalid_exec_vs_sl cp=%s sl=%s", cp, sl_f)
        return False, "invalid_exec_vs_sl", {}

    tick = _effective_tick(entry_f)
    metrics["tick_used"] = tick

    if side == 0:
        if tp2_f <= entry_f or sl_f >= entry_f:
            logger.info("[SKIP] invalid_levels tp2=%s entry=%s sl=%s", tp2_f, entry_f, sl_f)
            return False, "invalid_levels", metrics

        risk_w = entry_f - sl_f
        reward_w = tp2_f - entry_f
        if risk_w <= 0:
            logger.info("[SKIP] invalid_levels risk<=0 entry=%s sl=%s", entry_f, sl_f)
            return False, "invalid_levels", metrics

        if abs(reward_w) <= tick:
            logger.info("[SKIP] invalid_levels reward<=tick reward=%s tick=%s", reward_w, tick)
            return False, "invalid_levels", metrics

        rr = reward_w / risk_w
        metrics["rr"] = round(rr, 4)
        metrics["risk_abs"] = risk_w
        metrics["reward_abs"] = reward_w

        # Usar umbral del profile si existe
        if profile:
            min_rr = float(profile.get("minRR", getattr(config, "LSE_MIN_RR", 3.0)))
        else:
            min_rr = float(getattr(config, "LSE_MIN_RR", 3.0))
            dm = str(candidate.get("lse_detection_mode") or "").lower()
            if dm == "aggressive":
                min_rr = float(getattr(config, "MIN_RR_AGGRESSIVE_LSE", 2.0))

        if rr < min_rr:
            logger.info("[SKIP] low_rr rr=%s min_rr=%s", rr, min_rr)
            return False, "low_rr", metrics

        atr_f = float(atr) if atr is not None else 0.0
        tp_dist_pct = float(profile.get("minTpDistancePct", getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))) if profile else float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))
        pct_tp_floor = entry_f * tp_dist_pct
        if atr_f > 0:
            min_reward_abs = max(
                float(getattr(config, "MIN_TP_DISTANCE_ATR_MULT", 0.8)) * atr_f,
                pct_tp_floor,
            )
        else:
            min_reward_abs = pct_tp_floor
        if reward_w < min_reward_abs:
            logger.info("[SKIP] tp_too_close reward=%s min_reward=%s", reward_w, min_reward_abs)
            metrics["min_tp_distance_required"] = min_reward_abs
            return False, "tp_too_close", metrics

        sl_dist_pct = float(profile.get("minSlDistancePct", getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))) if profile else float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
        pct_floor = entry_f * sl_dist_pct
        if atr_f > 0:
            min_stop = max(
                float(getattr(config, "MIN_STOP_ATR_MULT", 0.5)) * atr_f,
                pct_floor,
            )
        else:
            min_stop = pct_floor

        if risk_w < min_stop:
            logger.info("[SKIP] stop_too_tight risk=%s min_stop=%s atr=%s", risk_w, min_stop, atr)
            metrics["min_stop_required"] = min_stop
            return False, "stop_too_tight", metrics

        slip = (cp - entry_f) / entry_f
        metrics["entry_slippage_pct"] = round(slip, 6)
        max_slip = float(profile.get("lseMaxEntrySlippagePct", getattr(config, "LSE_MAX_ENTRY_SLIPPAGE_PCT", 0.015))) if profile else float(getattr(config, "LSE_MAX_ENTRY_SLIPPAGE_PCT", 0.015))
        if slip > max_slip:
            logger.info("[SKIP] late_entry slippage_pct=%s max=%s", slip, max_slip)
            return False, "late_entry", metrics

        if reclaim is not None:
            try:
                rc = float(reclaim)
                if cp < rc:
                    logger.info("[SKIP] late_entry below_reclaim cp=%s reclaim=%s", cp, rc)
                    return False, "late_entry", metrics
            except (TypeError, ValueError):
                pass

    else:
        if tp2_f >= entry_f or sl_f <= entry_f:
            return False, "invalid_levels", metrics
        risk_w = sl_f - entry_f
        reward_w = entry_f - tp2_f
        if risk_w <= 0:
            return False, "invalid_levels", metrics
        rr = reward_w / risk_w
        metrics["rr"] = round(rr, 4)

    metrics["sl_distance_pct"] = round(abs(entry_f - sl_f) / entry_f, 6)
    metrics["atr_signal"] = float(atr) if atr is not None else None
    metrics["risk_pct_used"] = float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))

    return True, "ok", metrics


def validate_nexus_confluence_setup(
    candidate: dict, current_price: float, profile: dict = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Mismas ideas operativas que LSE: RR mínimo, TP/stop no microscópicos vs precio.
    Niveles TP/SL = mismos multiplicadores que RiskManager (estimated_range_pct).
    """
    global _VALIDATE_VETO_COUNT, _VALIDATE_PASS_COUNT
    metrics: Dict[str, Any] = {"pipeline": "nexus_scar"}
    symbol = candidate.get("symbol", "UNKNOWN")  # FIX v7.6: definir symbol antes de usarlo en f-strings
    side = int(candidate.get("side", 0))

    try:
        cp = float(current_price)
    except (TypeError, ValueError):
        return False, "invalid_numeric", metrics

    if cp <= 0:
        return False, "invalid_price", metrics

    # ── Bloqueos duros para señales Nexus ─────────────────────────────────
    # Extraer features del contexto de auditoría Nexus-15
    audit_ctx = candidate.get("agent_audit_context", {})
    nexus15_ctx = audit_ctx.get("nexus15", {})
    nexus_features = (
        nexus15_ctx.get("features", {}) if isinstance(nexus15_ctx, dict) else {}
    )

    # ── GOLDEN U-TURN v12.1: DESHABILITADO COMPLETAMENTE ──
    # 2/2 trades reales perdieron. Deshabilitado hasta nueva revisión.
    # El detector NO se llama — siempre False.
    uturn_detected, uturn_reason, uturn_metrics = False, "", {}
    
    # ── LEY DE NICO v12.0 (The L-Shape) — Exclusivo para MA Cross Momentum ──
    # Este detector tiene prioridad sobre Golden U-Turn para MA Cross Momentum
    if _is_ma_cross_momentum(profile) and getattr(config, "NICO_L_SHAPE_ENABLED", False):
        l_shape_detected, l_shape_reason, l_shape_metrics = _check_nico_l_shape(candidate, cp, symbol)
        if l_shape_detected:
            # L-SHAPE COMPLETA: Bypass Total
            candidate["nico_l_shape_mode"] = True
            candidate["confluence_score"] = float(getattr(config, "NICO_L_SHAPE_SCORE", 100.0))
            metrics.update(l_shape_metrics)
            
            # SL: low de las 12 velas de cemento
            cement_low = l_shape_metrics.get("cement_low", 0)
            if cement_low > 0:
                sl_buffer_pct = float(getattr(config, "NICO_L_SHAPE_SL_SPREAD_BUFFER_PCT", "0.1")) / 100.0
                custom_sl = cement_low * (1.0 - sl_buffer_pct)
                candidate["custom_sl_price"] = custom_sl
                logger.info(f"[NICO-L-SHAPE] {symbol}: SL Diamond Hands = {custom_sl:.6f} (low cemento {cement_low:.6f})")
            
            # TP: mínimo 10%
            min_tp_pct = float(getattr(config, "NICO_L_SHAPE_TP_MIN_DISTANCE_PCT", 10.0)) / 100.0
            custom_tp = cp * (1.0 + min_tp_pct)
            candidate["custom_tp_price"] = custom_tp
            logger.info(f"[NICO-L-SHAPE] {symbol}: TP Diamond Hands = {custom_tp:.6f} (mínimo {min_tp_pct*100:.1f}%)")
            
            # Marcar para trailing 5% después del 10%
            candidate["nico_trailing_enabled"] = True
            candidate["nico_trailing_pct"] = float(getattr(config, "NICO_L_SHAPE_TP_TRAILING_PCT", 5.0))
            
            logger.warning(
                f"[NICO-L-SHAPE v12.0] {symbol} - BYPASS TOTAL ACTIVADO! Score=100. "
                f"Ignorando IA, RSI, Wait. Solo la L de Nico manda."
            )
            return True, "nico_l_shape_bypass", metrics
    
    # ── FIX v11.10: TOTAL OBEDIENCE — SOLO para Golden U-Turn ──
    # Si check_uturn_detector devuelve False, respetar el veto SOLO si es candidato Golden.
    # Los candidatos Nexus regulares (como JTOUSDT con 94.5%) NO deben ser bloqueados
    # por falta de MA99 data. El MA99 es irrelevante para señales Nexus de alta confianza.
    _is_golden_candidate = bool(
        candidate.get("golden_uturn_mode")
        or candidate.get("source") == "golden_uturn"
        or (candidate.get("agent_audit_context", {}).get("golden_uturn", {}) or {}).get("detected")
    )
    if _is_golden_candidate and not uturn_detected and uturn_reason:
        logger.warning(
            f"[TOTAL-OBEDIENCE v11.10] {symbol}: VETO del detector respetado — {uturn_reason} (Score 99 NO puede pisar esto)"
        )
        return False, uturn_reason, metrics
    
    if uturn_reason == "uturn_top_block_long" and side == 0:
        logger.warning(
            f"[GOLDEN-U-TURN v9.1] {symbol}: TECHO — MA99 subió {uturn_metrics.get('ma99_change_pct', 0):.2f}% y lateraliza. BLOCK LONG."
        )
        return False, "uturn_top_block_long", metrics
    if uturn_detected:
        golden_ctx = (candidate.get("agent_audit_context", {}) or {}).get("golden_uturn", {})
        cement_ok, cement_code = _validate_golden_cement_floor(cp, golden_ctx, symbol)
        if not cement_ok:
            logger.warning(f"[GOLDEN-v9.4] {symbol}: bloqueado en ejecución — {cement_code}")
            return False, cement_code, metrics
        candidate["golden_uturn_mode"] = True
        candidate["confluence_score"] = float(getattr(config, "GOLDEN_UTURN_SCORE", 99.0))
        metrics.update(uturn_metrics)
        logger.info(
            f"[GOLDEN-U-TURN v9.4] {symbol}: Piso de Cemento confirmado — Score=99 bypass activo."
        )

    is_golden = bool(candidate.get("golden_uturn_mode"))

    rsi_14 = float(nexus_features.get("rsi_14", 50) or 50)
    upthrust_detected = bool(nexus_features.get("upthrust_detected", False))
    candle_body_ratio = float(nexus_features.get("candle_body_ratio", 1.0) or 1.0)
    explosion_bearish = bool(nexus_features.get("explosion_bearish", False))
    explosion_bullish = bool(nexus_features.get("explosion_bullish", False))
    consecutive_bull_bars = int(nexus_features.get("consecutive_bull_bars", 0) or 0)
    upper_wick_ratio = float(nexus_features.get("upper_wick_ratio", 0) or 0)
    macd_hist = float(nexus_features.get("macd_histogram", 0) or 0)
    ma7 = float(nexus_features.get("ma7", 0) or 0)
    volume_ratio_20 = float(nexus_features.get("volume_ratio_20", 1.0) or 1.0)
    volume_surge_bullish = bool(nexus_features.get("volume_surge_bullish", False))

    # ── VETO #1: Pump exhaustion (bypass Golden U-Turn — suelo tras caída)
    if not is_golden and side == 0 and explosion_bearish and not explosion_bullish and rsi_14 > 68:
        return False, "pump_exhaust_long", metrics

    # ── VETO #6: RSI Extreme Exhaustion (Parametrizado por Profile) ──────
    # BYPASS: Golden U-Turn v9.0 — un suelo real siempre tiene RSI bajo, no bloquear.
    # BYPASS v11.12: Nexus-15 confianza ≥80% — la IA ya factorizó el RSI en su score.
    #   Si Nexus dice 94.5% con RSI 78, la IA sabe lo que hace. No la contradigamos.
    _nexus_high_conf = float(candidate.get("nexus_confidence", 0) or 0) >= 80.0
    if not candidate.get("golden_uturn_mode") and not _nexus_high_conf:
        if profile:
            max_rsi_long = float(profile.get("maxRsiLong", getattr(config, "MAX_RSI_LONG_LIMIT", 75.0)))
            min_rsi_short = float(profile.get("minRsiShort", 15.0))
        else:
            max_rsi_long = float(getattr(config, "MAX_RSI_LONG_LIMIT", 75.0))
            min_rsi_short = 15.0

        if side == 0 and rsi_14 > max_rsi_long:
            logger.info("[VETO] rsi_extreme — %s | RSI=%.1f > limit=%.1f", candidate.get("symbol"), rsi_14, max_rsi_long)
            return False, "rsi_extreme_exhaustion", metrics

        if side == 1 and rsi_14 < min_rsi_short:
            logger.info("[VETO] rsi_extreme — %s | RSI=%.1f < limit=%.1f", candidate.get("symbol"), rsi_14, min_rsi_short)
            return False, "rsi_extreme_exhaustion", metrics
    elif _nexus_high_conf and not candidate.get("golden_uturn_mode"):
        logger.info(f"[NEXUS-BYPASS v11.12] {symbol}: Nexus={float(candidate.get('nexus_confidence', 0)):.1f}% >= 80% — RSI={rsi_14:.1f} ignorado (la IA ya lo factorizó)")

    # ── VETO #7: MA7 Distance (Parametrizado por Profile) ────────────────
    # BYPASS: Golden U-Turn v9.0 — no importa distancia a MA7, compramos el pivot.
    # BYPASS v11.12: Nexus-15 confianza ≥80% — momentum fuerte = distancia normal.
    if not candidate.get("golden_uturn_mode") and not _nexus_high_conf:
        if profile and ma7 > 0:
            max_dist_pct = float(profile.get("maxMa7DistancePct", 3.5))
            dist_pct = abs(cp - ma7) / ma7 * 100
            if dist_pct > max_dist_pct:
                logger.info("[VETO] ma7_distance — %s | dist=%.2f%% > limit=%.2f%%", candidate.get("symbol"), dist_pct, max_dist_pct)
                return False, "ma7_distance_overextended", metrics

    # ── VETO #8: Ranging sin volumen = trampa ──────────────────────────────
    # Prod 24h: Ranging + sin vol_expl = 0% WR, -7 USDT neto — dinero regalado.
    # v10.1 The Surgical Hook: MIN_VOLUME_RATIO_20 = 0.15 (más permisivo para ranging)
    min_vol_ratio = float(getattr(config, "MIN_VOLUME_RATIO_20", 0.15))
    bridge_regime = str(candidate.get("bridge_regime", "")).lower()
    nexus_regime = str(nexus15_ctx.get("regime", "")).lower() if isinstance(nexus15_ctx, dict) else ""
    regime = bridge_regime or nexus_regime
    
    if not is_golden and "ranging" in regime and not volume_surge_bullish and volume_ratio_20 < min_vol_ratio:
        if getattr(config, "MIN_CONFLUENCE_SCORE", 50.0) > 30.0:
            logger.info(
                "[VETO] ranging_no_momentum — %s | regime=%s vol_ratio=%.2f surge=False",
                candidate.get("symbol"), regime, volume_ratio_20
            )
            return False, "ranging_no_momentum", metrics
        else:
            logger.info("[TESTING] Bypassed ranging_no_momentum veto for %s", candidate.get("symbol"))

    # ── VETO #5: Bearish Rejection at Top (bypass Golden U-Turn) ───────
    if not is_golden and side == 0:
        # Si la mecha superior es > 35% del tamaño total de la vela y el RSI es > 70
        # es una trampa de liquidez. No importa el score de la IA.
        if upper_wick_ratio > 0.35 and rsi_14 > 70:
            logger.info("[VETO] CLIMAX_REJECTION — %s | Wick=%.2f RSI=%.1f", candidate.get("symbol"), upper_wick_ratio, rsi_14)
            return False, "climax_rejection_long", metrics
        
        # Si se detectó Upthrust (patrón de reversión de Wyckoff) y RSI > 70
        if upthrust_detected and rsi_14 > 70:
            logger.info("[VETO] UPTHRUST_REJECTION — %s | Upthrust detected and RSI=%.1f", candidate.get("symbol"), rsi_14)
            return False, "upthrust_rejection", metrics

    if not is_golden and candle_body_ratio < 0.05:
        return False, "no_body_no_trade", metrics

    # Golden U-Turn v9.6 Big Fish: SL = MAYOR entre (low-20velas, 3% bajo entrada)
    if is_golden:
        gu_sl = (
            candidate.get("custom_sl_price")
            or uturn_metrics.get("golden_uturn_sl_5low")
            or (candidate.get("agent_audit_context", {}).get("golden_uturn", {}) or {}).get("sl_5low")
        )
        # v9.6: SL = MAYOR entre (low estructural 20 velas, 3% fijo bajo entrada)
        min_sl_pct = float(getattr(config, "GOLDEN_UTURN_SL_MIN_DISTANCE_PCT", 3.0)) / 100.0
        pct_sl = cp * (1.0 - min_sl_pct)
        # Usar el MAYOR entre el low estructural y el 3% fijo
        if gu_sl and float(gu_sl) > 0:
            final_sl = max(float(gu_sl), pct_sl)
            if final_sl > 0 and final_sl < cp:
                candidate["custom_sl_price"] = final_sl
                sl_dist = (cp - final_sl) / cp * 100
                min_tp = float(getattr(config, "GOLDEN_UTURN_TP_MIN_DISTANCE_PCT", 10.0))
                logger.info(
                    f"[BIG-FISH-RISK] {symbol}: SL={sl_dist:.2f}% bajo entrada (MAYOR entre low-20 y 3%), TP objetivo ≥{min_tp:.1f}%"
                )

    # Volume check only blocks when volume is very weak AND no surge at all
    # BYPASS: Golden U-Turn v9.0 — el volumen suele ser bajo en el suelo exacto.
    # v10.1 The Surgical Hook: MIN_VOLUME_RATIO_20 = 0.15 (mata a CRDOUSDT, permite a UBUSDT)
    # BYPASS: MA Clone, Scalping Clone, Standard Scalping (solo aplican vetos #9+)
    if not _profile_has_veto_bypass(profile):
        min_vol_ratio = float(getattr(config, "MIN_VOLUME_RATIO_20", 0.15))
        if not candidate.get("golden_uturn_mode") and volume_ratio_20 < min_vol_ratio and not volume_surge_bullish:
            if getattr(config, "MIN_CONFLUENCE_SCORE", 50.0) > 30.0:
                logger.info(
                    "[SKIP] no_volume_confirmation — %s | volume_ratio_20=%.2f surge=False",
                    candidate.get("symbol"), volume_ratio_20,
                )
                return False, "no_volume_confirmation", metrics
            else:
                logger.info("[TESTING] Bypassed no_volume_confirmation veto for %s", candidate.get("symbol"))

    # ── VETO #3: Post-Pump/Dump Distance from MA7 ────────────────────────
    # Si el precio ya se alejó >3.5% de la MA7, el movimiento ya ocurrió.
    # Entrar LONG cuando el precio está >3.5% sobre MA7 = comprar el techo.
    # Entrar SHORT cuando el precio está >3.5% bajo MA7 = vender el piso.
    post_pump_threshold = float(profile.get("maxMa7DistancePct", getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035)) / 100.0) if profile else float(getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035))
    if not is_golden and ma7 > 0:
        ma7_distance = (cp - ma7) / ma7  # positivo = precio sobre MA7
        if side == 0 and ma7_distance > post_pump_threshold:
            logger.info(
                "[VETO] post_pump_exhaustion — %s | cp=%.6f MA7=%.6f dist=+%.2f%% (límite=%.1f%%) — LONG después del pump",
                candidate.get("symbol"), cp, ma7, ma7_distance * 100, post_pump_threshold * 100,
            )
            return False, "post_pump_exhaustion", metrics
        if side == 1 and ma7_distance < -post_pump_threshold:
            logger.info(
                "[VETO] post_pump_exhaustion — %s | cp=%.6f MA7=%.6f dist=%.2f%% (límite=%.1f%%) — SHORT después del dump",
                candidate.get("symbol"), cp, ma7, ma7_distance * 100, post_pump_threshold * 100,
            )
            return False, "post_pump_exhaustion", metrics

    # ── VETO #4: Signal Staleness (Nexus) ────────────────────────────────
    # Condión: AND entre edad y drift de precio.
    # Solo rechaza si AMBAS se cumplen: la señal es vieja Y el precio se movió.
    # Si el mercado está quieto, aunque la señal sea vieja, puede seguir válida.
    signal_age_s = float(candidate.get("scored_at_age_s", 0) or 0)
    price_at_signal = float(candidate.get("price_at_signal", 0) or 0)
    max_nexus_age = float(profile.get("maxNexusSignalAgeSeconds", getattr(config, "MAX_NEXUS_SIGNAL_AGE_SECONDS", 120.0))) if profile else float(getattr(config, "MAX_NEXUS_SIGNAL_AGE_SECONDS", 120.0))
    max_drift_pct = float(profile.get("nexusMaxPriceDriftPct", getattr(config, "NEXUS_MAX_PRICE_DRIFT_PCT", 0.025))) if profile else float(getattr(config, "NEXUS_MAX_PRICE_DRIFT_PCT", 0.025))

    if not is_golden and signal_age_s > max_nexus_age and price_at_signal > 0:
        price_drift = abs(cp - price_at_signal) / price_at_signal
        if price_drift > max_drift_pct:
            logger.info(
                "[VETO] stale_nexus_signal — %s | age=%.0fs (máx=%.0fs) drift=%.2f%% (máx=%.1f%%) — señal expirada con precio movido",
                candidate.get("symbol"), signal_age_s, max_nexus_age, price_drift * 100, max_drift_pct * 100,
            )
            return False, "stale_nexus_signal", metrics

    # ── VETO #9: Rango estimado demasiado pequeño ─────────────────────────────
    # Prod 24h: rango <3% = WR neto negativo en todos los buckets.
    #           rango >3.5% = 100% WR, +38 USDT (los 3 trades ganaron todos).
    # Un rango <3% en 15m no tiene recorrido suficiente para cubrir el riesgo.
    estimated_range_pct = float(candidate.get("estimated_range_pct", 0) or 0)
    MIN_RANGE_PCT = float(profile.get("minEstimatedRangePct", getattr(config, "MIN_ESTIMATED_RANGE_PCT", 3.0))) if profile else float(getattr(config, "MIN_ESTIMATED_RANGE_PCT", 3.0))
    if (not is_golden and not _is_direct_injection_candidate(candidate)
            and candidate.get("source") != "nexus_top" and estimated_range_pct < MIN_RANGE_PCT):
        logger.info(
            "[VETO] range_too_small — %s | range=%.2f%% < min=%.1f%%",
            candidate.get("symbol"), estimated_range_pct, MIN_RANGE_PCT
        )
        return False, "range_too_small", metrics

    # ── BONUS SMC Triple: OB + FVG + BOS simultáneos ──────────────
    # En producción: BILLUSDT con este patrón hizo +17.82% ROI en 5h.
    # Priorizar estos setups en el ranking es el siguiente nivel.
    smc_triple = (
        bool(nexus_features.get("order_block_detected", False)) and
        bool(nexus_features.get("fair_value_gap", False)) and
        bool(nexus_features.get("bos_detected", False))
    )

    wyckoff_markup = str(nexus_features.get("wyckoff_phase", "")).lower() == "markup"

    if smc_triple:
        # Agregar metadata al candidate para que el ranking lo priorice
        metrics["smc_triple_confirmed"] = True
        metrics["smc_bonus"] = 5.0  # puntos de bonus a documentar en audit
        if wyckoff_markup:
            metrics["smc_bonus"] = 8.0  # Markup + triple SMC = máxima calidad
        logger.info(
            "[BONUS] smc_triple_confirmed — %s | OB+FVG+BOS | Wyckoff=%s | bonus=+%.1f",
            candidate.get("symbol"),
            nexus_features.get("wyckoff_phase"),
            metrics["smc_bonus"]
        )

    # ── Fin bloqueos duros ────────────────────────────────────────────────

    range_pct = float(candidate.get("estimated_range_pct", 2.0) or 2.0) / 100.0
    tp_dist = range_pct * (float(profile.get("tpMultiplier", config.TP_MULTIPLIER)) if profile else config.TP_MULTIPLIER)
    sl_dist = range_pct * (float(profile.get("slMultiplier", config.SL_MULTIPLIER)) if profile else config.SL_MULTIPLIER)

    if side == 0:
        tp_price = cp * (1 + tp_dist)
        sl_price = cp * (1 - sl_dist)
        risk_w = cp - sl_price
        reward_w = tp_price - cp
        if cp <= sl_price:
            logger.info("[SKIP] nexus invalid_exec_vs_sl cp=%s sl=%s", cp, sl_price)
            return False, "invalid_exec_vs_sl", metrics
    else:
        tp_price = cp * (1 - tp_dist)
        sl_price = cp * (1 + sl_dist)
        risk_w = sl_price - cp
        reward_w = cp - tp_price
        if cp >= sl_price:
            logger.info("[SKIP] nexus invalid_exec_vs_sl cp=%s sl=%s", cp, sl_price)
            return False, "invalid_exec_vs_sl", metrics

    tick = _effective_tick(cp)
    if risk_w <= 0 or reward_w <= tick:
        logger.info("[SKIP] nexus invalid_levels risk=%s reward=%s", risk_w, reward_w)
        return False, "invalid_levels", metrics

    rr = reward_w / risk_w
    metrics["rr"] = round(rr, 4)
    metrics["risk_abs"] = risk_w
    metrics["reward_abs"] = reward_w

    min_rr = float(profile.get("minRR", getattr(config, "MIN_RR_NEXUS", 1.5))) if profile else float(getattr(config, "MIN_RR_NEXUS", 1.5))
    if rr < min_rr:
        logger.info("[SKIP] nexus low_rr rr=%s min=%s", rr, min_rr)
        return False, "low_rr", metrics

    tp_dist_pct = float(profile.get("minTpDistancePct", getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))) if profile else float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))
    pct_tp = cp * tp_dist_pct
    if reward_w < pct_tp:
        logger.info("[SKIP] nexus tp_too_close reward=%s min=%s", reward_w, pct_tp)
        metrics["min_tp_distance_required"] = pct_tp
        return False, "tp_too_close", metrics

    sl_dist_pct = float(profile.get("minSlDistancePct", getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))) if profile else float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
    pct_sl = cp * sl_dist_pct
    if risk_w < pct_sl:
        logger.info("[SKIP] nexus stop_too_tight risk=%s min=%s", risk_w, pct_sl)
        metrics["min_stop_required"] = pct_sl
        return False, "stop_too_tight", metrics

    metrics["sl_distance_pct"] = round(risk_w / cp, 6)
    metrics["risk_pct_used"] = float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))
    return True, "ok", metrics


def validate_pre_trade(
    candidate: dict, current_price: float, profile: dict = None, btc_filter=None, btc_corr=None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Punto único de entrada: LSE (con bloqueo reasoning) o Nexus/SCAR.
    Si se pasa 'profile', usa sus umbrales. Si no, usa config.py (Legacy).
    Si se pasan btc_filter y btc_corr, aplica penalización de correlación BTC.
    """
    global _VALIDATE_FIRST_CALL, _VALIDATE_CALL_COUNT, _VALIDATE_VETO_COUNT, _VALIDATE_PASS_COUNT
    
    _VALIDATE_CALL_COUNT += 1
    symbol = candidate.get("symbol", "?")
    side = int(candidate.get("side", 0))
    
    # ── Log de primera ejecución ──
    if _VALIDATE_FIRST_CALL:
        _VALIDATE_FIRST_CALL = False
        btc_shield = "ACTIVO" if btc_filter else "SIN btc_filter"
        logger.info(
            f"[SetupValidator] >>> PRIMERA EJECUCION v9.5 (DUAL SNIPER) <<< "
            f"| GOLDEN: MA99 ±0.5°/12v, distMA99≤15%, proxMA7≤2% | Nexus min=65% "
            f"| PERFORMANCE: ThreadPoolExecutor (10 workers), MSF fallback, quoteVolume mapping "
            f"| Vetos activos: #1 Pump Exhaustion, #3 Post-Pump MA7, #4 Stale Signal, #5 Climax Rejection, "
            f"#6 RSI Extreme, #7 MA7 Distance, #8 Ranging No Momentum, #9 Range Too Small "
            f"| BTC Shield: {btc_shield} | Symbol={symbol} side={'LONG' if side==0 else 'SHORT'}"
        )
    
    # ── Health Summary cada 10 validaciones ──────────────────────────
    if _VALIDATE_CALL_COUNT % 10 == 0 and _VALIDATE_CALL_COUNT > 0:
        btc_health = btc_filter.get_health_status() if btc_filter else {}
        corr_fallbacks = getattr(btc_corr, '_fallback_count', '?') if btc_corr else '?'
        corr_success = getattr(btc_corr, '_call_count', '?') if btc_corr else '?'
        logger.info(
            f"[SetupValidator] === HEALTH CHECK #{_VALIDATE_CALL_COUNT} === "
            f"| Validaciones: {_VALIDATE_CALL_COUNT} | Vetos: {_VALIDATE_VETO_COUNT} | Pasaron: {_VALIDATE_PASS_COUNT} "
            f"| BTC regime_calls={btc_health.get('regime_calls', '?')} bleeding_calls={btc_health.get('bleeding_calls', '?')} "
            f"errors={btc_health.get('errors', '?')} regime={btc_health.get('current_regime', '?')} "
            f"| Corr: ok={corr_success} fallbacks={corr_fallbacks}"
        )

    # ── VETO GLOBAL: Agotamiento Diario (MAX_DAILY_PUMP/DUMP) ──
    # Si ya subió más del 25% en el día, vetamos LONG. Si cayó más del 30%, vetamos SHORT.
    daily_change_pct = _fetch_24h_price_change_percent(symbol)
    max_daily_pump = float(getattr(config, "MAX_DAILY_PUMP_LONG_LIMIT", 25.0))  # Bajado a 25% para ser más estrictos
    max_daily_dump = float(getattr(config, "MAX_DAILY_DUMP_SHORT_LIMIT", -30.0))

    if side == 0 and daily_change_pct >= max_daily_pump:
        logger.warning(
            f"❌ [VETO-DAILY-PUMP] {symbol} rechazado para LONG. Cambio 24h: {daily_change_pct:.2f}% >= Límite {max_daily_pump}% (Agotamiento del pump)"
        )
        return False, "daily_pump_exhaustion_long", {"daily_change_pct": daily_change_pct, "limit": max_daily_pump}

    if side == 1 and daily_change_pct <= max_daily_dump:
        logger.warning(
            f"❌ [VETO-DAILY-DUMP] {symbol} rechazado para SHORT. Cambio 24h: {daily_change_pct:.2f}% <= Límite {max_daily_dump}% (Agotamiento del dump)"
        )
        return False, "daily_dump_exhaustion_short", {"daily_change_pct": daily_change_pct, "limit": max_daily_dump}

    # ── GOLDEN U-TURN v12.1: DESHABILITADO COMPLETAMENTE ──
    # 2/2 trades reales perdieron. Forzamos is_golden = False siempre.
    is_golden = False
    # Si algún candidato trae golden_uturn_mode, lo limpiamos
    candidate.pop("golden_uturn_mode", None)

    # ── NUEVO VETO: TECHO DE CONFLUENCIA (confluence_ceiling_veto) v12.1 ──
    # Score > 90 correlaciona con pérdida en la muestra actual (3 de 5 perdedores tuvieron 96.6-99).
    # Posible inflado artificial de bonus (SMC, grupos, SCAR) que no refleja condición real.
    # Aplica a TODAS las estrategias (Golden U-Turn ya está deshabilitado).
    confluence_score_for_ceiling = float(candidate.get("confluence_score", 0) or 0)
    if candidate.get("source") != "nexus_top" and confluence_score_for_ceiling > 90:
        logger.warning(
            f"[CONFLUENCE-CEILING v12.1] {symbol}: Score={confluence_score_for_ceiling:.1f} > 90 — VETO. "
            f"Nexus={candidate.get('nexus_confidence', 0):.1f}% | "
            f"Source={candidate.get('source', 'N/A')}"
        )
        return False, "confluence_ceiling_veto", {
            "confluence_score": confluence_score_for_ceiling,
            "nexus_confidence": float(candidate.get("nexus_confidence", 0) or 0),
            "reasoning": f"Score {confluence_score_for_ceiling:.1f} > 90 threshold"
        }

    # ── VETO GLOBAL: Rango Estimado Máximo (MAX_ESTIMATED_RANGE_PCT) ──
    # v11.7: Exclusivo para MA Cross Momentum - las estrategias de scalping operan en volátiles
    estimated_range_pct = float(candidate.get("estimated_range_pct", 0) or 0)
    max_range_pct = float(profile.get("maxEstimatedRangePct", getattr(config, "MAX_ESTIMATED_RANGE_PCT", 7.0))) if profile else float(getattr(config, "MAX_ESTIMATED_RANGE_PCT", 7.0))
    if not is_golden and _is_ma_cross_momentum(profile) and max_range_pct > 0 and estimated_range_pct > max_range_pct:
        logger.info(
            "[VETO] range_too_large — %s | range=%.2f%% > limit=%.1f%% (Evita hiper-volatilidad)",
            symbol, estimated_range_pct, max_range_pct
        )
        return False, "range_too_large", {"estimated_range_pct": estimated_range_pct, "max_limit": max_range_pct}

    # ── FIX A v11.1: VETO DE VOLATILIDAD EXTREMA (THE BARRIER) ──
    # Solo aplica a MA Cross Momentum (NO Golden U-Turn, NO otras estrategias)
    # Golden U-Turn usa SL estructural (low de 5 velas), no basado en rango estimado
    # EPICUSDT (01:48) tenía rango 10.76% y causó -$12.32 en 8 minutos
    # v11.7: Exclusivo para MA Cross Momentum - las estrategias de scalping operan en volátiles
    volatility_barrier_pct = 5.0
    if not is_golden and _is_ma_cross_momentum(profile) and estimated_range_pct > volatility_barrier_pct:
        logger.warning(
            f"[THE-BARRIER] {symbol} RECHAZADO: Volatilidad extrema {estimated_range_pct:.2f}% > {volatility_barrier_pct}% (FIX A v11.7 - MA Cross Momentum only)"
        )
        return False, "volatility_barrier_veto", {"estimated_range_pct": estimated_range_pct, "barrier_limit": volatility_barrier_pct}

    # ── VETO GLOBAL: Stop Loss Porcentual Máximo (MAX_STOP_LOSS_PCT) ──
    # v11.7: Exclusivo para MA Cross Momentum - las estrategias de scalping operan en volátiles
    max_sl_pct = float(profile.get("maxStopLossPct", getattr(config, "MAX_STOP_LOSS_PCT", 4.0))) if profile else float(getattr(config, "MAX_STOP_LOSS_PCT", 4.0))
    
    # Calcular SL % correspondiente
    if candidate.get("source") == "LSE":
        entry_price = float(candidate.get("lse_entry_price", 0) or 0)
        sl_price = float(candidate.get("lse_stop_loss", 0) or 0)
        if entry_price > 0 and sl_price > 0:
            sl_pct = abs(entry_price - sl_price) / entry_price * 100
        else:
            sl_pct = 0.0
    else:
        range_pct = float(candidate.get("estimated_range_pct", 2.0) or 2.0) / 100.0
        sl_dist = range_pct * (float(profile.get("slMultiplier", config.SL_MULTIPLIER)) if profile else config.SL_MULTIPLIER)
        sl_pct = sl_dist * 100

    if _is_ma_cross_momentum(profile) and max_sl_pct > 0 and sl_pct > max_sl_pct:
        logger.info(
            "[VETO] stop_loss_too_expensive — %s | sl_pct=%.2f%% > limit=%.1f%% (Evita stop carísimo)",
            symbol, sl_pct, max_sl_pct
        )
        return False, "stop_loss_too_expensive", {"sl_pct": sl_pct, "max_limit": max_sl_pct}

    # ── VALIDACIONES Y FILTRADO POR TIERS PARA NEXUS / BRIDGE ──
    # Golden U-Turn: bypass total de confluencia/Nexus — la geometría MA99 es la señal
    if is_golden and candidate.get("source") != "LSE":
        return validate_nexus_confluence_setup(candidate, current_price, profile)

    if candidate.get("source") != "LSE":
        # Detectar Tier
        tier = "N/A"
        if symbol in getattr(config, "WATCHLIST_TIER1", []):
            tier = "T1"
        elif symbol in getattr(config, "WATCHLIST_TIER2", []):
            tier = "T2"
        elif symbol in getattr(config, "WATCHLIST_TIER3", []):
            tier = "T3"

        # Regla A: Desactivar Trend Following en Tier 3
        # No aplica a inyección directa: su "nexus_confidence" es una copia
        # del score propio del detector geométrico, no una confianza real de
        # tendencia estilo Nexus — este veto mide otra cosa.
        nexus_conf = float(candidate.get("nexus_confidence", 0) or 0)
        is_trend_following = 60 < nexus_conf <= 80
        if tier == "T3" and is_trend_following and not _is_direct_injection_candidate(candidate):
            logger.info(
                "[VETO] disabled_signal_for_tier — %s | Trend Following desactivado en Tier 3",
                symbol
            )
            return False, "disabled_signal_for_tier", {"tier": tier, "nexus_confidence": nexus_conf}

        confluence_score = float(candidate.get("confluence_score", 0) or 0)

        # ── BTC CORRELATION PENALTY (Capa 3) ──
        # Penalizar score de confluencia cuando BTC está en DUMPING y la alt tiene alta correlación
        raw_confluence_score = confluence_score
        if btc_filter and btc_corr and candidate.get("source") != "LSE":
            btc_regime = btc_filter.get_regime()
            if btc_regime == "DUMPING":
                penalty = btc_corr.get_score_penalty(symbol, btc_regime)
                if penalty < 1.0:
                    confluence_score = raw_confluence_score * penalty
                    logger.info(f"[BTC-CORR] {symbol} nexus penalizado {raw_confluence_score:.1f}→{confluence_score:.1f} (penalty={penalty:.2f} régimen={btc_regime})")
                    # Actualizar el candidate con el score penalizado para validaciones subsiguientes
                    candidate["confluence_score"] = confluence_score

        # Regla de Oro (Veto Dinámico de Volatilidad / Confluencia):
        # v11.7: Exclusivo para MA Cross Momentum - las estrategias de scalping operan en volátiles
        vol_threshold = float(getattr(config, "HIGH_VOLATILITY_RANGE_THRESHOLD", 7.0))
        if _is_ma_cross_momentum(profile) and estimated_range_pct >= vol_threshold:
            high_vol_min_conf = float(profile.get("highVolMinConfluence", getattr(config, "HIGH_VOLATILITY_MIN_CONFLUENCE", 90.0))) if profile else float(getattr(config, "HIGH_VOLATILITY_MIN_CONFLUENCE", 90.0))
            if confluence_score < high_vol_min_conf:
                logger.info(
                    "[VETO] high_volatility_low_confluence — %s | Range=%.2f%% >= %.1f%% requires confluence >= %.1f (has %.1f)",
                    symbol, estimated_range_pct, vol_threshold, high_vol_min_conf, confluence_score
                )
                return False, "high_volatility_low_confluence", {
                    "confluence_score": confluence_score,
                    "min_limit": high_vol_min_conf,
                    "estimated_range_pct": estimated_range_pct
                }
        else:
            # Rango estándar (< 7%): Validar contra el piso correspondiente
            # Regla B: Subir MIN_CONFLUENCE_SCORE a 65.0 exclusivamente para Tier 3
            tier3_min_conf = float(profile.get("tier3MinConfluenceScore", getattr(config, "TIER3_MIN_CONFLUENCE_SCORE", 65.0))) if profile else float(getattr(config, "TIER3_MIN_CONFLUENCE_SCORE", 65.0))
            if tier == "T3" and confluence_score < tier3_min_conf:
                logger.info(
                    "[VETO] low_confluence_for_tier3 — %s | Score=%.1f < limit=%.1f en Tier 3",
                    symbol, confluence_score, tier3_min_conf
                )
                return False, "low_confluence_for_tier3", {"confluence_score": confluence_score, "min_limit": tier3_min_conf}

            # Regla C: Filtro estándar general para Tier 1 y 2
            std_min_conf = float(profile.get("minConfluenceScore", getattr(config, "MIN_CONFLUENCE_SCORE", 60.0))) if profile else float(getattr(config, "MIN_CONFLUENCE_SCORE", 60.0))
            if confluence_score < std_min_conf:
                logger.info(
                    "[VETO] low_confluence — %s | Score=%.1f < limit=%.1f",
                    symbol, confluence_score, std_min_conf
                )
                return False, "low_confluence", {"confluence_score": confluence_score, "min_limit": std_min_conf}

    if candidate.get("source") == "LSE":
        if lse_reasoning_blocks_trade(candidate):
            return False, "lse_warning_block", {}
        return validate_lse_setup(candidate, current_price, profile)

    return validate_nexus_confluence_setup(candidate, current_price, profile)
