"""Adaptador Band Touch 15m: trades REALES cerrados (selección de producción) con velas 15m del agente.

Entradas: `lab_inputs/band_touch_real_trades.csv`, export de PostgreSQL:
  select st."Symbol" symbol, st."Side" side, st."EntryPrice" entry, st."SlPrice" sl, st."TpPrice" tp,
         extract(epoch from st."OpenedAt")*1000 open_ms, extract(epoch from st."ClosedAt")*1000 close_ms,
         st."ExitReason" exit_reason, st."ClosePrice" close_price
  from "SimulatedTrades" st join "StrategyProfiles" sp on sp."Id"=st."StrategyProfileId"
  where sp."Name" ilike 'Band Touch%' and st."ClosedAt" is not null order by st."OpenedAt";
Velas: agent/data/klines.db (montada :ro en /app/live-research/klines.db), tabla `klines`, intervalo 15m.
N chico: los splits son por tiempo (50/25/25 % de las entradas) y la máquina NO permite la etiqueta ROBUSTO
con menos de 200 entradas OOS, por lo que el máximo posible aquí es INDICIO-DEBIL.
"""
from __future__ import annotations

import csv
import os

from . import Adapter, AdapterDefinition, EntryDefinition, SQLiteCandleSource, TemporalQuantileSplits

HOUR = 3_600_000
CSV_PATH = os.environ.get(
    "LAB_BAND_CSV", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "lab_inputs", "band_touch_real_trades.csv"))
LIVE_DB = os.environ.get("LAB_LIVE_DB", "/app/live-research/klines.db")


class BandTouchAdapter(Adapter):
    name = "band_touch"
    aliases = ("Band Touch 15m", "band_touch_15m")
    population = "real"
    bar_ms = 900_000
    expected_baseline = None  # sin baseline histórico congelado: el chequeo de regresión no aplica
    require_coverage = True   # entradas fuera de la cobertura de velas se descartan (y se cuentan)
    definition = AdapterDefinition(
        name=name, display_name="Band Touch 15m", aliases=aliases,
        population=population, bar_ms=bar_ms, require_coverage=require_coverage,
    )
    entry_definition = EntryDefinition(
        source="CSV congelado de trades reales cerrados",
        condition="toque de banda que ya pasó la selección de producción",
        execution_time="instante OpenedAt del trade real",
    )
    candle_source = SQLiteCandleSource(
        key="live", db_path=LIVE_DB, table="klines", interval="15m", timeout=10,
    )

    def __init__(self):
        self.split_policy = TemporalQuantileSplits()

    def build_entries(self):
        out = []
        with open(CSV_PATH, encoding="utf8") as handle:
            for row in csv.DictReader(handle):
                try:
                    out.append({"open_ms": int(float(row["open_ms"])), "symbol": row["symbol"], "entry": float(row["entry"]),
                                "side": int(row["side"]), "sl": float(row["sl"]), "tp": float(row["tp"])})
                except (ValueError, KeyError):
                    continue  # fila sin SL/TP/entrada válidos
        out.sort(key=lambda t: t["open_ms"])
        self.split_policy.fit(out)
        return out

    def candles(self, symbol):
        return self.candle_source.rows(self, symbol)

    def split_of(self, open_ms):
        if self.split_policy._cuts is None:
            self.entries()
        return self.split_policy.split_of(open_ms)
