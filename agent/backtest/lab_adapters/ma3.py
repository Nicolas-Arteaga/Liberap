"""Adaptador MA Slope Caso 3: stream BRUTO de señales (sin cupos, sin ranking, sin salida).

Población congelada de Fase 2: 9.400 señales sobre 2025-12-01 .. 2026-08-01. NO es la selección
real de producción. Cortes TRAIN/VAL/OOS fijados antes de ver resultados (MISION_LOG.md).
"""
from __future__ import annotations

import os
import pickle
from datetime import datetime, timezone

from . import Adapter, AdapterDefinition, EntryDefinition, FixedTimeSplits, SQLiteCandleSource

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
    definition = AdapterDefinition(
        name=name, display_name="MA Slope Caso 3", aliases=aliases,
        population=population, bar_ms=bar_ms,
    )
    entry_definition = EntryDefinition(
        source="stream pickle congelado de Fase 2",
        condition="señal MA Slope Caso 3 ya evaluada por engine.py",
        execution_time="cierre de la hora: b + interval_ms",
    )
    candle_source = SQLiteCandleSource(
        key="canon", db_path=CANONICAL_DB, table="klines_5m", interval="5m",
        start_ms=START, end_ms=END + 720 * HOUR,
    )
    split_policy = FixedTimeSplits(CUT_TRAIN_VAL, CUT_VAL_OOS)
    # Referencia histórica: calculada antes de corregir `b` -> instante real
    # de entrada. Se conserva como evidencia, pero no valida corridas nuevas.
    expected_baseline_v1_desalineado = {
        "unconditional|tp_bias_-2": 0.30710306548436167,
        "unconditional|tp_bias_+2": 0.43860991479943023,
        "conditional|tp_bias_-2": 0.058502362807107265,
        "conditional|tp_bias_+2": 0.5078174313002582,
    }
    # Baseline activo tras el corrigendum M1b: entradas al cierre de la hora.
    # Este mapa alimenta el gate de regresión de lab_diagnose.py; v1 queda sólo
    # como evidencia histórica y no puede validar una corrida nueva.
    expected_baseline = {
        "unconditional|tp_bias_-2": 0.3180237011,
        "unconditional|tp_bias_+2": 0.4504469093,
        "conditional|tp_bias_-2": 0.0548301563,
        "conditional|tp_bias_+2": 0.5053421017,
    }
    baseline_scenario_tol = 1e-8

    def build_entries(self):
        if not os.path.exists(STREAM_CACHE):
            raise SystemExit(
                f"falta el stream congelado {STREAM_CACHE}. Regeneralo con "
                "fase2_ma3_broad_matrix.py (≈1,5 h) o fijá LAB_MA3_STREAM.")
        with open(STREAM_CACHE, "rb") as handle:
            stream = pickle.load(handle)["stream"]
        # engine.py evalúa al cierre de la hora: now_ms=b+interval_ms. El
        # precio del stream coincide con ese cierre, no con el comienzo `b`.
        return [{"open_ms": b + HOUR, "symbol": s, "entry": e, "sl": sl, "tp": tp, "side": side}
                for b, s, e, sl, tp, side, _ in stream]

    def candles(self, symbol):
        return self.candle_source.rows(self, symbol)

    def split_of(self, open_ms):
        # END es inclusivo solo para el último split (4 señales caen exactamente en END; ver MISION_LOG.md).
        return self.split_policy.split_of(open_ms)
