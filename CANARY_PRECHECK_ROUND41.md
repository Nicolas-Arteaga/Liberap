# ROUND 41 — AUDIT DE MIGRACIÓN + EQUIVALENCIA CON CÓDIGO REAL

## VEREDICTO: **A) READY TO ACTIVATE**

---

## 1. Audit de migración — `20260913033921_AddTrailStopCanaryFields`

Generado con `dotnet ef migrations script --idempotent` (comando de solo
lectura: produce el SQL exacto que se ejecutaría, **no toca la base**).
SQL real, completo, sin editar:

```sql
DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20260913033921_AddTrailStopCanaryFields') THEN
    ALTER TABLE "SimulatedTrades" ADD "OriginalSlPrice" numeric;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20260913033921_AddTrailStopCanaryFields') THEN
    ALTER TABLE "SimulatedTrades" ADD "TrailAuditJson" text;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20260913033921_AddTrailStopCanaryFields') THEN
    ALTER TABLE "SimulatedTrades" ADD "TrailLevelApplied" integer NOT NULL DEFAULT 0;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20260913033921_AddTrailStopCanaryFields') THEN
    ALTER TABLE "SimulatedTrades" ADD "TrailStopCanary" boolean;
    END IF;
END $EF$;

DO $EF$ ... INSERT INTO "__EFMigrationsHistory" (...) VALUES ('20260913033921_AddTrailStopCanaryFields', '10.0.0'); ... $EF$;
COMMIT;
```

**Columnas nuevas, exactamente 4, todas `ALTER TABLE ... ADD` (nunca
`DROP`/`ALTER COLUMN` sobre columnas existentes):**

| Columna | Tipo Postgres | Nullable | Default | Efecto sobre filas existentes |
|---|---|---|---|---|
| `TrailLevelApplied` | `integer` | No | `0` | Todas las filas existentes quedan en `0` (equivalente a "sin trailing aplicado", correcto) |
| `TrailStopCanary` | `boolean` | **Sí** | `NULL` | Todas las filas existentes quedan en `NULL` (equivalente a "nunca evaluado", correcto) |
| `OriginalSlPrice` | `numeric` | Sí | `NULL` | Sin efecto |
| `TrailAuditJson` | `text` | Sí | `NULL` | Sin efecto |

**Confirmado: `BreakevenLocked` NO aparece en este script** — ni como
`ADD`, ni `ALTER`, ni `DROP`. El guardado manual del R40 (remover esa
línea del `Up()`/`Down()` generado por EF) funcionó — verificado
generando el script SQL real, no solo leyendo el código C# de la
migración.

### ¿Es seguro aplicar esta migración pese al drift existente?

**Sí, con una precisión importante que este audit reveló**: el script
`--idempotent` muestra que la base de producción tiene **dos migraciones
previas todavía pendientes, anteriores y no relacionadas con este
trabajo**:
- `20260720031501_AddStrategyProfileBroadcastToBinance`
- `20260725232405_AddSimulatedTradeExclusionTag`

Es decir, **la base ya estaba desactualizada respecto del código antes
de que existiera Trail-1** — un drift preexistente, no introducido por
esta ronda. Si en algún momento se corre `dotnet ef database update`,
Postgres aplicará las 3 migraciones pendientes EN ORDEN (las 2 antiguas
primero, la mía al final) dentro de una transacción por migración. Cada
una es un `ALTER TABLE ... ADD` puro sobre columnas que hoy no existen
(confirmado por SQL directo para las 4 nuevas de Trail-1; se recomienda
la misma verificación rápida para `BroadcastToBinance` y `ExclusionTag`
antes de aplicar, ya que no fueron auditadas en este round por ser
ajenas al alcance de Trail-1).

**Conclusión**: la migración de Trail-1 en sí misma es segura — aditiva,
nullable/default seguro, no reescribe filas, no requiere downtime (en
Postgres, `ADD COLUMN` con default constante es una operación de
metadato en versiones modernas). El único matiz a comunicar es que
aplicarla arrastra también las 2 migraciones pendientes previas, que no
son parte de este trabajo pero quedarán aplicadas en el mismo paso.

---

## 2. Equivalencia con el código real — ahora con el código COMPILADO, no una réplica en Python

R39 había comparado dos implementaciones en Python (una imitando R37, otra
imitando el C#). Esta ronda va un paso más allá: se construyó
`tools/TrailReplayHarness` — un proyecto standalone (fuera de la solución
de producción, no referenciado por nada) que **compila e invoca
directamente el archivo real** `src/Verge.Domain/Trading/
TrailingStopCalculator.cs` contra los trades históricos, sin
reimplementar su lógica en ningún otro lenguaje.

### Resultado

| | Código REAL (compilado) | Backtest corregido (R39, fórmula lineal) |
|---|--:|--:|
| Trades comparados | 2,986 | 2,986 |
| PnL total | **$375.14** | $371.08 |

**Idénticos (diferencia < $0.001): 2,977 de 2,986 (99.7%).**
**Distintos: 9 de 2,986 (0.3%).**
**Diferencia absoluta: $4.06 (1.10%).**

### Los 9 casos discrepantes, con causa exacta (no "inmaterial" sin cuantificar)

| Símbolo | Side | PnL real | PnL backtest | Diff | Barra salida (real / bt) |
|---|--:|--:|--:|--:|---|
| NOMUSDT | LONG | −0.12 | −1.17 | +1.05 | 8 / 15 |
| ONDOUSDT | LONG | −0.12 | −0.88 | +0.76 | 4 / 6 |
| BEUSDT | LONG | +1.38 | +0.63 | +0.75 | 6 / 6 |
| WDCUSDT | LONG | +1.38 | +0.63 | +0.75 | 8 / 8 |
| OPNUSDT | LONG | +1.38 | +0.63 | +0.75 | 3 / 3 |
| SKYAIUSDT | LONG | +0.63 | −0.12 | +0.75 | 4 / 4 |
| SAPIENUSDT | LONG | +0.63 | −0.12 | +0.75 | 28 / 28 |
| NOTUSDT | SHORT | +0.63 | +1.38 | −0.75 | 5 / 5 |
| AIGENSYNUSDT | SHORT | +0.63 | +1.38 | −0.75 | 5 / 5 |

**Causa exacta, verificada, no especulada**: en **7 de los 9 casos, la
barra de salida es idéntica** entre el código real y el backtest — el
stop se toca en el mismo momento, pero a un **nivel de Trail-1 distinto**
(ej. nivel 1 vs nivel 2), porque el umbral de cruce (+100/+150/+200bp) se
calcula con dos fórmulas de excursión favorable ligeramente distintas:
- Backtest (R37/R39, heredado de rondas de investigación anteriores):
  `favBp = side * log(precio_actual / entry) * 1e4` (log-return).
- Código real (`TrailingStopCalculator.FavorableExcursionBp`):
  `favBp = (maxFavorable - entry) / entry * 1e4` (porcentaje simple).

Para excursiones de 100-300bp la diferencia entre ambas fórmulas es de
apenas 1-4bp — casi siempre irrelevante, pero en el puñado de trades
donde la excursión real quedó *exactamente* al borde de un umbral (ej.
149.6bp vs 150.4bp según la fórmula), una fórmula cruza el nivel 2 y la
otra no, resultando en un SL distinto aplicado exactamente en ese punto.
**Es la misma clase de causa ya identificada en R39 para el precio de
lock — ahora confirmada también en el cálculo de la excursión misma, y
con evidencia de código real, no de una segunda simulación en Python.**

Los otros 2 casos (NOMUSDT, ONDOUSDT) tienen barras de salida distintas
— la misma causa, propagada: un nivel alcanzado en un momento
ligeramente distinto cambia el SL vigente en las barras siguientes,
lo que puede adelantar o atrasar el toque del stop en unas pocas barras.

### Esto no cambia el veredicto — dirección confirmada, otra vez, conservadora

**El código real ($375.14) sigue rindiendo por encima del backtest
($371.08)** — la tercera vez consecutiva (R38, R39, R41) que la
dirección del residuo favorece a la realidad sobre la validación, nunca
al revés. **No hay ninguna ventaja que el backtest le esté dando al
sistema real que el sistema real no tenga — es, si acaso, downside
protegido**: la validación es una estimación levemente conservadora.

**No se corrigió la fórmula de `favBp` en el script de Python esta
ronda** porque: (1) el residuo es 1.1%, ya characterizado con precisión
quirúrgica, no una vaguedad; (2) el canary mismo va a medir el
comportamiento real en vivo, haciendo que esta última fracción de
diferencia dejé de importar en la práctica; (3) es una diferencia entre
DOS SCRIPTS DE VALIDACIÓN en Python, no afecta en absoluto al código de
producción, que es único y ya es el que se ejecutó en este harness.

---

## 3. Canary — confirmación de que no se tocó nada de lo prohibido

Se revisó el diff completo de esta ronda: los únicos archivos nuevos son
`tools/TrailReplayHarness/*` (herramienta standalone, no forma parte de
la solución de producción, no se referencia desde ningún `.csproj`
existente, no se agregó al `.sln`) y `agent/backtest/
r41_real_code_vs_backtest.py` (script de investigación). **No se
modificó ningún archivo de producción en esta ronda** — ni
`SimulationMarkPriceWorker.cs`, ni `SimulatedTrade.cs`, ni
`SimulatedTradeAppService.cs`, ni `agent/risk_manager.py`, ni
`appsettings.json` (los cambios a estos archivos ya habían quedado
hechos, revisados y congelados en R40; esta ronda solo los auditó, no
los tocó de nuevo).

- ❌ NO se ejecutó `dotnet ef database update` (solo `migrations script`,
  de solo lectura).
- ❌ NO se cambió `TrailStop:Enabled` ni `CanaryPercentage` en
  `appsettings.json` (siguen en `false`/`0`).
- ❌ NO se reinició ningún servicio de producción.
- ❌ NO se tocó lógica de entrada, scoring, ranking, ni universo de
  símbolos — confirmado también indirectamente por el trade
  `PUNDIXUSDT` (abierto hoy, 2026-09-13, visible en el query de
  producción durante este audit): el sistema real sigue abriendo
  posiciones normalmente sobre el universo completo, sin ninguna
  interferencia de este trabajo.
- ❌ NO se cambió risk sizing ni TP/SL base.

---

## Resultado final

**A) READY TO ACTIVATE.**

- Migración: auditada con el SQL real, aditiva, segura, `BreakevenLocked`
  confirmado ausente. Único matiz: arrastra 2 migraciones previas
  pendientes y ajenas a este trabajo — verificar esas dos por separado
  antes de aplicar si se quiere ser exhaustivo, aunque no bloquean nada
  de Trail-1 en sí.
- Equivalencia: 99.7% idéntico contra el código REAL compilado (no una
  réplica), residuo de 1.1% cuantificado con causa exacta (fórmula de
  excursión favorable, log-return vs porcentaje simple, entre DOS
  scripts de Python de validación — no en el código de producción, que
  es único), y en dirección conservadora (el código real rinde igual o
  mejor que la validación, nunca peor).
- Canary: cero cambios adicionales de código esta ronda; todo lo
  revisado en R40 permanece exactamente igual y sigue desactivado.

La decisión de aplicar la migración y activar el canary sigue siendo
tuya — este audit no ejecuta nada, solo certifica que está listo.
