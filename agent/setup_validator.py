"""
Validación previa a ejecución: LSE (niveles estructurales) y Nexus/SCAR (rango estimado).
Devuelve métricas para auditoría / trade_analytics.
"""
from __future__ import annotations

import logging
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
    for line in _normalize_reasons(candidate):
        if needle in line.lower():
            return True
    return False


def validate_lse_setup(
    candidate: dict,
    current_price: float,
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

        min_rr = float(getattr(config, "MIN_RR_DEFAULT", 1.5))
        dm = str(candidate.get("lse_detection_mode") or "").lower()
        if dm == "aggressive":
            min_rr = float(getattr(config, "MIN_RR_AGGRESSIVE_LSE", 2.0))

        if rr < min_rr:
            logger.info("[SKIP] low_rr rr=%s min_rr=%s mode=%s", rr, min_rr, dm)
            return False, "low_rr", metrics

        atr_f = float(atr) if atr is not None else 0.0
        pct_tp_floor = entry_f * float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))
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

        pct_floor = entry_f * float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
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
        max_slip = float(getattr(config, "MAX_ENTRY_SLIPPAGE_PCT", 0.002))
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
    candidate: dict,
    current_price: float,
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

    range_pct = float(candidate.get("estimated_range_pct", 2.0) or 2.0) / 100.0
    tp_dist = range_pct * config.TP_MULTIPLIER
    sl_dist = range_pct * config.SL_MULTIPLIER

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

    min_rr = float(getattr(config, "MIN_RR_NEXUS", getattr(config, "MIN_RR_DEFAULT", 1.5)))
    if rr < min_rr:
        logger.info("[SKIP] nexus low_rr rr=%s min=%s", rr, min_rr)
        return False, "low_rr", metrics

    pct_tp = cp * float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))
    if reward_w < pct_tp:
        logger.info("[SKIP] nexus tp_too_close reward=%s min=%s", reward_w, pct_tp)
        metrics["min_tp_distance_required"] = pct_tp
        return False, "tp_too_close", metrics

    pct_sl = cp * float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
    if risk_w < pct_sl:
        logger.info("[SKIP] nexus stop_too_tight risk=%s min=%s", risk_w, pct_sl)
        metrics["min_stop_required"] = pct_sl
        return False, "stop_too_tight", metrics

    metrics["sl_distance_pct"] = round(risk_w / cp, 6)
    metrics["risk_pct_used"] = float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))
    return True, "ok", metrics


def validate_pre_trade(
    candidate: dict,
    current_price: float,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Punto único de entrada: LSE (con bloqueo reasoning) o Nexus/SCAR."""
    if candidate.get("source") == "LSE":
        if lse_reasoning_blocks_trade(candidate):
            return False, "lse_warning_block", {}
        return validate_lse_setup(candidate, current_price)
    return validate_nexus_confluence_setup(candidate, current_price)
