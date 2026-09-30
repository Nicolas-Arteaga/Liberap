# Evaluación de generalización — Laboratorio de Diagnóstico

Fecha: 2026-09-30. Alcance: diagnóstico de arquitectura solamente. No se modificaron `lab_core.py`, `lab_integrity.py`, los adaptadores existentes, scripts cerrados de Fase 2 ni producción.

## Veredicto

El núcleo de ejecución ya es **parcialmente genérico**: una tercera estrategia puede obtener `result.json` con `lab_diagnose.py --strategy <nombre>` sin cambiar el simulador ni la CLI. No obstante, agregarla hoy no es todavía "llenar una plantilla": requiere escribir un adaptador Python, registrarlo manualmente y, si se exige el informe narrativo M1/M2, desacoplar un auditor que hoy sólo conoce MA3 y Band Touch.

## Evidencia inspeccionada

Comando ejecutado el 2026-09-30 desde la raíz del repositorio:

```powershell
rg -n "class .*Adapter|MA3Adapter|BandTouch|lab_diagnose|lab_report" agent/backtest -g "*.py"
rg -n "get_adapter\(|--strategy|Adapter\(|MA3Adapter|BandTouchAdapter|population|expected_baseline|require_coverage" agent/backtest -g "*.py"
```

El contrato está documentado en `agent/backtest/lab_adapters/__init__.py:3-11`; la CLI toma el nombre por `--strategy` en `agent/backtest/lab_diagnose.py:167-175` y opera con el adaptador sin ramas por estrategia en `agent/backtest/lab_diagnose.py:27-47, 185-223`.

## Contrato reutilizable actual

La clase base `Adapter` exige sólo tres métodos:

1. `entries()` — devuelve por trade/señal `open_ms`, `symbol`, `entry`, `side`, `sl` y `tp` (`lab_adapters/__init__.py:28-35`).
2. `candles(symbol)` — devuelve velas ordenadas como `(open_time_ms, high, low, close)` (`lab_adapters/__init__.py:31-32`).
3. `split_of(open_ms)` — decide TRAIN/VALIDATION/OOS desde la hora real de entrada (`lab_adapters/__init__.py:34-35`).

Además, debe declarar `name`, `aliases`, `population`, `bar_ms`, `cost_pct`, `split_names` y, opcionalmente, `expected_baseline`/`baseline_scenario_tol` (`lab_adapters/__init__.py:18-26`). Para una población real puede activar `require_coverage`, que hace que la CLI descarte y cuente entradas sin velas suficientes (`lab_diagnose.py:45-47`).

El núcleo reutiliza estos datos para ATR, path metrics, cuatro escenarios, matriz, trayectorias y regresión (`lab_diagnose.py:27-47, 185-223`). Por lo tanto no hay motivo técnico para tocar `lab_core.py` ni `lab_diagnose.py` al sumar una estrategia que respete el contrato.

## Patrones confirmados en los dos adaptadores

| Aspecto | MA3 | Band Touch | Común/reutilizable |
|---|---|---|---|
| Población | Stream bruto congelado, `raw` | Trades cerrados exportados, `real` | Mismo diccionario de entrada |
| Fuente | Pickle y SQLite 5m (`ma3.py:50-66`) | CSV y SQLite 15m (`band_touch.py:39-57`) | `entries()` + `candles()` aíslan la fuente |
| Instante de entrada | Cierre horario `b + HOUR` (`ma3.py:55-59`) | `open_ms` real del CSV (`band_touch.py:41-47`) | Integridad distingue `raw` de `real` |
| Splits | Cortes UTC fijos (`ma3.py:68-74`) | Percentiles temporales 50/25/25 (`band_touch.py:47-66`) | `split_of()` encapsula la decisión |
| Regresión | Baseline v2 obligatorio (`ma3.py:42-48`) | No hay baseline histórico | `expected_baseline=None` desactiva sólo ese gate |

La diferencia de población es importante: `lab_integrity.py:10-17` comprueba para `real` que el precio caiga en el rango de la vela contenedora; para replay/raw exige el cierre de la vela que termina en `open_ms`. Una plantilla debe obligar a elegir una de estas dos semánticas antes de correr.

## Archivos que habría que tocar hoy

### Mínimo para una matriz diagnóstica reproducible

1. **Uno nuevo:** `agent/backtest/lab_adapters/<estrategia>.py`, con la subclase y la lectura de sus datos.
2. **Uno existente:** `agent/backtest/lab_adapters/__init__.py`, para importar la clase y añadirla a `registry` (`:52-60`). El registro es hoy manual y estático.
3. **Uno nuevo o fuente versionada ya existente:** un CSV/pickle de entradas bajo `agent/backtest/lab_inputs/` o una referencia explícita y de sólo lectura a una base local. Debe dejar documentada la consulta/export que lo originó, como hace Band Touch (`band_touch.py:3-9`).
4. **Uno nuevo:** un test de contrato/regresión. Si existe un simulador histórico comparable, debe reproducirlo como `test_lab_band_selftest.py:15-44`; si no existe, el test debe fijar al menos fixtures de entrada, vela, split e integridad.

Resultado: **4 piezas, de las cuales 2 son archivos Python nuevos y 1 edición de registro**; el cuarto elemento puede ser sólo datos de entrada si ya hay fuente estable. El CLI no requiere modificación.

### Para obtener el informe narrativo M1/M2 existente

Hay un acoplamiento adicional: `agent/backtest/lab_m1_ma3_audit.py:8-12,61,84` importa ambas clases y selecciona con un ternario `MA3Adapter() if ... else BandTouchAdapter()`. Para una tercera estrategia hoy habría que modificar ese archivo en al menos esos tres puntos (imports, factory y etiqueta), además de proveer entradas y velas. El archivo llamado `lab_report.py` no es el informe diagnóstico M1/M2: lee `lab_tested_all.jsonl` del laboratorio evolutivo (`lab_report.py:9-13`), por lo que no debe reutilizarse para esta tarea.

En consecuencia: para el producto completo "informe legible + result.json", el costo actual es **5 archivos/piezas** como mínimo: nuevo adaptador, registro, datos, test y auditor narrativo. Para sólo `lab_diagnose.py`, es **4 piezas**.

## Dónde ya es genérico y dónde no

**Genérico y listo para reutilizar**

- Matriz de variantes y cuatro escenarios: centralizados en `lab_core` y llamados desde la CLI sin condicionales MA3/Band (`lab_diagnose.py:35-47`).
- Splits, timeframe, costos y población: salen del adaptador (`lab_adapters/__init__.py:18-38`).
- Chequeos de integridad: usan `population` y el contrato de velas; no importan una estrategia concreta (`lab_integrity.py:7-37`).
- Salida estándar `result.json` y `progress.json`: única CLI (`lab_diagnose.py:175-223`).

**Todavía específico/manual**

- Registro de adaptadores manual por imports/tupla en `lab_adapters/__init__.py:52-55`.
- Auditoría legible M1/M2 con nombres y factory hardcodeados en `lab_m1_ma3_audit.py:8-12,61,84`.
- Selftest de la CLI sólo compara MA3 contra scripts de Fase 2 (`lab_diagnose.py:126-160`). Band Touch necesita su prueba separada contra Fase 2c (`test_lab_band_selftest.py:15-44`).
- No hay esquema/validador único que falle temprano si una entrada omite claves, usa `side` fuera de 0/1, carece de horizonte posterior o mezcla semántica `raw`/`real`.

## Propuesta para volverlo una plantilla (no implementada)

1. Crear una **plantilla de adaptador** con campos obligatorios declarativos: identidad, tipo de población, fuente de entradas, timeframe, costo, política de splits, cobertura y definición exacta de `open_ms`. La plantilla devolvería el mismo contrato actual; no cambiaría cálculos.
2. Cambiar el registro estático por un único manifiesto explícito (`nombre -> clase`) o descubrimiento controlado de módulos. El manifiesto debe ser la única edición fuera de la carpeta de la estrategia.
3. Extraer de `lab_m1_ma3_audit.py` un `run_audit(adapter, out_dir)` y un mapa de etiquetas opcional. Así el informe narrativo recibiría `get_adapter(args.strategy)` igual que la CLI, sin ternarios por estrategia.
4. Añadir un **test de contrato parametrizado** que ejecute sobre cualquier adaptador: claves/tipos de entradas, monotonicidad de velas, semántica de entrada según `population`, splits exhaustivos y cobertura. Cada estrategia conservaría, además, un test de referencia propio cuando exista histórico.
5. Definir un generador de fixtures/export reproducible: CSV/pickle con hash, consulta fuente y ventana temporal. Esto evita que un cambio silencioso en una DB local parezca un cambio de estrategia.

Con esos cambios, incorporar una estrategia sería: (a) copiar plantilla, (b) declarar las fuentes/cortes, (c) añadir fixture y baseline o justificar que no existe, (d) registrar una línea en el manifiesto y (e) ejecutar el test parametrizado. La implementación propuesta es futura: no se hizo ningún refactor ni se tocó código cerrado en esta evaluación.

## Riesgos que la plantilla debe impedir

- Repetir el desfase de entrada: `open_ms` debe definirse como instante de ejecución, no como inicio de señal; el control `raw`/`real` ya detecta parte de esto (`lab_integrity.py:10-23`).
- Etiquetar una población raw como desempeño de producción: cada adaptador debe declarar `population` y el informe debe conservarlo.
- Activar un baseline no reproducible: si se declara `expected_baseline`, la CLI invalida la corrida al no coincidir (`lab_diagnose.py:214-226`).
- Cambiar cortes después de ver resultados: el adaptador/manifest debe versionar cortes y su fecha de congelamiento.

## Conclusión operativa

Hoy sumar una estrategia al **motor** es factible sin tocar el laboratorio cerrado: un adaptador, su registro, datos y test. Sumarla al **producto completo legible** requiere además desacoplar el auditor M1/M2, que es el único acoplamiento funcional relevante identificado. La mejora de "plantilla" es viable y acotada, pero debe hacerse en una fase futura con tests de contrato; esta evaluación no la implementa.
