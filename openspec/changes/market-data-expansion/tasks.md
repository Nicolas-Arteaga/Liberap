## 1. Order book imbalance (primero — gratis, sin dependencias externas)

- [x] 1.1 Nuevo módulo `agent/orderbook_ws.py` (o extensión de `market_ws_server.py`): suscripción WebSocket a profundidad de order book (`@depth20`) de Binance Futures para los símbolos del watchlist activo
- [x] 1.2 Tabla nueva en SQLite (mismo archivo/patrón que `kline_cache.py`) para persistir snapshots de order book recientes por símbolo
- [x] 1.3 Función de cómputo de Order Flow Imbalance (OFI) normalizado (-1.0 a +1.0) a partir de los niveles capturados
- [x] 1.4 Manejo explícito de "datos insuficientes" → devolver `None` auditable, nunca un score inventado (spec: datos insuficientes para calcular OFI)
- [x] 1.5 Exponer OFI histórico reconstruible (sin lookahead) para que `agent/backtest_engine.py` pueda usarlo — seguir el mismo patrón de precálculo O(n) ya usado para las MAs (`_precompute_ma_series`)
- [x] 1.6 Suscripción inicial acotada al subconjunto de símbolos de mayor volumen (`config.WATCHLIST_TIER1`, 30 símbolos — no hay `VolatileSymbolsService` en Python, es un service de Angular; TIER1 es su equivalente real ya usado por el resto de `market_ws_server.py`), no a los 400+ completos
- [ ] 1.7 Backtest A/B: MA Slope Caso 3 con y sin filtro de OFI, mismo período histórico, comparar profit factor — **bloqueado hasta acumular historia real de OFI** (la captura recién arranca con este deploy, no hay snapshots previos a reconstruir; no confundir con backtest de klines, que sí tiene ~2.5 meses ya cacheados)

## 2. Funding rate como señal

- [x] 2.1 Lectura de funding rate actual + histórico (mín. 30 períodos) por símbolo, cacheado igual que klines (`agent/funding_rates.py` + tabla `funding_rates` en `kline_cache.py`) — REST de baja frecuencia (cada 2h), no WS: se probó el WS de markPrice para reusar la infra de order book, pero se verificó en vivo que este entorno solo recibe mensajes del canal `@depth` (markPrice/kline/aggTrade/ticker conectan pero no entregan datos — ver nota en `funding_rates.py`)
- [x] 2.2 Backfill on-demand para símbolos sin historial de funding cacheado — cada ciclo re-backfillea los últimos 30 períodos por símbolo (idempotente vía upsert)
- [x] 2.3 Nuevo parámetro opcional en `patternParamsJson` (`fundingFilter.enabled` + `maxAbsFundingPct`) — perfiles que no lo configuren quedan 100% sin tocar (verificado con test aislado antes de tocar el agente en vivo)
- [x] 2.4 Veto auditable en `setup_validator.py` (`funding_extreme_long`/`funding_extreme_short`) — fail-open si el símbolo aún no tiene funding cacheado, nunca bloquea por falta de un dato opcional
- [x] 2.5 Feature de predicción de próximo funding usando el OFI ya calculado en la sección 1 — `funding_rates.funding_pressure_hint()`, heurística de alineación de signos (OFI vs. funding vigente), explícitamente NO un valor numérico predicho ni un modelo entrenado (mismo criterio anti-"parece real y no lo es" que motivó todo este epic)
- [ ] 2.6 Backtest A/B: mismo criterio que 1.7, ahora con el filtro de funding — **bloqueado igual que 1.7**, recién arranca la acumulación de historia real de funding en `agent/data/klines.db` (el backfill inicial trae ~30 períodos ya, pero el motor de backtesting todavía no tiene wireado el uso de `get_funding_series_aligned` dentro de `run_backtest()` — falta esa integración mecánica, no la data)

## 3. Dinámica de liquidaciones

**Nota (2026-07-17): re-diagnosticado y resuelto con una fuente alternativa.**
Binance sigue sin funcionar (verificado dos sesiones distintas, con y sin
baneos recientes — `!forceOrder@arr` conecta pero no entrega mensajes,
mismo patrón que markPrice/kline/ticker/aggTrade, mientras `@depth` sí
funciona perfecto en la misma conexión — no es un ban, Binance no vuelve a
probarse). El REST público (`/fapi/v1/allForceOrders`) sigue dado de baja
oficialmente. Se usa **Bybit** en su lugar (`allLiquidation.<symbol>`, WS
ya usado en este proyecto para klines, verificado en vivo con eventos
reales) — mismo tipo de dato, gratis, sin cuenta.

- [x] 3.1 Suscripción a `allLiquidation.<symbol>` de Bybit (no Binance `forceOrder`, ver nota arriba) — `agent/liquidation_tracker.py`, TIER1 (30 símbolos), auto-resuscripción cada 30 min igual que `orderbook_ws.py`. **Bug real encontrado y arreglado en el primer deploy**: la conexión se caía cada ~60s ("Connection to remote host was lost") — Bybit corta conexiones sin tráfico reciente, y a diferencia de klines (mensajes constantes) las liquidaciones pueden tener silencios largos por símbolo. Agregado ping de aplicación (`{"op":"ping"}`) cada 20s en un thread propio. Verificado en producción tras el fix: 0 desconexiones y 42 eventos reales capturados en 5 min (AKEUSDT, etc.)
- [x] 3.2 Tabla `liquidations` en `kline_cache.py` (symbol, timestamp, side, qty, price) — ventana reciente configurable vía `get_liquidation_cascade(recent_minutes=...)`
- [x] 3.3 `get_liquidation_cascade()`: compara el volumen reciente por lado contra el promedio por-ventana de las baseline_hours previas DEL MISMO símbolo (no un umbral fijo global) — devuelve `cascade_side`+`magnitude` si supera `threshold_multiplier` (default 3x) y un piso mínimo en USD. Verificado con datos sintéticos (cascada real detectada, evento chico correctamente ignorado, sin cobertura → None)
- [x] 3.4 Veto opt-in `liquidation_cascade_same_direction` en `setup_validator.py` (`liquidationFilter.enabled` en `patternParamsJson`) — Sell cascade (longs liquidados) vetea SHORT nuevo, Buy cascade (shorts liquidados) vetea LONG nuevo. Verificado con 4 casos aislados antes de tocar el agente en vivo (sin filter no afecta nada; con filter y sin cobertura, fail-open; cascada real vetea el lado correcto; el lado contrario no se toca)
- [x] 3.5 `get_liquidation_events_before()` + el parámetro `at_timestamp_ms` de `get_liquidation_cascade()` — reconstruye el estado histórico sin usar datos posteriores al punto evaluado, mismo principio que `get_ofi_before`/`get_funding_before`
- [ ] 3.6 Backtest A/B — bloqueado igual que 1.7/2.6: la captura recién arrancó hoy (2026-07-17), no hay historia previa que backtestear todavía

## 4. On-chain real (reemplazo del widget de ballenas)

- [x] 4.1 Decidido: **sin proveedor pago** (pedido explícito del usuario, "así como logramos toda la app, gratis"). Se descartó CryptoQuant/similares. Etherscan V1 (keyless) fue dado de baja (confirmado en vivo: "deprecated V1 endpoint"); V2 exige API key/cuenta gratuita que el usuario tiene que generar él mismo (no es algo automatizable de este lado). Fuente activa hoy: WS público de blockchain.info (BTC), sin cuenta ni key — verificado en vivo.
- [x] 4.2 `agent/whale_tracker.py` + tabla `whale_events` en `kline_cache.py` — captura transferencias BTC on-chain >= 10 BTC en tiempo real. Cobertura ERC-20 activada (2026-07-17, usuario generó su propia API key gratuita de Etherscan): se monitorea UNA wallet caliente de Binance verificada en vivo (balance real ~740k ETH), sin mapeo símbolo→contrato — cualquier token que se mueva por ahí y matchee el watchlist se registra. Primer ciclo real: 18 eventos (FF, OGN, SXT, PENDLE, GMT, etc.), verificado end-to-end vía `/whale/<symbol>`.
- [x] 4.3 `get_whale_activity()` distingue explícitamente "sin cobertura" (None) de "cobertura real, cero actividad ballena" ({"count":0,...}) — nunca un score inventado. Endpoint `/whale/<symbol>` en el HTTP del agente (puerto 8002) expone `{"available": false}` para símbolos sin cobertura.
- [x] 4.4 (parcial) Sacado el bug real de `dashboard.component.ts`: el default de `whaleScore = 65` por keyword-matching ("ballena"/"whale" en el texto de la alerta) — **eliminado**, era exactamente el antipatrón que este epic busca cerrar. Falta la segunda mitad: cablear `/whale/<symbol>` end-to-end hasta el widget (agente Python → backend .NET → SignalR → Angular) — es cambio de 3 capas, quedó fuera del alcance de esta sesión.
- [ ] 4.5 Badge visible "real vs no disponible" en el dashboard — bloqueado por 4.4 (necesita el dato real llegando al frontend primero, ver arriba)

## 5. Entrenamiento del modelo XGBoost de Nexus-15/Nexus-5

- [x] 5.1 Construir dataset de entrenamiento — `python-service/nexus15/build_training_dataset.py`, reusa `Nexus15FeatureEngine` (misma lógica que corre en vivo, evita mismatch train/serve). Label: close en +5 velas > close actual (misma definición que ya documentaba `train_nexus15.py`). 206.879 ejemplos, 723 símbolos, sin lookahead (cada ejemplo usa solo velas hasta el índice evaluado), ordenado cronológicamente GLOBAL (no por símbolo) antes de guardar para que el split posicional de `train_nexus15.py` sea un split temporal real
- [x] 5.2 Símbolos con < 206 velas de 15m excluidos automáticamente (filtro `get_symbols_with_history`), sin bloquear el resto — 723/varios cientos de símbolos con historia suficiente procesados
- [x] 5.3 Split temporal 70/15/15 (ya lo hacía `train_nexus15.py`, que existía pero nunca se había corrido por falta del dataset)
- [x] 5.4 Entrenado — `xgb_nexus15_v1.json` + `nexus15_meta.json` generados (2026-07-17)
- [x] 5.5 **Resultado: señal débil, NO se despliega.** val-AUC ~0.54 (apenas por encima de 0.50 = azar), y con el threshold de mejor F1 el modelo queda casi degenerado (recall clase "bajista" = 0.01 — básicamente predice "alcista" siempre). Dataset balanceado (53/47), así que no es un artefacto de clases desbalanceadas — es una señal real y honesta de que 20 features derivadas 100% de OHLCV/price-action en 15m no alcanzan para predecir el retorno a 5 velas, lo cual **refuerza** el hallazgo original de esta misma sesión (sección "Why this exists" de la memoria verge_2026_2040: el price-action puro ya está mayormente arbitrado). Documentado acá en vez de forzar un despliegue que repetiría el antipatrón g6=0.5-pero-parece-real.
- [ ] 5.6 Desplegar el `.json` del modelo — **NO se hace** (no pasó 5.5). El archivo entrenado queda en `python-service/nexus15/models/nexus15/` (fuera del path que lee `Nexus15ModelLoader`), sin tocar el comportamiento actual (`g6=0.5` placeholder sigue activo en producción)
- [ ] 5.7 N/A — no se despliega, `Nexus15ModelLoader` sigue en modo fallback tal como estaba
- [ ] 5.8 Backtest comparativo — no tiene sentido correrlo dado 5.5 (ya se sabe por AUC que no va a mejorar el profit factor); queda como candidato real si en el futuro se reentrena incluyendo OFI/funding (secciones 1-2 de este mismo epic) como features adicionales, no solo OHLCV — ver Nexus5ModelLoader también pendiente si se decide continuar esa línea

## 6. Cierre del change

- [x] 6.1 Documentado en `.claude/PROGRESS_LOG.md` (entradas 2026-07-17) qué señales quedaron activas (OFI, funding, liquidaciones, ballenas) y cuál se descartó por no mostrar mejora (Nexus-15)
- [ ] 6.2 `openspec archive market-data-expansion` — **todavía no**, quedan pendientes reales (ver TODO abajo), no cerrar hasta que estén resueltos o descartados explícitamente

## 7. Mejoras a Arrow Reversal (fuera del alcance original — hallazgo de sesión 2026-07-17)

No estaba en el plan original de este epic, pero surgió de un análisis en vivo con el usuario sobre por qué Arrow Reversal (Arrow Peak) tarda más en tocar TP que MA Slope Caso 3, a partir de un caso real (XANUSDT) con un pump "flojo" (4 días verdes, no un +20% raspando el mínimo). Verificado con datos reales (348 picos históricos, 681 símbolos, cero llamadas a Binance): el precio NUNCA recupera el nivel del pico en el primer día después de la primera vela roja (0/348), y solo el 25.6% lo recupera dentro de 10 días — confirma que el mecanismo de fondo es real, no solo el backtest de trading (185 trades, WR 62%, PF 1.39, robusto en los 3 regímenes de BTC — no depende de que BTC esté bajista, contra la sospecha inicial).

- [x] 7.1 TP graduado según magnitud del pump (`prev_rise_pct`) — analizado con los 185 trades reales (`agent/arrow_peak_backtest.py --export-csv`): la relación NO es lineal, forma de "U" (20-25% PF 1.52, 25-35% PF 1.12, 35-50% PF ~1.00, 50%+ PF 2.02, con la franja 25-50% además tardando más en cerrar). **Implementado como clon** `arrow_peak_v2` (`_build_arrow_peak_v2_candidate` en `verge_agent.py`, gateado por `ARROW_PEAK_V2_ENABLED=false` default) — TP al 50% del retroceso (peak→arrow_start) en la franja 25-50%, idéntico al original fuera de esa franja. Corre en PARALELO al original sin reemplazarlo (pedido explícito del usuario): agregada una excepción puntual al anti-churn diario (`_should_skip_arrow_peak_pair` + `state_manager.get_symbol_sources_traded_today`) para que original y clon puedan abrir posiciones simultáneas en el mismo símbolo el mismo día — comparación real, mismo evento, no repartido al azar. Verificado con 8 casos aislados (exención mutua, no se rompe el bloqueo contra terceras estrategias) antes de tocar el agente en vivo. Deploy hecho con el flag en `false` — cero cambio de comportamiento hasta activarlo.
- [x] 7.2 Investigado: SÍ hay protección — `has_traded_symbol_today` (anti-churn genérico, cualquier estrategia) bloquea una segunda entrada en el mismo símbolo el mismo día, lo que en la práctica evita que Arrow Peak reentre en un rebote posterior dentro del mismo día. Limitación real que queda: no elige el "mejor" rebote a propósito, abre en el primero que dispare — y si el patrón sigue vivo cruzando la medianoche, al día siguiente se resetea el bloqueo.
- [x] 7.3 Hipótesis de confluencia multi-timeframe de medias móviles verificada con datos reales (`agent/arrow_ma_confluence_check.py`, 153/185 trades evaluables): entrar con MA7/MA25 "comprimidas" en 5m (respecto a su propio promedio de 4h) sí correlaciona con mejor resultado (PF 1.71 vs 1.14), pero la correlación lineal continua es débil (~-0.02 a -0.04) — sugestivo, no una señal limpia y confirmada. No mejora la velocidad de cierre (al revés, tarda un poco más). No se implementó en producción — necesitaría una métrica más fiel a la narrativa original del usuario o más muestra antes de confiar en ella.

### TODO general del epic (para no perder de vista al retomar)

- Nexus-15 "pro": esperar a que madure la historia de OFI/funding/liquidaciones (arrancó 2026-07-17) y reentrenar incluyéndolas como features — sin esto, ya se probó 2 veces que no mejora (ver sección 5)
- Cablear `/whale/<symbol>` hasta el widget del dashboard (agente → backend .NET → SignalR → Angular) — sección 4.4/4.5
- Sección 3 (liquidaciones): reintentar el diagnóstico del WS de Binance de tanto en tanto — no confirmado como bloqueo permanente, aunque Bybit ya cubre la necesidad real
- Sección 7 (Arrow Reversal): las 3 tareas de arriba, recién identificadas, sin empezar
