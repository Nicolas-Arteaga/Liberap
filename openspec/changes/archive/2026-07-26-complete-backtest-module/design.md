## Context

`agent/backtest/engine.py` ya define `_run_generic(profile, symbols, ...,
candidate_fn)` — un loop de caminata (avanza cada 5 min, igual que
`LOOP_INTERVAL_SECONDS=300` del agente real) que recibe un callback
`candidate_fn(symbol) -> candidato|None` con la detección específica de cada
`StrategyType`. `run_ma_geometry` y `run_fvg` ya son implementaciones finas
de ese contrato (~15-20 líneas cada una). El resto (TP/SL, zombie_timeout,
tope estructural con fallback multi-exchange, capital limitado por slots) es
compartido y ya validado.

`agent/backtest/api.py` expone esto vía FastAPI (puerto 8010, proceso propio
dentro de `agent/`, con acceso directo a `verge_agent.py`/`risk_manager.py`/
`config.py` — no puede vivir en `python-service` sin duplicar esos imports).
Guarda jobs en un dict en memoria (`_jobs`), se pierde al reiniciar.

La base de datos histórica (`agent/data/binance_vision_clean.db`, SQLite) ya
tiene tablas `klines_clean` (15m, Binance), `klines_5m` (base de caminata) y
`klines_multi_exchange` (fallback del tope de TP). Es el mismo archivo donde
se agrega la persistencia de corridas — evita tocar Postgres/.NET.

## Goals / Non-Goals

**Goals:**
- AdnCompression backtesteable con el mismo nivel de confianza que
  MaGeometry/FVG (reuso de código real, cero reimplementación).
- Cobertura de datos verificable y actualizable desde la UI, sin scripts
  manuales.
- Historial de corridas persistente y consultable.
- Corrida completa de 8 meses en minutos, no en ~100 min.

**Non-Goals:**
- `StrategyType=Generic` (Nexus-15/LSE completo) — explícitamente fuera de
  alcance, otro change.
- Autenticación/multi-usuario en el servidor de backtest (sigue siendo un
  proceso local de un solo operador, como hoy).
- Persistencia en Postgres/.NET — se decide SQLite local a propósito (ver
  Decisiones).

## Decisions

**1. AdnCompression reusa `AdnCompressionAnalyzer._analyze_symbol` directo,
no HTTP.** Igual que FVG con `FvgAnalyzer`: se importa la clase de
`python-service/adn_compression/analyzer.py` y se monkeypatchea
`_fetch_klines` para servir datos históricos. Alternativa descartada: levantar
python-service real y pegarle por HTTP — más fiel al camino de producción,
pero mucho más lento (miles de calls HTTP por backtest) y frágil (requiere
tener el servicio corriendo). El propio código de producción
(`_build_adn_compression_candidate`) ya trabaja con el `item` como dict
plano, igual que FVG, así que el mismo patrón de conversión
(`item.model_dump()` si es Pydantic) aplica.

**2. Persistencia en SQLite local (`binance_vision_clean.db`, tabla nueva
`backtest_runs`), NO en Postgres/.NET.** Motivo real, no solo técnico: cada
migración EF en este proyecto requiere que el usuario pare manualmente su
`Verge.HttpApi.Host.exe` corriendo desde Visual Studio — fricción recurrente
ya documentada en `PROGRESS_LOG.md` de esta sesión. El motor de backtest ya
vive fuera del ciclo de vida del backend .NET (proceso propio, puerto 8010);
mantener su propio almacenamiento evita ese acoplamiento. Trade-off aceptado:
el historial de corridas no aparece en el admin de .NET ni se puede
consultar por SQL desde Postgres — se acepta porque el consumidor real es
únicamente la pantalla de backtesting.

**3. Sincronización de datos ("Actualizar datos") vía chequeo de gaps +
descarga incremental, generalizando los scripts de hoy.** Nuevo módulo
`agent/backtest/data_sync.py` con `check_coverage(symbols, start, end) ->
dict` (qué falta) y `sync(symbols, start, end, progress_cb)` (descarga solo
lo que falta, mismo ThreadPoolExecutor de 48-64 workers ya probado hoy).
Reutiliza `data.binance.vision` (mensual para meses cerrados, diario para el
mes en curso) para `klines_clean`/`klines_5m`; `klines_multi_exchange` se
sincroniza con las mismas APIs REST de Bybit/OKX/Bitget ya usadas en
`agent/download_multi_exchange.py`.

**4. Paralelización por símbolo con `ProcessPoolExecutor`, no threads.** La
caminata por símbolo es CPU-bound (SMA/slope en Python puro, sin I/O una vez
cargados los datos en memoria) — threads no ayudan por el GIL. Se particiona
la lista de símbolos entre N procesos (N = núcleos disponibles), cada uno
con su propia conexión SQLite de solo lectura y su propia instancia de
`BacktestEngine`; los resultados parciales (`all_trades`) se combinan al
final antes de `_capital_sim` (el capital compartido de 3 slots SÍ necesita
verse en conjunto, no por proceso). Alternativa descartada: paralelizar
dentro de la caminata de un mismo símbolo — no tiene sentido, es
inherentemente secuencial en el tiempo.

## Risks / Trade-offs

- [Paralelizar con procesos aumenta uso de RAM (cada proceso carga su propia
  copia de klines en memoria)] → mitigado limitando a `min(cpu_count(), 8)`
  procesos y cargando solo los símbolos asignados a cada uno, no todo el
  dataset.
- [SQLite con múltiples escritores (API + data_sync + capital_sim) puede
  dar "database is locked"] → mismo fix ya aplicado hoy
  (`check_same_thread=False` + un solo writer a la vez, nunca dos scripts
  escribiendo la misma tabla en simultáneo).
- [AdnCompression puede tener su propio bug de fidelidad no descubierto
  todavía, como pasó con MaGeometry (tope de TP, resolución de 5min, zombie
  timeout)] → mitigado corriendo la misma validación 1:1 contra trades
  reales antes de darla por buena (mismo método que se usó para MA Slope
  Caso 3).

## Migration Plan

Todo aditivo, sin romper lo existente:
1. `data_sync.py` + endpoints de cobertura/sync (no depende de nada nuevo).
2. `run_adn_compression` + registro en `api.py` (aditivo, mismo patrón).
3. `storage.py` (tabla nueva en SQLite, `CREATE TABLE IF NOT EXISTS`) +
   endpoints de listado/detalle.
4. Paralelización de `_run_generic` (cambio interno, misma firma pública —
   los métodos `run_ma_geometry`/`run_fvg`/`run_adn_compression` no cambian
   su contrato).

Rollback: cada pieza es independiente; si la paralelización da problemas se
puede volver al loop secuencial sin afectar los otros 3 puntos.

## Open Questions

Ninguna bloqueante — se resuelven implementando (ver tasks.md).
