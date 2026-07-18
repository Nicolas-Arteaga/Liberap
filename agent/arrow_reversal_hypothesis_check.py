"""
Verifica la hipótesis del usuario (2026-07-17): después de un "flecha" limpio
(pump de 3-5 días todos verdes, >=20%), una vez que aparece la primera vela
roja, el precio NO recupera el nivel del pico en solo 1 día — la reversión,
una vez que arranca, tiende a seguir, no a deshacerse sola.

100% sobre datos ya cacheados (agent/data/klines.db, agregando 1h -> diario),
CERO llamadas a Binance ni a ninguna API — no hay riesgo de baneo acá.

Metodología: reusa la MISMA detección de "pump limpio" que
arrow_peak_backtest.py/arrow_peak_analyzer.py (3-5 días verdes consecutivos,
>=20% de suba) para encontrar TODOS los picos históricos, sin exigir además
que haya 1-3 días de sangrado confirmados (eso ya lo probamos en el
backtest de trading) — acá la pregunta es más simple: ¿el precio recupera
el pico en N días después de la primera vela roja, sí o no?
"""
from collections import defaultdict
from datetime import datetime, timezone

from kline_cache import get_cache
from arrow_peak_backtest import _build_daily_from_1h, MIN_1H_CANDLES

RECOVERY_WINDOWS = [1, 2, 3, 5, 7, 10]


def find_clean_pumps(daily: list):
    """Devuelve lista de (peak_idx, peak_price) para TODOS los pumps limpios detectados, sin exigir sangrado posterior."""
    pumps = []
    n = len(daily)
    for peak_idx in range(14, n):
        # Ventana de "últimos 10 días" centrada en este candidato a pico
        window_start = max(0, peak_idx - 9)
        candidate_window = daily[window_start: peak_idx + 1]
        if daily[peak_idx]["high"] != max(d["high"] for d in candidate_window):
            continue  # este día no es el máximo de su propia ventana de 10 días -> no es un "pico" real ahí

        before_peak = daily[: peak_idx + 1]
        n_before = len(before_peak)
        is_clean = False
        for end_pos in (n_before, n_before - 1):
            if is_clean:
                break
            for length in (5, 4, 3):
                start_pos = end_pos - length
                if start_pos < 0:
                    continue
                sub = before_peak[start_pos:end_pos]
                if all(c["close"] > c["open"] for c in sub):
                    first_open = sub[0]["open"]
                    rise_pct = (daily[peak_idx]["high"] - first_open) / first_open * 100
                    if rise_pct >= 20.0:
                        is_clean = True
                        break
        if is_clean:
            pumps.append((peak_idx, daily[peak_idx]["high"]))
    return pumps


def check_recovery(daily: list, peak_idx: int, peak_price: float):
    """
    Requiere que el día siguiente al pico sea rojo (arranca el sangrado) —
    si no, este pico no es relevante para la hipótesis (nunca empezó a caer).
    Devuelve dict {recovered_within_N: bool} para cada N en RECOVERY_WINDOWS,
    o None si no hay suficientes días posteriores para evaluar la ventana más larga.
    """
    n = len(daily)
    if peak_idx + 1 >= n:
        return None
    first_after = daily[peak_idx + 1]
    if not (first_after["close"] < first_after["open"]):
        return None  # no empezó a sangrar al día siguiente, no aplica a la hipótesis

    if peak_idx + max(RECOVERY_WINDOWS) >= n:
        return None  # no hay suficiente historia futura para evaluar todas las ventanas

    result = {}
    for w in RECOVERY_WINDOWS:
        days_after = daily[peak_idx + 1: peak_idx + 1 + w]
        recovered = any(d["close"] >= peak_price for d in days_after)
        result[w] = recovered
    return result


def main():
    cache = get_cache()
    symbols = cache.get_symbols_with_history("1h", min_candles=MIN_1H_CANDLES)

    totals = defaultdict(int)
    evaluated = 0
    examples_recovered_fast = []

    for idx, symbol in enumerate(symbols):
        klines_1h = cache.get_klines(symbol, "1h", limit=100_000)
        if len(klines_1h) < MIN_1H_CANDLES:
            continue
        daily = _build_daily_from_1h(klines_1h)
        if len(daily) < 20:
            continue

        pumps = find_clean_pumps(daily)
        for peak_idx, peak_price in pumps:
            rec = check_recovery(daily, peak_idx, peak_price)
            if rec is None:
                continue
            evaluated += 1
            for w in RECOVERY_WINDOWS:
                if rec[w]:
                    totals[w] += 1
            if rec[1] and len(examples_recovered_fast) < 10:
                examples_recovered_fast.append((symbol, daily[peak_idx]["day"], peak_price))

        if (idx + 1) % 100 == 0:
            print(f"[Check] {idx + 1}/{len(symbols)} símbolos, {evaluated} picos evaluados hasta ahora...")

    if evaluated == 0:
        print("No se encontraron picos evaluables en todo el universo.")
        return

    print(f"\n=== HIPÓTESIS: ¿recupera el precio del pico N días después de la primera vela roja? ===")
    print(f"Total de picos limpios evaluados (con sangrado confirmado al día siguiente): {evaluated}\n")
    for w in RECOVERY_WINDOWS:
        pct = totals[w] / evaluated * 100
        print(f"  Recuperó el pico dentro de {w:2d} día(s): {totals[w]:4d}/{evaluated} = {pct:.1f}%")

    if examples_recovered_fast:
        print("\nEjemplos que SÍ recuperaron el pico en 1 día (contraejemplos de la hipótesis, si los hay):")
        for s, day, price in examples_recovered_fast:
            print(f"  {s} — pico del {day} en {price}")


if __name__ == "__main__":
    main()
