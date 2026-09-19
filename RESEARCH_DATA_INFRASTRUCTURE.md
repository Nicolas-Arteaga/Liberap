# VERGE — RESEARCH DATA INFRASTRUCTURE

> **UPDATE Round 4 (2026-09-09 ~00:40 UTC) — activación.** Ver
> `RESEARCH_COLLECTORS_HEALTH.md` para la evidencia detallada. Cambios de
> estado respecto de lo de abajo:
>
> | Antes (Round 3) | Ahora (Round 4) |
> |---|---|
> | OI collector con universo nuevo = UNVERIFIED | **VERIFIED** — PID 54348, 63 símbolos, **BTC/ETH/SOL presentes** (2015 filas c/u, 7 d de backfill), 0 duplicados, último bucket ~5 min. `syms_ge90_fresh`: 2 → **40** |
> | `liquidations_research` vacía = UNVERIFIED | **VERIFIED** — liq tracker PID 18672, Bybit 63 topics, eventos entrando a `liquidations_research` desde 2026-09-09 00:31 UTC, 0 duplicados |
> | Restart-continuidad = testeada en DB temporal | **VERIFIED en vivo** — kill del OI collector (PID 30652) → relanzar → dataset continúa (469.375 → 542k filas), 0 dups |
> | Backup = 1 corrida | **VERIFIED ×2** — `research_klines_20260909_003348.sql.gz` (48.109.435 B, sha256 `b89db63f…c2641e41`), restore en `:memory:` OK |
> | AUTO-START (Task Scheduler) = UNVERIFIED | **sigue UNVERIFIED** — `Register-ScheduledTask`/`schtasks` → "Acceso denegado" (sesión no elevada). Script listo: `research/ops/register_research_tasks.ps1` (correr elevado) |
> | REBOOT | **UNVERIFIED** — no se puede rebootear el host en la sesión |
> | OHLCV estático off-host | **UNVERIFIED** — sin disco externo provisto |
>
> **Archivos nuevos de Round 4:** `agent/_run_liq_tracker.py` (runner UTF-8),
> `research/ops/register_research_tasks.ps1`, `OI_BACKFILL_DAYS` env en
> `open_interest_collector.py` (reinicio suave). Zombies limpiados: ahora hay
> **exactamente 1** instancia de cada colector (PIDs 54348, 18672).

**Fecha:** 2026-09-07
**Alcance:** SOLO infraestructura de datos. No se implementó H15, no se
crearon señales, no se tocó producción / StrategyProfiles / DB de producción /
motor live / validation protocol. H13 = PARK, H14 = congelado, H15 = esperando
datos.

Objetivo: garantizar que cuando llegue octubre tengamos datos buenos y no
descubramos que estuvimos perdiendo información 40 días.

---

## 0. Resumen de lo hecho (con evidencia)

| Ítem | Estado | Evidencia |
|---|---|---|
| Universo OI ampliado (Tier 0 BTC/ETH/SOL + 60 perps líquidos, ex-ante) | **HECHO** | `research/universe/oi_universe.json` (63 símbolos) + `OI_UNIVERSE.md`; generado por `build_oi_universe.py` desde liquidez local, **sin usar H13** |
| OI collector usa ese universo | **HECHO** (código) · **UNVERIFIED** (colectando) | `agent/open_interest_collector.py` — `load_research_universe()`. No se pudo reiniciar/verificar contra Binance desde este entorno (IP compartida con el agente live, riesgo de ban) → lo reinicia el usuario |
| OI persistencia idempotente / sin dups / gaps detectables / sobrevive restart | **VERIFICADO** | `research/tests/test_data_integrity.py` → **15/15 PASS**; `oi_coverage_report.json` → `duplicate_rows: 0` |
| Separación LIVE CACHE ↔ RESEARCH DATASET de liquidaciones | **HECHO** | nueva tabla `liquidations_research` (append-only, PK de dedup) + `liq_collector_health`; `prune_old_liquidations` documentado como "solo live" |
| **El prune NO borra research** | **VERIFICADO** | `test_data_integrity.py` test 10-11: `prune_old_liquidations(keep_hours=0)` vacía `liquidations` y deja `liquidations_research` intacto — **PASS** |
| Liq collector: universo ampliado + escribe a research + registra salud | **HECHO** (código) · **UNVERIFIED** (colectando) | `agent/liquidation_tracker.py` — el proceso **no está corriendo ahora**; lo levanta el usuario |
| Monitores de calidad (JSON + MD) | **HECHO y CORRIENDO** | `research/data_quality/oi_quality_monitor.py`, `liquidation_quality_monitor.py` → 4 reportes generados |
| Backup de datasets de research + verificación de restore | **HECHO** | `research/backup/backup_research_data.py` (checkpoint WAL → dump → restore en `:memory:` → rota 14) |
| Docker independence | **YA SE CUMPLE** | los `.db` viven en `agent/data/` del **host**, no en volúmenes; sobrevivieron el Docker reset que sí borró Postgres |

**Lo que falta y depende del usuario:** reiniciar los dos colectores para que
tomen el universo nuevo; programar el auto-arranque tras reboot; correr el
backup del OHLCV estático a un disco externo.

---

## 1. ¿Dónde vive ahora cada dataset?

| Dataset | Archivo / tabla | Ubicación física | Tipo |
|---|---|---|---|
| **OI histórico** | `open_interest` en `agent/data/klines.db` | **host FS** `C:\Users\Nicolas\Desktop\Verge\Verge\agent\data\klines.db` | SQLite (WAL) |
| **Liquidaciones (live cache)** | `liquidations` en `klines.db` | idem host FS | SQLite — retención 7 d (prod) |
| **Liquidaciones (research)** | `liquidations_research` en `klines.db` (**nueva**) | idem host FS | SQLite — **append-only, sin prune** |
| Salud del liq collector | `liq_collector_health` en `klines.db` (**nueva**) | idem | SQLite |
| **Taker flow** | `taker_flow` en `agent/data/binance_vision_clean.db` | **host FS** (5.6 GB) | SQLite — **estático** (descarga de data.binance.vision, se congeló 2026-08-17) |
| **OHLCV 5m/15m** | `klines_5m` / `klines_clean` en `binance_vision_clean.db` | host FS | SQLite — **estático** |
| OHLCV live cache | `klines` en `klines.db` | host FS | SQLite — cache del agente (append + prune manual) |
| Funding | `funding_rates` en `klines.db` | host FS | SQLite |
| OFI | `orderbook_ofi` en `klines.db` | host FS | SQLite — prune 30 d |
| Whale/on-chain | `whale_events` en `klines.db` | host FS | SQLite — prune 72 h |
| **Reportes de research** | `*_REPORT.md`, `ALPHA_*.md`, `research/` | host FS (git repo) | Markdown / JSON / .py |
| DB de producción `Verge` (trades, StrategyProfiles) | Postgres | **volumen Docker `pg_data`** | **NON-CANONICAL** (ver `RESEARCH_RESET_PLAN.md §2`); no es research data |

### Dónde corren los colectores

| Proceso | Cómo corre | Contenedor | Estado ahora |
|---|---|---|---|
| `open_interest_collector.py` | **proceso del host** (`python -u open_interest_collector.py`) | NO | **CORRIENDO** (verificado, PID activo) |
| `liquidation_tracker.py` | proceso del host (se lanza aparte) | NO | **NO CORRIENDO** — hay que levantarlo |
| OFI (`orderbook_ws.py`) | proceso del host | NO | corriendo (30 d acumulados) |

No hay servicio `oi-collector` ni `liquidation` en `docker-compose.yml` (el
`docker-compose.yml` actual solo tiene redis, db, market-data, market-ws,
backtest). Los colectores de research **no dependen de Docker**.

---

## 2. ¿Sobrevive a Docker reset?

| Recurso | ¿Sobrevive Docker reset? | Por qué |
|---|---|---|
| `klines.db` (OI, liquidaciones, funding, OFI) | **SÍ** | archivo en `agent/data/` del host, **no** es un volumen Docker. **Probado**: sobrevivió el reset del 2026-09-06 que sí borró el volumen `pg_data` de Postgres |
| `binance_vision_clean.db` (OHLCV, taker, spot) | **SÍ** | idem host FS |
| Reportes / scripts / `research/` | **SÍ** | git repo en el host |
| Procesos colectores | **SÍ a `docker restart`**, **NO a un reboot del host** | son procesos del host; un `docker reset` no los toca; un reboot sí → necesitan auto-arranque (§ punto pendiente) |
| DB de producción `Verge` (Postgres) | **NO** | vive en el volumen `pg_data`; ya se perdió una vez. **No es research data.** |

**Conclusión:** el dataset científico **ya existe fuera del lifecycle del
container.** Docker no es requisito para preservarlo. El único riesgo real es
un **reboot del host** que mate los colectores sin que arranquen solos.

---

## 3. ¿Sobrevive a restart?

| Escenario | ¿Se pierde dato? | Evidencia |
|---|---|---|
| Restart del colector (proceso muere y vuelve) | **NO** | SQLite WAL: toda transacción commiteada está en disco. El collector hace `conn.commit()` por batch (OI) / por evento (liq). Al reabrir, SQLite recupera del WAL. Test `OI sobrevive reopen` + `LIQ research sobrevive reopen` → **PASS** |
| Reconexión del WS de liquidaciones | **NO** (y no duplica) | cada evento se persiste inmediato con `INSERT ... ON CONFLICT DO NOTHING` sobre PK natural. Test `LIQ research duplicado devuelve False` + `dedup (1 fila)` → **PASS** |
| Evento fuera de orden (llega uno viejo después) | **NO** (queda ordenado al leer) | tests `OI out-of-order` + `LIQ research out-of-order` → **PASS** (SQLite ordena por `ORDER BY timestamp`, no por orden de inserción) |
| Kill -9 en mitad de un batch | a lo sumo se pierde el batch **en curso** (no commiteado); el OI collector lo re-trae el próximo ciclo (backfill idempotente de 1 h) | por diseño: `RECENT_LIMIT=12` buckets (1 h) por ciclo tapan huecos cortos |
| Reboot del host | los colectores **mueren** hasta que arranquen | **PENDIENTE**: registrar Task Scheduler para `open_interest_collector.py` y `liquidation_tracker.py` (`agent/register_oi_collector_task.ps1` existe pero da "Acceso denegado" sin PowerShell elevado) → **UNVERIFIED** |

Para OI, además, la fuente (Binance `openInterestHist`) retiene ~30 días — un
downtime < 30 días se recupera al 100% con el backfill de arranque. Para
**liquidaciones NO hay recuperación**: lo que no se captura en vivo se pierde
(Bybit no tiene REST histórico). Por eso la supervisión del liq collector es
crítica.

---

## 4. ¿Cómo se detectan gaps?

- **OI:** `research/data_quality/oi_quality_monitor.py` → por símbolo cuenta
  intervalos de 5 m consecutivos ausentes entre el primer y último timestamp
  (`n_gaps`, `biggest_gap_buckets`, `total_missing_buckets`, `coverage_pct`).
  También `out_of_order_pairs`. Salida: `oi_coverage_report.json` +
  `OI_COVERAGE_REPORT.md`. Corrida actual: **span 34.38 d, 0 duplicados**,
  cobertura mediana del universo 89.8 %.
- **Liquidaciones:** `liquidation_quality_monitor.py` → mayor silencio entre
  eventos consecutivos (`biggest_inter_event_gap_min`), eventos/día,
  `liq_collector_health` (connect/disconnect/heartbeat) → **downtime estimado**
  sumando `disconnect → connect`. Salida: `liquidation_coverage_report.json` +
  `LIQUIDATION_COVERAGE_REPORT.md`.
- **Diferencia clave:** en liquidaciones "sin eventos" puede ser mercado quieto,
  NO downtime. Por eso el `liq_collector_health` con heartbeats explícitos: si
  no hay heartbeat, el colector está caído; si hay heartbeat con
  `events_since_last=0`, el mercado está quieto.
- Correr por cron: ambos monitores son idempotentes y solo leen. Sugerido cada
  6 h (ver `research/data_quality/` — se puede agregar a la misma tarea
  programada del backup).

---

## 5. ¿Cómo se detectan duplicados?

| Dataset | Mecanismo anti-duplicado | Verificación |
|---|---|---|
| **OI** | `PRIMARY KEY (exchange, symbol, period, timestamp)` + `INSERT ... ON CONFLICT DO UPDATE`. Re-backfillear el mismo período **no** duplica. | test `OI sin duplicados tras re-insert x3` → PASS; `oi_coverage_report.json → duplicate_rows: 0` |
| **Liquidaciones (research)** | `PRIMARY KEY (venue, symbol, timestamp, side, price, qty)` + `ON CONFLICT DO NOTHING`. Un resubscribe de Bybit reenvía el snapshot → se ignora. | test `LIQ research duplicado devuelve False` + `dedup (1 fila)` → PASS. **Riesgo residual**: dos liquidaciones genuinamente idénticas en el mismo ms se colapsan en 1 (despreciable para agregados de H14) — marcado como limitación (§10) |
| **Liquidaciones (live cache)** | tabla `liquidations` NO tiene PK — puede duplicar. Es aceptable: es cache efímero de 7 d que el agente usa para "¿hay cascada ahora?". El research dataset es el que importa. |
| Monitores | ambos cuentan explícitamente `GROUP BY ... HAVING COUNT(*)>1` y lo reportan | — |

---

## 6. ¿Qué universo OI estamos recolectando?

Definido **ex-ante** en `research/universe/oi_universe.json` (`build_oi_universe.py`):

- **Tier 0 (obligatorio):** BTCUSDT, ETHUSDT, SOLUSDT.
- **Tier 1:** top **60** perps por **mediana de dollar-volume de 5 m** sobre
  los últimos 30 días de datos locales (`binance_vision_clean.db / klines_5m`,
  perps de Binance Futures), con cobertura ≥ 95 % en la ventana.
- **Excluidos ex-ante:** perps tokenizados de acciones/commodities/ETFs (XAU,
  XAG, SOXL, MSTR, COIN, NVDA, ...) — son otra clase de activo (gapean con la
  bolsa). Lista completa en el JSON (`excluded_equity_commodity`).
- **Total: 63 símbolos.** Primeros de Tier 1: XRP, ZEC, HYPE, DOGE, BNB, ADA,
  1000PEPE, WLD, PUMP, LINK, SUI, NEAR, ENA, UNI, ONDO, AAVE, AVAX, ...
- **NO se seleccionó ningún símbolo por resultados de H13.**

**Estado de captura (monitor, 2026-09-08):** el colector todavía venía con el
watchlist viejo (~30 microcaps). De los 63 del universo nuevo, **28 tienen
algún dato** y **BTC/ETH/SOL faltan** (`OI_COVERAGE_REPORT.md →
symbols_missing_from_universe`). Al reiniciar el colector con el código nuevo,
hace backfill de 30 d de los 63 y a partir de ahí acumula. → **acción del
usuario: reiniciar `open_interest_collector.py`.**

---

## 7. ¿Qué universo de liquidaciones estamos recolectando?

- **Mismo archivo** `research/universe/oi_universe.json` (los 63), vía
  `load_research_universe()` en `liquidation_tracker.py` (antes: solo
  `config.WATCHLIST_TIER1`, ~30 microcaps).
- **Venue: Bybit** (`allLiquidation.<symbol>`, WS). Binance `forceOrder` está
  muerto globalmente (documentado en el propio `liquidation_tracker.py`).
- **Se intentan los 63; cuáles están disponibles en Bybit = UNVERIFIED** hasta
  que corra (algunos perps de Binance no existen en Bybit). El monitor lo
  reporta: `universe_symbols_seen` vs `universe_symbols` y
  `universe_symbols_missing`.
- **Nota de mismatch de venue:** OI = Binance, liquidaciones = Bybit. Para H14,
  cruzar OI (Binance) con cascadas (Bybit) asume que el posicionamiento agregado
  se mueve parecido en ambos venues. Limitación documentada (§10).

---

## 8. ¿Cuál es la cobertura actual?

### OI (`oi_coverage_report.json`, 2026-09-08)

| Métrica | Valor |
|---|---|
| Span histórico | **34.38 días** (2026-08-04 → 2026-09-08) |
| Universo esperado | 63 |
| Símbolos con datos | 28 (watchlist viejo) |
| Símbolos ≥ 90 % cobertura **y frescos** | **2** (con el universo nuevo; con el viejo eran ~45) |
| Cobertura mediana (universo nuevo) | 89.8 % |
| Duplicados | **0** |
| Faltan del universo | 35, **incluidos BTC/ETH/SOL** → se resuelve al reiniciar el colector |

### Liquidaciones (`liquidation_coverage_report.json`, 2026-09-08)

| Métrica | Valor |
|---|---|
| Tabla `liquidations_research` | **creada, 0 filas** (el colector no corrió aún con el código nuevo) |
| `liquidations` (live cache) | 7 días, 106 microcaps, auto-podada a 7 d (sin cambios; es el cache de prod) |
| Downtime histórico | no medible retroactivamente (no había health table) — empieza a medirse ahora |

---

## 9. ETAs

| Objetivo | Estado hoy | ETA | Base del cálculo |
|---|---|---|---|
| **OI ≥ 70 días** | 34.38 d | **~2026-10-13** | del monitor (`gate_70d.eta_utc`), asumiendo colección continua |
| **OI ≥ 70 d con ≥ 20 símbolos ≥ 90 %** | hoy 2 (universo nuevo) | **~2026-10-13** si el colector arranca ya con los 63; los símbolos nuevos necesitan ~35 d para llegar a 90 % de su propia ventana | requiere reinicio del colector **ahora** |
| **Liquidaciones ≥ 60 días** | 0 d de research | **~2026-11-06** | si el colector arranca 2026-09-07 y corre continuo |
| **Liquidaciones ≥ 90 días** | 0 d | **~2026-12-06** | idem |

**Riesgo de cronograma:** cada día que el liq collector no corra con el código
nuevo es un día perdido irrecuperable (sin backfill posible). El OI tolera
downtime < 30 d.

---

## 10. Limitaciones conocidas

| # | Limitación | Severidad | Mitigación |
|---|---|---|---|
| 1 | **Colectores no reiniciados** con el código nuevo → OI aún sin majors, `liquidations_research` vacía | ALTA (cronograma) | acción del usuario: reiniciar ambos procesos |
| 2 | **OI collector colectando = UNVERIFIED** contra Binance (IP compartida con el agente live → no se testeó desde acá) | MEDIA | el usuario lo reinicia; el monitor confirma en el próximo run |
| 3 | **Bybit puede no tener los 63 símbolos** de liquidaciones; y no se sabe si el feed trae *todas* las liq o solo las grandes | MEDIA | el monitor reporta `universe_symbols_missing`; para completitud del feed, comparar 1 día contra Coinglass (requiere que el usuario pague una muestra) |
| 4 | **Auto-arranque tras reboot = UNVERIFIED** (Task Scheduler necesita PowerShell elevado, "Acceso denegado" desde acá) | MEDIA | el usuario corre `register_oi_collector_task.ps1` + una tarea equivalente para liquidaciones, elevado |
| 5 | **Mismatch de venue**: OI=Binance, liquidaciones=Bybit | MEDIA (afecta H14) | documentado; a futuro, sumar OI de Bybit (`/v5/market/open-interest`) — el esquema ya tiene columna `exchange` |
| 6 | Dedup de liquidaciones colapsa 2 eventos idénticos en el mismo ms | BAJA | despreciable para agregados de cascada |
| 7 | `binance_vision_clean.db` (OHLCV/taker) **se congeló 2026-08-17** — no cubre la ventana de OI actual para el análisis conjunto | MEDIA | usar `klines.db/klines` (1h, cubre hasta hoy) para el overlap; o rebajar el análisis a lo que cubran ambos |
| 8 | **Backup off-host del OHLCV estático (5.6 GB) = UNVERIFIED** | MEDIA | el usuario corre `backup_research_data.py --copy-static <disco externo>` una vez |
| 9 | El `.db` de research vive en un solo disco del host (sin RAID/replicación) | MEDIA | el backup periódico (`research/backup/`) + la copia off-host cubren el caso de disco muerto |
| 10 | Los monitores de calidad no están programados aún (se corrieron a mano) | BAJA | agregar al Task Scheduler junto con el backup |

---

## 11. Estrategia de backup

| Qué | Cómo | Frecuencia | Verificación |
|---|---|---|---|
| **Datasets de colectores** (OI, liquidaciones live+research, funding, OFI, whale) | `research/backup/backup_research_data.py`: checkpoint WAL → copia compacta `.sqlite` con solo esas tablas → `.sql.gz` portable → **restaura el `.sql.gz` en `:memory:` y compara conteos contra el snapshot** → rota (conserva 14) | diaria + al login (programar con `.ps1`) | el propio script aborta si el dump es sospechosamente chico o si el restore no matchea |
| **OHLCV estático** (`binance_vision_clean.db`, 5.6 GB) | `backup_research_data.py --copy-static <DIR>` — copia one-shot a un disco externo (no se re-copia si ya existe idéntico) | **una vez** (es estático) | comparación de tamaño |
| **Reportes / scripts / `research/`** | git (ya versionado) | cada commit | — |
| **DB de producción `Verge`** | `backups/backup_verge.ps1` (ya existe, de la sesión anterior) | diaria | ese script también verifica |

**Restauración:** `gunzip -c research_klines_<ts>.sql.gz | sqlite3 nueva.db`
(o cargar el `.sqlite` directo). **No se ejecutó ninguna restauración** sobre
datos reales — solo la verificación en `:memory:` que hace el script.

---

## 12. Tests ejecutados (evidencia)

`research/tests/test_data_integrity.py` — DB temporal, sin tocar la real, sin
APIs. **15/15 PASS** (`INTEGRITY_TEST_RESULTS.md`):

| # | Test | Resultado |
|---|---|---|
| 1 | OI upsert idempotente (1 fila tras doble insert) | PASS |
| 2 | OI upsert actualiza el valor | PASS |
| 3 | OI evento out-of-order queda ordenado al leer | PASS |
| 4 | OI gap detectable (`missing > 0`) | PASS |
| 5 | OI sin duplicados tras re-insert ×3 | PASS |
| 6 | OI sobrevive cerrar+reabrir la conexión (restart) | PASS |
| 7 | LIQ research: insert nuevo devuelve True | PASS |
| 8 | LIQ research: duplicado exacto devuelve False (dedup) | PASS |
| 9 | LIQ research: eventos genuinamente distintos SÍ se guardan | PASS |
| 10 | LIQ research out-of-order ordenado al leer | PASS |
| 11 | **`prune_old_liquidations` borra del live cache** | PASS |
| 12 | **`prune_old_liquidations` NO toca `liquidations_research`** | PASS |
| 13 | **`prune keep_hours=0` vacía el live, research intacto** | PASS |
| 14 | LIQ research sobrevive restart | PASS |
| 15 | (agregados en el propio archivo) | PASS |

Monitores ejecutados: `oi_coverage_report.{json,md}` y
`liquidation_coverage_report.{json,md}` generados 2026-09-08.
Backup ejecutado: `research/backup/research_klines_20260908_*.sqlite` + `.sql.gz`
con verificación de restore.

---

## 13. Criterio de terminación — checklist

| Requisito | Estado |
|---|---|
| cobertura | **medida y reportada** (`oi_coverage_report`, `liquidation_coverage_report`) |
| persistencia | **verificada** (WAL + commit por batch/evento; tests de reopen PASS) |
| reinicio | **verificado** (tests `sobrevive reopen` PASS); auto-arranque tras reboot = **UNVERIFIED** (punto 4) |
| ausencia de duplicados | **verificada** (PK + tests; `duplicate_rows: 0`) |
| ausencia de prune sobre research | **VERIFICADA** (tests 11-13 PASS) |
| ubicación persistente | **confirmada** (host FS, fuera de volúmenes Docker; sobrevivió un Docker reset real) |
| backup | **hecho + auto-verificado**; copia off-host del estático = **UNVERIFIED** (punto 8) |
| tests ejecutados | **15/15 PASS** |
| colectores tomando el universo nuevo | **UNVERIFIED** — código listo, faltan los reinicios (puntos 1-2) |

---

## 14. Acciones pendientes del usuario (todo research infra, nada de producción)

1. **Reiniciar `open_interest_collector.py`** para que tome los 63 símbolos
   (incl. BTC/ETH/SOL). Verá un backfill de 30 d al arranque.
2. **Levantar `liquidation_tracker.py`** (no está corriendo) — cada día sin
   correr es dato de liquidaciones perdido para siempre.
3. **Programar** en Task Scheduler (PowerShell elevado): los dos colectores con
   auto-arranque + reinicio, `research/backup/backup_research_data.ps1` (diario)
   y los dos monitores de calidad (cada 6 h).
4. **Una vez:** `python research/backup/backup_research_data.py --copy-static
   <disco externo>` para el OHLCV estático.
5. Re-generar el universo (`build_oi_universe.py`) cuando haya klines locales
   más nuevas que 2026-08-17.

---

## Ledger de infraestructura (hechos, no hipótesis)

- 2026-09-07: universo de research OI/liq definido ex-ante (63 símbolos,
  Tier 0 BTC/ETH/SOL + top-60 por liquidez local, excluye equity/commodity
  perps). `research/universe/`.
- 2026-09-07: `liquidations_research` (append-only) + `liq_collector_health`
  agregadas a `klines.db`; `prune_old_liquidations` acotado a `liquidations`
  (live). Verificado por tests que el prune no toca research.
- 2026-09-07: `open_interest_collector.py` y `liquidation_tracker.py`
  re-apuntados al universo de research.
- 2026-09-07: monitores de calidad + backup + suite de integridad creados y
  ejecutados. OI span 34.38 d, 0 duplicados, ETA gate 70 d ≈ 2026-10-13.
- Pendiente: reinicio de ambos colectores; auto-arranque; copia off-host del
  estático.
