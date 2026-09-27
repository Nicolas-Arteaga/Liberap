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
import sqlite3

from . import Adapter

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

    def __init__(self):
        self._cuts = None

    def entries(self):
        out = []
        for row in csv.DictReader(open(CSV_PATH, encoding="utf8")):
            try:
                out.append({"open_ms": int(float(row["open_ms"])), "symbol": row["symbol"], "entry": float(row["entry"]),
                            "side": int(row["side"]), "sl": float(row["sl"]), "tp": float(row["tp"])})
            except (ValueError, KeyError):
                continue  # fila sin SL/TP/entrada válidos
        out.sort(key=lambda t: t["open_ms"])
        n = len(out)
        if n:
            self._cuts = (out[int(n * 0.50)]["open_ms"], out[min(n - 1, int(n * 0.75))]["open_ms"])
        return out

    def candles(self, symbol):
        conn = self._pid_conn("live", lambda: sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True, timeout=10))
        return conn.execute(
            "SELECT open_time, high, low, close FROM klines WHERE symbol=? AND interval='15m' "
            "ORDER BY open_time", (symbol,)).fetchall()

    def split_of(self, open_ms):
        if self._cuts is None:
            self.entries()
        if open_ms < self._cuts[0]:
            return "TRAIN"
        if open_ms < self._cuts[1]:
            return "VALIDATION"
        return "OOS"
