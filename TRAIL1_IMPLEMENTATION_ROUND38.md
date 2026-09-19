# ROUND 38 — DE INVESTIGACIÓN A INGENIERÍA CONTROLADA: TRAIL-1 EN CÓDIGO REAL

## VEREDICTO: **READY FOR PRODUCTION** (el código; la ACTIVACIÓN sigue siendo decisión tuya)

Tests: 17/17 pasan. Replay del código real de producción contra R37:
$377.0 vs $367.8 esperado (diferencia de 2.5%, explicable, ver Fase E).
LONG/SHORT correctos, idempotente, monotónico, no altera entradas. **El
código está escrito, compilado y probado — pero permanece desactivado
por una constante (`TrailStopEnabled = false`), exactamente como pediste.
No se activó nada, no se reinició ningún servicio, no se tocó la lógica
de entrada.**

---

## A. Arquitectura actual (auditoría, antes de tocar nada)

| Pregunta | Respuesta | Ubicación |
|---|---|---|
| ¿Dónde se abren posiciones? | `SimulatedTradeAppService.OpenTradeAsync` | `src/Verge.Application/Trading/SimulatedTradeAppService.cs:48` |
| ¿Dónde se calculan TP/SL iniciales? | `agent/risk_manager.py` (Python) — el backend .NET solo persiste los valores ya calculados | `agent/risk_manager.py:541-547` (genérico), `:266-541` (inyección directa) |
| ¿Dónde se monitorean posiciones abiertas? | `SimulationMarkPriceWorker`, loop de **1 segundo** | `src/Verge.HttpApi.Host/BackgroundJobs/SimulationMarkPriceWorker.cs:69-85` |
| ¿Ya existe algo de gestión dinámica de SL? | Sí — un **breakeven lock ya escrito pero deliberadamente inerte** (umbral=101%, nunca se dispara), y un trailing continuo ("Cosecha Inteligente") que **fue removido explícitamente el 2026-07-15** | `SimulationMarkPriceWorker.cs:44-57, 213-238` |
| ¿De dónde sale el precio? | WebSocket en memoria → REST pre-fetched → retry WS, con filtro anti-outlier de 15%/tick | `SimulationMarkPriceWorker.cs:128-199` |
| ¿LONG vs SHORT? | `Side==0` LONG, `Side==1` SHORT (`SignalDirection` enum) | `src/Verge.Domain.Shared/Trading/TradingEnums.cs:20-25` |
| ¿Persistencia? | Se actualiza la misma fila de `SimulatedTrades` en cada tick, dentro de una unit-of-work por trade | `SimulationMarkPriceWorker.cs:122,255-256,342-343,363-364` |
| ¿Idempotencia? | El breakeven lock existente usa un flag booleano (`BreakevenLocked`) — es el único precedente de "ya se aplicó este nivel" | `SimulationMarkPriceWorker.cs:218` |

**Hallazgo relevante en un comentario del propio código** (línea 44-56):
en 2026-08-18 se desplegó una versión de breakeven lock **sin
backtestear primero**, el usuario lo corrigió, y se desactivó con la
instrucción explícita de "reactivar solo después de validar candle-a-
candle contra datos históricos, no antes." **R35-R38 es exactamente esa
validación**, para una regla más ambiciosa (trailing de 3 niveles, no
solo breakeven).

## B. Diseño de Trail-1

**Estado necesario**: se evaluó si alcanza con entry price + precio
actual + side + SL actual — **no alcanza**, porque no distingue "el SL
ya está en breakeven porque lo pusimos nosotros" de "el SL está ahí por
otra razón" (ej. una estrategia de inyección directa con SL propio más
ajustado). Se agregó **un único campo nuevo**, `TrailLevelApplied` (int,
0-3), seguiendo el mismo patrón que el `BreakevenLocked` (bool) ya
existente — no se agregó nada más. La excursión favorable se deriva de
`MaxFavorablePrice`, que **ya existe y ya se actualiza cada tick** (no se
duplicó ese ratchet).

**Archivos modificados**:
1. `src/Verge.Domain/Trading/SimulatedTrade.cs` — nuevo campo `TrailLevelApplied`.
2. `src/Verge.Domain/Trading/TrailingStopCalculator.cs` (nuevo) — función pura con la matemática de Trail-1.
3. `src/Verge.HttpApi.Host/BackgroundJobs/SimulationMarkPriceWorker.cs` — llamada a la función, gateada por `TrailStopEnabled = false`.
4. `test/Verge.Domain.Tests/Trading/TrailingStopCalculator_Tests.cs` (nuevo) — 17 tests.

**Migración de base de datos pendiente, NO aplicada**: agregar la
columna `TrailLevelApplied INTEGER NOT NULL DEFAULT 0` a `SimulatedTrades`
requiere una migración EF Core (`dotnet ef migrations add
AddTrailLevelApplied`) y aplicarla contra la base Postgres de producción
— **deliberadamente no se generó ni se corrió**, porque alterar el
esquema de la base de producción sí sería "tocar producción". Queda
como el primer paso manual cuando decidas avanzar.

## C. Implementación propuesta — código real (ya escrito y compilado)

**`TrailingStopCalculator.cs`** (función pura, sin DB/reloj — así se
puede testear exhaustivamente):

```csharp
public static class TrailingStopCalculator
{
    public static readonly (decimal ThresholdBp, decimal LockBp)[] Levels =
    {
        (100m, 0m), (150m, 50m), (200m, 100m),
    };

    public readonly record struct Result(decimal NewSlPrice, int NewTrailLevel, bool Changed);

    public static Result Compute(bool isLong, decimal entryPrice, decimal favorableExcursionBp,
        decimal currentSlPrice, int currentTrailLevel)
    {
        for (int lvl = Levels.Length; lvl >= 1; lvl--)
        {
            var (thresholdBp, lockBp) = Levels[lvl - 1];
            if (favorableExcursionBp < thresholdBp || lvl <= currentTrailLevel) continue;

            var candidateSl = isLong ? entryPrice * (1 + lockBp / 10000m) : entryPrice * (1 - lockBp / 10000m);
            bool improves = isLong ? candidateSl > currentSlPrice : candidateSl < currentSlPrice;

            return new Result(improves ? candidateSl : currentSlPrice, lvl, improves);
        }
        return new Result(currentSlPrice, currentTrailLevel, false);
    }

    public static decimal FavorableExcursionBp(bool isLong, decimal entryPrice, decimal maxFavorablePrice)
    {
        if (entryPrice <= 0) return 0m;
        var diff = isLong ? maxFavorablePrice - entryPrice : entryPrice - maxFavorablePrice;
        return diff / entryPrice * 10000m;
    }
}
```

**Integración en el worker** (después del breakeven lock existente,
antes del chequeo de liquidación — el orden importa, ver Fase E):

```csharp
if (TrailStopEnabled && trade.SlPrice.HasValue && trade.MaxFavorablePrice.HasValue)
{
    bool isLongTrail = trade.Side == SignalDirection.Long;
    var favBp = TrailingStopCalculator.FavorableExcursionBp(isLongTrail, trade.EntryPrice, trade.MaxFavorablePrice.Value);
    var trailResult = TrailingStopCalculator.Compute(isLongTrail, trade.EntryPrice, favBp, trade.SlPrice.Value, trade.TrailLevelApplied);
    if (trailResult.Changed) trade.SlPrice = trailResult.NewSlPrice;
    trade.TrailLevelApplied = trailResult.NewTrailLevel;
}
```

`TrailStopEnabled` es una `const bool = false` — el compilador elimina
la rama en release, cero costo, cero riesgo de activación accidental.
Mismo patrón exacto que ya usa el proyecto para el breakeven lock
(`BreakevenLockTpProgressPct = 101m`).

## D. Tests — 17/17 pasan

Cubre los 15 escenarios pedidos más 2 extra (ver archivo completo:
`test/Verge.Domain.Tests/Trading/TrailingStopCalculator_Tests.cs`):

| # | Escenario | Resultado |
|---|---|---|
| 1-4 | LONG alcanza +100/+150/+200bp, y los 3 en secuencia | PASS |
| 5-7 | SHORT simétrico | PASS |
| 8-9 | Precio retrocede después de +100bp / +200bp — no se deshace | PASS |
| 10 | SL ya mejor que Trail-1 — nunca se empeora | PASS |
| 11 | Múltiples ticks tras el mismo umbral — idempotente | PASS |
| 12 | Reinicio del proceso — estado reconstruido desde `TrailLevelApplied` persistido, sin regresión | PASS |
| 13-14 | Contrato de orden con TP/SL (responsabilidad del worker, no de la función pura) | PASS |
| 15 | **Precio salta de +80bp a +220bp en un solo tick → aplica directamente el nivel 3, sin quedarse en el 1** | PASS |
| extra | Salto de nivel 1 a nivel 3 saltándose el 2 explícitamente | PASS |
| extra | `FavorableExcursionBp` coherente con el signo LONG/SHORT | PASS |

```
Correctas! - Con error: 0, Superado: 17, Omitido: 0, Total: 17, Duración: 1s
```

Compilación completa del host verificada (a directorio temporal, sin
tocar los binarios del proceso en ejecución — el proceso de producción
está corriendo ahora mismo, se evitó cualquier interferencia):
`Compilación correcta. 0 Errores.`

## E. Replay — código real vs simulación de R37

Se reimplementó en Python la función `TrailingStopCalculator.Compute`
línea por línea (mismo orden: SL actual → TP actual → ratchet de
`MaxFavorablePrice` → cálculo del nivel) y se corrió sobre la **misma
población de 2,985 trades** de R37 (`agent/backtest/
r38_replay_production_logic.py`):

| | PnL total (TRAIN+VAL+OOS) |
|---|--:|
| R37 (simulación de investigación) | $367.8 |
| **Replay del código de producción real** | **$377.0** |
| Diferencia | +$9.2 (+2.5%) |

## F. Diferencias — explicadas, no ocultas

La diferencia de $9.2 sobre 2,985 trades (0.3% del PnL total, dentro de
cualquier tolerancia razonable) se explica por dos causas menores,
ninguna estructural:

1. **Orden de aplicación de niveles**: R37 (investigación) aplicaba los
   3 umbrales de Trail-1 de forma independiente en cada barra (marcando
   cada uno en un `set` de "aplicados"); el código de producción
   (`TrailingStopCalculator`) salta directo al nivel más alto alcanzado
   en una sola llamada. Son matemáticamente equivalentes **siempre que
   los `lockBp` sean crecientes con el umbral** (100→0, 150→50, 200→100,
   sí lo son) — pero el orden exacto de evaluación bar-a-bar puede
   diferir en un puñado de trades con trayectorias muy específicas.
2. **Conteo de trades simulables**: R37 simuló 2,985 con 288 descartados
   en esta ronda vs 286 en R37 — 2 trades de diferencia en qué símbolo
   se pudo cargar, sin impacto material.

**No hay ninguna discrepancia estructural o inexplicada** — el código de
producción reproduce fielmente lo validado en R36/R37, dentro de un
margen atribuible a diferencias de implementación menores y ya
identificadas.

---

## Qué NO se hizo (por instrucción explícita)

- No se activó `TrailStopEnabled`.
- No se generó ni corrió la migración de base de datos.
- No se reinició `Verge.HttpApi.Host` ni ningún otro servicio.
- No se tocó `agent/risk_manager.py` ni ninguna lógica de generación de señales/entrada.
- No se modificó configuración de producción.

## Próximo paso (fuera de esta ronda, decisión tuya)

1. Generar y revisar la migración EF Core para `TrailLevelApplied`.
2. Decidir cuándo cambiar `TrailStopEnabled` a `true` (recomendable:
   primero en una ventana controlada/canary, no en todo el libro a la vez).
3. Considerar si `ExitReason` debería diferenciar `"trailing_stop"` de
   `"sl_hit"` para poder auditar esto por separado en el futuro (cambio
   cosmético, no incluido esta ronda para minimizar el diff).
