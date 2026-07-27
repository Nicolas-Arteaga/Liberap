## 1. AdnCompression conectado al motor

- [x] 1.1 Agregar import de `AdnCompressionAnalyzer` (python-service/adn_compression/analyzer.py) en agent/backtest/engine.py, con sys.path ya preparado para python-service
- [x] 1.2 `make_adn_agent(fetcher)` (VergeAgent.__new__ + agent.fetcher = fetcher, igual que make_fvg_agent)
- [x] 1.3 `make_adn_analyzer(fetcher)` monkeypatcheando `_fetch_klines` de AdnCompressionAnalyzer a datos históricos
- [x] 1.4 `BacktestEngine.run_adn_compression(...)`: candidate_fn que llama `_analyze_symbol`, filtra `phase != "PULLBACK_TO_MA7"`, arma dict con `.model_dump()`/similar y pasa a `_build_adn_compression_candidate`
- [x] 1.5 Registrar "AdnCompression" -> `engine.run_adn_compression` en el diccionario `runners` de agent/backtest/api.py
- [x] 1.6 Agregar "AdnCompression" a SUPPORTED_TYPES en angular backtesting.component.ts
- [x] 1.7 Validar 1:1 contra al menos un trade real de un perfil AdnCompression existente -- EDUUSDT 24/7 22:15: SL calculado 0.0311048 vs real 0.0311056 (match casi exacto), entry 0.03137 vs 0.03135

## 2. Sincronización de datos on-demand

- [x] 2.1 agent/backtest/data_sync.py: `check_coverage(symbols, start_ms, end_ms) -> dict` (símbolo -> lista de días faltantes en klines_5m y klines_clean)
- [x] 2.2 `sync_coverage(symbols, start_ms, end_ms, progress_cb)`: descarga solo lo faltante (siempre via archivo diario, funciona para cualquier dia pasado, ThreadPoolExecutor 48 workers)
- [x] 2.3 Endpoints en api.py: GET /backtest/data/coverage, POST /backtest/data/sync (con job_id + polling, mismo patron que /backtest/run)
- [x] 2.4 Botón "Actualizar datos" en backtesting.component.html/ts con su propia barra de progreso
- [x] 2.5 Probado con BTCUSDT/ETHUSDT/COMPUSDT en rango con huecos reales (14 combinaciones simbolo/dia faltantes) -- check_coverage las detecto, sync_coverage las completo (14->0, salvo el dia de HOY que Binance aun no publico, esperado)

## 3. Persistencia de corridas

- [x] 3.1 agent/backtest/storage.py: `init_db(conn)` crea tabla `backtest_runs` (id, strategy_profile_id, strategy_name, start_date, end_date, run_at, result_json) en binance_vision_clean.db
- [x] 3.2 `save_run(result, profile, start_date, end_date) -> run_id` y `list_runs(strategy_profile_id=None) -> list` y `get_run(run_id) -> dict|None`
- [x] 3.3 En api.py: al completar un job (`_run_job`), llamar `save_run(...)` antes de marcar `status=completed`
- [x] 3.4 Endpoints: GET /backtest/runs (listado), GET /backtest/runs/{id} (detalle)
- [x] 3.5 Seccion "Corridas anteriores" en backtesting.component.html/ts: lista, click para ver detalle sin re-correr

## 4. Paralelizacion por simbolo

- [x] 4.1-4.3 `BacktestEngine.run_parallel(strategy_type, ...)` + `_parallel_worker` (funcion de modulo, picklable) en engine.py: reparte simbolos entre `min(cpu_count(),8)` procesos, cada uno con su propio BacktestEngine/conexion sqlite; combina `all_signals_raw` de todos antes de `_capital_sim` (una sola vez, sobre el total). Conectado en api.py (`_run_job` ahora llama `engine.run_parallel` en vez del runner secuencial directo).
- [x] 4.4 Medido en ventana de 1 mes (julio 2026, 425 simbolos): secuencial 899s vs paralelo 287s (3.1x mas rapido)
- [x] 4.5 Bug real encontrado y arreglado en el camino: primera corrida completa (8 meses) dio resultado DISTINTO al secuencial (466 vs 460 trades, PnL de signo opuesto) por desempate no-determinista entre procesos cuando 2+ señales comparten el mismo open_time -- arreglado ordenando `(open_time, symbol)` antes de asignar cupos de capital (reproduce el orden alfabetico que ya usaba la version secuencial). Reverificado en ventana de 1 mes: resultado IDENTICO (14.8 USD, 65 trades, 15.4% WR en ambas versiones).

## 5. Cierre

- [ ] 5.1 Actualizar PROGRESS_LOG.md con lo agregado en este change
- [ ] 5.2 Correr `openspec archive complete-backtest-module` una vez validado todo
- [ ] 5.3 Commit + push
