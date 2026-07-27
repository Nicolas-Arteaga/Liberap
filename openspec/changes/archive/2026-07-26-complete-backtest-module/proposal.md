## Why

El motor de backtest genérico (`agent/backtest/engine.py` + `agent/backtest/api.py`)
ya está validado con evidencia real: ~80% de coincidencia contra trades reales
de producción en dos ventanas independientes de una semana cada una (MA Slope
Caso 3). Hoy solo cubre 2 de 4 `StrategyType` existentes (MaGeometry, FVG —
11 de 19 perfiles reales), la actualización de datos históricos es manual
(scripts sueltos que corrió el operador a mano), los resultados de cada
corrida se pierden al reiniciar el servidor (solo viven en memoria), y una
corrida completa de 8 meses tarda ~100 minutos, lo que hace lenta la
iteración al probar variantes de una estrategia. El objetivo de este cambio
es cerrar esas cuatro brechas para que el backtesting sea una herramienta de
uso diario, no un experimento puntual de una sesión.

## What Changes

- Conectar `StrategyType=AdnCompression` al motor genérico, reusando
  `AdnCompressionAnalyzer` real (`python-service/adn_compression/analyzer.py`)
  y `verge_agent.py::_build_adn_compression_candidate` — mismo patrón ya
  usado para FVG (sin reimplementar lógica de detección).
- Endpoint + botón "Actualizar datos" en la UI que detecta qué símbolos/días
  faltan en `klines_5m`/`klines_clean` y descarga SOLO eso (generaliza la
  lógica ya escrita en `agent/download_5m_julio.py` /
  `agent/download_binance_vision_daily_all_v2.py`), en vez de scripts
  manuales por sesión.
- Persistencia de resultados de backtest en una tabla SQLite local dentro de
  `agent/data/binance_vision_clean.db` (no requiere migración EF del backend
  .NET, evita el bloqueo recurrente de tener que parar el proceso de VS del
  usuario) — cada corrida se guarda con su fecha/parámetros, nunca se
  sobreescribe, y se puede listar/comparar desde la UI.
- Optimizar la velocidad de una corrida completa de 8 meses (hoy ~100 min)
  paralelizando el procesamiento por símbolo, para que iterar sobre
  variantes de una estrategia sea práctico.

Fuera de alcance de este change: `StrategyType=Generic` (el motor de scoring
Nexus-15/LSE completo) — es un trabajo bastante más grande, se deja para un
change aparte.

## Capabilities

### New Capabilities
- `backtest-adn-compression`: detección y backtest de estrategias
  `StrategyType=AdnCompression` reusando el analizador real.
- `backtest-data-sync`: sincronización on-demand de cobertura de datos
  históricos (detecta huecos, descarga solo lo faltante).
- `backtest-run-history`: persistencia y listado de corridas de backtest
  pasadas (nunca se pisan entre sí).

### Modified Capabilities
- (ninguna — no hay specs previas registradas en `openspec/specs/` para el
  motor de backtest; este change las crea de cero además de extenderlo)

## Impact

- `agent/backtest/engine.py`: nuevo método `run_adn_compression` (mismo
  patrón `_run_generic` que `run_ma_geometry`/`run_fvg`), y paralelización
  por símbolo en `_run_generic`.
- `agent/backtest/api.py`: nuevo runner registrado para `AdnCompression`;
  nuevos endpoints `/backtest/data/coverage`, `/backtest/data/sync`,
  `/backtest/runs` (listado), `/backtest/runs/{id}` (detalle).
- `agent/backtest/` nuevo módulo `storage.py` (tabla SQLite de corridas) y
  `data_sync.py` (chequeo de cobertura + descarga incremental).
- `angular/src/app/backtesting/`: botón "Actualizar datos" con su propia
  barra de progreso, y una sección "Corridas anteriores" (listado desde
  `/backtest/runs`).
- Sin cambios en `src/` (.NET) ni migraciones EF — decisión explícita para
  no bloquear con el backend del usuario.
