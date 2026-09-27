"""Adaptadores de la máquina de diagnóstico.

Un adaptador entrega, para UNA estrategia:
  - entries(): lista de entradas {open_ms, symbol, entry, side, sl, tp}  (side 1 = short, 0 = long)
  - candles(symbol): velas ordenadas [(open_time_ms, high, low, close)] con margen posterior de 720 h
  - bar_ms, cost_pct, split_names y split_of(open_ms)
  - population: "raw" (stream bruto de señales) o "real" (trades reales = selección de producción)
  - expected_baseline: {scenario_key: media OOS esperada} para el chequeo de regresión (o None)

Cómo enchufar una estrategia nueva: crear un módulo aquí con una clase que herede de `Adapter`,
implementar los 4 métodos y registrarla en `REGISTRY`. No hace falta tocar `lab_core.py` ni `lab_diagnose.py`.
"""
from __future__ import annotations

import os


class Adapter:
    name = "base"
    aliases: tuple = ()
    population = "raw"           # "raw" | "real"
    bar_ms = 300_000
    cost_pct = 0.08              # 0,04 % por lado
    split_names = ("TRAIN", "VALIDATION", "OOS")
    expected_baseline = None     # {scenario_key: baseline_oos_mean}
    baseline_scenario_tol = 1e-9

    def entries(self) -> list:
        raise NotImplementedError

    def candles(self, symbol: str) -> list:
        raise NotImplementedError

    def split_of(self, open_ms: int) -> str:
        raise NotImplementedError

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
    registry = (MA3Adapter, BandTouchAdapter)
    key = name.strip().lower().replace(" ", "_")
    for cls in registry:
        if key == cls.name or key in tuple(a.lower().replace(" ", "_") for a in cls.aliases):
            return cls()
    raise SystemExit(f"estrategia desconocida: {name!r}. Disponibles: " +
                     ", ".join(c.name for c in registry))
