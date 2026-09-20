"""Cacheado y aislado para auditar MA Geometry sobre velas locales.

No usa APIs, no escribe perfiles y no puede enviar ordenes.  Carga una vez
las velas 15m de cada simbolo, deriva 1h, calcula MAs rolling y despues
simula las salidas/cupos en orden temporal global.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

FEE_PER_SIDE = 0.0004
HOUR = 60 * 60 * 1000


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def _angle(values: list[float], window: int) -> float:
    values = values[-window:]
    if len(values) < 2 or not values[-1]:
        return 0.0
    normalized = [value / values[-1] * 100.0 for value in values]
    n = len(normalized)
    sx = n * (n - 1) / 2
    sx2 = n * (n - 1) * (2 * n - 1) / 6
    sy = sum(normalized)
    sxy = sum(i * value for i, value in enumerate(normalized))
    denominator = n * sx2 - sx * sx
    return math.degrees(math.atan((n * sxy - sx * sy) / denominator)) if denominator else 0.0


def _hourly(rows: list[tuple]) -> list[tuple]:
    groups: dict[int, list[tuple]] = defaultdict(list)
    for row in rows:
        groups[row[0] - row[0] % HOUR].append(row)
    result = []
    for stamp in sorted(groups):
        group = groups[stamp]
        if len(group) == 4:  # una hora completa de velas de 15m
            result.append((stamp, group[0][1], max(x[2] for x in group), min(x[3] for x in group), group[-1][4]))
    return result


class CachedMaSlopeReplay:
    """Baseline reproducible de MA Slope Caso 3, short-only, research-only."""

    def __init__(self, db_path: str, margin: float = 150.0, slots: int = 3):
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.margin, self.slots = margin, slots

    def close(self) -> None:
        self.conn.close()

    def symbols(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m' ORDER BY symbol")]

    def _rows(self, symbol: str, start_ms: int, end_ms: int) -> list[tuple]:
        # 120h de warmup alcanza MA99 + pendiente/SL.
        return self.conn.execute(
            "SELECT open_time,open,high,low,close FROM klines_clean WHERE symbol=? AND interval='15m' AND open_time BETWEEN ? AND ? ORDER BY open_time",
            (symbol, start_ms - 120 * HOUR, end_ms),
        ).fetchall()

    def signals(self, symbol: str, start_ms: int, end_ms: int) -> list[dict]:
        rows = self._rows(symbol, start_ms, end_ms)
        hourly = _hourly(rows)
        closes = [x[4] for x in hourly]
        ma7, ma25, ma50, ma99 = (_sma(closes, p) for p in (7, 25, 50, 99))
        signals: list[dict] = []
        by_time = {row[0]: i for i, row in enumerate(rows)}
        for i in range(105, len(hourly)):
            stamp, _open, high, _low, close = hourly[i]
            if not start_ms <= stamp <= end_ms or not all(x[i] is not None for x in (ma7, ma25, ma50, ma99)):
                continue
            # Perfil congelado de Caso 3: MAs ordenadas alcistas + giro MA7 hacia abajo + pico reciente.
            if not (ma7[i] > ma25[i] > ma50[i] > ma99[i]):
                continue
            if not (_angle([x for x in ma7[i - 2:i + 1] if x is not None], 3) <= -0.2 and _angle([x for x in ma7[i - 5:i - 2] if x is not None], 3) >= 0.2):
                continue
            recent_high = max(x[2] for x in hourly[i - 9:i + 1])
            if abs(close - recent_high) / recent_high * 100 > 1.0:
                continue
            entry_time = stamp + HOUR
            index = by_time.get(entry_time)
            if index is None:
                continue
            entry = rows[index][1]
            sl = recent_high * 1.01
            tp = entry * 0.90  # tpMinPct congelado: 10% para short
            signals.append({"symbol": symbol, "side": "short", "open_time": entry_time, "entry": entry, "sl": sl, "tp": tp, "rows": rows, "index": index})
        return signals

    def _exit(self, signal: dict, max_bars: int = 192) -> dict:
        rows, start = signal["rows"], signal["index"]
        end = min(len(rows), start + max_bars + 1)
        for row in rows[start:end]:
            if row[2] >= signal["sl"]:
                return {**signal, "close_time": row[0] + 15 * 60 * 1000, "close": signal["sl"], "reason": "SL"}
            if row[3] <= signal["tp"]:
                return {**signal, "close_time": row[0] + 15 * 60 * 1000, "close": signal["tp"], "reason": "TP"}
        row = rows[end - 1]
        return {**signal, "close_time": row[0] + 15 * 60 * 1000, "close": row[4], "reason": "timeout"}

    def run(self, start_ms: int, end_ms: int, symbols: list[str] | None = None) -> dict:
        raw = []
        for symbol in symbols or self.symbols():
            raw.extend(self.signals(symbol, start_ms, end_ms))
        raw = [self._exit(signal) for signal in raw]
        raw.sort(key=lambda trade: (trade["open_time"], trade["symbol"]))
        open_until, accepted = [], []
        for trade in raw:
            open_until = [close for close in open_until if close > trade["open_time"]]
            if len(open_until) >= self.slots:
                continue
            open_until.append(trade["close_time"])
            qty = self.margin / trade["entry"]
            trade["pnl"] = qty * (trade["entry"] - trade["close"]) - (self.margin + qty * trade["close"]) * FEE_PER_SIDE
            accepted.append(trade)
        months: dict[str, float] = defaultdict(float)
        for trade in accepted:
            months[datetime.fromtimestamp(trade["open_time"] / 1000, timezone.utc).strftime("%Y-%m")] += trade["pnl"]
        return {"mode": "cached_ma_slope_case3_research", "signals": len(raw), "trades": accepted, "pnl": sum(t["pnl"] for t in accepted), "monthly": dict(months)}
