"""Adaptador MA Slope Caso 3: stream BRUTO de señales (sin cupos, sin ranking, sin salida).

Población congelada de Fase 2: 9.400 señales sobre 2025-12-01 .. 2026-08-01. NO es la selección
real de producción. Cortes TRAIN/VAL/OOS fijados antes de ver resultados (MISION_LOG.md).
"""
from __future__ import annotations

import os
import pickle
import sqlite3
from datetime import datetime, timezone

from . import Adapter

HOUR = 3_600_000
START = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
CUT_TRAIN_VAL = int(datetime(2026, 4, 26, tzinfo=timezone.utc).timestamp() * 1000)
CUT_VAL_OOS = int(datetime(2026, 6, 14, tzinfo=timezone.utc).timestamp() * 1000)

STREAM_CACHE = os.environ.get(
    "LAB_MA3_STREAM", "/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl")
CANONICAL_DB = os.environ.get("LAB_CANONICAL_DB", "/app/data/binance_vision_clean.db")


class MA3Adapter(Adapter):
    name = "ma3"
    aliases = ("MA Slope Caso 3", "ma_slope_caso_3", "caso3")
    population = "raw"
    bar_ms = 300_000
    # Referencia histórica: calculada antes de corregir `b` -> instante real
    # de entrada. Se conserva como evidencia, pero no valida corridas nuevas.
    expected_baseline_v1_desalineado = {
        "unconditional|tp_bias_-2": 0.30710306548436167,
        "unconditional|tp_bias_+2": 0.43860991479943023,
        "conditional|tp_bias_-2": 0.058502362807107265,
        "conditional|tp_bias_+2": 0.5078174313002582,
    }

    def entries(self):
        if not os.path.exists(STREAM_CACHE):
            raise SystemExit(
                f"falta el stream congelado {STREAM_CACHE}. Regeneralo con "
                "fase2_ma3_broad_matrix.py (≈1,5 h) o fijá LAB_MA3_STREAM.")
        stream = pickle.load(open(STREAM_CACHE, "rb"))["stream"]
        # engine.py evalúa al cierre de la hora: now_ms=b+interval_ms. El
        # precio del stream coincide con ese cierre, no con el comienzo `b`.
        return [{"open_ms": b + HOUR, "symbol": s, "entry": e, "sl": sl, "tp": tp, "side": side}
                for b, s, e, sl, tp, side, _ in stream]

    def candles(self, symbol):
        conn = self._pid_conn("canon", lambda: sqlite3.connect(f"file:{CANONICAL_DB}?mode=ro", uri=True))
        return conn.execute(
            "SELECT open_time, high, low, close FROM klines_5m WHERE symbol=? AND interval='5m' "
            "AND open_time>=? AND open_time<? ORDER BY open_time",
            (symbol, START, END + 720 * HOUR)).fetchall()

    def split_of(self, open_ms):
        # END es inclusivo solo para el último split (4 señales caen exactamente en END; ver MISION_LOG.md).
        if open_ms < CUT_TRAIN_VAL:
            return "TRAIN"
        if open_ms < CUT_VAL_OOS:
            return "VALIDATION"
        return "OOS"
