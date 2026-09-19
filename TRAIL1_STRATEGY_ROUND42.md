# ROUND 42 — LAS 2 MIGRACIONES "PENDIENTES" (corrección) + TRAIL-1 COMO CONFIGURACIÓN NORMAL DE PERFIL

## Parte 1 — Corrección: esas 2 migraciones NO estaban pendientes

En R41 afirmé que `AddStrategyProfileBroadcastToBinance` y
`AddSimulatedTradeExclusionTag` quedaban pendientes junto con la mía.
**Era un error de interpretación mío**, ahora corregido con evidencia
directa: `dotnet ef migrations script --idempotent` (sin acotar rango)
imprime el **historial completo** con guardas idempotentes, no solo lo
que falta aplicar — al hacer `tail` del output, esas dos aparecían justo
antes de la mía porque son cronológicamente las últimas dos antes de
Trail-1, no porque estuvieran sin aplicar.

**Verificado por consulta directa a `__EFMigrationsHistory`**: las 37
migraciones del proyecto, salvo la mía, ya están registradas y aplicadas
en la base de producción. Confirmado además que sus columnas
(`BroadcastToBinance`, `ExclusionTag`) existen físicamente en la tabla.
**No había ningún drift ahí** — el único drift real que existe es
`BreakevenLocked` (documentado en R40/R41: una columna que existe en la
base pero nunca tuvo una migración propia en este repo).

### Qué corrige cada una y si son necesarias/seguras

| Migración | Qué agrega | Para qué se usa en el código | ¿Necesaria? | ¿Segura? |
|---|---|---|---|---|
| `AddStrategyProfileBroadcastToBinance` (2026-07-20) | `StrategyProfiles.BroadcastToBinance` (bool, default false); además quita el DEFAULT a nivel de columna de `StrategyType` (queda solo con default en el modelo C#, no en la DB) | `StrategyProfileAppService.cs:114,150` — controla si una estrategia también espeja sus entradas/salidas contra Binance real (Testnet/Mainnet), reemplazando un hardcodeo previo por nombre de estrategia | **Sí** — el código ya la referencia activamente; sin ella, cualquier query sobre `StrategyProfiles` fallaría | Sí — aditiva, default seguro, ya aplicada y corriendo sin incidentes desde julio |
| `AddSimulatedTradeExclusionTag` (2026-07-25) | `SimulatedTrades.ExclusionTag` (text, nullable) | `SimulatedTradeAppService.cs:617-621` — permite excluir un trade puntual de las estadísticas agregadas (win rate, PnL total) sin borrarlo, para casos de "sabotaje"/anomalía de datos conocida | **Sí** — mismo motivo, ya referenciada activamente | Sí — aditiva, nullable, ya aplicada desde julio |

**Ambas ya están aplicadas, funcionando, y no requieren ninguna acción.**
No hay nada que decidir sobre ellas — la corrección de R41 era necesaria
para no generar preocupación sobre algo que ya está resuelto desde hace
casi 2 meses.

---

## Parte 2 — Trail-1 como configuración real, con el flujo normal de Verge

**Se reemplazó el mecanismo de canary por hash de R40** (`TrailStop:
CanaryPercentage` en `appsettings.json`, un porcentaje ciego aplicado a
trades al azar) **por un flag por `StrategyProfile`** — exactamente el
mismo patrón que ya usa `BroadcastToBinance`: editable desde la misma
API/UI de perfiles, sin tocar configuración de infraestructura para
activar o desactivar.

### Cómo funciona ahora

- **`StrategyProfile.UseTrailStop`** (bool, default `false`) — nuevo
  campo, mismo lugar y mismo patrón que `BroadcastToBinance`
  (`src/Verge.Domain/Trading/StrategyProfile.cs`).
- Expuesto en `StrategyProfileDto` / `CreateUpdateStrategyProfileDto`
  y mapeado en `StrategyProfileAppService.ApplyInput`/`MapToDto` —
  **se crea/edita con el mismo endpoint `CreateAsync`/`UpdateAsync`
  que cualquier otro parámetro de un perfil**, no hay endpoint nuevo.
- **Toggle agregado al editor de estrategias en Angular**
  (`strategy-editor.component.html/.ts`), con el mismo estilo visual que
  el toggle de "Ejecución contra Binance" — el usuario lo prende/apaga
  desde la pantalla de edición de perfil, como cualquier otro ajuste.
- **`SimulationMarkPriceWorker`** ahora resuelve, **una vez por ciclo
  (no una query por trade)**, qué `StrategyProfileId` tienen
  `UseTrailStop=true`, y aplica Trail-1 solo a los trades cuyo perfil
  esté en ese conjunto. Trades sin `StrategyProfileId` (legacy/manuales)
  nunca lo reciben.
- **`TrailStop:Enabled` en `appsettings.json` sigue existiendo como
  interruptor maestro global** — defensa en profundidad: aunque un
  perfil tenga `UseTrailStop=true`, si el interruptor global está en
  `false`, no pasa nada. Apagar Trail-1 de una para todo el sistema
  sigue siendo un solo cambio, sin tener que revisar perfil por perfil.

### Por qué esto es mejor que el canary por hash de R40

- **Activación intencional, no estadística**: en vez de "el 10% de los
  trades al azar reciben Trail-1", ahora es "esta estrategia específica
  (la que el usuario elija, por ejemplo la de menor riesgo o menor
  volumen) recibe Trail-1, el resto no" — un canary real y controlado,
  no una lotería.
- **Reversible al instante y de forma dirigida**: apagar el toggle de UN
  perfil puntual, sin tocar `appsettings.json` ni reiniciar nada.
- **Auditable de la forma en que ya se audita todo lo demás en Verge**:
  aparece en el historial de cambios de perfiles como cualquier otro
  ajuste, no en una variable de entorno separada.

### Estado de la migración — generada, NO aplicada

`AddUseTrailStopToStrategyProfile` (nueva, además de
`AddTrailStopCanaryFields` de R40/R41, que sigue sin aplicar):

```csharp
protected override void Up(MigrationBuilder migrationBuilder)
{
    migrationBuilder.AddColumn<bool>(
        name: "UseTrailStop",
        table: "StrategyProfiles",
        type: "boolean",
        nullable: false,
        defaultValue: false);
}
```

Un solo `ADD COLUMN`, nullable=false con default seguro — verificado por
SQL directo que la columna **no existe todavía** en producción (no hay
drift, es una migración genuinamente nueva y pendiente, a diferencia de
las dos de la Parte 1).

### Verificación

- Compilación completa del host: **0 errores** (a directorio temporal,
  sin tocar el proceso en ejecución).
- Los 17 tests de `TrailingStopCalculator` siguen pasando sin cambios
  (la función pura no se tocó, solo quién decide llamarla).
- **No verificado visualmente en el navegador**: el toggle nuevo en
  Angular replica exactamente el markup/estilo del toggle de
  `BroadcastToBinance` ya existente y probado, pero no se levantó el
  stack completo (Angular + backend + Postgres) para un chequeo e2e
  visual esta ronda — se recomienda una revisión visual rápida la
  próxima vez que se abra el editor de estrategias en desarrollo, antes
  de considerar esto "verificado en UI" y no solo "verificado por
  código".

### Qué NO se hizo (sigue igual que en rondas anteriores)

- ❌ NO se aplicó ninguna migración (`database update`).
- ❌ NO se cambió `TrailStop:Enabled` (sigue en `false`).
- ❌ NO se activó `UseTrailStop=true` en ningún perfil real.
- ❌ NO se reinició ningún servicio.
- ❌ NO se tocó lógica de entrada, scoring, sizing, ni universo de símbolos.

---

## Cómo se activa, cuando el usuario decida

1. Aplicar las migraciones pendientes: `dotnet ef database update --project src/Verge.EntityFrameworkCore --startup-project src/Verge.DbMigrator` (aplica `AddTrailStopCanaryFields` + `AddUseTrailStopToStrategyProfile`, ambas seguras y aditivas).
2. En `appsettings.json`, `"TrailStop": { "Enabled": true }`.
3. Reiniciar `Verge.HttpApi.Host`.
4. En la UI de Verge, abrir el perfil elegido como canary y activar el
   toggle "Trailing stop (Trail-1)" — sin tocar código ni configuración
   de infraestructura para esto último.

**Para desactivar de inmediato**: apagar el toggle del perfil (afecta
solo a ese perfil, al instante) o volver `TrailStop:Enabled` a `false`
en `appsettings.json` (apaga todo, para cualquier perfil, requiere
reinicio).
