# Plantilla para sumar una estrategia al Laboratorio

La máquina ya resuelve en común la simulación, los seis chequeos M1b, los
splits, bootstrap por día, severidad e informe. Una estrategia nueva no debe
copiar esos módulos: debe completar un adaptador dentro de
`agent/backtest/lab_adapters/`.

## Los cuatro datos que hay que definir

1. `AdapterDefinition`: nombre estable, aliases, población (`raw` para replay
   de señales o `real` para operaciones ejecutadas), timeframe y costo.
2. `EntryDefinition`: fuente, condición que dispara la entrada y significado
   exacto de `open_ms`. Para replay, `open_ms` es el **fin de la vela cuyo
   cierre forma el precio de entrada**; para datos reales es el instante real
   de apertura.
3. `build_entries()`: devuelve sólo
   `{open_ms, symbol, entry, side, sl, tp}`. `side=0` es LONG y `side=1` es
   SHORT. No simula salidas ni calcula métricas.
4. Velas y splits: se puede reutilizar `SQLiteCandleSource` y
   `FixedTimeSplits` o `TemporalQuantileSplits`. El split siempre recibe
   `open_ms`, no la hora de detección.

## Esqueleto mínimo

```python
from . import Adapter, AdapterDefinition, EntryDefinition, SQLiteCandleSource, TemporalQuantileSplits

class NuevaAdapter(Adapter):
    name = "nueva"
    aliases = ("Nueva Estrategia",)
    population = "raw"
    bar_ms = 900_000
    definition = AdapterDefinition(name, "Nueva Estrategia", aliases, population, bar_ms)
    entry_definition = EntryDefinition("fuente congelada", "condición", "cierre de vela")
    candle_source = SQLiteCandleSource("nueva", "/app/data/binance_vision_clean.db", "klines_clean", "15m")

    def __init__(self):
        self.split_policy = TemporalQuantileSplits()

    def build_entries(self):
        entries = [...]  # sólo la definición de entrada
        entries.sort(key=lambda row: row["open_ms"])
        self.split_policy.fit(entries)
        return entries

    def candles(self, symbol):
        return self.candle_source.rows(self, symbol)

    def split_of(self, open_ms):
        return self.split_policy.split_of(open_ms)
```

Registrá la clase en `get_adapter()` de `lab_adapters/__init__.py`. El
generador de auditoría ya es genérico: no se edita `lab_core.py` ni
`lab_integrity.py`.

## Validación obligatoria

1. Agregá un test de contrato que compare las entradas contra su fuente
   congelada o contra el simulador previo, con cero diferencias.
2. Corré `python -m py_compile` sobre el módulo y
   `python -m unittest test_lab_adapter_contract.py -v` dentro del contenedor.
3. Generá el informe con
   `LAB_AUDIT_STRATEGY=nueva LAB_AUDIT_OUT=/app/backtest/lab_artifacts/mX-nueva \
   python /app/backtest/lab_m1_ma3_audit.py`.
4. El informe sólo es publicable si los seis chequeos de integridad dan PASS.
   Si falla uno, corregí la semántica de entrada o declaralo inválido; nunca
   ajustes los chequeos para hacerlo pasar.
