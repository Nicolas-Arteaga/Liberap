"""Contexto reutilizable y acotado para auditorías del Laboratorio.

No decide señales ni altera las fórmulas. Sólo evita que candidatos de un
mismo worker vuelvan a materializar la misma fuente OHLC y sus derivados.
"""
from __future__ import annotations

import bisect
import hashlib
import math
import os
import pickle
import sqlite3
import statistics
import ctypes
from collections import OrderedDict
from dataclasses import dataclass

import lab_core as C


@dataclass(frozen=True)
class SymbolContext:
    rows: list
    opens: list[int]
    hours: list
    hour_starts: list[int]
    atr14: tuple[float | None, ...]
    range_pct: tuple[float | None, ...]
    adx14: tuple[float | None, ...]
    rv20_mid: tuple[bool | None, ...]

    def closed_hour_count(self, open_ms: int) -> int:
        return bisect.bisect_right(self.hour_starts, int(open_ms) - C.HOUR)

    def atr_before(self, open_ms: int) -> float | None:
        return self.atr14[self.closed_hour_count(open_ms)]


class _Fenwick:
    """Árbol de frecuencias para percentiles exactos en O(log n)."""
    def __init__(self, size: int):
        self.tree = [0] * (size + 1)
        self.size = size

    def add(self, index: int) -> None:
        index += 1
        while index <= self.size:
            self.tree[index] += 1
            index += index & -index

    def kth(self, rank: int) -> int:
        """Índice cero-basado del valor con rango cero-basado ``rank``."""
        target, index, bit = rank + 1, 0, 1 << (self.size.bit_length() - 1)
        while bit:
            candidate = index + bit
            if candidate <= self.size and self.tree[candidate] < target:
                index, target = candidate, target - self.tree[candidate]
            bit >>= 1
        return index


def _atr14_schedule(hours: list) -> tuple[float | None, ...]:
    values: list[float | None] = [None] * (len(hours) + 1)
    for end in range(C.ATR_PERIOD + 1, len(hours) + 1):
        trs = []
        for index in range(end - C.ATR_PERIOD, end):
            _, high, low, _ = hours[index]
            previous_close = hours[index - 1][3]
            trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        values[end] = sum(trs) / C.ATR_PERIOD
    return tuple(values)


def _adx14_schedule(hours: list) -> tuple[float | None, ...]:
    """Replica `_adx14(hours[:end])` en una sola pasada."""
    period = 14
    out: list[float | None] = [None] * (len(hours) + 1)
    if len(hours) < period * 2:
        return tuple(out)
    trs, plus_dm, minus_dm = [], [], []
    for index in range(1, len(hours)):
        _, high, low, close = hours[index]
        _, prev_high, prev_low, prev_close = hours[index - 1]
        up, down = high - prev_high, prev_low - low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(trs[:period]) / period
    plus = sum(plus_dm[:period]) / period
    minus = sum(minus_dm[:period]) / period
    dxs, adx = [], None
    for index in range(period - 1, len(trs)):
        if index > period - 1:
            atr = (atr * (period - 1) + trs[index]) / period
            plus = (plus * (period - 1) + plus_dm[index]) / period
            minus = (minus * (period - 1) + minus_dm[index]) / period
        denominator = plus + minus
        dxs.append(0.0 if denominator <= 0 else 100.0 * abs(plus - minus) / denominator)
        if len(dxs) == period:
            adx = sum(dxs) / period
        elif len(dxs) > period:
            adx = (adx * (period - 1) + dxs[-1]) / period
        if adx is not None:
            out[index + 2] = adx
    return tuple(out)


def _rv20_mid_schedule(hours: list) -> tuple[bool | None, ...]:
    """Tercil medio RV20 causal, exacto y O(n log n), sin look-ahead."""
    window = 20
    out: list[bool | None] = [None] * (len(hours) + 1)
    closes = [row[3] for row in hours]
    if len(closes) < window + 21 or any(a <= 0 or b <= 0 for a, b in zip(closes, closes[1:])):
        return tuple(out)
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
    if len(returns) < window + 20:
        return tuple(out)
    vols = [statistics.stdev(returns[index - window:index]) for index in range(window, len(returns) + 1)]
    universe = sorted(set(vols))
    ranks = {value: index for index, value in enumerate(universe)}
    counts = _Fenwick(len(universe))
    for value in vols[:20]:
        counts.add(ranks[value])
    for index in range(20, len(vols)):
        size = index
        low = universe[counts.kth(int((size - 1) / 3))]
        high = universe[counts.kth(int((size - 1) * 2 / 3))]
        out[window + index + 1] = low <= vols[index] <= high
        counts.add(ranks[vols[index]])
    return tuple(out)


class AuditContext:
    """LRU de símbolos y derivados causales, compartible por un worker.

    ``max_symbols=None`` habilita un límite adaptativo: conserva las series
    mientras Windows mantenga la reserva de memoria indicada. Esto permite
    que un worker cubra el universo real del candidato cuando cabe, sin
    asumir de antemano que 16 (o cualquier otro número fijo) es seguro.
    """
    def __init__(self, adapter, funding_store=None, max_symbols: int | None = None,
                 feature_cache_path=None, min_available_bytes: int = 4 * 1024**3):
        if max_symbols is not None and max_symbols < 1:
            raise ValueError("max_symbols debe ser positivo")
        self.adapter = adapter
        self.funding_store = funding_store
        self.max_symbols = max_symbols
        self.min_available_bytes = int(min_available_bytes)
        self.memory_limited = False
        self.feature_store = FeatureStore(feature_cache_path or os.path.join(os.path.dirname(__file__), "..", "data", "audit_feature_cache.db"))
        self.source_key = feature_source_key(adapter)
        self._symbols: OrderedDict[str, SymbolContext] = OrderedDict()
        # Estos caches son compactos: guardan resultados por trade, no velas.
        # Persiste el trabajo entre variantes aun cuando el LRU de velas evicta
        # el símbolo para respetar memoria.
        self._baseline: dict[tuple, dict] = {}
        self._paths: dict[tuple, C.TradePath] = {}
        self._variants: dict[tuple, tuple] = {}
        self._integrity: dict[tuple, dict] = {}
        self._funding: dict[tuple, object] = {}
        self.stats = {"hits": 0, "misses": 0, "evictions": 0,
                      "trade_hits": 0, "trade_misses": 0}

    @staticmethod
    def available_memory_bytes() -> int | None:
        """Memoria física libre de Windows, sin dependencia opcional externa."""
        if os.name != "nt":
            return None
        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullAvailPhys)

    def _capacity_reached(self) -> bool:
        if self.max_symbols is not None:
            return len(self._symbols) >= self.max_symbols
        available = self.available_memory_bytes()
        if available is None:
            return False
        return available < self.min_available_bytes

    def warm_symbols(self, symbols) -> dict:
        """Precarga series de un candidato hasta el límite de memoria real.

        Si el universo no cabe, el contexto degrada a LRU; nunca fuerza una
        precarga que invada la reserva mínima del sistema.
        """
        requested = list(dict.fromkeys(symbols))
        for symbol in requested:
            if self._capacity_reached():
                self.memory_limited = True
                break
            self.symbol(symbol)
        return {
            "requested_symbols": len(requested),
            "resident_symbols": len(self._symbols),
            "memory_limited": self.memory_limited,
            "available_memory_bytes": self.available_memory_bytes(),
        }

    def symbol(self, symbol: str) -> SymbolContext:
        cached = self._symbols.pop(symbol, None)
        if cached is not None:
            self.stats["hits"] += 1
            self._symbols[symbol] = cached
            return cached
        self.stats["misses"] += 1
        rows = self.adapter.candles(symbol)
        features = self.feature_store.load(self.source_key, symbol)
        if features is None:
            hours = C.hourly_series(rows)
            features = {
                "hours": hours,
                "atr14": _atr14_schedule(hours),
                "range_pct": tuple([None] + [((row[1] - row[2]) / row[3] * 100.0 if row[3] > 0 else None) for row in hours]),
                "adx14": _adx14_schedule(hours),
                "rv20_mid": _rv20_mid_schedule(hours),
            }
            self.feature_store.save(self.source_key, symbol, features)
        hours = features["hours"]
        context = SymbolContext(rows=rows, opens=[row[0] for row in rows], hours=hours,
            hour_starts=[row[0] for row in hours], atr14=tuple(features["atr14"]),
            range_pct=tuple(features["range_pct"]), adx14=tuple(features["adx14"]),
            rv20_mid=tuple(features["rv20_mid"]))
        self._symbols[symbol] = context
        over_fixed_limit = self.max_symbols is not None and len(self._symbols) > self.max_symbols
        over_memory_reserve = self.max_symbols is None and self._capacity_reached()
        if (over_fixed_limit or over_memory_reserve) and len(self._symbols) > 1:
            self._symbols.popitem(last=False)
            self.stats["evictions"] += 1
            self.memory_limited = True
        return context

    def filter_value(self, symbol: str, open_ms: int, variant_id: str):
        item = self.symbol(symbol)
        end = item.closed_hour_count(open_ms)
        if variant_id == "cost_hourly_range_ge_2x_roundtrip":
            value = item.range_pct[end] if end < len(item.range_pct) else None
            return None if value is None else value >= 2.0 * self.adapter.cost_pct
        if variant_id == "entry_adx14_ge_25":
            value = item.adx14[end] if end < len(item.adx14) else None
            return None if value is None else value >= 25.0
        if variant_id == "entry_realized_vol_20_mid":
            return item.rv20_mid[end] if end < len(item.rv20_mid) else None
        raise ValueError(f"filtro no soportado: {variant_id}")

    @staticmethod
    def trade_key(trade: dict, split: str, cost_pct: float) -> tuple:
        return (trade["symbol"], int(trade["open_ms"]), float(trade["entry"]),
                int(trade["side"]), float(trade["sl"]), float(trade["tp"]), split, float(cost_pct))

    def baseline_audit(self, key: tuple, factory):
        cached = self._baseline.get(key)
        if cached is not None:
            self.stats["trade_hits"] += 1
            return dict(cached)
        self.stats["trade_misses"] += 1
        value = factory()
        self._baseline[key] = dict(value)
        return dict(value)

    def trade_path(self, key: tuple, factory) -> C.TradePath:
        cached = self._paths.get(key)
        if cached is None:
            cached = factory()
            self._paths[key] = cached
        return cached

    def variant_outcome(self, key: tuple, variant: str, factory) -> tuple:
        """Resultado perezoso: una variante, no el catálogo entero, por trade."""
        cache_key = (key, variant)
        cached = self._variants.get(cache_key)
        if cached is None:
            cached = factory()
            self._variants[cache_key] = cached
        return cached

    def static_integrity(self, key: tuple, factory) -> dict:
        cached = self._integrity.get(key)
        if cached is None:
            cached = dict(factory())
            self._integrity[key] = cached
        return dict(cached)

    def funding_accrual(self, key: tuple, factory):
        cached = self._funding.get(key)
        if cached is None:
            cached = factory()
            self._funding[key] = cached
        return cached


def feature_source_key(adapter) -> str:
    """Identidad de la fuente; cambia si cambia DB, intervalo o ventana."""
    source = adapter.candle_source
    path = os.path.abspath(source.db_path)
    try:
        stat = os.stat(path)
        version = (stat.st_size, stat.st_mtime_ns)
    except OSError:
        version = None
    payload = repr((source.key, path, version, source.table, source.interval, source.start_ms, source.end_ms)).encode()
    return hashlib.sha256(payload).hexdigest()


class FeatureStore:
    """Derivados causales compactos, persistentes entre candidatos/workers."""
    def __init__(self, path):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS audit_symbol_features (
                source_key TEXT NOT NULL, symbol TEXT NOT NULL, payload BLOB NOT NULL,
                created_at_ms INTEGER NOT NULL, PRIMARY KEY(source_key, symbol))""")
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load(self, source_key: str, symbol: str):
        conn = self._connect()
        try:
            row = conn.execute("SELECT payload FROM audit_symbol_features WHERE source_key=? AND symbol=?", (source_key, symbol)).fetchone()
        finally:
            conn.close()
        return pickle.loads(row[0]) if row else None

    def save(self, source_key: str, symbol: str, features: dict) -> None:
        conn = self._connect()
        try:
            conn.execute("INSERT OR REPLACE INTO audit_symbol_features(source_key,symbol,payload,created_at_ms) VALUES (?,?,?,?)",
                         (source_key, symbol, sqlite3.Binary(pickle.dumps(features, protocol=5)), int(__import__('time').time() * 1000)))
            conn.commit()
        finally:
            conn.close()
