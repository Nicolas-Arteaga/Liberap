# ROUND 40 — PLAN DE CANARY CONTROLADO PARA TRAIL-1

## VEREDICTO: **READY TO ENABLE CANARY**

Todo el código está escrito, compilado (0 errores, verificado a
directorios temporales sin tocar el proceso en ejecución) y los 17 tests
siguen pasando. La migración está generada (no aplicada). **Nada se
activó — `TrailStop:Enabled=false`, `CanaryPercentage=0` en
`appsettings.json`, exactamente el comportamiento de hoy.**

---

## 1. Migración — generada, NO aplicada

`dotnet ef migrations add AddTrailStopCanaryFields` (solo genera
archivos locales, no toca la base — confirmado, es un comando distinto
de `dotnet ef database update`, que nunca se ejecutó).

**Hallazgo no relacionado, encontrado al generar la migración**: EF
propuso agregar también la columna `BreakevenLocked` — al verificar
por SQL directo contra la base de producción, **esa columna ya existe
ahí** (drift preexistente: en algún momento se agregó a la base sin
pasar por una migración de este proyecto, algo previo a esta ronda). Se
removió manualmente esa línea del `Up()`/`Down()` generado para que la
migración no falle con "column already exists" — el `ModelSnapshot`
sigue describiendo el estado final correctamente, la migración en sí solo
agrega lo que realmente falta.

**Columnas que sí agrega esta migración** (`SimulatedTrades`):

| Columna | Tipo | Nullable | Default | Uso |
|---|---|---|---|---|
| `TrailLevelApplied` | integer | No | `0` | Nivel de Trail-1 ya aplicado (0-3), monotónico |
| `TrailStopCanary` | boolean | **Sí** | `null` | `null`=sin evaluar, `true`=canary, `false`=control |
| `OriginalSlPrice` | decimal | Sí | `null` | SL original antes de que Trail-1 lo mueva (para el contrafactual) |
| `TrailAuditJson` | text | Sí | `null` | Bitácora de auditoría, máx. 3 eventos por trade |

**Compatibilidad verificada**: todas nullable o con default seguro — **no
modifica ni un solo valor de fila existente**. No requiere downtime (es
un `ADD COLUMN` puro en Postgres, operación de metadato, no reescribe la
tabla). Archivo:
`src/Verge.EntityFrameworkCore/Migrations/Trading/20260913033921_AddTrailStopCanaryFields.cs`.

## 2. Feature flag — de constante a configuración

Antes (R38): `private const bool TrailStopEnabled = false;` — para
cambiarlo había que recompilar y redeployar.

Ahora (`appsettings.json`, sección nueva):
```json
"TrailStop": {
  "Enabled": false,
  "CanaryPercentage": 0
}
```
Leído en el worker vía `IConfiguration` (inyectado por DI, patrón
estándar de ASP.NET Core, no requiere infraestructura nueva):
```csharp
private bool TrailStopEnabled => _configuration.GetValue<bool>("TrailStop:Enabled", false);
private int TrailStopCanaryPercentage => Math.Clamp(_configuration.GetValue<int>("TrailStop:CanaryPercentage", 0), 0, 100);
```
**Con los valores por defecto (ausencia de la sección, o `Enabled:false`),
el comportamiento es idéntico al de hoy** — verificado por los mismos 17
tests (siguen pasando sin cambios).

## 3. Diseño del canary — determinístico, sin símbolos hardcodeados

```csharp
private static bool IsCanaryAssigned(Guid tradeId, int canaryPercentage)
{
    if (canaryPercentage <= 0) return false;
    if (canaryPercentage >= 100) return true;
    var bucket = Math.Abs(tradeId.GetHashCode()) % 100;
    return bucket < canaryPercentage;
}
```

- **Asignación por `trade.Id` (Guid), no por símbolo** — `Guid.
  GetHashCode()` es estable para el mismo valor de Guid en cualquier
  proceso/máquina/reinicio, así que un trade asignado a canary sigue
  siendo canary para siempre, sin depender de estado en memoria.
- Se evalúa **una sola vez por trade** (la primera vez que el worker lo
  ve con el feature activo) y se persiste en `TrailStopCanary` — cambiar
  `CanaryPercentage` en caliente nunca le mueve el piso a un trade ya en
  curso, solo afecta a los trades nuevos que se abran después.
- **Grupo control (`TrailStopCanary==false`)**: cero cambios de
  comportamiento — ni siquiera se calcula `favBp`. Es exactamente el
  sistema de hoy.
- No se creó ninguna lista de símbolos ni lógica ad-hoc — es
  puramente estadístico sobre el flujo real de trades nuevos.

## 4. Telemetría — solo eventos relevantes, nunca por tick

Se loggea (structured logging, `ILogger`) y se persiste en
`TrailAuditJson` **únicamente cuando el nivel cambia** (cruce de
+100/+150/+200bp), nunca en cada uno de los ticks de 1 segundo:

```
📈 Trail-1 CANARY nivel {Lvl} {Symbol} {Id} side={Side}: entry={Entry}
   current={Current} favBp={Bp} SL {Old} -> {New} changed={Changed}
```

Cada evento en `TrailAuditJson` (JSON array, máx. 3 entradas):
`{level, ts, favBp, oldSl, newSl, changed}`. Con el `trade.Id`, `Symbol`,
`Side`, `EntryPrice` ya presentes en la fila, esto permite reconstruir
completamente cada movimiento de stop de cada trade canary sin consultar
nada más.

## 5. Seguridad — invariantes verificadas

| Invariante | Cómo se garantiza |
|---|---|
| SL solo se mueve a favor | `TrailingStopCalculator.Compute` compara `candidateSl` contra el SL actual antes de aplicar — verificado por el test `ExistingStopAlreadyBetter_NeverWorsened` |
| Nunca reduce protección | Mismo mecanismo — un candidato peor nunca reemplaza al SL vigente |
| Nunca cancela TP | El bloque de Trail-1 solo toca `trade.SlPrice`/`trade.TrailLevelApplied`, nunca `trade.TpPrice` |
| No duplica modificación | `TrailLevelApplied` monotónico — un nivel ya aplicado no se re-evalúa (`lvl <= currentLevel` corta el loop) |
| Idempotencia | Test `MultipleTicksAfterSameThreshold_Idempotent` |
| Recuperación tras restart | Estado 100% en DB (`TrailLevelApplied`, `TrailStopCanary`), nada en memoria del proceso — test `ProcessRestart_StateReconstructedFromPersistedLevel_NoRegression` |
| Si falla la actualización, el SL original permanece | El bloque de Trail-1 vive DENTRO del mismo `try` por-trade que ya existía; si lanza una excepción, el `catch` general la loggea y el ciclo continúa SIN llamar a `tradeRepo.UpdateAsync`/`uow.CompleteAsync` — nada se persiste ese ciclo, el trade se re-lee limpio (con su SL previo) en el siguiente tick |
| Trail-1 nunca cierra una posición por sí mismo | El bloque de Trail-1 solo escribe `SlPrice`; el cierre real ocurre después, en el chequeo de TP/SL existente, comparando contra el `SlPrice` ya actualizado — es indirecto, nunca hay un `trade.Status = Closed` dentro del bloque de Trail-1 |

## 6. Control vs Canary — sin trades duplicados

- **Control** (`TrailStopCanary==false`): se gestiona exactamente igual
  que hoy. Su resultado real (`RealizedPnl`, `ExitReason`, duración) YA
  ES el dato que necesitamos — no requiere ningún cálculo adicional.
- **Canary** (`TrailStopCanary==true`): el `SlPrice` en vivo se modifica,
  así que para saber "qué hubiera pasado sin Trail-1" se necesita el
  contrafactual — **por eso se persiste `OriginalSlPrice`** al momento de
  la asignación. El contrafactual se calcula post-hoc reproduciendo el
  camino de precio real (mismo método que R36-R39: barrido de OHLC entre
  apertura y cierre contra `OriginalSlPrice`/`TpPrice`), no requiere abrir
  ninguna posición extra.
- Comparación final: `RealizedPnl` real (canary) vs PnL contrafactual
  (canary con `OriginalSlPrice`) — la métrica de delta ya la calcula el
  mismo código de R36-R39, solo hay que apuntarlo a los trades canary
  reales en vez de al histórico.

## 7. Criterio de éxito — no "un trade ganó"

Métricas a recolectar (no un veredicto binario por trade):

| Métrica | Qué mide |
|---|---|
| Posiciones canary gestionadas | Tamaño de muestra real |
| Activaciones +100 / +150 / +200bp | Frecuencia de cada nivel |
| SL originales que Trail-1 habría evitado | Cuántos trades canary NO habrían llegado a `sl_hit` original si no se hubiera movido el stop (contrafactual) |
| PnL real (canary) vs PnL contrafactual (mismo grupo, sin Trail-1) | El delta real, no contra el grupo control (que son trades DISTINTOS) |
| Errores de ejecución | Excepciones capturadas en el bloque de Trail-1 (por logging) |
| Stops modificados correctamente | `Changed==true` en `TrailAuditJson` vs total de cruces de nivel |
| Incidentes | Cualquier caso donde `SlPrice` empeore, TP se pierda, o el trade se cierre sin pasar por el chequeo estándar |

**Comparar canary-real vs canary-contrafactual (mismos trades, dos
resultados) es la comparación correcta** — comparar canary vs control
(trades distintos, símbolos/momentos distintos) mezclaría el efecto de
Trail-1 con la variabilidad normal entre trades, exactamente el error que
un A/B mal diseñado cometería.

## 8. Duración — basada en cantidad de trades, no en tiempo

En R37, sobre 746 trades OOS, el **73% (544) fueron "salvados"** por
Trail-1 (mejoraron respecto del baseline) — una proporción muy alta, no
un efecto sutil. Para una señal así de consistente, un test de signo
simple (¿el contrafactual mejora en más del 50% de los casos?) alcanza
significancia estadística con una muestra bastante más chica que un test
de diferencia de medias:

- **Mínimo para señal inicial útil: ~100 trades canary.** Con una tasa de
  mejora real cercana al 70%, 100 observaciones ya distinguen esa
  proporción de un 50% al azar con confianza alta (test de signo,
  p<0.01).
- **Recomendado antes de escalar más allá del canary: ~300 trades
  canary.** Da un intervalo de confianza razonablemente ajustado sobre el
  PnL delta en dólares, no solo sobre la dirección del efecto.
- Con `CanaryPercentage` en, por ejemplo, 10-15% del flujo actual de
  trades nuevos (el ritmo histórico del sistema ronda cientos de trades
  por mes, ver R35-R37), **100 trades canary son alcanzables en días,
  no en una ventana de tiempo fija arbitraria** — por eso el criterio de
  parada/checkpoint debe ser el conteo de trades, no un reloj.

## 9. No se tocó la entrada

Confirmado por revisión del diff: los únicos archivos modificados son
`SimulatedTrade.cs` (agregar columnas), `TrailingStopCalculator.cs` (ya
existía de R38, sin cambios), `SimulationMarkPriceWorker.cs` (gestión de
posiciones abiertas) y `appsettings.json` (configuración). **Ninguno
toca** `agent/risk_manager.py`, `SimulatedTradeAppService.OpenTradeAsync`,
ni ningún componente de señales/scoring/ranking/filtros/tamaño inicial.
La asignación de canary ocurre en el **worker de monitoreo**, en el
primer tick DESPUÉS de que el trade ya fue abierto por el flujo existente
— nunca decide si un trade se abre ni con qué tamaño.

---

## 10. Resultado — READY TO ENABLE CANARY

**Qué falta**: nada de código. Falta que decidas **cuándo** aplicar la
migración y **con qué porcentaje** arrancar.

**Cómo se habilita** (cuando decidas avanzar, dos pasos separados,
ninguno ejecutado todavía):
1. `dotnet ef database update --project src/Verge.EntityFrameworkCore --startup-project src/Verge.DbMigrator` (aplica la migración — recién ahí las columnas nuevas existen en la base real).
2. En `appsettings.json` (o `appsettings.Production.json` si existe un override), cambiar:
   ```json
   "TrailStop": { "Enabled": true, "CanaryPercentage": 10 }
   ```
   y reiniciar `Verge.HttpApi.Host` (los cambios de config solo se leen al arrancar, salvo que el hosting use `reloadOnChange` — confirmar antes).

**Cómo se deshabilita inmediatamente**: volver `Enabled` a `false` (o
`CanaryPercentage` a `0`) y reiniciar — **no requiere revertir la
migración** (las columnas nuevas quedan ahí, inertes, sin afectar nada
mientras el flag esté apagado). Los trades ya asignados a canary que
sigan abiertos dejarían de recibir actualizaciones de Trail-1 en el acto
(su SL queda fijo donde estaba, se gestiona por TP/SL estándar de ahí en
más) — no hay ningún estado que quede "a medio camino" de forma insegura.

**Qué métricas observar**: las 7 de la sección 7 — el foco inicial más
importante es "SL originales que Trail-1 habría evitado" y "PnL real vs
contrafactual", los mismos dos números que sostienen todo el caso desde
R36.

**Cómo determinamos si Trail-1 realmente agrega PnL**: comparando, sobre
los mismos trades canary, su `RealizedPnl` real contra el PnL
contrafactual calculado con `OriginalSlPrice` — exactamente la misma
metodología usada en R36-R39, ahora sobre datos en vivo en vez de
históricos.

**No se desplegó nada. No se activó nada. La decisión de encender el
canary, y con qué porcentaje, es tuya.**
