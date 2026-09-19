"""
ORDER BLOCK DETECTOR — concepto ICT/SMC distinto a FVG (no es un gap de
precio, es un evento de estructura de mercado). Investigado el 2026-08-21
tras que el laboratorio automático de parámetros y el modelo de IA
entrenado agotaran el espacio de indicadores tecnicos clasicos (RSI/MA/
ATR) sin encontrar edge real -- este es un concepto DISTINTO, con
confluencia de 3 piezas (igual que la literatura real de trading
institucional, no una sola señal aislada):

  1. SWING STRUCTURE: maximos/minimos confirmados (fractal, lag L velas).
  2. MARKET STRUCTURE SHIFT (BOS -- Break of Structure): el precio cierra
     mas alla del ultimo swing confirmado en la direccion opuesta a la
     tendencia previa -- evidencia de que "algo cambio" en el mercado.
  3. ORDER BLOCK: la ULTIMA vela de color contrario antes del impulso que
     causo el BOS -- la zona donde se presume que se acumulo la posicion
     institucional antes de mover el precio con fuerza.

Señal de entrada = LIQUIDITY SWEEP + BOS + mitigacion del Order Block: el
precio, despues del BOS, vuelve a tocar la zona del OB por primera vez
(retroceso/"mitigacion") -- ahi es donde entra, a favor de la direccion
del BOS (continuacion, no reversion). Nunca mira al futuro: el swing solo
se confirma L velas despues de formado, y el OB solo se identifica una
vez que el BOS ya ocurrio.
"""
from typing import List, Dict, Optional, Tuple

SWING_LAG = 3  # velas a cada lado para confirmar un swing high/low (fractal)
MAX_CANDLES_TO_MITIGATION = 60  # si el precio no vuelve a tocar el OB en N velas, se descarta (señal vieja)


def find_confirmed_swings(highs: List[float], lows: List[float], n: int, lag: int = SWING_LAG) -> Tuple[list, list]:
    """
    Devuelve dos listas paralelas a highs/lows: swing_high[i] = True si la
    vela i es un maximo local confirmado (solo se puede saber esto `lag`
    velas despues, nunca antes -- sin look-ahead en el uso real).
    """
    swing_high = [False] * n
    swing_low = [False] * n
    for i in range(lag, n - lag):
        window_h = highs[i - lag:i + lag + 1]
        window_l = lows[i - lag:i + lag + 1]
        if highs[i] == max(window_h) and window_h.count(highs[i]) == 1:
            swing_high[i] = True
        if lows[i] == min(window_l) and window_l.count(lows[i]) == 1:
            swing_low[i] = True
    return swing_high, swing_low


def detect_order_block_signals(
    opens: List[float], highs: List[float], lows: List[float], closes: List[float],
    open_times: List[int], lag: int = SWING_LAG,
) -> List[Dict]:
    """
    Recorre toda la serie UNA sola vez (sin look-ahead: en el indice i solo
    usa informacion de swings ya confirmados en i-lag o antes) y devuelve
    la lista de señales de mitigacion de Order Block encontradas.

    Cada señal: {direction, ob_top, ob_bottom, bos_idx, ob_idx, entry_idx,
                 entry_price, formed_at_ms}
    direction: "bullish" (LONG) o "bearish" (SHORT) -- direccion del BOS,
    que es la direccion en la que se opera al mitigar el OB.
    """
    n = len(closes)
    swing_high, swing_low = find_confirmed_swings(highs, lows, n, lag)

    signals = []
    last_confirmed_high_idx: Optional[int] = None
    last_confirmed_high_val: Optional[float] = None
    last_confirmed_low_idx: Optional[int] = None
    last_confirmed_low_val: Optional[float] = None

    # Estado de "estructura pendiente de mitigar" -- como maximo UN OB
    # bullish y UN OB bearish activo a la vez (el mas reciente rompe al
    # anterior si no se llego a mitigar).
    pending_bullish_ob: Optional[Dict] = None
    pending_bearish_ob: Optional[Dict] = None

    for i in range(lag, n):
        # Confirmar el swing que quedo `lag` velas atras (recien ahora se sabe).
        confirm_idx = i - lag
        if confirm_idx >= lag:
            if swing_high[confirm_idx]:
                last_confirmed_high_idx, last_confirmed_high_val = confirm_idx, highs[confirm_idx]
            if swing_low[confirm_idx]:
                last_confirmed_low_idx, last_confirmed_low_val = confirm_idx, lows[confirm_idx]

        # ── BOS alcista: el cierre actual supera el ultimo swing high confirmado ──
        if last_confirmed_high_val is not None and closes[i] > last_confirmed_high_val:
            # Buscar la ultima vela BAJISTA (close<open) entre el swing y el
            # BOS -- esa es el Order Block bullish real.
            ob_idx = None
            for j in range(i - 1, last_confirmed_high_idx, -1):
                if closes[j] < opens[j]:
                    ob_idx = j
                    break
            if ob_idx is not None:
                pending_bullish_ob = {
                    "direction": "bullish", "ob_top": highs[ob_idx], "ob_bottom": lows[ob_idx],
                    "bos_idx": i, "ob_idx": ob_idx, "formed_at_ms": int(open_times[ob_idx]),
                }
            last_confirmed_high_val = None  # esa estructura ya se rompio, no volver a disparar

        # ── BOS bajista: el cierre actual perfora el ultimo swing low confirmado ──
        if last_confirmed_low_val is not None and closes[i] < last_confirmed_low_val:
            ob_idx = None
            for j in range(i - 1, last_confirmed_low_idx, -1):
                if closes[j] > opens[j]:
                    ob_idx = j
                    break
            if ob_idx is not None:
                pending_bearish_ob = {
                    "direction": "bearish", "ob_top": highs[ob_idx], "ob_bottom": lows[ob_idx],
                    "bos_idx": i, "ob_idx": ob_idx, "formed_at_ms": int(open_times[ob_idx]),
                }
            last_confirmed_low_val = None

        # ── Mitigacion: el precio vuelve a tocar la zona del OB pendiente ──
        if pending_bullish_ob is not None and i > pending_bullish_ob["bos_idx"]:
            ob = pending_bullish_ob
            if i - ob["bos_idx"] > MAX_CANDLES_TO_MITIGATION:
                pending_bullish_ob = None
            elif lows[i] <= ob["ob_top"]:  # la mecha toco la zona (o la atraveso)
                signals.append({
                    **ob, "entry_idx": i,
                    "entry_price": min(closes[i], ob["ob_top"]),
                })
                pending_bullish_ob = None

        if pending_bearish_ob is not None and i > pending_bearish_ob["bos_idx"]:
            ob = pending_bearish_ob
            if i - ob["bos_idx"] > MAX_CANDLES_TO_MITIGATION:
                pending_bearish_ob = None
            elif highs[i] >= ob["ob_bottom"]:
                signals.append({
                    **ob, "entry_idx": i,
                    "entry_price": max(closes[i], ob["ob_bottom"]),
                })
                pending_bearish_ob = None

    return signals


def find_live_pending_blocks(
    opens: List[float], highs: List[float], lows: List[float], closes: List[float],
    open_times: List[int], lag: int = SWING_LAG,
) -> Dict[str, Optional[Dict]]:
    """
    Para uso EN VIVO (scan del agente/panel, no backtest): misma logica de
    deteccion que detect_order_block_signals, pero en vez de devolver el
    historial completo de mitigaciones ya ocurridas, devuelve el estado
    actual -- el Order Block bullish y/o bearish que quedaron PENDIENTES de
    mitigar al final de la serie (la zona real a vigilar ahora mismo).
    None si no hay ninguno pendiente en esa direccion.
    """
    n = len(closes)
    swing_high, swing_low = find_confirmed_swings(highs, lows, n, lag)

    last_confirmed_high_idx: Optional[int] = None
    last_confirmed_high_val: Optional[float] = None
    last_confirmed_low_idx: Optional[int] = None
    last_confirmed_low_val: Optional[float] = None

    pending_bullish_ob: Optional[Dict] = None
    pending_bearish_ob: Optional[Dict] = None

    for i in range(lag, n):
        confirm_idx = i - lag
        if confirm_idx >= lag:
            if swing_high[confirm_idx]:
                last_confirmed_high_idx, last_confirmed_high_val = confirm_idx, highs[confirm_idx]
            if swing_low[confirm_idx]:
                last_confirmed_low_idx, last_confirmed_low_val = confirm_idx, lows[confirm_idx]

        if last_confirmed_high_val is not None and closes[i] > last_confirmed_high_val:
            ob_idx = None
            for j in range(i - 1, last_confirmed_high_idx, -1):
                if closes[j] < opens[j]:
                    ob_idx = j
                    break
            if ob_idx is not None:
                pending_bullish_ob = {
                    "direction": "bullish", "ob_top": highs[ob_idx], "ob_bottom": lows[ob_idx],
                    "bos_idx": i, "ob_idx": ob_idx, "formed_at_ms": int(open_times[ob_idx]),
                }
            last_confirmed_high_val = None

        if last_confirmed_low_val is not None and closes[i] < last_confirmed_low_val:
            ob_idx = None
            for j in range(i - 1, last_confirmed_low_idx, -1):
                if closes[j] > opens[j]:
                    ob_idx = j
                    break
            if ob_idx is not None:
                pending_bearish_ob = {
                    "direction": "bearish", "ob_top": highs[ob_idx], "ob_bottom": lows[ob_idx],
                    "bos_idx": i, "ob_idx": ob_idx, "formed_at_ms": int(open_times[ob_idx]),
                }
            last_confirmed_low_val = None

        if pending_bullish_ob is not None and i > pending_bullish_ob["bos_idx"]:
            ob = pending_bullish_ob
            if i - ob["bos_idx"] > MAX_CANDLES_TO_MITIGATION:
                pending_bullish_ob = None
            elif lows[i] <= ob["ob_top"]:
                pending_bullish_ob = None  # se mitigo -- ya no esta pendiente

        if pending_bearish_ob is not None and i > pending_bearish_ob["bos_idx"]:
            ob = pending_bearish_ob
            if i - ob["bos_idx"] > MAX_CANDLES_TO_MITIGATION:
                pending_bearish_ob = None
            elif highs[i] >= ob["ob_bottom"]:
                pending_bearish_ob = None

    return {"bullish": pending_bullish_ob, "bearish": pending_bearish_ob}
