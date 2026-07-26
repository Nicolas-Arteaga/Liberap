"""
Backtest de "FVG - 15m Pulido" (Short-only + filtro de agotamiento) contra
klines historicos cacheados en agent/data/klines.db, SIN look-ahead.

Reusa el motor REAL de deteccion de FVG (python-service/fvg/analyzer.py,
detect_fvgs de detector.py) en vez de reimplementar la logica — se
monkeypatchea unicamente _fetch_klines para que en lugar de pegarle a
Binance en vivo, devuelva la ventana de 200 velas que YA EXISTIA en el
momento simulado (nunca velas futuras).

Filtro de agotamiento (mismo que produccion, ver verge_agent.py):
pendiente de EMA50 (10 velas) >= MIN_EXHAUSTION_SLOPE_DEG para aceptar un
SHORT. Solo SHORT (Long ya descartado con evidencia real, ver PROGRESS_LOG
2026-07-25).

Uso: python fvg_short_backtest.py [--symbols N] [--min-slope 3.0]
"""
import sys
import os
import sqlite3
import math
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python-service"))

import pandas as pd

from fvg.analyzer import FvgAnalyzer
from fvg.schemas import FvgScanRequest

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
TABLE = "klines_clean"
INTERVAL = "15m"
SCAN_WINDOW = 200          # mismo tamano de ventana que produccion (_scan_symbol)
STEP_BARS = 1              # re-escanea CADA vela de 15m — es lo mas fino posible con
                           # este dato (el agente real escanea cada 5 min, pero 15m es
                           # la resolucion minima que tenemos cacheada). Bug real
                           # 2026-07-25: con STEP_BARS=4 (cada 1h) el backtest no
                           # reprodujo ni un solo trade en NIGHTUSDT (el mejor ganador
                           # real en vivo) — la señal probablemente aparecio y se
                           # llenaria dentro de esa hora sin que el muestreo la viera.
SL_BUFFER_RATIO_CHECK = 0.15


def load_symbol_klines(conn, symbol):
    cur = conn.cursor()
    cur.execute(
        f"SELECT open_time, open, high, low, close, volume FROM {TABLE} "
        "WHERE symbol=? AND interval=? ORDER BY open_time ASC",
        (symbol, INTERVAL),
    )
    return cur.fetchall()


def has_gap(window_rows, max_gap_ms=15 * 60 * 1000 * 2):
    """True si hay un salto de tiempo > 2 velas seguidas en la ventana —
    evita calcular pendiente/detectar gaps sobre datos discontinuos."""
    for i in range(1, len(window_rows)):
        if window_rows[i][0] - window_rows[i - 1][0] > max_gap_ms:
            return True
    return False


def ema50_slope_deg(closes_window):
    """Replica _compute_compression_snapshot: pendiente de MA50 sobre las
    ultimas 10 velas, en grados. closes_window debe tener >= 60 cierres."""
    n = len(closes_window)
    if n < 60:
        return None

    def sma(arr, period, idx):
        start = max(0, idx - period + 1)
        w = arr[start:idx + 1]
        return sum(w) / len(w) if w else 0.0

    ma50 = [sma(closes_window, 50, i) for i in range(n)]
    if ma50[-1] <= 0 or ma50[-10] <= 0:
        return None
    slope_raw = (ma50[-1] - ma50[-10]) / ma50[-10]
    return round(math.degrees(math.atan(slope_raw * 100)), 4)


def make_patched_analyzer(rows_up_to_now):
    """rows_up_to_now: lista de tuplas (open_time,o,h,l,c,v) YA recortada
    al instante simulado (nada de despues)."""
    analyzer = FvgAnalyzer()

    def _fetch_klines_patched(symbol, interval, limit):
        window = rows_up_to_now[-limit:]
        # formato identico al que devuelve Binance REST (lista de listas)
        return [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in window]

    analyzer._fetch_klines = _fetch_klines_patched
    return analyzer


def backtest_symbol(symbol, rows, min_slope_deg=None, direction="bearish", max_gap_pct=None):
    """
    direction: "bearish" (Short, filtro de pendiente) o "bullish" (Long,
    filtro de gap chico — ver auditoria real 2026-07-25, la pendiente NO
    sirve para Long, se contamina con mechas puntuales).
    """
    trades = []
    n = len(rows)
    if n < SCAN_WINDOW + 60:
        return trades

    i = SCAN_WINDOW + 60  # primer indice con suficiente historia (ventana + slope)
    open_trade = None
    last_trade_day = None

    while i < n:
        # ── ¿hay posicion abierta? simular hasta que cierre ──
        if open_trade:
            row = rows[i]
            _, o, h, l, c, v = row
            if direction == "bearish":
                if l <= open_trade["tp"]:
                    trades.append({**open_trade, "close_reason": "TP", "close_time": row[0]})
                    open_trade = None
                elif h >= open_trade["sl"]:
                    trades.append({**open_trade, "close_reason": "SL", "close_time": row[0]})
                    open_trade = None
                else:
                    i += 1
                    continue
            else:  # bullish (Long): TP arriba, SL abajo — checks invertidos
                if h >= open_trade["tp"]:
                    trades.append({**open_trade, "close_reason": "TP", "close_time": row[0]})
                    open_trade = None
                elif l <= open_trade["sl"]:
                    trades.append({**open_trade, "close_reason": "SL", "close_time": row[0]})
                    open_trade = None
                else:
                    i += 1
                    continue

        # ── buscar candidato nuevo cada STEP_BARS velas ──
        if i % STEP_BARS != 0:
            i += 1
            continue

        day_key = datetime.utcfromtimestamp(rows[i][0] / 1000).date()
        if last_trade_day == day_key:
            i += 1
            continue  # anti-churn: 1 entrada por dia por simbolo (igual que produccion)

        window_rows = rows[max(0, i - SCAN_WINDOW + 1): i + 1]
        if has_gap(window_rows):
            i += 1
            continue
        analyzer = make_patched_analyzer(window_rows)
        try:
            item, reason = analyzer._scan_symbol(symbol, INTERVAL, sort_by="range")
        except Exception:
            i += 1
            continue

        if not item or item.direction != direction:
            i += 1
            continue

        slope = None
        if min_slope_deg is not None:
            closes = [r[4] for r in window_rows]
            slope = ema50_slope_deg(closes)
            if slope is None or slope < min_slope_deg:
                i += 1
                continue

        if max_gap_pct is not None:
            gap_pct = item.gap_pct
            if gap_pct is None or gap_pct >= max_gap_pct:
                i += 1
                continue

        open_trade = {
            "symbol": symbol,
            "open_time": rows[i][0],
            "entry": item.current_price,
            "sl": item.sl_price,
            "tp": item.tp_price,
            "slope": slope,
            "gap_pct": item.gap_pct,
        }
        last_trade_day = day_key
        i += 1

    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=200)
    ap.add_argument("--min-slope", type=float, default=None)
    ap.add_argument("--max-gap-pct", type=float, default=None)
    ap.add_argument("--direction", choices=["bearish", "bullish"], default="bearish")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"SELECT symbol, COUNT(*) n FROM {TABLE} WHERE interval=? GROUP BY symbol ORDER BY n DESC LIMIT ?",
        (INTERVAL, args.symbols),
    )
    symbols = [r[0] for r in cur.fetchall()]
    print(f">>> Backtesting {len(symbols)} simbolos, direction={args.direction}, min_slope={args.min_slope}, max_gap_pct={args.max_gap_pct}", flush=True)

    all_trades = []
    for idx, sym in enumerate(symbols):
        rows = load_symbol_klines(conn, sym)
        trades = backtest_symbol(sym, rows, args.min_slope, direction=args.direction, max_gap_pct=args.max_gap_pct)
        all_trades.extend(trades)
        if (idx + 1) % 20 == 0:
            print(f"  [{idx+1}/{len(symbols)}] {sym}: {len(trades)} trades (total acumulado={len(all_trades)})", flush=True)

    wins = [t for t in all_trades if t["close_reason"] == "TP"]
    losses = [t for t in all_trades if t["close_reason"] == "SL"]
    print()
    print(f"=== RESULTADO FINAL ===")
    print(f"Total trades: {len(all_trades)}")
    print(f"Wins (TP): {len(wins)} | Losses (SL): {len(losses)}")
    if all_trades:
        wr = len(wins) / len(all_trades) * 100
        print(f"Win rate: {wr:.1f}%")

    import json
    out_path = os.path.join(os.path.dirname(__file__), "fvg_short_backtest_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=2, default=str)
    print(f"Guardado: {out_path}")


if __name__ == "__main__":
    main()
