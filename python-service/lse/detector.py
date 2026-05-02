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
    CandleInput, LSESignal, LSESubScores, LSEState, LSEEntryMode,
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


def _detect_sweep(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    vols: np.ndarray,
    support_level: float,
    atrs: np.ndarray,
    cfg: LSESymbolConfig,
) -> Tuple[bool, int, float, float, float, float]:
    """
    Busca, en las últimas `sweep_lookback` velas, una que:
      - Baje por debajo del nivel de soporte (sweep)
      - Tenga mecha inferior >= wick_ratio_min * rango_total
      - Cierre POR ENCIMA del nivel roto (reclaim inmediato)
      - Volumen > promedio(50) * volume_spike_mult
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
        if wick_ratio < cfg.wick_ratio_min:
            continue

        # 4. Volumen spike
        vol_ratio = c_vol / avg_vol if avg_vol > 0 else 1.0
        if vol_ratio < cfg.volume_spike_mult:
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

def run_lse_detection(
    symbol: str,
    timeframe: str,
    candles_1h: List[CandleInput],
    candles_4h: List[CandleInput],
    entry_mode: LSEEntryMode = LSEEntryMode.conservative,
) -> Tuple[Optional[LSESignal], List[str]]:
    """
    Pipeline completo de detección LSE.
    Retorna (señal | None, diagnostics) — diagnostics describe por qué falló o el camino completo.
    """
    cfg = get_config(symbol)
    sm  = LSEStateMachine.get()

    # Tick de estado (nueva vela procesada)
    sm.tick(symbol, timeframe)

    # Bloqueo: no emitir si ya estamos triggered o en cooldown
    if not sm.can_emit(symbol, timeframe):
        msg = (
            f"🔒 {symbol}: cooldown LSE activo para este par/timeframe — esperá velas o "
            f"POST /lse/reset-state/{symbol}?timeframe={timeframe}"
        )
        logger.debug(msg)
        return None, [msg]

    # Mínimo de datos
    if len(candles_1h) < 120:
        logger.debug("⚠️ [%s] Insuficientes velas 1H (%d)", symbol, len(candles_1h))
        return None, [
            f"⚠️ Insuficientes velas 1H ({len(candles_1h)}); se requieren ≥120 para MA99 estable."
        ]

    opens, highs, lows, closes, vols = _to_arrays(candles_1h)

    # --- Medias móviles ---
    ma7  = _ema(closes, 7)
    ma25 = _ema(closes, 25)
    ma99 = _ema(closes, 99)
    atrs = _atr(highs, lows, closes, period=14)

    reasoning: List[str] = []
    sub = LSESubScores()

    # ── PASO 1: COMPRESIÓN ──────────────────────────────────────────────────
    compressed, comp_score, compression_pct = _detect_compression(ma25, ma99, closes, cfg)

    if compressed:
        sub.compression = comp_score
        reasoning.append(f"✅ Compresión MA25/MA99 detectada ({compression_pct:.3f}% distancia)")
    else:
        reasoning.append(f"⏳ Sin compresión MA25/MA99 ({compression_pct:.3f}%)")
        # Sin compresión = sin señal (condición base)
        return None, reasoning

    # ── PASO 2: NIVEL DE SOPORTE ────────────────────────────────────────────
    support_level = _find_support_level(highs, lows, closes, atrs, cfg)

    if support_level is None:
        reasoning.append("❌ No se encontró nivel de soporte validado (equal lows)")
        return None, reasoning

    reasoning.append(f"✅ Nivel de soporte: {support_level:.6f}")

    # ── PASO 3: FILTRO ATR ──────────────────────────────────────────────────
    atr_ok, atr_ratio = _atr_filter(atrs, cfg)
    if not atr_ok:
        reasoning.append(f"🚫 ATR caótico ({atr_ratio:.2f}x promedio) — señal descartada")
        return None, reasoning

    # ── PASO 4: SWEEP ───────────────────────────────────────────────────────
    sweep_found, sweep_idx, sweep_low, sweep_high, reclaim_close, vol_ratio = _detect_sweep(
        opens, highs, lows, closes, vols, support_level, atrs, cfg
    )

    if not sweep_found or sweep_idx < 0:
        reasoning.append("⏳ Sin sweep detectado todavía")
        return None, reasoning

    sub.sweep  = 25.0  # Sweep detectado = score completo
    sub.volume = min(20.0, 20.0 * (vol_ratio / (cfg.volume_spike_mult * 1.5)))
    reasoning.append(f"🎯 Sweep detectado: low={sweep_low:.6f} close={reclaim_close:.6f} vol_ratio={vol_ratio:.2f}x")

    # ── PASO 5: RECLAIM ─────────────────────────────────────────────────────
    reclaimed, entry_price, reclaim_j = _find_reclaim_candle(
        highs, closes, ma7, ma25, support_level, sweep_high, sweep_idx, entry_mode
    )

    if not reclaimed:
        reasoning.append("⏳ Esperando reclaim confirmado...")
        return None, reasoning

    sub.reclaim = 20.0
    reasoning.append(f"✅ Reclaim confirmado (vela índice {reclaim_j}). Entry price: {entry_price:.6f}")

    # ── PASO 6: CONTEXTO HTF 4H ─────────────────────────────────────────────
    htf_score, htf_reasons = _htf_context_score(candles_4h, cfg)
    sub.htf_context = htf_score
    reasoning.extend(htf_reasons)

    if htf_score == 0.0:
        return None, reasoning

    # ── SCORING FINAL ───────────────────────────────────────────────────────
    total_score = sub.total

    reasoning.append(
        f"📊 Score: {total_score:.1f}/100 "
        f"[comp={sub.compression:.1f} sweep={sub.sweep:.1f} "
        f"reclaim={sub.reclaim:.1f} vol={sub.volume:.1f} htf={sub.htf_context:.1f}]"
    )

    if total_score < cfg.min_score_to_trigger:
        reasoning.append(f"❌ Score insuficiente ({total_score:.1f} < {cfg.min_score_to_trigger})")
        return None, reasoning

    # ── GESTIÓN DE RIESGO ───────────────────────────────────────────────────
    stop_loss   = sweep_low * 0.995  # SL debajo del mínimo del sweep
    tp1         = _find_tp1(highs, entry_price, cfg)
    tp2         = _find_tp2(highs, entry_price)

    reasoning.append(f"🛡️ SL={stop_loss:.6f} | TP1={tp1:.6f} | TP2={tp2:.6f}")

    # Validación mínima R:R (mínimo 1:1.5)
    risk   = entry_price - stop_loss
    reward = tp1 - entry_price
    if risk > 0 and reward / risk < 1.5:
        reasoning.append(f"⚠️ R:R bajo ({reward/risk:.2f}) — señal emitida igual (ejecutar con cautela)")

    # ── CONSTRUIR SEÑAL ─────────────────────────────────────────────────────
    sm.enter_emit_cooldown(symbol, timeframe, cfg.cooldown_candles)

    signal = LSESignal(
        symbol        = symbol,
        timeframe     = timeframe,
        state         = LSEState.triggered,
        score         = round(total_score, 2),
        sub_scores    = sub,
        entry_price   = entry_price,
        stop_loss     = round(stop_loss, 8),
        take_profit_1 = round(tp1, 8),
        take_profit_2 = round(tp2, 8),
        sweep_low     = round(sweep_low, 8),
        reclaim_close = round(reclaim_close, 8),
        ma7           = round(float(ma7[-1]), 8),
        ma25          = round(float(ma25[-1]), 8),
        ma99          = round(float(ma99[-1]), 8),
        atr           = round(float(atrs[-1]), 8) if not np.isnan(atrs[-1]) else None,
        volume_ratio  = round(vol_ratio, 3),
        compression_pct = compression_pct,
        reasoning     = reasoning,
        entry_mode    = entry_mode,
        detected_at   = datetime.now(timezone.utc).isoformat(),
        alert_message = (
            f"🚨 LSE | {symbol} | Score {total_score:.0f}/100 | "
            f"Entry {entry_price:.6f} | SL {stop_loss:.6f} | TP1 {tp1:.6f}"
        ),
    )

    logger.info("🔥 LSE SEÑAL EMITIDA: %s", signal.alert_message)
    return signal, reasoning
