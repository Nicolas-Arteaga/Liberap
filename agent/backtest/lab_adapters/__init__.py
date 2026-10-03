"""Contrato genérico de adaptadores del Laboratorio de Diagnóstico.

El motor de auditoría sólo conoce :class:`Adapter`: recibe entradas normalizadas,
velas y una política temporal de splits.  La estrategia nueva declara su
``EntryDefinition`` y aporta exclusivamente cómo materializa sus señales; los
chequeos M1b, simulación, bootstrap, severidad e informe siguen siendo comunes.
"""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterDefinition:
    """Metadatos inmutables consumidos por el motor genérico."""

    name: str
    display_name: str
    aliases: tuple[str, ...]
    population: str
    bar_ms: int
    cost_pct: float = 0.08
    require_coverage: bool = False


@dataclass(frozen=True)
class EntryDefinition:
    """Definición humana y temporal de la señal que el adaptador materializa."""

    source: str
    condition: str
    execution_time: str
    side_convention: str = "0=long, 1=short"


@dataclass(frozen=True)
class SQLiteCandleSource:
    """Fuente declarativa reutilizable de OHLC, siempre de sólo lectura."""

    key: str
    db_path: str
    table: str
    interval: str
    start_ms: int | None = None
    end_ms: int | None = None
    timeout: float | None = None

    def rows(self, adapter: "Adapter", symbol: str) -> list:
        def connect():
            kwargs = {"uri": True}
            if self.timeout is not None:
                kwargs["timeout"] = self.timeout
            return sqlite3.connect(f"file:{self.db_path}?mode=ro", **kwargs)

        clauses = ["symbol=?", "interval=?"]
        params: list[object] = [symbol, self.interval]
        if self.start_ms is not None:
            clauses.append("open_time>=?")
            params.append(self.start_ms)
        if self.end_ms is not None:
            clauses.append("open_time<?")
            params.append(self.end_ms)
        sql = (
            f"SELECT open_time, high, low, close FROM {self.table} WHERE "
            + " AND ".join(clauses)
            + " ORDER BY open_time"
        )
        return adapter._pid_conn(self.key, connect).execute(sql, params).fetchall()


class FixedTimeSplits:
    """Política genérica para cortes preregistrados por instante de entrada."""

    def __init__(self, train_validation_ms: int, validation_oos_ms: int):
        self.train_validation_ms = train_validation_ms
        self.validation_oos_ms = validation_oos_ms

    def split_of(self, open_ms: int) -> str:
        if open_ms < self.train_validation_ms:
            return "TRAIN"
        if open_ms < self.validation_oos_ms:
            return "VALIDATION"
        return "OOS"


class TemporalQuantileSplits:
    """Cortes 50/25/25 calculados sólo desde el instante de entrada."""

    def __init__(self):
        self._cuts: tuple[int, int] | None = None

    def fit(self, entries: list[dict]) -> None:
        if not entries:
            self._cuts = None
            return
        self._cuts = (
            entries[int(len(entries) * 0.50)]["open_ms"],
            entries[min(len(entries) - 1, int(len(entries) * 0.75))]["open_ms"],
        )

    def split_of(self, open_ms: int) -> str:
        if self._cuts is None:
            raise RuntimeError("TemporalQuantileSplits requiere fit(entries) antes de split_of().")
        if open_ms < self._cuts[0]:
            return "TRAIN"
        if open_ms < self._cuts[1]:
            return "VALIDATION"
        return "OOS"


class Adapter(ABC):
    """Interfaz estable entre una definición de entrada y el laboratorio común."""

    name = "base"
    aliases: tuple = ()
    population = "raw"           # "raw" | "real"
    bar_ms = 300_000
    cost_pct = 0.08              # 0,04 % por lado
    split_names = ("TRAIN", "VALIDATION", "OOS")
    expected_baseline = None     # {scenario_key: baseline_oos_mean}
    baseline_scenario_tol = 1e-9
    fidelity_result = {'detection':'37/38','exit_reason':'84%','return':'66%','selection':'no reproducible sin ledger'}
    fidelity_note = 'Fidelidad: detección 37/38, motivo 84%, retorno fino 66%; selección/timeouts de producción no reproducibles sin ledger.'
    definition: AdapterDefinition
    entry_definition: EntryDefinition

    def entries(self) -> list:
        """Materializa entradas normalizadas sin alterar el orden del proveedor."""
        entries = list(self.build_entries())
        required = ("open_ms", "symbol", "entry", "side", "sl", "tp")
        for index, entry in enumerate(entries):
            missing = [key for key in required if key not in entry]
            if missing:
                raise ValueError(f"{self.name}: entrada {index} sin campos requeridos: {missing}")
        return entries

    @abstractmethod
    def build_entries(self):
        """Única parte de señal: devuelve entradas ya decididas por la estrategia."""

    @abstractmethod
    def candles(self, symbol: str) -> list:
        """Devuelve OHLC ordenado para reproducir la trayectoria desde ``open_ms``."""

    @abstractmethod
    def split_of(self, open_ms: int) -> str:
        """Clasifica con el instante de entrada, nunca con la detección previa."""

    def describe(self) -> dict:
        return {"name": self.name, "population": self.population, "bar_ms": self.bar_ms, "cost_pct": self.cost_pct}

    def _pid_conn(self, key, factory):
        """Conexión sqlite por proceso (segura ante fork)."""
        pid = os.getpid()
        holder = getattr(self, "_conns", None)
        if holder is None:
            holder = self._conns = {}
        cur = holder.get(key)
        if cur is None or cur[0] != pid:
            holder[key] = (pid, factory())
        return holder[key][1]


def get_adapter(name: str) -> Adapter:
    from .ma3 import MA3Adapter
    from .band_touch import BandTouchAdapter
    from .level_sweep import LevelSweepAdapter
    registry = (MA3Adapter, BandTouchAdapter, LevelSweepAdapter)
    key = name.strip().lower().replace(" ", "_")
    for cls in registry:
        if key == cls.name or key in tuple(a.lower().replace(" ", "_") for a in cls.aliases):
            return cls()
    raise SystemExit(f"estrategia desconocida: {name!r}. Disponibles: " +
                     ", ".join(c.name for c in registry))
