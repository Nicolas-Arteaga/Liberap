"""
FVG DETECTOR — gap de 3 velas (ICT/SMC) + progreso de relleno + IFVG.

Regla (misma que feature_engine.py de nexus15, pero guardando el borde real
del gap y el progreso de relleno, no solo un booleano):
  Alcista: high[i-2] < low[i]      -> zona [bottom=high[i-2], top=low[i]]
  Bajista: low[i-2]  > high[i]     -> zona [bottom=high[i],   top=low[i-2]]

Un gap se considera "lleno" cuando el precio, en cualquier vela posterior a
la que lo formó, cruzó la zona completa (una mecha que la toca alcanza). Si
además el CIERRE de esa vela (no solo la mecha) queda del otro lado del
borde lejano, el gap fue INVALIDADO con fuerza — y en vez de simplemente
descartarlo, nace una zona IFVG (Inverse FVG): mismo rango de precio,
dirección invertida, formada en esa vela de invalidación. Una mecha que
solo toca sin que el cuerpo cierre del otro lado NO genera IFVG, es
relleno normal sin señal. Se soporta un solo nivel de inversión (no se
vuelve a invertir una IFVG que a su vez se invalida).
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple

MIN_GAP_PCT_DEFAULT = 0.0008  # 0.08% — piso contra ruido, no contra señal real (15m promedia 0.14-0.18%)


def _track_fill(
    direction: str, top: float, bottom: float, start_idx: int,
    highs: list, lows: list, closes: list, n: int,
) -> Tuple[float, bool, bool, Optional[int]]:
    """
    Escanea hacia adelante desde start_idx+1 y mide cuánto se rellenó la
    zona [bottom, top] en la dirección dada.
    Devuelve (fill_progress_pct, fully_filled, body_invalidated, invalidation_idx).
    body_invalidated = el CIERRE de alguna vela (no solo la mecha) quedó
    más allá del borde lejano -> esto es lo que dispara una IFVG.
    """
    fill_progress_pct = 0.0
    fully_filled = False
    body_invalidated = False
    invalidation_idx = None

    for j in range(start_idx + 1, n):
        if direction == "bullish":
            if lows[j] <= bottom:
                fully_filled = True
                fill_progress_pct = 100.0
                if closes[j] < bottom:
                    body_invalidated = True
                    invalidation_idx = j
                break
            if lows[j] < top:
                progress = (top - lows[j]) / (top - bottom) * 100.0
                fill_progress_pct = max(fill_progress_pct, progress)
        else:
            if highs[j] >= top:
                fully_filled = True
                fill_progress_pct = 100.0
                if closes[j] > top:
                    body_invalidated = True
                    invalidation_idx = j
                break
            if highs[j] > bottom:
                progress = (highs[j] - bottom) / (top - bottom) * 100.0
                fill_progress_pct = max(fill_progress_pct, progress)

    return round(fill_progress_pct, 2), fully_filled, body_invalidated, invalidation_idx


def detect_fvgs(df: pd.DataFrame, min_gap_pct: float = MIN_GAP_PCT_DEFAULT) -> List[Dict]:
    """
    df: columnas open, high, low, close, open_time (ms). Ordenado ascendente por tiempo.
    Devuelve zonas SIN RELLENAR (parcial o totalmente no tocadas) — FVGs
    normales e IFVGs nacidas de invalidaciones — más recientes primero.
    """
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()
    open_times = df["open_time"].tolist() if "open_time" in df.columns else [0] * len(df)

    zones = []
    n = len(df)

    for i in range(2, n):
        bullish = lows[i] > highs[i - 2]
        bearish = highs[i] < lows[i - 2]
        if not (bullish or bearish):
            continue

        if bullish:
            bottom, top = highs[i - 2], lows[i]
        else:
            top, bottom = lows[i - 2], highs[i]

        if top <= bottom:
            continue

        ref_price = closes[i] or 1.0
        gap_pct = (top - bottom) / ref_price * 100.0
        if gap_pct / 100.0 < min_gap_pct:
            continue

        direction = "bullish" if bullish else "bearish"
        fill_pct, fully_filled, body_invalidated, inval_idx = _track_fill(
            direction, top, bottom, i, highs, lows, closes, n
        )

        if not fully_filled:
            zones.append({
                "direction": direction,
                "top": top,
                "bottom": bottom,
                "gap_pct": round(gap_pct, 4),
                "candle_index": i,
                "formed_at_ms": int(open_times[i]),
                "fill_progress_pct": fill_pct,
                "is_ifvg": False,
            })
            continue

        if not body_invalidated:
            continue  # relleno por mecha nomás, sin fuerza -> sin señal, se descarta

        # Invalidación con cuerpo -> nace una IFVG con dirección invertida.
        ifvg_direction = "bearish" if bullish else "bullish"
        ifvg_fill_pct, ifvg_fully_filled, _, _ = _track_fill(
            ifvg_direction, top, bottom, inval_idx, highs, lows, closes, n
        )
        if ifvg_fully_filled:
            continue  # la IFVG también se consumió ya, no se vuelve a invertir

        ifvg_ref_price = closes[inval_idx] or 1.0
        zones.append({
            "direction": ifvg_direction,
            "top": top,
            "bottom": bottom,
            "gap_pct": round((top - bottom) / ifvg_ref_price * 100.0, 4),
            "candle_index": inval_idx,
            "formed_at_ms": int(open_times[inval_idx]),
            "fill_progress_pct": ifvg_fill_pct,
            "is_ifvg": True,
        })

    zones.reverse()  # más recientes primero
    return zones
