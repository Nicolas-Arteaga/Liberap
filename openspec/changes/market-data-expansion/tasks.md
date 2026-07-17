## 1. Order book imbalance (primero — gratis, sin dependencias externas)

- [ ] 1.1 Nuevo módulo `agent/orderbook_ws.py` (o extensión de `market_ws_server.py`): suscripción WebSocket a profundidad de order book (`@depth20`) de Binance Futures para los símbolos del watchlist activo
- [ ] 1.2 Tabla nueva en SQLite (mismo archivo/patrón que `kline_cache.py`) para persistir snapshots de order book recientes por símbolo
- [ ] 1.3 Función de cómputo de Order Flow Imbalance (OFI) normalizado (-1.0 a +1.0) a partir de los niveles capturados
- [ ] 1.4 Manejo explícito de "datos insuficientes" → devolver `None` auditable, nunca un score inventado (spec: datos insuficientes para calcular OFI)
- [ ] 1.5 Exponer OFI histórico reconstruible (sin lookahead) para que `agent/backtest_engine.py` pueda usarlo — seguir el mismo patrón de precálculo O(n) ya usado para las MAs (`_precompute_ma_series`)
- [ ] 1.6 Suscripción inicial acotada al subconjunto de símbolos de mayor volumen (reusar `VolatileSymbolsService`), no a los 400+ completos, para no repetir el problema de rate-limit de Binance de esta sesión
- [ ] 1.7 Backtest A/B: MA Slope Caso 3 con y sin filtro de OFI, mismo período histórico, comparar profit factor

## 2. Funding rate como señal

- [ ] 2.1 Lectura de funding rate actual + histórico (mín. 30 períodos) por símbolo, cacheado igual que klines
- [ ] 2.2 Backfill on-demand para símbolos sin historial de funding cacheado
- [ ] 2.3 Nuevo parámetro opcional en `patternParamsJson` (ej. `fundingFilter.maxAbsFunding`) consumido por `_evaluate_ma_geometry_profile` o equivalente, sin romper perfiles existentes que no lo configuren
- [ ] 2.4 Veto auditable en `setup_validator.py` cuando el funding excede el umbral configurado (mismo patrón que los vetos existentes)
- [ ] 2.5 Feature de predicción de próximo funding usando el OFI ya calculado en la sección 1
- [ ] 2.6 Backtest A/B: mismo criterio que 1.7, ahora con el filtro de funding

## 3. Dinámica de liquidaciones

- [ ] 3.1 Suscripción al stream `forceOrder` de Binance Futures por símbolo
- [ ] 3.2 Ventana reciente configurable (4-24h) de volumen liquidado por lado (long/short), persistida
- [ ] 3.3 Bandera de "cascada de liquidaciones en curso" con timestamp y magnitud, cuando el volumen liquidado de un lado supera el umbral respecto al promedio del símbolo
- [ ] 3.4 Filtro anti-cascada opt-in por perfil (no abrir en la misma dirección que una cascada activa reciente)
- [ ] 3.5 Historial reconstruible sin lookahead para el motor de backtesting
- [ ] 3.6 Backtest A/B: mismo criterio que 1.7 y 2.6, ahora con el filtro anti-cascada

## 4. On-chain real (reemplazo del widget de ballenas)

- [ ] 4.1 Decidir proveedor on-chain (ver Open Questions en design.md) según presupuesto real disponible
- [ ] 4.2 Nuevo cliente de datos on-chain (flujos netos exchange in/out, movimiento de wallets grandes) para los símbolos de mayor capitalización del watchlist
- [ ] 4.3 Manejo explícito de fuente no disponible/rate-limited (degradar con gracia, loguear, nunca inventar el dato)
- [ ] 4.4 Reemplazar el cálculo de `whaleScore` en `angular/src/app/dashboard/dashboard.component.ts` (hoy: keyword-matching en texto) por el dato real
- [ ] 4.5 Badge visible en el dashboard indicando si el score de ballenas mostrado es real o fallback — no repetir el patrón de "parece real y no lo es" sin que se note

## 5. Entrenamiento del modelo XGBoost de Nexus-15/Nexus-5

- [ ] 5.1 Construir dataset de entrenamiento: las 20 features de `NEXUS15_FEATURES` (`python-service/nexus15/model_loader.py`) calculadas sobre `agent/data/klines.db`, etiquetado con resultado real (retorno a N velas o resultado TP/SL simulado)
- [ ] 5.2 Excluir símbolos con historia insuficiente para generar ejemplos válidos, sin bloquear el resto
- [ ] 5.3 Split temporal (no aleatorio) entrenamiento/validación — nunca validar sobre datos vistos en entrenamiento
- [ ] 5.4 Entrenar el modelo (XGBoost, mismo formato que ya espera `Nexus15ModelLoader`/`Nexus5ModelLoader`)
- [ ] 5.5 Si el resultado en validación no sostiene lo visto en entrenamiento (señal de sobreajuste): documentar y NO desplegar — reintentar con más datos/regularización o descartar
- [ ] 5.6 Desplegar el `.json` del modelo en el path esperado (`models/nexus15/xgb_nexus15_v1.json`, `models/nexus5/xgb_nexus5_v1.json`) solo si pasa validación
- [ ] 5.7 Confirmar que `Nexus15ModelLoader`/`Nexus5ModelLoader` cargan el modelo real y loguean explícitamente el cambio (en vez del warning de "fallback mode active")
- [ ] 5.8 Backtest comparativo: cualquier perfil que dependa de Nexus-15/5, CON el modelo real vs. CON el placeholder de 0.5 — no desplegar a producción si no mejora el profit factor

## 6. Cierre del change

- [ ] 6.1 Documentar en `.claude/PROGRESS_LOG.md` qué señales quedaron activas y cuáles se descartaron por no mostrar mejora en backtest (mismo criterio ya aplicado a Caso 1/Caso 2/FVG)
- [ ] 6.2 `openspec archive market-data-expansion` una vez completadas las tareas anteriores, para que las specs pasen a `openspec/specs/` como estado vigente del sistema
