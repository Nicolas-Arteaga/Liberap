"""
LSE Detector — Motor principal del LiquiditySweepEngine.

Secuencia de detección:
  1. Compresión MA25/MA99 (pendiente plana + distancia dinámica)
  2. Nivel de soporte validado (equal lows con tolerancia ATR)
  3. Sweep real (mecha + cierre por encima + volumen spike)
  4. Reclaim (cierre sobre nivel roto + MA7 o MA25)
  5. Filtro HTF 4H (evita longs en bearish estructural)
  6. Filtro ATR (evita entrar en caos)
  7. Scoring dinámico (65/100 mínimo)
"""
import logging
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from .models import (
    CandleInput,
    LSESignal,
    LSESubScores,
    LSEState,
    LSEEntryMode,
    LSEDetectionMode,
)
from .config import LSESymbolConfig, get_config
from .state_machine import LSEStateMachine

logger = logging.getLogger("LSE_DETECTOR")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_arrays(candles: List[CandleInput]):
    """Convierte lista de CandleInput a arrays numpy."""
    opens  = np.array([c.open   for c in candles], dtype=float)
    highs  = np.array([c.high   for c in candles], dtype=float)
    lows   = np.array([c.low    for c in candles], dtype=float)
    closes = np.array([c.close  for c in candles], dtype=float)
    vols   = np.array([c.volume for c in candles], dtype=float)
    return opens, highs, lows, closes, vols


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    """EMA simple sin dependencias externas."""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(series)
    result[0] = series[0]
    for i in range(1, len(series)):
        result[i] = alpha * series[i] + (1 - alpha) * result[i - 1]
    return result


def _sma(series: np.ndarray, period: int) -> np.ndarray:
    """SMA con padding NaN para los primeros valores."""
    result = np.full_like(series, np.nan)
    for i in range(period - 1, len(series)):
        result[i] = series[i - period + 1 : i + 1].mean()
    return result


def _atr(highs, lows, closes, period=14) -> np.ndarray:
    """ATR (Average True Range)."""
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        ),
    )
    tr = np.concatenate([[highs[0] - lows[0]], tr])
    return _sma(tr, period)


def _slope_pct_per_candle(series: np.ndarray, window: int) -> float:
    """Pendiente relativa media por vela en las últimas `window` velas."""
    if len(series) < window + 1:
        return 1.0  # no hay datos suficientes → no comprimido
    segment = series[-window:]
    if segment[0] == 0:
        return 1.0
    total_change = abs(segment[-1] - segment[0]) / abs(segment[0])
    return total_change / window  # cambio porcentual por vela


# ---------------------------------------------------------------------------
# Sub-detectors
# ---------------------------------------------------------------------------

def _compression_snapshot_at(
    ma25: np.ndarray,
    ma99: np.ndarray,
    closes: np.ndarray,
    cfg: LSESymbolConfig,
    end_idx: int,
) -> Tuple[bool, float, float]:
    """
    Evalúa compresión MA25/MA99 usando datos hasta end_idx (inclusive).
    """
    w = cfg.compression_slope_window
    if end_idx < w or end_idx >= len(closes):
        return False, 0.0, 0.0

    m25 = ma25[: end_idx + 1]
    m99 = ma99[: end_idx + 1]

    slope25 = _slope_pct_per_candle(m25, w)
    slope99 = _slope_pct_per_candle(m99, w)

    price = closes[end_idx]
    if price == 0:
        return False, 0.0, 0.0

    dist_pct = abs(ma25[end_idx] - ma99[end_idx]) / price

    flat25 = slope25 < cfg.compression_slope_max
    flat99 = slope99 < cfg.compression_slope_max
    close_enough = dist_pct < cfg.compression_threshold_pct

    compressed = flat25 and flat99 and close_enough

    score = 0.0
    if compressed:
        closeness_ratio = max(0.0, 1.0 - dist_pct / cfg.compression_threshold_pct)
        flatness = max(0.0, 1.0 - (slope25 + slope99) / (2 * cfg.compression_slope_max))
        score = 20.0 * 0.5 * (closeness_ratio + flatness)

    return compressed, round(score, 2), round(dist_pct * 100, 4)


def _detect_compression(
    ma25: np.ndarray,
    ma99: np.ndarray,
    closes: np.ndarray,
    cfg: LSESymbolConfig,
) -> Tuple[bool, float, float]:
    """
    Compresión en la última vela cerrada, o en ventana reciente si hubo compresión antes del sweep.
    """
    if len(ma25) < cfg.compression_slope_window + 1:
        return False, 0.0, 0.0

    last_idx = len(closes) - 2  # penúltima = última cerrada si la última está formándose
    if last_idx < cfg.compression_slope_window:
        last_idx = len(closes) - 1

    ok, score, pct = _compression_snapshot_at(ma25, ma99, closes, cfg, last_idx)
    if ok:
        return True, score, pct

    lb = getattr(cfg, "compression_recent_lookback", 56)
    best_score = 0.0
    best_pct = 0.0
    found = False
    start = max(cfg.compression_slope_window, len(closes) - lb - 1)
    for end_idx in range(len(closes) - 2, start - 1, -1):
        ok_r, sc, pc = _compression_snapshot_at(ma25, ma99, closes, cfg, end_idx)
        if ok_r and sc >= best_score:
            found = True
            best_score = sc * 0.88  # penalización leve: compresión no es en la vela actual
            best_pct = pc

    if found:
        return True, round(best_score, 2), best_pct

    _, _, pct_now = _compression_snapshot_at(ma25, ma99, closes, cfg, last_idx)
    return False, 0.0, pct_now


def _find_support_level(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atrs: np.ndarray,
    cfg: LSESymbolConfig,
) -> Optional[float]:
    """
    Busca el mínimo de los últimos N candles con al menos 2 toques
    (equal lows con tolerancia dinámica ATR).
    Retorna el nivel de soporte o None si no es significativo.
    """
    lb = cfg.lookback_lows
    if len(lows) < lb:
        return None

    window_lows = lows[-lb:]
    atr_val = atrs[-1] if not np.isnan(atrs[-1]) else closes[-1] * 0.005

    tol = max(
        cfg.equal_lows_tolerance_pct * closes[-1],
        atr_val * cfg.equal_lows_atr_k,
    )

    level = np.min(window_lows)

    # Contar toques: cuántas velas tienen low dentro de tolerancia del mínimo
    touches = np.sum(np.abs(window_lows - level) <= tol)

    if touches >= cfg.equal_lows_min_touches:
        return float(level)
    return None


def _find_support_aggressive(
    lows: np.ndarray,
    closes: np.ndarray,
    cfg: LSESymbolConfig,
) -> Optional[float]:
    """
    Modo aggressive: nivel roto = mínimo de últimos N velas (single tap permitido).
    Sin equal lows obligatorio.
    """
    lb = cfg.lookback_lows
    if len(lows) < lb:
        return None
    return float(np.min(lows[-lb:]))


def _effective_aggressive_sweep_thresholds(cfg: LSESymbolConfig) -> Tuple[float, float]:
    """Wick mínimo enfatizado + volumen más flexible — overrides opcionales por símbolo."""
    wick = cfg.aggressive_wick_ratio_min
    if wick is None:
        wick = max(cfg.wick_ratio_min, 0.35)
    vol_mult = cfg.aggressive_volume_spike_mult
    if vol_mult is None:
        vol_mult = 1.2
    return float(wick), float(vol_mult)


def _weighted_aggressive_score(sub: LSESubScores) -> float:
    """
    Pesos aggressive: Compression 15%, Sweep 30%, Reclaim 25%, Volume 15%, HTF 15%.
    Normaliza cada componente a su techo conservador habitual antes de ponderar.
    """
    nc = min(1.0, max(0.0, sub.compression / 20.0))
    ns = min(1.0, max(0.0, sub.sweep / 25.0))
    nr = min(1.0, max(0.0, sub.reclaim / 20.0))
    nv = min(1.0, max(0.0, sub.volume / 20.0))
    nh = min(1.0, max(0.0, sub.htf_context / 15.0))
    return round(nc * 15.0 + ns * 30.0 + nr * 25.0 + nv * 15.0 + nh * 15.0, 2)


def _detect_sweep(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    vols: np.ndarray,
    support_level: float,
    atrs: np.ndarray,
    cfg: LSESymbolConfig,
    wick_ratio_min: float,
    volume_spike_mult: float,
) -> Tuple[bool, int, float, float, float, float]:
    """
    Busca, en las últimas `sweep_lookback` velas, una que:
      - Baje por debajo del nivel de soporte (sweep)
      - Tenga mecha inferior >= wick_ratio_min * rango_total
      - Cierre POR ENCIMA del nivel roto (reclaim inmediato)
      - Volumen > promedio(50) * volume_spike_mult (parámetros explícitos por modo)
    Retorna (encontrado, sweep_idx, sweep_low, sweep_high, reclaim_close_sweep, vol_ratio)
    """
    lb = cfg.sweep_lookback
    vol_lb = cfg.volume_lookback

    if len(closes) < vol_lb:
        return False, -1, 0.0, 0.0, 0.0, 0.0

    avg_vol = np.mean(vols[-vol_lb:-1]) if len(vols) > vol_lb else np.mean(vols[:-1])

    # Última vela suele estar en formación — no usar como sweep
    check_end = len(closes) - 1
    check_start = max(1, check_end - lb)
    check_range = range(check_start, check_end)

    for i in check_range:
        c_open  = opens[i]
        c_high  = highs[i]
        c_low   = lows[i]
        c_close = closes[i]
        c_vol   = vols[i]

        total_range = c_high - c_low
        if total_range == 0:
            continue

        # 1. Debe romper por debajo del soporte
        if c_low >= support_level:
            continue

        # 2. Debe cerrar POR ENCIMA del soporte (reclaim inmediato = sweep real)
        if c_close <= support_level:
            continue

        # 3. Mecha inferior significativa
        # lower_wick = min(c_open, c_close) - c_low
        lower_wick = min(c_open, c_close) - c_low
        wick_ratio = lower_wick / total_range
        if wick_ratio < wick_ratio_min:
            continue

        # 4. Volumen spike
        vol_ratio = c_vol / avg_vol if avg_vol > 0 else 1.0
        if vol_ratio < volume_spike_mult:
            continue

        # 5. Filtro anomalía (noticias/manipulación)
        atr_val = atrs[i] if not np.isnan(atrs[i]) else closes[i] * 0.005
        if total_range > cfg.anomaly_candle_ratio * atr_val:
            logger.debug("⚠️ Vela anomalía ignorada (rango %.4f > %.1fx ATR)", total_range, cfg.anomaly_candle_ratio)
            continue

        logger.debug(
            "🎯 Sweep detectado idx=%d low=%.6f close=%.6f wick_ratio=%.2f vol_ratio=%.2f",
            i, c_low, c_close, wick_ratio, vol_ratio
        )
        return True, i, float(c_low), float(c_high), float(c_close), float(vol_ratio)

    return False, -1, 0.0, 0.0, 0.0, 0.0


def _find_reclaim_candle(
    highs: np.ndarray,
    closes: np.ndarray,
    ma7: np.ndarray,
    ma25: np.ndarray,
    support_level: float,
    sweep_high: float,
    sweep_idx: int,
    entry_mode: LSEEntryMode,
) -> Tuple[bool, float, int]:
    """
    Busca la vela de reclaim más reciente desde sweep_idx.
    Conservador: vela posterior al sweep con ruptura del high del sweep (fake breakdown reversal).
    """
    max_j = len(closes) - 2  # misma convención que sweep: última vela = incompleta
    if max_j < sweep_idx:
        max_j = len(closes) - 1

    for j in range(max_j, sweep_idx - 1, -1):
        c = closes[j]
        if c <= support_level:
            continue
        if np.isnan(ma7[j]) or np.isnan(ma25[j]):
            continue
        above_ma = c > ma7[j] or c > ma25[j]
        if not above_ma:
            continue

        if entry_mode == LSEEntryMode.conservative:
            if j <= sweep_idx:
                continue
            if highs[j] <= sweep_high:
                continue
        return True, float(c), j

    return False, 0.0, -1


def _htf_context_score(
    candles_4h: List[CandleInput],
    cfg: LSESymbolConfig,
) -> Tuple[float, List[str]]:
    """
    Evalúa el contexto 4H:
    - Si precio está muy por debajo de MA99 en 4H (bearish estructural) → 0 pts
    - Si está por encima o neutral → hasta 15 pts
    Retorna (score_0_15, reasoning_list)
    """
    reasons = []
    if not candles_4h or len(candles_4h) < cfg.htf_ma_period:
        reasons.append("⚠️ HTF: sin datos 4H suficientes — contexto neutro")
        return 7.5, reasons  # Neutral

    _, _, _, closes_4h, _ = _to_arrays(candles_4h)
    ma99_4h = _ema(closes_4h, cfg.htf_ma_period)
    last_close_4h = closes_4h[-1]
    last_ma99_4h  = ma99_4h[-1]

    if last_ma99_4h == 0:
        return 7.5, reasons

    dist_pct = (last_close_4h - last_ma99_4h) / last_ma99_4h  # positivo = por encima

    if dist_pct > cfg.htf_overextension_pct:
        reasons.append(f"⚠️ HTF 4H: sobreextendido alcista {dist_pct:.1%} sobre MA99 — cautela")
        return 5.0, reasons
    elif dist_pct < -cfg.htf_overextension_pct:
        reasons.append(f"🚫 HTF 4H: tendencia bajista fuerte ({dist_pct:.1%} bajo MA99) — señal descartada")
        return 0.0, reasons
    else:
        reasons.append(f"✅ HTF 4H: precio neutral/alcista ({dist_pct:.1%} vs MA99)")
        return 15.0, reasons


def _atr_filter(atrs: np.ndarray, cfg: LSESymbolConfig) -> Tuple[bool, float]:
    """
    Filtra si el ATR actual es caótico vs la media histórica.
    Retorna (ok, ratio)
    """
    if len(atrs) < cfg.volume_lookback:
        return True, 1.0

    valid_atrs = atrs[~np.isnan(atrs)]
    if len(valid_atrs) < 10:
        return True, 1.0

    avg_atr = np.mean(valid_atrs[-cfg.volume_lookback:])
    current_atr = valid_atrs[-1]
    ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
    return ratio < cfg.atr_ratio_max, round(ratio, 3)


def _find_tp1(highs: np.ndarray, entry_price: float, cfg: LSESymbolConfig) -> float:
    """TP1: último high relevante en los últimos N candles."""
    lb = cfg.tp1_lookback
    window = highs[-lb:] if len(highs) >= lb else highs
    candidates = window[window > entry_price]
    if len(candidates) == 0:
        return entry_price * 1.05  # fallback +5%
    return float(np.min(candidates))  # primer resistencia alcanzable


def _find_tp2(highs: np.ndarray, entry_price: float) -> float:
    """TP2: high máximo histórico en ventana como zona objetivo extendida."""
    return float(np.max(highs))


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

def _finalize_lse_signal(
    symbol: str,
    timeframe: str,
    sub: LSESubScores,
    reasoning: List[str],
    compression_pct: float,
    highs: np.ndarray,
    ma7: np.ndarray,
    ma25: np.ndarray,
    ma99: np.ndarray,
    atrs: np.ndarray,
    sweep_low: float,
    sweep_high: float,
    reclaim_close: float,
    vol_ratio: float,
    entry_price: float,
    entry_mode: LSEEntryMode,
    detection_mode: LSEDetectionMode,
    cfg: LSESymbolConfig,
    sm: LSEStateMachine,
    total_score: float,
    preview_only: bool = False,
) -> Tuple[LSESignal, List[str]]:
    stop_loss = sweep_low * 0.995
    tp1 = _find_tp1(highs, entry_price, cfg)
    tp2 = _find_tp2(highs, entry_price)

    reasoning.append(f"🛡️ SL={stop_loss:.6f} | TP1={tp1:.6f} | TP2={tp2:.6f}")

    risk = entry_price - stop_loss
    reward = tp1 - entry_price
    if risk > 0 and reward / risk < 1.5:
        reasoning.append(f"⚠️ R:R bajo ({reward/risk:.2f}) — señal emitida igual (ejecutar con cautela)")

    if not preview_only:
        sm.enter_emit_cooldown(symbol, timeframe, cfg.cooldown_candles)

    alert_message = (
        f"🚨 LSE[{detection_mode.value}] | {symbol} | Score {total_score:.0f}/100 | "
        f"Entry {entry_price:.6f} | SL {stop_loss:.6f} | TP1 {tp1:.6f}"
    )

    signal = LSESignal(
        symbol          = symbol,
        timeframe       = timeframe,
        state           = LSEState.triggered,
        detection_mode  = detection_mode,
        score           = round(total_score, 2),
        sub_scores      = sub,
        entry_price     = entry_price,
        stop_loss       = round(stop_loss, 8),
        take_profit_1   = round(tp1, 8),
        take_profit_2   = round(tp2, 8),
        sweep_low       = round(sweep_low, 8),
        sweep_high      = round(sweep_high, 8),
        reclaim_close   = round(reclaim_close, 8),
        ma7             = round(float(ma7[-1]), 8),
        ma25            = round(float(ma25[-1]), 8),
        ma99            = round(float(ma99[-1]), 8),
        atr             = round(float(atrs[-1]), 8) if not np.isnan(atrs[-1]) else None,
        volume_ratio    = round(vol_ratio, 3),
        compression_pct = compression_pct,
        reasoning       = reasoning,
        entry_mode      = entry_mode,
        detected_at     = datetime.now(timezone.utc).isoformat(),
        alert_message   = alert_message,
    )

    logger.info("🔥 LSE SEÑAL EMITIDA [%s]: %s", detection_mode.value, alert_message)
    return signal, reasoning


def _pipeline_conservative(
    symbol: str,
    timeframe: str,
    candles_4h: List[CandleInput],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    vols: np.ndarray,
    ma7: np.ndarray,
    ma25: np.ndarray,
    ma99: np.ndarray,
    atrs: np.ndarray,
    cfg: LSESymbolConfig,
    entry_mode: LSEEntryMode,
    sm: LSEStateMachine,
    preview_only: bool = False,
) -> Tuple[Optional[LSESignal], List[str]]:
    """Pipeline conservador — igual al comportamiento histórico del LSE."""
    reasoning: List[str] = []
    reasoning.append(f"📘 detection_mode={LSEDetectionMode.conservative.value}")
    sub = LSESubScores()

    compressed, comp_score, compression_pct = _detect_compression(ma25, ma99, closes, cfg)

    if compressed:
        sub.compression = comp_score
        reasoning.append(f"✅ Compresión MA25/MA99 detectada ({compression_pct:.3f}% distancia)")
    else:
        reasoning.append(f"⏳ Sin compresión MA25/MA99 ({compression_pct:.3f}%)")
        return None, reasoning

    support_level = _find_support_level(highs, lows, closes, atrs, cfg)

    if support_level is None:
        reasoning.append("❌ No se encontró nivel de soporte validado (equal lows)")
        return None, reasoning

    reasoning.append(f"✅ Nivel de soporte (equal lows): {support_level:.6f}")

    atr_ok, atr_ratio = _atr_filter(atrs, cfg)
    if not atr_ok:
        reasoning.append(f"🚫 ATR caótico ({atr_ratio:.2f}x promedio) — señal descartada")
        return None, reasoning

    sweep_found, sweep_idx, sweep_low, sweep_high, reclaim_close, vol_ratio = _detect_sweep(
        opens, highs, lows, closes, vols, support_level, atrs, cfg,
        cfg.wick_ratio_min, cfg.volume_spike_mult,
    )

    if not sweep_found or sweep_idx < 0:
        reasoning.append("⏳ Sin sweep detectado todavía")
        return None, reasoning

    sub.sweep = 25.0
    sub.volume = min(20.0, 20.0 * (vol_ratio / (cfg.volume_spike_mult * 1.5)))
    reasoning.append(f"🎯 Sweep detectado: low={sweep_low:.6f} close={reclaim_close:.6f} vol_ratio={vol_ratio:.2f}x")

    reclaimed, entry_price, reclaim_j = _find_reclaim_candle(
        highs, closes, ma7, ma25, support_level, sweep_high, sweep_idx, entry_mode
    )

    if not reclaimed:
        reasoning.append("⏳ Esperando reclaim confirmado...")
        return None, reasoning

    sub.reclaim = 20.0
    reasoning.append(f"✅ Reclaim confirmado (vela índice {reclaim_j}). Entry price: {entry_price:.6f}")

    htf_score, htf_reasons = _htf_context_score(candles_4h, cfg)
    sub.htf_context = htf_score
    reasoning.extend(htf_reasons)

    if htf_score == 0.0:
        return None, reasoning

    total_score = sub.total

    reasoning.append(
        f"📊 Score (conservative sum): {total_score:.1f}/100 "
        f"[comp={sub.compression:.1f} sweep={sub.sweep:.1f} "
        f"reclaim={sub.reclaim:.1f} vol={sub.volume:.1f} htf={sub.htf_context:.1f}]"
    )

    if total_score < cfg.min_score_to_trigger:
        reasoning.append(f"❌ Score insuficiente ({total_score:.1f} < {cfg.min_score_to_trigger})")
        return None, reasoning

    return _finalize_lse_signal(
        symbol, timeframe, sub, reasoning, compression_pct,
        highs, ma7, ma25, ma99, atrs,
        sweep_low, sweep_high, reclaim_close, vol_ratio,
        entry_price, entry_mode, LSEDetectionMode.conservative,
        cfg, sm, total_score, preview_only,
    )


def _pipeline_aggressive(
    symbol: str,
    timeframe: str,
    candles_4h: List[CandleInput],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    vols: np.ndarray,
    ma7: np.ndarray,
    ma25: np.ndarray,
    ma99: np.ndarray,
    atrs: np.ndarray,
    cfg: LSESymbolConfig,
    entry_mode: LSEEntryMode,
    sm: LSEStateMachine,
    preview_only: bool = False,
) -> Tuple[Optional[LSESignal], List[str]]:
    """Pipeline agresivo — sin equal lows obligatorio; pesos de score distintos."""
    reasoning: List[str] = []
    reasoning.append(f"📙 detection_mode={LSEDetectionMode.aggressive.value}")
    sub = LSESubScores()

    compressed, comp_score, compression_pct = _detect_compression(ma25, ma99, closes, cfg)

    if compressed:
        sub.compression = comp_score
        reasoning.append(f"✅ Compresión MA25/MA99 detectada ({compression_pct:.3f}% distancia)")
    elif cfg.aggressive_compression_optional:
        sub.compression = 0.0
        reasoning.append(
            f"ℹ️ Aggressive: sin compresión MA25/99 ({compression_pct:.3f}%) — siguiendo (compression_optional)"
        )
    else:
        reasoning.append(f"⏳ Sin compresión MA25/MA99 ({compression_pct:.3f}%) — aggressive_compression_optional=false")
        return None, reasoning

    support_level = _find_support_aggressive(lows, closes, cfg)
    if support_level is None:
        reasoning.append("❌ Sin nivel soporte aggressive (lookback insuficiente)")
        return None, reasoning

    reasoning.append(f"✅ Nivel soporte aggressive (min últimos {cfg.lookback_lows}): {support_level:.6f}")

    atr_ok, atr_ratio = _atr_filter(atrs, cfg)
    if not atr_ok:
        reasoning.append(f"🚫 ATR caótico ({atr_ratio:.2f}x promedio) — señal descartada")
        return None, reasoning

    wick_eff, vol_eff = _effective_aggressive_sweep_thresholds(cfg)
    reasoning.append(f"⚙️ Sweep aggressive: wick_ratio_min={wick_eff:.2f} volume_spike_mult={vol_eff:.2f}")

    sweep_found, sweep_idx, sweep_low, sweep_high, reclaim_close, vol_ratio = _detect_sweep(
        opens, highs, lows, closes, vols, support_level, atrs, cfg,
        wick_eff, vol_eff,
    )

    if not sweep_found or sweep_idx < 0:
        reasoning.append("⏳ Sin sweep detectado todavía")
        return None, reasoning

    sub.sweep = 25.0
    sub.volume = min(20.0, 20.0 * (vol_ratio / (vol_eff * 1.5)))
    reasoning.append(f"🎯 Sweep detectado: low={sweep_low:.6f} close={reclaim_close:.6f} vol_ratio={vol_ratio:.2f}x")

    reclaimed, entry_price, reclaim_j = _find_reclaim_candle(
        highs, closes, ma7, ma25, support_level, sweep_high, sweep_idx, entry_mode
    )

    if not reclaimed:
        reasoning.append("⏳ Esperando reclaim confirmado...")
        return None, reasoning

    sub.reclaim = 20.0
    reasoning.append(f"✅ Reclaim confirmado (vela índice {reclaim_j}). Entry price: {entry_price:.6f}")

    htf_score, htf_reasons = _htf_context_score(candles_4h, cfg)
    sub.htf_context = htf_score
    reasoning.extend(htf_reasons)

    if htf_score == 0.0:
        return None, reasoning

    total_score = _weighted_aggressive_score(sub)
    raw_sum = sub.total

    reasoning.append(
        f"📊 Score (aggressive weighted): {total_score:.1f}/100 | suma raw ref={raw_sum:.1f} "
        f"[comp={sub.compression:.1f} sweep={sub.sweep:.1f} "
        f"reclaim={sub.reclaim:.1f} vol={sub.volume:.1f} htf={sub.htf_context:.1f}]"
    )

    if total_score < cfg.min_score_to_trigger:
        reasoning.append(f"❌ Score insuficiente ({total_score:.1f} < {cfg.min_score_to_trigger})")
        return None, reasoning

    return _finalize_lse_signal(
        symbol, timeframe, sub, reasoning, compression_pct,
        highs, ma7, ma25, ma99, atrs,
        sweep_low, sweep_high, reclaim_close, vol_ratio,
        entry_price, entry_mode, LSEDetectionMode.aggressive,
        cfg, sm, total_score, preview_only,
    )


def run_lse_detection(
    symbol: str,
    timeframe: str,
    candles_1h: List[CandleInput],
    candles_4h: List[CandleInput],
    entry_mode: LSEEntryMode = LSEEntryMode.conservative,
    detection_mode: LSEDetectionMode = LSEDetectionMode.conservative,
    preview_only: bool = False,
) -> Tuple[Optional[LSESignal], List[str]]:
    """
    Pipeline completo de detección LSE (conservative sin cambios vs aggressive opt-in).
    preview_only=True: no tick SM, no gate cooldown, no enter_emit_cooldown (dashboard).
    """
    cfg = get_config(symbol)
    sm = LSEStateMachine.get()

    if not preview_only:
        sm.tick(symbol, timeframe)

        if not sm.can_emit(symbol, timeframe):
            msg = (
                f"🔒 {symbol}: cooldown LSE activo para este par/timeframe — esperá velas o "
                f"POST /lse/reset-state/{symbol}?timeframe={timeframe}"
            )
            logger.debug(msg)
            return None, [msg]

    if len(candles_1h) < 120:
        logger.debug("⚠️ [%s] Insuficientes velas TF principal (%d)", symbol, len(candles_1h))
        return None, [
            f"⚠️ Insuficientes velas ({len(candles_1h)}); se requieren ≥120 para MA99 estable."
        ]

    opens, highs, lows, closes, vols = _to_arrays(candles_1h)

    ma7 = _ema(closes, 7)
    ma25 = _ema(closes, 25)
    ma99 = _ema(closes, 99)
    atrs = _atr(highs, lows, closes, period=14)

    if detection_mode == LSEDetectionMode.aggressive:
        return _pipeline_aggressive(
            symbol, timeframe, candles_4h,
            opens, highs, lows, closes, vols, ma7, ma25, ma99, atrs,
            cfg, entry_mode, sm, preview_only,
        )

    return _pipeline_conservative(
        symbol, timeframe, candles_4h,
        opens, highs, lows, closes, vols, ma7, ma25, ma99, atrs,
        cfg, entry_mode, sm, preview_only,
    )
