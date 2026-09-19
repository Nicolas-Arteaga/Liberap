"""
2026-08-19: verificacion directa pedida por el usuario -- ¿el motor de
backtest reconoce las MISMAS entradas reales que abrio produccion, con el
mismo SL/TP? Si SI las reconoce (mismo simbolo, misma vela, mismo SL/TP) y
el desacuerdo es solo en el AGREGADO (universo completo vs 6 posiciones
reales), el motor esta bien -- la diferencia es de muestra, no de logica.
Si NO las reconoce, hay un bug real de deteccion que hay que encontrar.
"""
import sys
import os
import bisect
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import load_15m, resample, atr_series, detect_signal, DB_PATH  # noqa: E402

REAL_TRADES = [
    # (strat_label, symbol, tf_min, atr_sl_mult, rr_mult, lookback, entry_real, sl_real, tp_real, opened_at_iso)
    ("L15", "AIXBTUSDT", 15, 3.0, 3.0, 20, 0.0191100, 0.02037786, 0.01654643, "2026-08-13T00:57:21"),
    ("L15", "POWERUSDT", 15, 3.0, 3.0, 20, 0.0992600, 0.10208929, 0.09193214, "2026-08-13T01:08:06"),
    ("L15", "GUAUSDT", 15, 3.0, 3.0, 20, 0.0515000, 0.05363714, 0.04492857, "2026-08-13T01:15:16"),
    ("L15", "COTIUSDT", 15, 3.0, 3.0, 20, 0.0127060, 0.01390336, 0.00881793, "2026-08-13T16:12:00"),
    ("L15", "SCRTUSDT", 15, 3.0, 3.0, 20, 0.0381800, 0.04294429, 0.02612714, "2026-08-14T00:38:46"),
    ("L60", "HOLOUSDT", 60, 1.5, 3.0, 10, 0.0994500, 0.1070275, 0.0701575, "2026-08-12T03:29:56"),
    ("L60", "CYSUSDT", 60, 1.5, 3.0, 10, 1.6543000, 1.81445714, 1.25782857, "2026-08-13T00:38:13"),
    ("L60", "STARUSDT", 60, 1.5, 3.0, 10, 0.0887300, 0.09253321, 0.07968036, "2026-08-13T04:08:25"),
    ("L60", "APRUSDT", 60, 1.5, 3.0, 10, 0.5308000, 0.56037857, 0.36366429, "2026-08-14T04:17:06"),
    ("L60", "BEATUSDT", 60, 1.5, 3.0, 10, 0.4490000, 0.4588, 0.25686429, "2026-08-16T12:11:04"),
    ("L60", "BIGTIMEUSDT", 60, 1.5, 3.0, 10, 0.0051990, 0.00528046, 0.00494661, "2026-08-17T23:00:03"),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    strat = {"side": "SHORT"}

    matches, no_signal, no_data = 0, 0, 0
    for label, symbol, tf_min, atr_sl_mult, rr_mult, lb, entry_real, sl_real, tp_real, opened_iso in REAL_TRADES:
        rows = load_15m(conn, symbol)
        if len(rows) < 300:
            print(f"[{label}] {symbol}: SIN DATOS suficientes en klines_clean")
            no_data += 1
            continue
        candles = resample(rows, tf_min) if tf_min != 15 else rows
        opened_ts = int(datetime.fromisoformat(opened_iso).replace(tzinfo=timezone.utc).timestamp() * 1000)

        times = [c[0] for c in candles]
        idx = bisect.bisect_right(times, opened_ts) - 1
        if idx < lb + 20:
            print(f"[{label}] {symbol}: vela no encontrada / insuficiente historia previa")
            no_data += 1
            continue

        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        volumes = [c[5] for c in candles]
        atr = atr_series(candles, 14)
        a = atr[idx]

        level_high = max(highs[idx - lb:idx])
        level_low = min(lows[idx - lb:idx])
        strat_full = dict(strat, entry_type="level_sweep", lookback=lb, atr_sl_mult=atr_sl_mult, rr_mult=rr_mult)
        sig = detect_signal(strat_full, closes, highs, lows, idx, level_high, level_low, volumes)

        real_dt = datetime.utcfromtimestamp(candles[idx][0] / 1000)
        if sig == 1:  # SHORT
            entry_bt = candles[idx][4]
            sl_dist = atr_sl_mult * a
            tp_dist = sl_dist * rr_mult
            sl_bt = entry_bt + sl_dist
            tp_bt = entry_bt - tp_dist
            entry_diff_pct = abs(entry_bt - entry_real) / entry_real * 100
            sl_diff_pct = abs(sl_bt - sl_real) / sl_real * 100
            tp_diff_pct = abs(tp_bt - tp_real) / tp_real * 100
            print(f"[{label}] {symbol} @ {real_dt}: SEÑAL SI coincide | "
                  f"entry bt={entry_bt:.6f} real={entry_real:.6f} (diff {entry_diff_pct:.2f}%) | "
                  f"sl bt={sl_bt:.6f} real={sl_real:.6f} (diff {sl_diff_pct:.2f}%) | "
                  f"tp bt={tp_bt:.6f} real={tp_real:.6f} (diff {tp_diff_pct:.2f}%)")
            matches += 1
        else:
            print(f"[{label}] {symbol} @ {real_dt}: el motor NO detecta señal SHORT en esta vela (sig={sig})")
            no_signal += 1

    print(f"\n=== RESUMEN: {matches} coinciden | {no_signal} sin señal detectada | {no_data} sin datos ===")


if __name__ == "__main__":
    main()
