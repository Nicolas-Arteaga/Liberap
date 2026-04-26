"""
SCAR Detector — Core engine. Evaluates the 5 signals and computes SCORE_GRIAL.
Persists results to SQLite. Thread-safe for concurrent FastAPI requests.
"""
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict

from .schemas import ScarResultDto, ScarFlagDetail
from .proxies import (
    detect_whale_withdrawal_proxy,
    detect_supply_drying_proxy,
    detect_price_stable,
    detect_negative_funding,
    detect_silence,
)
from . import data_store

logger = logging.getLogger("SCAR_DETECTOR")

# Prediction thresholds
PUMP_IMMINENT_SCORE = 4
MONITORING_SCORE    = 2


def _predict(score: int, withdrawal_days: int, template: Optional[Dict]) -> tuple[str, Optional[int]]:
    """Returns (prediction_text, estimated_hours)."""
    if score >= PUMP_IMMINENT_SCORE:
        if template and template.get("avg_withdrawal_days"):
            avg_days = template["avg_withdrawal_days"]
            days_remaining = max(0, avg_days - withdrawal_days)
            if days_remaining <= 1:
                return "PUMP INMINENTE (cualquier momento)", 12
            return f"PUMP en ~{int(days_remaining)} día(s)", int(days_remaining * 24)
        return "PUMP INMINENTE en 24-72hs", 48

    if score >= MONITORING_SCORE:
        return "En monitoreo — acumulando señales", None

    return "Sin señal activa", None


def analyze_symbol(symbol: str, external_funding: Optional[float] = None) -> Optional[ScarResultDto]:
    """
    Run all 5 signals for a single symbol and return a ScarResultDto.
    Returns None if the symbol is invalid or all API calls fail.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        # ── Signal 1: Whale Withdrawal Proxy ──────────────────────────────
        s1, s1_reason, s1_val = detect_whale_withdrawal_proxy(symbol)

        # ── Signal 2: Supply Drying Proxy ──────────────────────────────────
        s2, s2_reason, s2_val = detect_supply_drying_proxy(symbol)

        # ── Signal 3: Price Stability ──────────────────────────────────────
        s3, s3_reason, s3_val = detect_price_stable(symbol)

        # ── Signal 4: Negative Funding Rate ───────────────────────────────
        s4, s4_reason, s4_val = detect_negative_funding(symbol, external_rate=external_funding)

        # ── Signal 5: Volume Silence ──────────────────────────────────────
        s5, s5_reason, s5_val = detect_silence(symbol)

        # ── Score ─────────────────────────────────────────────────────────
        score = sum([s1, s2, s3, s4, s5])

        # Pull historical template for this token (create default if missing)
        template = data_store.get_template_or_default(symbol)

        # Count consecutive withdrawal days from history
        history = data_store.get_history(symbol, days=14)
        withdrawal_days = sum(1 for h in history if h.get("flag_whale_withdrawal"))

        prediction, est_hours = _predict(score, withdrawal_days, template)

        # ── Persist ───────────────────────────────────────────────────────
        data_store.upsert_daily_signal(
            symbol=symbol,
            flag_whale=s1, flag_supply=s2,
            flag_price=s3, flag_funding=s4, flag_silence=s5,
            score=score, prediction=prediction
        )

        # Days since last pump (from template)
        days_since_pump = None
        next_window = None
        if template and template.get("last_pump_date"):
            try:
                last = datetime.fromisoformat(template["last_pump_date"])
                days_since_pump = (datetime.now() - last).days
                if template.get("avg_withdrawal_days"):
                    nxt = days_since_pump + int(template["avg_withdrawal_days"])
                    next_window = f"~{nxt} días desde el último pump"
            except Exception:
                pass

        return ScarResultDto(
            symbol=symbol,
            score_grial=score,
            prediction=prediction,
            estimated_hours=est_hours,
            flag_whale_withdrawal=s1,
            flag_supply_drying=s2,
            flag_price_stable=s3,
            flag_funding_negative=s4,
            flag_silence=s5,
            detail_whale_withdrawal=ScarFlagDetail(triggered=s1, reason=s1_reason, value=s1_val),
            detail_supply_drying=ScarFlagDetail(triggered=s2, reason=s2_reason, value=s2_val),
            detail_price_stable=ScarFlagDetail(triggered=s3, reason=s3_reason, value=s3_val),
            detail_funding_negative=ScarFlagDetail(triggered=s4, reason=s4_reason, value=s4_val),
            detail_silence=ScarFlagDetail(triggered=s5, reason=s5_reason, value=s5_val),
            days_since_last_pump=days_since_pump,
            estimated_next_window=next_window,
            withdrawal_days_count=withdrawal_days,
            total_withdrawn_usd=0.0,   # Only available with on-chain data
            mode="degraded",
            analyzed_at=now,
        )

    except Exception as e:
        logger.error("❌ SCAR analyze_symbol error for %s: %s", symbol, e)
        return None


def scan_symbols(symbols: List[str], funding_rates: Optional[Dict[str, float]] = None,
                 max_workers: int = 6) -> List[ScarResultDto]:
    """
    Scan a list of symbols concurrently.
    Returns results sorted by score_grial descending.
    """
    funding_rates = funding_rates or {}
    results: List[ScarResultDto] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(analyze_symbol, sym, funding_rates.get(sym)): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logger.error("SCAR scan error for %s: %s", sym, e)

    results.sort(key=lambda r: r.score_grial, reverse=True)
    logger.info("✅ SCAR scan complete: %d/%d symbols processed", len(results), len(symbols))
    return results
