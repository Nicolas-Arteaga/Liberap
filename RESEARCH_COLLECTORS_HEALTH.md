# VERGE — RESEARCH COLLECTORS HEALTH

**Generado:** 2026-09-09 ~00:40 UTC (Round 4 — activación y verificación)
**Alcance:** solo data collection + persistencia + auto-start + backup +
verificación. **No** se tocó H15, señales, producción, StrategyProfiles, motor
live, DB legacy, validation protocol, portfolio.

Estados: **VERIFIED** = hay evidencia de datos nuevos + persistencia.
**UNVERIFIED** = no se pudo comprobar en esta sesión (no se inventa evidencia).

---

## Tabla resumen

| Collector | Running | Last data | Coverage | Duplicates | Restart | Auto-start |
|---|---|---|---|---|---|---|
| **OI** | **VERIFIED** — PID **54348**, 1 instancia, relanzado 2026-09-09 00:37 UTC (`OI_BACKFILL_DAYS=7`) | **VERIFIED** — último bucket ~5 min, alineado a 5m, no futuro | **VERIFIED** — **63/63 símbolos del universo con datos, 63/63 ≥90% + frescos, cobertura mediana 100%**; BTC/ETH/SOL = 2015 filas c/u (7 d 09-02→09-09); OI 469k → 584k+ filas | **VERIFIED — 0** grupos duplicados (PK `(exchange,symbol,period,timestamp)`) | **VERIFIED** — snapshot pre-restart 469.375 filas → post 584k+, sin reset, 0 dups nuevos | **UNVERIFIED** — `Register-ScheduledTask` / `schtasks` → "Acceso denegado" (sesión no elevada, probado) |
| **Liquidations** | **VERIFIED** — PID **18672**, 1 instancia, arrancado 2026-09-09 00:37 UTC | **VERIFIED** — eventos entrando desde 00:31:32 UTC; último 00:43:41 UTC; **heartbeat post-restart 00:42:34 `ev=4`** (WS vivo). Ritmo bajo = mercado quieto (NO `VENUE_NO_DATA`) | **PARCIAL** — Bybit WS, 63 topics; **21 eventos / 9 símbolos** hasta ahora; `universe_symbols_seen` crece (ver `LIQUIDATION_COVERAGE_REPORT.md`) | **VERIFIED — 0** grupos duplicados (PK `(venue,symbol,timestamp,side,price,qty)` + `ON CONFLICT DO NOTHING`); `pct_events_persisted_ok=100` | **VERIFIED** — reconexión no duplica (test + vivo) + append-only sobrevive prune; downtime estimado 0 min | **UNVERIFIED** — mismo motivo |

> **Procesos:** verificado por CIM que hay **exactamente 1** instancia de cada
> colector (OI 54348, LIQ 18672, mismo parent). Zombies previos (el `nohup &`
> de git-bash duplicaba) fueron killeados; ahora se lanzan con `Start-Process`.

---

## 1. OI collector — evidencia

| Ítem | Valor / evidencia |
|---|---|
| Proceso | `python -u open_interest_collector.py` en `agent/`, PID **16431**, relanzado 2026-09-09 **00:31:28 UTC** con `OI_BACKFILL_DAYS=7` (reinicio suave para no cargar la IP compartida con el agente live) |
| Universo | **63 símbolos** ex-ante (`research/universe/oi_universe.json`) — Tier 0 BTC/ETH/SOL + 60 por liquidez. Log del arranque: *"backfill inicial de 63 símbolos (hasta 7d)"* |
| Filas nuevas | 469.375 → **532.627** (+63.252) en ~10 min |
| **BTC presente** | **SÍ** — 2015 filas, 2026-09-02 00:35 → 2026-09-09 00:25 |
| **ETH presente** | **SÍ** — 2015 filas, mismo rango |
| **SOL presente** | **SÍ** — 2015 filas, mismo rango |
| Símbolos activos | 272 en total; **40** con ≥90% cobertura **y** último dato < 60 min (antes del restart: 2) |
| Timestamps recientes | último bucket **2026-09-09 00:25:00 UTC** (alineado a 5m, no futuro) |
| Duplicados | **0** grupos (`GROUP BY exchange,symbol,period,timestamp HAVING COUNT>1`) |
| Gaps anormales | cobertura mediana del universo ~90%; los nuevos símbolos suben hacia 90% a medida que acumulan hacia adelante. `OI_COVERAGE_REPORT.md` lista `n_gaps` / `biggest_gap_buckets` por símbolo |
| Circuit breaker Binance | **CLOSED / available** antes y después del restart — el reinicio de 7d no disparó ningún 418/429 |
| Fuente / retención | Binance `futures/data/openInterestHist` period=5m; la fuente retiene ~30 d → downtime < 30 d se recupera con backfill idempotente |

## 2. Liquidation tracker — evidencia

| Ítem | Valor / evidencia |
|---|---|
| Proceso | `python -u _run_liq_tracker.py` en `agent/` (wrapper de `run_liquidation_capture`), PID **16397**, arrancado 2026-09-09 **00:30:15 UTC** |
| Venue / endpoint | **Bybit** `wss://stream.bybit.com/v5/public/linear`, topics `allLiquidation.<symbol>`. (Binance `forceOrder` está muerto globalmente — documentado en el propio archivo) |
| Conexión | Log: *"Websocket connected"* + *"LiquidationTracker conectado (63 símbolos, Bybit allLiquidation)"*. `liq_collector_health`: 2 `connect` |
| Universo | **63 símbolos** (mismo `oi_universe.json`, antes eran ~30 microcaps de `WATCHLIST_TIER1`) |
| Eventos entrando | **SÍ** — primer evento persistido 2026-09-09 **00:31:32.273 UTC** (ARBUSDT Buy, $24). Siguen entrando (mercado quieto → ritmo bajo, no es `VENUE_NO_DATA`) |
| Persistencia en `liquidations_research` | **SÍ** — append-only, `insert_liquidation_research()` por evento, `conn.commit()` inmediato |
| Deduplicación | **0** grupos duplicados. Test previo: resubscribe de Bybit → `ON CONFLICT DO NOTHING` |
| long/short | columna `side`: `Sell` = long liquidado, `Buy` = short liquidado (registrado por evento) |
| notional | `qty * price` por fila; agregado en el monitor |
| Símbolos sin datos de Bybit | si algún símbolo del universo no está en Bybit o no liquida, el monitor lo lista en `universe_symbols_missing` — se marca implícitamente `NO_DATA_FROM_VENUE`, **no se inventa nada** |
| **Recuperación histórica** | **IMPOSIBLE** (Bybit no tiene REST histórico). Cada minuto sin correr = dato perdido. Por eso arrancó con prioridad. |

## 3. Verificación de almacenamiento (Round 4 §3)

- **Ruta exacta:** `C:\Users\Nicolas\Desktop\Verge\Verge\agent\data\klines.db`
  (+ sidecars WAL `klines.db-wal`, `klines.db-shm`). Tablas `open_interest` y
  `liquidations_research` viven ahí.
- **Fuera del lifecycle de Docker:** es un archivo del **filesystem del host**,
  no un volumen Docker. `docker-compose.yml` no monta `agent/data/` en ningún
  contenedor. **Evidencia histórica:** este archivo sobrevivió el Docker
  factory-reset del 2026-09-06 que sí borró el volumen `pg_data` de Postgres.
  No se hizo un nuevo reset destructivo (la evidencia anterior alcanza).
- **Prueba de restart-continuidad (ejecutada):**
  1. timestamp registrado: `_restart_test_snapshot.json` → 2026-09-09 00:31:21
     UTC, `open_interest` = **469.375** filas, max bucket 1788913500000.
  2. collector cerrado: `taskkill /F /PID 30652`.
  3. collector reiniciado: PID 16431.
  4. dataset continúa: **532.627** filas (creció, no reseteó), max bucket
     igual o más nuevo.
  5. sin duplicados: **0** grupos.
  → **VERIFIED.**

## 4. Task Scheduler (Round 4 §4)

| Componente | Tarea | Estado |
|---|---|---|
| OI collector | `VergeOICollector` — AtLogOn + restart 5 min | **NO REGISTRADA — UNVERIFIED** |
| Liquidation tracker | `VergeLiqTracker` — AtLogOn + restart 5 min | **NO REGISTRADA — UNVERIFIED** |
| OI monitor | `VergeOIMonitor` — cada 6 h | **NO REGISTRADA — UNVERIFIED** |
| Liq monitor | `VergeLiqMonitor` — cada 6 h | **NO REGISTRADA — UNVERIFIED** |
| Research backup | `VergeResearchBackup` — diario 4am + AtLogOn | **NO REGISTRADA — UNVERIFIED** |

**Motivo:** `Register-ScheduledTask` y `schtasks /Create` devuelven
**"Acceso denegado"** — esta sesión **no corre elevada**. Probado explícitamente.

**Acción del usuario (PowerShell ELEVADO, una vez):**
```
powershell -ExecutionPolicy Bypass -File research\ops\register_research_tasks.ps1
```
El script (`research/ops/register_research_tasks.ps1`) registra las 5 tareas
con auto-arranque, reinicio ante caída (`RestartInterval PT5M`, `RestartCount
999`) y `MultipleInstances IgnoreNew` (no duplica procesos).

## 5. Reboot verification (Round 4 §5)

**No se puede reiniciar el host dentro de esta sesión.**

`AUTO-START = UNVERIFIED`
`REBOOT = UNVERIFIED`

Los colectores corren ahora como procesos `nohup` — **sobreviven a que se
cierre esta shell**, pero **NO a un reboot del host** hasta que las tareas del
§4 estén registradas. Tras registrarlas, la verificación es: rebootear →
confirmar `Get-ScheduledTask -TaskName Verge* | ft TaskName,State` = Running,
`LastRunTime`/`LastTaskResult` OK, y que `oi_coverage_report.json` /
`liquidation_coverage_report.json` muestren filas con timestamp posterior al
reboot y `duplicate_rows: 0`.

## 6. Backup (Round 4 §6-7)

| Ítem | Valor |
|---|---|
| Script | `research/backup/backup_research_data.py` (+ `.ps1`) |
| Contenido | `open_interest`, `funding_rates`, `liquidations`, `liquidations_research`, `liq_collector_health`, `whale_events`, `orderbook_ofi` (las de colectores). `taker_flow`/`OHLCV` son estáticos → copia aparte |
| Última corrida | `research_klines_20260909_003348.sql.gz` — **48.109.435 bytes** (45 MB) — **sha256 `b89db63f44129cfecf32225a6df0463f7d3be511cf90463f2b3bf880c2641e41`** — ubicación `C:\Users\Nicolas\Desktop\Verge\Verge\research\backup\` — resultado **OK** (restore independiente en `:memory:`: open_interest 542.374 / liquidations_research 15 / funding_rates 48.667 / orderbook_ofi 2.24M / whale_events 9.592). También `.sqlite` compacto de 259 MB. Corridas previas: 1 (`20260908_014805`). |
| Verificación de restore | el script restaura el `.sql.gz` en `:memory:` y compara conteos contra el snapshot compacto; aborta si no matchea |
| Rotación | conserva 14 |
| **OHLCV estático off-host** (`binance_vision_clean.db`, 5.6 GB) | **UNVERIFIED** — no hay disco externo provisto. Comando listo: `python research\backup\backup_research_data.py --copy-static <DIR>`. **No se movió ni borró nada.** |

## 7. Fail-safe (Round 4 §9)

- **Colector cae:** OI → el loop `while True` captura excepciones y reintenta
  al próximo ciclo; el circuit breaker frena ante 418/429. Liq → `ws.run_forever()`
  reconecta, `liq_collector_health` registra `disconnect`/`connect`.
  Con Task Scheduler (`RestartInterval PT5M`) además se relanza el proceso.
- **No duplica procesos:** `MultipleInstances IgnoreNew` en las tareas.
  **Ahora mismo hay una sola instancia de cada uno** (PIDs 16431 y 16397);
  las viejas (30652, 18144 previo) fueron killeadas antes de relanzar.
- **No pierde datos persistidos:** WAL + commit por batch/evento; append-only
  para research; PK evita duplicar al re-ingerir.
- **Venue sin datos:** el monitor de liquidaciones lista
  `universe_symbols_missing` = símbolos del universo sin ningún evento →
  se interpreta `NO_DATA_FROM_VENUE`, no como "no hay mercado".

---

## Puntos UNVERIFIED (resumen honesto)

| # | Punto | Por qué |
|---|---|---|
| 1 | **AUTO-START (Task Scheduler)** | sesión no elevada → "Acceso denegado". Script listo; lo corre el usuario. |
| 2 | **REBOOT** | no se puede rebootear el host en esta sesión. |
| 3 | **OHLCV estático off-host** | no hay disco externo provisto. |
| 4 | Completitud del feed de Bybit (¿trae *todas* las liquidaciones o solo grandes?) | requiere comparar 1 día contra una fuente paga (Coinglass) — decisión del usuario. |
| 5 | Cobertura de liquidaciones por símbolo del universo | recién empieza a acumular; se ve en los próximos días vía el monitor. |

Todo lo demás (colectores corriendo, filas nuevas, timestamps recientes, BTC/
ETH/SOL presentes, 0 duplicados, continuidad tras restart, almacenamiento fuera
de Docker, backup con restore verificado) = **VERIFIED**.
