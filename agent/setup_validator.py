"""
Validación previa a ejecución: LSE (niveles estructurales) y Nexus/SCAR (rango estimado).
Devuelve métricas para auditoría / trade_analytics.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Tuple

import config

logger = logging.getLogger("SetupValidator")


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
    candidate: dict, current_price: float, profile: dict = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Punto único de entrada: LSE (con bloqueo reasoning) o Nexus/SCAR.
    Si se pasa 'profile', usa sus umbrales. Si no, usa config.py (Legacy).
    """
    symbol = candidate.get("symbol", "?")

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
