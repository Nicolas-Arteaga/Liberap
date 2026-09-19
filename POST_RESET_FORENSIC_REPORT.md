# POST-RESET FORENSIC REPORT — 2026-09-06

Auditoría del estado tras el "Docker Reset/Restart" reportado + el error
`System.InvalidOperationException: Nullable object must have a value` en
`SimulatedTradeAppService.GetPerformanceStatsAsync` (línea 583).

**NO se aplicó ningún cambio.** Esto es solo diagnóstico.

---

## 0. Resumen ejecutivo (leer esto)

1. **No hubo ningún Docker reset ni restart de la base en las últimas ~23 h.**
   El volumen `verge_pg_data` y el contenedor `verge-db` tienen 23 h de
   antigüedad; el backend (`Verge.HttpApi.Host.exe` PID 30832) nunca reinició.
   La base tiene **3315 SimulatedTrades intactos, 0 NULLs** en todos los
   campos relevantes.
2. **El error 500 NO es por datos ni por el reset.** Es un **bug latente
   pre-existente**: `GetPerformanceStatsAsync` hace `CurrentUser.Id!.Value` en
   la línea 583 y **no tiene `[Authorize]`**. Cualquier request **sin token**
   llega al cuerpo del método y `null.Value` tira la excepción. Con token
   devuelve 200 (verificado con `curl` y en el browser).
3. **El "Ganancia $0 / 0 trades" es OTRO síntoma, y sí es de hoy:** entre las
   **20:40 y 20:43 (hora local)** se **borraron 17 de las 20 estrategias
   desde la UI** (ícono de tacho en /estrategias). Es un *soft-delete*
   (`IsDeleted=true`, las filas siguen ahí). `GetPerformanceStatsAsync` solo
   suma trades de estrategias **no borradas y activas**, y las 3 que
   sobreviven (ARROW-PEAK, FVG-15m, MA Slope Caso 3) tienen **0 trades**
   porque sus trades se borraron antes a pedido explícito. Los **3315 trades
   siguen en la base**, colgando de las 17 estrategias soft-deleted → el
   endpoint los oculta.
4. **Nada nuevo se perdió de forma irreversible hoy.** Todo es recuperable
   (flag de soft-delete + backup `verge_20260906_204820.sql`).

---

## 1. El NULL exacto

### Código (`src/Verge.Application/Trading/SimulatedTradeAppService.cs`)

```
580  [HttpGet]
581  public async Task<SimulationPerformanceDto> GetPerformanceStatsAsync(Guid? strategyProfileId = null)
582  {
583      var userId = CurrentUser.Id!.Value;      // <-- acá tira
584      ...
```

| Pregunta | Respuesta |
|---|---|
| Qué nullable usa `.Value` | **`CurrentUser.Id`** — tipo `Guid?` de `Volo.Abp.Users.ICurrentUser` (inyectado en `ApplicationService`). |
| De qué entidad/query proviene | **De ninguna.** No es un dato de base. `ICurrentUser.Id` sale del claim `sub` del JWT, que el middleware `app.UseAuthentication()` pone en `HttpContext.User`. La excepción ocurre en la **primera línea**, antes de tocar el `_tradeRepo`. |
| Qué registro causa el NULL | **Ninguno.** Lo causa un **request HTTP sin token válido** → `HttpContext.User` no autenticado → `CurrentUser.Id == null` → `null.Value` → `InvalidOperationException`. |
| Cuál debería ser el valor | El `Guid` del usuario autenticado (para `agent@verge.internal` = `3a238b27-442d-5ee4-8f98-8722fba950e8`). Cuando hay token, ese es el valor y el endpoint responde **200**. |
| Existía antes del reset | **El bug de código sí** (nunca tuvo `[Authorize]` ni guard — 100% reproducible con cualquier llamada anónima). **El disparo operativo** (frontend llamando sin token) apareció después de que la sesión del browser quedó sin token válido. |

### Verificación en vivo

```
curl -sk .../api/app/simulated-trade/performance-stats                     -> 500  (sin Authorization header)
curl -sk .../api/app/simulated-trade/performance-stats -H "Bearer <tok>"   -> 200  {"totalGain":0,"winRate":0,"totalTrades":0,...}
```

En el browser con la sesión de `agent@verge.internal` (token válido hasta
2027): **todas** las llamadas a `performance-stats` devuelven **200**.

### Otros 7 métodos con el mismo patrón (mismo bug latente)

`OpenTradeAsync:51`, `CloseTradeAsync:366`, `GetActiveTradesAsync:542`,
`GetTradeHistoryAsync:549`, `GetVirtualBalanceAsync:556`,
`GetRecentTradesAsync:656`, `UpdateTpSlAsync:687`,
`UpdateMaxAdversePriceAsync:710` — todos `CurrentUser.Id!.Value` sin guard.

---

## 2. Auditoría de la base actual

| Ítem | Valor |
|---|---|
| DB que usa la API | `Host=localhost;Port=5433;Database=Verge` (`appsettings.json`; `appsettings.secrets.json` solo overridea `Redis`) |
| Container | `verge-db` (postgres 16.15), Up 23 h |
| Volume | `verge_pg_data` → `/var/lib/postgresql/data`, creado `2026-09-06T01:15:41Z` (23 h) — **no fue recreado** |
| Redis | `verge-redis` :6380 (Up 23 h) + `verge-redis-6379` (Up 21 h) — no relevante para el bearer auth (JWT RS256 autocontenido) |
| Backend | `Verge.HttpApi.Host.exe` PID **30832**, host, bajo VS — **mismo PID de toda la sesión, no reinició** |

### Conteo de tablas (sin modificar nada)

| Tabla | Filas | Nota |
|---|---|---|
| `SimulatedTrades` | **3315** | 443 Win + 2872 Loss, **0 Open** |
| `StrategyProfiles` | **20** | **3** `IsDeleted=f` · **17** `IsDeleted=t` (soft-deleted 20:40–20:43 local hoy) |
| `AbpUsers` | 2 | `admin` (`3a238694…`), `agent` (`3a238b27…`) — ambos activos |
| `OpenIddictTokens` | 30 | (estaban en 0 tras el reset de hace semanas; se regeneraron con logins) |
| `OpenIddictAuthorizations` | 9 | |
| `OpenIddictApplications` | 2 | `Verge_App`, `Verge_Swagger` |
| `TraderProfiles` | 1 | `agent`, balance 10000 |
| `AbpUserRoles` | 2 | admin→admin, agent→admin |

### NULLs en campos relevantes de `SimulatedTrades` (n=3315)

| Campo | Filas con NULL |
|---|---|
| `UserId` | **0** |
| `Status` | **0** |
| `RealizedPnl` | **0** |
| `StrategyProfileId` | **0** |
| `OpenedAt` | **0** |
| `ClosedAt` (status≠Open) | **0** |
| trades huérfanos (profile inexistente) | **0** |
| trades cuyo profile es de otro usuario | **0** |

**→ No hay ningún NULL de datos. La base está íntegra.**

### Dónde están los 3315 trades

| Estrategia | `IsDeleted` | trades en DB |
|---|---|---|
| ARROW-PEAK | f | **0** |
| FVG - 15m | f | **0** |
| MA Slope Caso 3 | f | **0** |
| Nexus | t | 1927 |
| FVG - 1m | t | 388 |
| FVG - 5m | t | 182 |
| GOLDEN-U-TURN | t | 132 |
| MA Pattern | t | 99 |
| FVG - 15m TP50 | t | 96 |
| FVG - 15m Pulido | t | 88 |
| FVG - 15m Pulido Long | t | 82 |
| MA Slope Caso 2 | t | 70 |
| MA Slope Caso 1 | t | 59 |
| MA Slope Caso 3 (15m) | t | 53 |
| FVG - 15m Pulido V2 | t | 35 |
| FVG - 15m v2 (filtros minados) | t | 34 |
| FVG - 15m Gap Chico | t | 29 |
| MA Slope Caso 3 Pulido | t | 24 |
| FVG - 15m v3 (anti-racha) | t | 10 |
| ARROW-PEAK-V2 | t | 7 |

**Los 3315 trades cuelgan de las 17 estrategias soft-deleted.** Las 3 vivas
tienen 0 porque sus trades (293 + 17 + 57 = 367) se borraron en la sesión
anterior, a pedido explícito ("limpia esos 3").

---

## 3. Comparación con el estado pre-reset y con lo que hicimos hoy

### Timeline reconstruido (hora local, UTC-3)

| ~Hora | Evento | Fuente |
|---|---|---|
| hace semanas | **Reset de fábrica de Docker** borra la base `Verge` original | PROGRESS_LOG 2026-09-06 |
| hace semanas | Reconstrucción desde `agent/data/trades.csv` → 20 profiles (config APROXIMADA) + 3682 trades (PnL no confiable) | `agent/reconstruct_db.py` |
| hoy ~20:1x | Recreo usuario `agent@verge.internal`, rol admin, muevo 20 profiles + 3682 trades de `admin` a `agent`, `IsActive=true` en las 20 | PROGRESS_LOG (8), este chat |
| **hoy 20:40:13 → 20:43:31** | **El usuario borra 17 de 20 estrategias desde la UI** (una cada ~5-10 s) | `StrategyProfiles.DeletionTime` |
| hoy 20:48:20 | Backup `verge_20260906_204820.sql` (**3682** trades, 17 profiles ya `IsDeleted=t`) | filesystem |
| hoy 20:48:xx | `DELETE FROM "SimulatedTrades"` de FVG-15m + ARROW-PEAK + MA Slope Caso 3 = **367 filas** | PROGRESS_LOG (8) |
| hoy 20:49:26 | Backup `verge_20260906_204926.sql` (**3315** trades) | filesystem |

### Evidencia del estado anterior encontrada

| Fuente | Qué aporta |
|---|---|
| `.claude/PROGRESS_LOG.md` | Historia completa: reset de Docker, reconstrucción, mis acciones (7) y (8) |
| `backups/verge_20260906_204820.sql` | **3682** trades (incluye los 367 borrados) — 17 profiles ya `IsDeleted=t` |
| `backups/verge_20260906_204926.sql` | 3315 trades (post-borrado) |
| `agent/data/trades.csv` | Fuente original de la reconstrucción (log del agente, PnL aproximado) |
| `scratch_gate_v4_results.json`, `scratch_caso3_gt.json`, `scratch_all_trades_p2.csv` | Ground-truth de Caso 3 usado en la investigación — intactos |
| Reportes `DIAG_CASO3_WR_REPORT.md`, `CASO3_SLOT_CAUSAL_REPORT.md`, `GOLDEN_CASO3_BACKTESTER_FIDELITY_REPORT.md` | Intactos |

**No existe ningún dump de la base ORIGINAL pre-Docker-reset.** Se perdió con
el volumen hace semanas (documentado). Lo que hay hoy es la reconstrucción.

---

## 4. Clasificación de cada recurso

| Recurso | Clase | Detalle |
|---|---|---|
| `SimulatedTrades` (3315 filas, todos los campos) | **A — intacto** | 0 NULLs, owner correcto, linkeo correcto. Ocultos en el resumen por el soft-delete de sus profiles, pero **presentes**. |
| 3 `StrategyProfiles` vivos (ARROW-PEAK, FVG-15m, MA Slope Caso 3) | **A — intacto** | 0 trades (borrados a pedido). |
| 17 `StrategyProfiles` soft-deleted | **B — restaurable** | Filas presentes, `IsDeleted=t`. `UPDATE "IsDeleted"=false` los revive con sus 3315 trades. |
| 367 trades borrados (de los 3 vivos) | **B — restaurable** | Solo en `backups/verge_20260906_204820.sql`. Restore selectivo o full. |
| Configs exactas de las 20 estrategias | **C — parcialmente perdido** | Ya eran "RECONSTRUIDO… APROXIMADA" desde el reset de Docker. El soft-delete de hoy **no empeora** esto (las filas con la config aproximada siguen). |
| PnL/PF/WR/DD reales por trade | **C — parcialmente perdido** | Ya no confiables desde la reconstrucción (CSV). No cambió hoy. |
| Base ORIGINAL pre-Docker-reset (PnL real, configs reales, posiciones abiertas, estrategias sin trades en el CSV) | **D — perdido** | Hace semanas, sin backup. **Nada de esto se perdió hoy.** |
| `AbpUsers`, `OpenIddict*`, `TraderProfiles`, roles | **A — intacto** | |
| Binance Vision (`binance_vision_clean.db` 5.97 GB), `klines.db` (OI 32 d) | **A — intacto** | No tocados. |
| OI collector (PID 30652), scripts diagnósticos, reportes, PROGRESS_LOG | **A — intacto** | |
| Causa de que el frontend llame sin token (refresh fallido vs race de UI) | **E — desconocido** | Requiere repro con DevTools abierto; en mi sesión autenticada no ocurre. |

---

## 5. Qué NO tocar

- Metodología **H11**, **H12**, criterios de investigación.
- **Caso 3**: parámetros, config, reportes.
- Datos históricos de **Binance Vision** / `klines.db` / **OI collector**.
- Scripts de `agent/backtest/` y los reportes generados.
- **No** hacer Docker reset. **No** reconstruir la base de cero. **No**
  borrar más datos. **No** re-correr backtests.
- **No** aplicar `?? 0` en la línea 583 (oculta el problema real y computaría
  stats de un "usuario cero").

---

## 6. Causa causal y fix recomendado

### Cadena causal del 500

```
request HTTP sin bearer token válido
  -> app.UseAuthentication() no puebla HttpContext.User (anónimo)
  -> ICurrentUser.Id == null   (no hay claim `sub`)
  -> GetPerformanceStatsAsync NO tiene [Authorize]  (ABP no rechaza anónimos)
  -> se ejecuta el cuerpo; línea 583: CurrentUser.Id!.Value
  -> null.Value  ->  System.InvalidOperationException: "Nullable object must have a value."
  -> ASP.NET Core -> HTTP 500
```

**No hay `NULL -> campo -> query -> entidad`. No hay dato corrupto.** El NULL
es la identidad del usuario en un request no autenticado, y el bug es que el
endpoint no exige autenticación.

### Fix correcto (NO es `?? 0`)

**Parte A — el 500 (bug de código, aplica siempre):**
Hacer que un request anónimo reciba **401**, no 500. Dos opciones:

1. **`[Authorize]` a nivel de clase** en `SimulatedTradeAppService`.
   ABP entonces rechaza anónimos con 401 y el SPA redirige a login.
   *Riesgo:* si algún caller interno (agente/worker) pega a métodos de esta
   clase **sin** token, pasaría a recibir 401. Hay que verificar: el agente
   se autentica por password-grant (`auth_manager.py`), así que OK; los
   métodos `UpdateMaxFavorablePriceAsync` / `ResolveBinancePriceOnlyAsync`
   no usan `CurrentUser` — confirmar quién los llama antes.
2. **Guard explícito** en cada método (más quirúrgico, cero riesgo de romper
   otro caller):
   ```csharp
   if (CurrentUser.Id is not Guid userId)
       throw new AbpAuthorizationException("Not authenticated.");
   ```
   Devuelve 401, no 500. No inventa datos.

**Recomendado:** opción 2 en los 8 métodos, o `[Authorize]` de clase si se
confirma que ningún caller anónimo legítimo la usa.

**Parte B — el "0 trades / $0" (no es bug de código, es estado de datos):**
Los 3315 trades están, pero sus 17 estrategias están soft-deleted y el
endpoint las excluye. Decisión del usuario:

- Si el borrado de las 17 fue intencional ("ya no importa") → el 0 es
  **correcto**, no hay nada que arreglar del lado datos.
- Si se quieren de vuelta → `UPDATE "StrategyProfiles" SET "IsDeleted"=false,
  "DeletionTime"=NULL, "DeleterId"=NULL WHERE "IsDeleted";` → reaparecen las
  20 estrategias, los 3315 trades y el resumen de performance.
- Los 367 trades borrados (de los 3 profiles vivos) solo vuelven restaurando
  desde `backups/verge_20260906_204820.sql`.

---

## 7. Riesgo del fix

| Fix | Riesgo |
|---|---|
| Guard `if (CurrentUser.Id is not Guid userId)` en los 8 métodos | **Muy bajo.** Solo cambia 500→401 en requests anónimos. No toca datos. Recompilar + reiniciar backend. |
| `[Authorize]` a nivel de clase | **Bajo-medio.** Podría devolver 401 a un caller interno anónimo hoy silencioso. Verificar callers de `UpdateMaxFavorablePriceAsync`, `UpdateExitInfoAsync`, `ResolveBinancePriceOnlyAsync` primero. |
| `UPDATE IsDeleted=false` en las 17 | **Bajo.** Reversible (volver a `true`). Restaura visibilidad de datos íntegros. |
| Restore de los 367 trades desde el .sql | **Bajo** si es selectivo (extraer esas filas). Un restore **full** del dump revertiría también el `IsActive`/`IsDeleted` al estado del backup. |
| `?? 0` en línea 583 (NO hacer) | **Alto conceptual.** Computaría stats para `userId = Guid.Empty` → number equivocado presentado como válido; oculta el request no autenticado. |

---

## 8. Plan de recuperación

1. **Congelar:** ya hay 2 backups (`backups/verge_20260906_204820.sql` = 3682,
   `_204926.sql` = 3315). Correr `backups/backup_verge.ps1` una vez más ahora
   para tener el estado exacto post-forensic.
2. **Decidir sobre las 17 estrategias:**
   - mantenerlas borradas → no hacer nada; el resumen en $0 es fiel.
   - recuperarlas → `UPDATE "StrategyProfiles" SET "IsDeleted"=false,
     "DeletionTime"=NULL, "DeleterId"=NULL WHERE "IsDeleted";` (revierte con
     `=true`).
3. **Decidir sobre los 367 trades** de ARROW-PEAK/FVG-15m/MA Slope Caso 3:
   - dejarlos borrados (fue pedido explícito) → nada.
   - recuperarlos → restore selectivo de esas filas desde
     `verge_20260906_204820.sql`.
4. **Aplicar el fix del 500** (guard 401 en los 8 métodos, o `[Authorize]`),
   recompilar `Verge.HttpApi.Host`, reiniciar el backend.
5. **Verificar** (no solo "no tira excepción"):
   - anónimo → 401 (no 500).
   - autenticado → 200 con `totalTrades`, `totalGain`, `winRate`, `avgPerTrade`,
     `equityCurve` coherentes con `SimulatedTrades`.
   - `GetRecentTradesAsync` lista los trades esperados.
   - PF/WR/DD/equity recalculados == suma directa sobre la tabla.
6. **Programar** `backups/backup_verge.ps1` (Task Scheduler, PS elevado) para
   que un futuro reset no vuelva a costar todo.

---

## 9. Estado final de cada DB / volumen / archivo

| Recurso | Estado |
|---|---|
| DB `Verge` (`verge-db`, vol `verge_pg_data`) | **Intacta.** 3315 trades (0 NULLs), 20 profiles (3 vivos + 17 soft-deleted), auth OK. No reseteada (vol 23 h). |
| `verge-db` container / volume | Up 23 h / creado hace 23 h. Sin cambios estructurales. |
| `verge-redis` :6380 / `verge-redis-6379` | Up. No afectan el bearer auth. |
| Backend `Verge.HttpApi.Host.exe` (PID 30832) | Corriendo, sin reinicio. Bug de código latente en `SimulatedTradeAppService` (8 métodos). |
| `backups/verge_20260906_204820.sql` | OK — 3682 trades (única copia con los 367 borrados). |
| `backups/verge_20260906_204926.sql` | OK — 3315 trades (estado actual). |
| `backups/backup_verge.ps1` / `RESTORE.md` | OK. |
| `agent/data/trades.csv` | Intacto (fuente de la reconstrucción). |
| `binance_vision_clean.db` (5.97 GB) / `klines.db` (OI 32 d) | Intactos, no tocados. |
| OI collector (PID 30652) | Corriendo. |
| Scripts `agent/backtest/*` + reportes de investigación + PROGRESS_LOG | Intactos. |
| Base ORIGINAL pre-Docker-reset | **Perdida** hace semanas (sin backup). No recuperable. Nada de esto cambió hoy. |

---

## Conclusión

- **No hubo reset hoy.** El error 500 es un **bug de código pre-existente**
  (`CurrentUser.Id!.Value` sin `[Authorize]`/guard) que se dispara con
  cualquier request sin token; el trigger fue el frontend llamando sin token.
- **No se perdió ningún dato nuevo.** Los 3315 trades están íntegros; 17
  estrategias fueron soft-deleted desde la UI hoy (20:40–20:43) y eso oculta
  esos trades en el resumen, pero es **reversible con un flag**.
- **Fix correcto:** devolver **401** en requests anónimos (guard o
  `[Authorize]`), NO `?? 0`. Y decidir si se revierten las 17 estrategias
  soft-deleted y/o los 367 trades borrados (ambos recuperables).
- **Sin cambios aplicados.** Esperando tu decisión sobre los puntos 2–4 del
  plan de recuperación.
