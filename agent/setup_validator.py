"""
Validación previa a ejecución: LSE (niveles estructurales) y Nexus/SCAR (rango estimado).
Devuelve métricas para auditoría / trade_analytics.
"""
from __future__ import annotations

import logging
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
    metrics: Dict[str, Any] = {}

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
    metrics: Dict[str, Any] = {"pipeline": "nexus_scar"}
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

    # ── VETO #1: Pump exhaustion
    if side == 0 and explosion_bearish and not explosion_bullish and rsi_14 > 68:
        return False, "pump_exhaust_long", metrics

    # ── VETO #6: RSI Extreme Exhaustion (Parametrizado por Profile) ──────
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

    # ── VETO #7: MA7 Distance (Parametrizado por Profile) ────────────────
    if profile and ma7 > 0:
        max_dist_pct = float(profile.get("maxMa7DistancePct", 3.5))
        dist_pct = abs(cp - ma7) / ma7 * 100
        if dist_pct > max_dist_pct:
            logger.info("[VETO] ma7_distance — %s | dist=%.2f%% > limit=%.2f%%", candidate.get("symbol"), dist_pct, max_dist_pct)
            return False, "ma7_distance_overextended", metrics

    # ── VETO #8: Ranging sin volumen = trampa ──────────────────────────────
    # Prod 24h: Ranging + sin vol_expl = 0% WR, -7 USDT neto — dinero regalado.
    # Solo pasa si volume_ratio_20 >= 2.0 (doble del promedio confirma movimiento).
    bridge_regime = str(candidate.get("bridge_regime", "")).lower()
    nexus_regime = str(nexus15_ctx.get("regime", "")).lower() if isinstance(nexus15_ctx, dict) else ""
    regime = bridge_regime or nexus_regime

    if "ranging" in regime and not volume_surge_bullish and volume_ratio_20 < 2.0:
        if getattr(config, "MIN_CONFLUENCE_SCORE", 50.0) > 30.0:
            logger.info(
                "[VETO] ranging_no_momentum — %s | regime=%s vol_ratio=%.2f surge=False",
                candidate.get("symbol"), regime, volume_ratio_20
            )
            return False, "ranging_no_momentum", metrics
        else:
            logger.info("[TESTING] Bypassed ranging_no_momentum veto for %s", candidate.get("symbol"))

    # ── VETO #5: Bearish Rejection at Top ──────────────────────────────
    if side == 0:
        # Si la mecha superior es > 35% del tamaño total de la vela y el RSI es > 70
        # es una trampa de liquidez. No importa el score de la IA.
        if upper_wick_ratio > 0.35 and rsi_14 > 70:
            logger.info("[VETO] CLIMAX_REJECTION — %s | Wick=%.2f RSI=%.1f", candidate.get("symbol"), upper_wick_ratio, rsi_14)
            return False, "climax_rejection_long", metrics
        
        # Si se detectó Upthrust (patrón de reversión de Wyckoff) y RSI > 70
        if upthrust_detected and rsi_14 > 70:
            logger.info("[VETO] UPTHRUST_REJECTION — %s | Upthrust detected and RSI=%.1f", candidate.get("symbol"), rsi_14)
            return False, "upthrust_rejection", metrics

    if candle_body_ratio < 0.05:
        return False, "no_body_no_trade", metrics

    # ── VETO #12: Volume Floor (Liquidez Mínima) ─────────────────────────────
    # Si el volumen es < 80% del promedio, la moneda está "muerta".
    # Entrar ahí es regalar plata al spread. Cualquier movimiento pequeño liquida.
    # USUSDT ejemplo: VolumeRatio 0.0045 = 0.4% del promedio → trade liquidado al instante.
    if volume_ratio_20 < 0.80:
        _VALIDATE_VETO_COUNT += 1
        logger.warning(
            f"❌ [VETO-12-VOLUME-FLOOR] Bloqueando trade en {symbol}. "
            f"VolumeRatio20={volume_ratio_20:.4f} < 0.80 (80% del promedio). "
            f"Moneda sin liquidez - spread te liquida. "
            f"(veto #{_VALIDATE_VETO_COUNT} total)"
        )
        return False, "volume_floor_insufficient", {"volume_ratio_20": volume_ratio_20, "min_required": 0.80}

    # Volume check only blocks when volume is very weak AND no surge at all
    if volume_ratio_20 < 0.8 and not volume_surge_bullish:
        if getattr(config, "MIN_CONFLUENCE_SCORE", 50.0) > 30.0:
            logger.info(
                "[SKIP] no_volume_confirmation — %s | volume_ratio_20=%.2f surge=False",
                candidate.get("symbol"), volume_ratio_20,
            )
            return False, "no_volume_confirmation", metrics
        else:
            logger.info("[TESTING] Bypassed no_volume_confirmation veto for %s", candidate.get("symbol"))

    # ── VETO #13: Technical Floor (Confluencia Orgánica) ──────────────────────
    # No importa si Nexus tiene 99% de confianza. Si los grupos técnicos (SMC, PA, Vol)
    # son un desastre (< 40 puntos promedio), el trade es una timba.
    # USUSDT ejemplo: PA=18.6, SMC=20, Vol=19.9 → promedio ~19 → trade liquidado.
    group_scores = candidate.get("group_scores", {})
    if group_scores:
        pa_score = float(group_scores.get("g1_price_action", 0) or 0)
        smc_score = float(group_scores.get("g2_smc_ict", 0) or 0)
        vol_score = float(group_scores.get("g5_volume", 0) or 0)
        
        # Solo aplicar si los 3 scores están disponibles (no son 0)
        if pa_score > 0 and smc_score > 0 and vol_score > 0:
            tech_avg = (pa_score + smc_score + vol_score) / 3.0
            if tech_avg < 40.0:
                _VALIDATE_VETO_COUNT += 1
                logger.warning(
                    f"❌ [VETO-13-TECH-FLOOR] Bloqueando trade en {symbol}. "
                    f"Promedio técnico (PA+SMC+Vol)/3 = {tech_avg:.1f} < 40.0. "
                    f"PA={pa_score:.1f}, SMC={smc_score:.1f}, Vol={vol_score:.1f}. "
                    f"Estructura técnica de mierda - IA fanática ignorando realidad. "
                    f"(veto #{_VALIDATE_VETO_COUNT} total)"
                )
                return False, "technical_floor_insufficient", {
                    "pa_score": pa_score,
                    "smc_score": smc_score,
                    "vol_score": vol_score,
                    "tech_avg": tech_avg,
                    "min_required": 40.0
                }
    # ── VETO #3: Post-Pump/Dump Distance from MA7 ────────────────────────
    # Si el precio ya se alejó >3.5% de la MA7, el movimiento ya ocurrió.
    # Entrar LONG cuando el precio está >3.5% sobre MA7 = comprar el techo.
    # Entrar SHORT cuando el precio está >3.5% bajo MA7 = vender el piso.
    post_pump_threshold = float(profile.get("maxMa7DistancePct", getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035)) / 100.0) if profile else float(getattr(config, "POST_PUMP_MA7_DISTANCE_PCT", 0.035))
    if ma7 > 0:
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

    if signal_age_s > max_nexus_age and price_at_signal > 0:
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
    if estimated_range_pct < MIN_RANGE_PCT:
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
    
    # ── Log de primera ejecución: confirma que los VETOS NUEVOS están activos ──
    if _VALIDATE_FIRST_CALL:
        _VALIDATE_FIRST_CALL = False
        btc_shield = "ACTIVO" if btc_filter else "SIN btc_filter"
        corr_block = "ACTIVO" if (btc_filter and btc_corr) else "SIN btc_corr"
        bleed_threshold = getattr(config, "BTC_BLEED_1H_THRESHOLD", "?")
        hard_block_corr = getattr(config, "BTC_CORR_HARD_BLOCK_THRESHOLD", "?")
        ceiling_threshold = getattr(config, "BTC_RED_ALT_CEILING_PCT", 12.0)
        logger.info(
            f"[SetupValidator] >>> PRIMERA EJECUCION v5.2 <<< "
            f"| VETO #10 BTC Blood Shield: {btc_shield} (umbral {bleed_threshold}%/1h) "
            f"| VETO #11 Dynamic Ceiling: {btc_shield} (BTC ROJO=12%, BTC VERDE=22% + Room to Breathe) "
            f"| VETO #11.1 Insufficient Upside: {btc_shield} (espacio restante < TP necesario) "
            f"| VETO #12 Volume Floor: ACTIVO (VolumeRatio20 < 0.80 = moneda muerta) "
            f"| VETO #13 Technical Floor: ACTIVO (PA+SMC+Vol promedio < 40 = estructura de mierda) "
            f"| BTC DUMPING hard block: {corr_block} (corr>={hard_block_corr}) "
            f"| Symbol={symbol} side={'LONG' if side==0 else 'SHORT'}"
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

    # ── VETO GLOBAL: Rango Estimado Máximo (MAX_ESTIMATED_RANGE_PCT) ──
    estimated_range_pct = float(candidate.get("estimated_range_pct", 0) or 0)
    max_range_pct = float(profile.get("maxEstimatedRangePct", getattr(config, "MAX_ESTIMATED_RANGE_PCT", 7.0))) if profile else float(getattr(config, "MAX_ESTIMATED_RANGE_PCT", 7.0))
    if max_range_pct > 0 and estimated_range_pct > max_range_pct:
        logger.info(
            "[VETO] range_too_large — %s | range=%.2f%% > limit=%.1f%% (Evita hiper-volatilidad)",
            symbol, estimated_range_pct, max_range_pct
        )
        return False, "range_too_large", {"estimated_range_pct": estimated_range_pct, "max_limit": max_range_pct}

    # ── VETO GLOBAL: Stop Loss Porcentual Máximo (MAX_STOP_LOSS_PCT) ──
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

    if max_sl_pct > 0 and sl_pct > max_sl_pct:
        logger.info(
            "[VETO] stop_loss_too_expensive — %s | sl_pct=%.2f%% > limit=%.1f%% (Evita stop carísimo)",
            symbol, sl_pct, max_sl_pct
        )
        return False, "stop_loss_too_expensive", {"sl_pct": sl_pct, "max_limit": max_sl_pct}

    # ── VALIDACIONES Y FILTRADO POR TIERS PARA NEXUS / BRIDGE ──
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
        nexus_conf = float(candidate.get("nexus_confidence", 0) or 0)
        is_trend_following = 60 < nexus_conf <= 80
        if tier == "T3" and is_trend_following:
            logger.info(
                "[VETO] disabled_signal_for_tier — %s | Trend Following desactivado en Tier 3",
                symbol
            )
            return False, "disabled_signal_for_tier", {"tier": tier, "nexus_confidence": nexus_conf}

        confluence_score = float(candidate.get("confluence_score", 0) or 0)

        # ── VETO #10: BTC BLOOD SHIELD (HARD VETO) ──────────────────────────
        # Si BTC está sangrando >1% en 1h, BLOQUEO TOTAL de LONGs.
        # No importa cuán bueno sea el setup de la altcoin.
        # Este veto previene la repetición de la pérdida de 20 USDT del 1/6/2026
        # donde BTC cayó de 73k a 71k gradualmente y el bot abrió 14 LONGs.
        if btc_filter and side == 0:
            is_bleeding, btc_pct_1h = btc_filter.is_btc_bleeding()
            if is_bleeding:
                _VALIDATE_VETO_COUNT += 1
                logger.warning(
                    f"❌ [VETO-BTC-BLOOD] Bloqueando LONG en {symbol}. "
                    f"BTC sangrando {btc_pct_1h:.2f}% en 1h. "
                    f"NO importa la confluencia del setup. "
                    f"(veto #{_VALIDATE_VETO_COUNT} total)"
                )
                return False, "btc_bleeding_1h", {"btc_dump_1h": btc_pct_1h}

        # ── VETO #11: DYNAMIC CEILING (BTC STATE + ALT EXHAUSTION) ─────────────
        # Techo dinámico según el estado de BTC:
        # - Si BTC daily es ROJO: techo = 12% (mercado bajista, alts agotadas rápido)
        # - Si BTC daily es VERDE: techo = 22% (mercado alcista, alts pueden correr más)
        # Esto permite capturar "Home Runs" (+30-40%) cuando BTC acompaña,
        # pero sigue protegiendo de techos cuando BTC está en rojo.
        #
        # VETO #11.1: ROOM TO BREATHE (Espacio para respirar)
        # Validamos que haya espacio suficiente para el TP.
        # Si el espacio restante hasta el techo es menor al TP que necesita la estrategia,
        # el trade se anula por "insufficient_upside_for_ceiling".
        if btc_filter and side == 0:
            btc_daily_red, btc_daily_open, btc_current = btc_filter.is_btc_daily_red()
            alt_24h_low = _fetch_24h_low_price(symbol)
            if alt_24h_low > 0:
                alt_move_from_low = ((current_price - alt_24h_low) / alt_24h_low) * 100

                # Techo dinámico según estado de BTC
                if btc_daily_red:
                    ceiling_threshold = float(getattr(config, "BTC_RED_ALT_CEILING_PCT", 12.0))
                    btc_state = "ROJA"
                else:
                    ceiling_threshold = float(getattr(config, "BTC_GREEN_ALT_CEILING_PCT", 22.0))
                    btc_state = "VERDE"

                # Calcular el TP que la estrategia necesita (en porcentaje)
                target_tp_pct = 0.0
                if candidate.get("source") == "LSE":
                    # Para LSE: TP2 es el take profit objetivo
                    lse_entry = float(candidate.get("lse_entry_price", 0) or 0)
                    lse_tp2 = float(candidate.get("lse_take_profit_2", 0) or 0)
                    if lse_entry > 0 and lse_tp2 > 0:
                        target_tp_pct = ((lse_tp2 - lse_entry) / lse_entry) * 100
                else:
                    # Para Nexus/SCAR: TP se calcula del rango estimado
                    estimated_range_pct = float(candidate.get("estimated_range_pct", 2.0) or 2.0)
                    tp_multiplier = float(profile.get("tpMultiplier", config.TP_MULTIPLIER)) if profile else config.TP_MULTIPLIER
                    target_tp_pct = estimated_range_pct * tp_multiplier

                # Espacio restante hasta el techo de cristal
                remaining_upside = ceiling_threshold - alt_move_from_low

                # VETO #11: Si ya pasó el techo absoluto
                if alt_move_from_low > ceiling_threshold:
                    _VALIDATE_VETO_COUNT += 1
                    logger.warning(
                        f"❌ [VETO-DYNAMIC-CEILING] Bloqueando LONG en {symbol}. "
                        f"BTC vela diaria {btc_state} (open={btc_daily_open:.2f}, close={btc_current:.2f}). "
                        f"Alt subió {alt_move_from_low:.2f}% desde low 24h (límite={ceiling_threshold}%). "
                        f"Agotamiento extremo - techo dinámico según estado BTC. "
                        f"(veto #{_VALIDATE_VETO_COUNT} total)"
                    )
                    return False, "dynamic_ceiling_exhaustion", {
                        "btc_daily_open": btc_daily_open,
                        "btc_current": btc_current,
                        "btc_state": btc_state,
                        "alt_move_from_low": alt_move_from_low,
                        "ceiling_threshold": ceiling_threshold
                    }

                # VETO #11.1: Si no hay espacio suficiente para el TP (Room to Breathe)
                if remaining_upside < target_tp_pct:
                    _VALIDATE_VETO_COUNT += 1
                    logger.warning(
                        f"❌ [VETO-CEILING-SPACE] Bloqueando LONG en {symbol}. "
                        f"BTC vela diaria {btc_state}. Espacio restante ({remaining_upside:.2f}%) menor al TP necesario ({target_tp_pct:.2f}%). "
                        f"Alt ya subió {alt_move_from_low:.2f}% desde low 24h (techo={ceiling_threshold}%). "
                        f"No hay room to breathe - trade nace asfixiado. "
                        f"(veto #{_VALIDATE_VETO_COUNT} total)"
                    )
                    return False, "insufficient_upside_for_ceiling", {
                        "btc_daily_open": btc_daily_open,
                        "btc_current": btc_current,
                        "btc_state": btc_state,
                        "alt_move_from_low": alt_move_from_low,
                        "ceiling_threshold": ceiling_threshold,
                        "remaining_upside": remaining_upside,
                        "target_tp_pct": target_tp_pct
                    }

        # ── BTC CORRELATION PENALTY (Capa 3) — AHORA CON BLOQUEO DURO ──
        # Si BTC está en DUMPING y la alt tiene alta correlación:
        #   - correlación > 0.8 → BLOQUEO TOTAL (veto duro, no solo penalización)
        #   - correlación > 0.6 → penalización del score
        raw_confluence_score = confluence_score
        if btc_filter and btc_corr and candidate.get("source") != "LSE":
            btc_regime = btc_filter.get_regime()
            if btc_regime == "DUMPING":
                correlation = btc_corr.get_correlation(symbol)
                penalty = btc_corr.get_score_penalty(symbol, btc_regime)
                
                # HARD BLOCK: Correlación alta + BTC DUMPING = veto absoluto
                btc_hard_block_threshold = float(getattr(config, "BTC_CORR_HARD_BLOCK_THRESHOLD", 0.75))
                if side == 0 and correlation >= btc_hard_block_threshold:
                    logger.warning(
                        f"❌ [VETO-BTC-DUMPING-HIGH-CORR] Bloqueando LONG en {symbol}. "
                        f"BTC en DUMPING + correlación {correlation:.3f} >= {btc_hard_block_threshold}. "
                        f"Las alts correlacionadas CAEN con BTC."
                    )
                    return False, "btc_dumping_high_correlation", {
                        "btc_regime": btc_regime, 
                        "correlation": correlation,
                        "threshold": btc_hard_block_threshold
                    }
                
                if penalty < 1.0:
                    confluence_score = raw_confluence_score * penalty
                    logger.info(f"[BTC-CORR] {symbol} nexus penalizado {raw_confluence_score:.1f}→{confluence_score:.1f} (penalty={penalty:.2f} régimen={btc_regime})")
                    # Actualizar el candidate con el score penalizado para validaciones subsiguientes
                    candidate["confluence_score"] = confluence_score

        # Regla de Oro (Veto Dinámico de Volatilidad / Confluencia):
        vol_threshold = float(getattr(config, "HIGH_VOLATILITY_RANGE_THRESHOLD", 7.0))
        if estimated_range_pct >= vol_threshold:
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
