"""Contrato histórico para FVG-15m de producción.

La detección se mantiene en ``python-service/fvg/detector.py``: es una
función pura de OHLC y no llama HTTP.  La materialización formal no usa la
API ni el servidor FastAPI: ``fvg_formal.py`` le inyecta velas históricas al
replay global de producción, que conserva la selección Top-5, los vetos y el
constructor estructural de SL/TP.  Este adaptador aporta exclusivamente el
proveedor de velas y los splits para volver a auditar esas entradas
inmutables.
"""
from __future__ import annotations

import os

from . import Adapter, AdapterDefinition, EntryDefinition, SQLiteCandleSource, TemporalQuantileSplits

BAR_MS = 15 * 60 * 1000
CANONICAL_DB = os.environ.get("LAB_CANONICAL_DB", "/app/data/binance_vision_clean.db")


class FVGProductionAdapter(Adapter):
    name = "fvg_production"
    aliases = ("FVG Production 15m", "fvg_15m_production")
    population = "raw"
    bar_ms = BAR_MS
    require_coverage = True
    definition = AdapterDefinition(
        name=name, display_name="FVG 15m — replay productivo", aliases=aliases,
        population=population, bar_ms=bar_ms, require_coverage=True,
    )
    entry_definition = EntryDefinition(
        source="replay global FVG sobre klines históricas locales; detector puro detect_fvgs",
        condition=("FVG de tres velas activo, IN_ZONE/APPROACHING, alineado con EMA25/50; "
                   "selección Top-5 global por recorrido a TP y vetos productivos. "
                   "SL estructural = borde de invalidación ±15% del gap; TP = liquidez "
                   "estructural con haircut productivo."),
        execution_time="tick de scan histórico de 5m que pasa la selección y validación productivas",
    )
    candle_source = SQLiteCandleSource(
        key="fvg_production_canon", db_path=CANONICAL_DB, table="klines_clean", interval="15m",
    )

    def __init__(self):
        self.split_policy = TemporalQuantileSplits()

    def build_entries(self):
        raise RuntimeError("FVGProductionAdapter se materializa mediante fvg_formal.py; no regenera señales.")

    def candles(self, symbol):
        return self.candle_source.rows(self, symbol)

    def split_of(self, open_ms):
        return self.split_policy.split_of(open_ms)
