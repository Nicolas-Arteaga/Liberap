"""Adaptador de Level Sweep 15m SL3/RR3, construido sobre velas históricas locales.

La definición replica la condición simple que ya usa el backtest de producción:
una vela barre el máximo/mínimo de las ``LOOKBACK`` velas anteriores y cierra
de vuelta dentro del nivel.  La entrada se toma al cierre de esa vela; por eso
``open_ms`` es su fin y satisface explícitamente el contrato M1b de replay.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from . import Adapter, AdapterDefinition, EntryDefinition, SQLiteCandleSource, TemporalQuantileSplits

BAR_MS = 15 * 60 * 1000
HOUR = 60 * 60 * 1000
ARG_OFFSET_MS = 3 * HOUR
LOOKBACK = 20
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
RR_MULT = 3.0
CANONICAL_DB = os.environ.get("LAB_CANONICAL_DB", "/app/data/binance_vision_clean.db")

# La misma canasta líquida congelada en backtest.engine::TOP_40_SYMBOLS. Se
# copia aquí para que importar un adaptador sea una operación de sólo lectura
# y no cargue el motor de producción ni sus efectos de configuración.
TOP_40_SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "SUIUSDT", "INJUSDT", "TIAUSDT", "SEIUSDT", "FILUSDT",
    "ETCUSDT", "TRXUSDT", "BCHUSDT", "UNIUSDT", "AAVEUSDT", "MKRUSDT", "RUNEUSDT",
    "FTMUSDT", "GALAUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT", "CHZUSDT", "ENJUSDT",
    "XLMUSDT", "ALGOUSDT", "VETUSDT", "EOSUSDT", "WLDUSDT",
)


def rolling_atr(rows: list[tuple], period: int = ATR_PERIOD) -> list[float | None]:
    """ATR simple de 14 TR: la misma fórmula de strategy_lab.atr_series."""
    trs = [0.0]
    for index in range(1, len(rows)):
        high, low, previous_close = rows[index][2], rows[index][3], rows[index - 1][4]
        trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    values: list[float | None] = [None] * len(rows)
    for index in range(period, len(rows)):
        window = trs[max(1, index - period + 1):index + 1]
        values[index] = sum(window) / len(window) if window else None
    return values


class LevelSweepAdapter(Adapter):
    name = "level_sweep"
    aliases = ("Level Sweep 15m", "level_sweep_15m", "level_sweep_15m_sl3_rr3")
    population = "raw"
    bar_ms = BAR_MS
    require_coverage = True
    expected_baseline = None
    fidelity_result = {
        "detection": "no evaluada",
        "exit_reason": "no evaluada",
        "return": "no evaluada",
        "selection": "no reproducible sin ledger ni export de trades reales",
    }
    fidelity_note = (
        "Fidelidad: no evaluada todavía contra ledger ni contra export de trades reales; "
        "este informe describe señales históricas brutas, no selección de producción."
    )
    definition = AdapterDefinition(
        name=name, display_name="Level Sweep 15m SL3/RR3", aliases=aliases,
        population=population, bar_ms=bar_ms, require_coverage=require_coverage,
    )
    entry_definition = EntryDefinition(
        source="velas 15m locales de la canasta TOP_40 congelada",
        condition="mecha supera el máximo/mínimo de 20 velas y el cierre recupera el nivel",
        execution_time="cierre de la vela 15m que confirma el barrido",
    )
    candle_source = SQLiteCandleSource(
        key="level_canon", db_path=CANONICAL_DB, table="klines_clean", interval="15m",
    )

    def __init__(self):
        self.split_policy = TemporalQuantileSplits()
        self._entries_cache: list[dict] | None = None

    def _signal_rows(self, symbol: str) -> list[tuple]:
        conn = self._pid_conn(
            "level_entry",
            lambda: sqlite3.connect(f"file:{CANONICAL_DB}?mode=ro", uri=True),
        )
        return conn.execute(
            "SELECT open_time, open, high, low, close FROM klines_clean "
            "WHERE symbol=? AND interval='15m' ORDER BY open_time",
            (symbol,),
        ).fetchall()

    def build_entries(self):
        if self._entries_cache is not None:
            return self._entries_cache
        out: list[dict] = []
        for symbol in TOP_40_SYMBOLS:
            rows = self._signal_rows(symbol)
            if len(rows) <= LOOKBACK + ATR_PERIOD:
                continue
            atr = rolling_atr(rows)
            last_signal_day = None
            # Se omiten las últimas 720h por símbolo: el replay debe poder
            # observar toda la trayectoria máxima, igual que MA3.
            last_allowed_open = rows[-1][0] - 720 * HOUR
            for index in range(max(LOOKBACK + 1, ATR_PERIOD), len(rows)):
                ts, _open, high, low, close = rows[index]
                if ts > last_allowed_open or not atr[index] or atr[index] <= 0:
                    continue
                level_high = max(row[2] for row in rows[index - LOOKBACK:index])
                level_low = min(row[3] for row in rows[index - LOOKBACK:index])
                if high > level_high and close < level_high:
                    side = 1
                elif low < level_low and close > level_low:
                    side = 0
                else:
                    continue
                # El agente no vuelve a operar el mismo símbolo durante el
                # día local. Usar UTC-3 replica la convención documentada en
                # backtest.engine::ARG_OFFSET_MS sin importar el reloj host.
                entry_ms = ts + BAR_MS
                day = datetime.fromtimestamp((entry_ms - ARG_OFFSET_MS) / 1000, tz=timezone.utc).date()
                if day == last_signal_day:
                    continue
                distance = ATR_SL_MULT * atr[index]
                if side == 1:
                    sl, tp = close + distance, close - distance * RR_MULT
                else:
                    sl, tp = close - distance, close + distance * RR_MULT
                out.append({
                    "open_ms": entry_ms,
                    "symbol": symbol,
                    "entry": close,
                    "side": side,
                    "sl": sl,
                    "tp": tp,
                })
                last_signal_day = day
        out.sort(key=lambda item: (item["open_ms"], item["symbol"]))
        self.split_policy.fit(out)
        self._entries_cache = out
        return out

    def candles(self, symbol):
        return self.candle_source.rows(self, symbol)

    def split_of(self, open_ms):
        if self.split_policy._cuts is None:
            self.entries()
        return self.split_policy.split_of(open_ms)
