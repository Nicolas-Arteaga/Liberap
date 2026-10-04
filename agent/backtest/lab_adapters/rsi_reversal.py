"""Adaptador de reversión RSI14 15m, definido para la E2E Research↔Máquina.

Regla fija y causal (no una variante de MA3, Band Touch ni Level Sweep):

* LONG: el RSI Wilder de 14 velas cruza desde ``<= 30`` a ``> 30``.
* SHORT: el RSI Wilder de 14 velas cruza desde ``>= 70`` a ``< 70``.

La señal se confirma al cierre de la vela 15m y se abre exactamente entonces.
El stop es 2 × ATR14 simple de las velas cerradas y el objetivo es 3R.  Sólo
se conserva la primera señal de cada símbolo por día UTC para evitar churn.
No lee red, producción, ledger ni StrategyProfiles.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from . import Adapter, AdapterDefinition, EntryDefinition, SQLiteCandleSource, TemporalQuantileSplits
from .level_sweep import TOP_40_SYMBOLS, rolling_atr

BAR_MS = 15 * 60 * 1000
HOUR = 60 * 60 * 1000
RSI_PERIOD = 14
ATR_SL_MULT = 2.0
RR_MULT = 3.0
CANONICAL_DB = os.environ.get("LAB_CANONICAL_DB", "/app/data/binance_vision_clean.db")


def wilder_rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    """RSI Wilder igual a ``btc_condition_scan.rsi_series``; sin velas futuras."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = losses = 0.0
    for index in range(1, period + 1):
        delta = closes[index] - closes[index - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) if avg_loss > 0 else 100.0
    for index in range(period + 1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gain, loss = max(delta, 0.0), max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[index] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) if avg_loss > 0 else 100.0
    return out


class RSIReversalAdapter(Adapter):
    name = "rsi_reversal"
    aliases = ("RSI Reversal 15m", "rsi14_reversal_15m")
    population = "raw"
    bar_ms = BAR_MS
    require_coverage = True
    expected_baseline = None
    fidelity_result = {
        "detection": "no evaluada",
        "exit_reason": "no evaluada",
        "return": "no evaluada",
        "selection": "replay histórico bruto; no es selección de producción",
    }
    fidelity_note = (
        "Fidelidad: estrategia nueva de Research; no fue medida contra ledger ni contra operaciones reales."
    )
    definition = AdapterDefinition(
        name=name, display_name="RSI14 Reversal 15m SL2/RR3", aliases=aliases,
        population=population, bar_ms=bar_ms, require_coverage=require_coverage,
    )
    entry_definition = EntryDefinition(
        source="velas 15m locales klines_clean de la canasta TOP_40 congelada",
        condition=("LONG RSI14 Wilder cruza <=30 a >30; SHORT cruza >=70 a <70; "
                   "máximo una señal por símbolo/día UTC; SL=2*ATR14, TP=3R"),
        execution_time="cierre de la vela 15m que confirma el cruce RSI",
    )
    candle_source = SQLiteCandleSource(
        key="rsi_reversal_canon", db_path=CANONICAL_DB, table="klines_clean", interval="15m",
    )

    def __init__(self):
        self.split_policy = TemporalQuantileSplits()
        self._entries_cache: list[dict] | None = None

    def _signal_rows(self, symbol: str) -> list[tuple]:
        conn = self._pid_conn(
            "rsi_reversal_entry",
            lambda: sqlite3.connect(f"file:{CANONICAL_DB}?mode=ro", uri=True),
        )
        return conn.execute(
            "SELECT open_time, open, high, low, close FROM klines_clean "
            "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)
        ).fetchall()

    def build_entries(self):
        if self._entries_cache is not None:
            return self._entries_cache
        out: list[dict] = []
        for symbol in TOP_40_SYMBOLS:
            rows = self._signal_rows(symbol)
            if len(rows) <= RSI_PERIOD + 2:
                continue
            rsi, atr = wilder_rsi([row[4] for row in rows]), rolling_atr(rows)
            last_allowed_open = rows[-1][0] - 720 * HOUR
            last_signal_day = None
            for index in range(max(RSI_PERIOD + 1, 14), len(rows)):
                timestamp, _open, _high, _low, close = rows[index]
                previous, current, atr_value = rsi[index - 1], rsi[index], atr[index]
                if timestamp > last_allowed_open or previous is None or current is None or not atr_value or atr_value <= 0:
                    continue
                if previous <= 30.0 < current:
                    side = 0
                elif previous >= 70.0 > current:
                    side = 1
                else:
                    continue
                open_ms = timestamp + BAR_MS
                day = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).date()
                if day == last_signal_day:
                    continue
                risk = ATR_SL_MULT * atr_value
                sl = close - risk if side == 0 else close + risk
                tp = close + risk * RR_MULT if side == 0 else close - risk * RR_MULT
                out.append({"open_ms": open_ms, "symbol": symbol, "entry": close,
                            "side": side, "sl": sl, "tp": tp})
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
