# ROUND 44 — Forensic reverse engineering de "Nexus"

## Veredicto en una línea

**FAILED — en el Paso 1 (integridad de datos), antes de llegar a reconstruir ningún contexto de mercado.** "Nexus" no es una estrategia con historial real ejecutándose: sus 264 trades son un **registro sintético reconstruido** el 2026-09-06 a partir de `agent/data/trades.csv`, ya marcado en el propio proyecto como **"PnL NO confiable"** — no hay lógica de entrada real que extraer porque los datos de entrada mismos no reflejan decisiones reales tomadas por ningún motor de trading.

Esto no es un "primer pase" ni una hipótesis descartada por falta de tiempo: es una conclusión definitiva respaldada por 5 piezas de evidencia independientes y verificables, cualquiera de las cuales por sí sola ya sería descalificante.

---

## 1. Limpieza de datos (hecho, tal como se pidió)

| | Total Nexus | Limpio (excl. ONUSDT/BBUSDT) |
|---|---|---|
| Trades cerrados | 264 | 260 |
| PnL bruto | **+$363,260.61** | — |
| PnL limpio | — | **+$3,549.46** |
| Rango temporal | 2026-05-16 06:35 UTC → 2026-09-04 16:42 UTC | igual |

El PnL bruto está inflado 100x por la corrupción de precio ya documentada en R37/R43 en `ONUSDT` (3 trades por sí solos suman +$359,702 sobre esos 264). **A partir de acá, todo el análisis usa exclusivamente la población limpia de 260 trades** — el mandato explícito de esta ronda de nunca reusar el agregado contaminado.

Éste hallazgo de limpieza, sin embargo, resultó ser la parte menos importante del problema.

## 2-4. Por qué NO se reconstruyó el contexto de mercado (evidencia, no elección)

Al intentar reconstruir el contexto de entrada (Paso 2 del brief) para el primer trade limpio, aparecieron cinco anomalías, cada una verificada directamente contra la base:

### Evidencia A — El perfil "Nexus" nació DESPUÉS de todos sus propios trades

```
StrategyProfile "Nexus".CreationTime = 2026-09-06 01:53:16 UTC
Primer trade de "Nexus"            = 2026-05-16 06:35:14 UTC   (¡114 días antes!)
Último trade de "Nexus"            = 2026-09-04 16:42:00 UTC   (2 días antes)
```

Es lógicamente imposible que un perfil real haya generado trades 114 días antes de existir. Este solo hecho ya prueba que la relación `StrategyProfileId` fue asignada retroactivamente por un script, no por el motor de trading en el momento de cada entrada.

### Evidencia B — Cada trade está marcado explícitamente como reconstruido

```sql
SimulatedTrades.ExtraProperties = {"reconstructed":"trades.csv 2026-09-05"}
```

en el **100% de los 264 trades** de Nexus (verificado, no una muestra). Esto no es una inferencia — es una etiqueta que el propio sistema (o quien restauró la base) dejó puesta.

### Evidencia C — Confirmado por la memoria del proyecto (incidente ya documentado antes de esta ronda)

El `PROGRESS_LOG.md` del repo ya registra el incidente exacto: un reset de Docker Desktop borró `SimulatedTrades`+`StrategyProfiles` sin backup (~2026-09-05/06); la base se reconstruyó recreando el esquema y reinsertando **3,682 filas desde `agent/data/trades.csv`, con el propio proyecto etiquetando el resultado "PnL NO confiable"**, y citando textualmente: *"el log legacy reconstruye Nexus a +$228k"* — el mismo tipo de cifra absurda que volvimos a ver acá ($363k brutos). Esto no es un hallazgo nuevo de esta ronda: ya estaba en la memoria (`verge_backtest_gate.md`) y en el log, simplemente R43 no lo cruzó antes de reportar el agregado de "Nexus" como interesante.

### Evidencia D — Cero contexto de decisión disponible

```
AgentDecisionJson vacío/NULL en 264/264 trades de Nexus (100%)
Ma7DistancePctAtEntry, MaxAdversePrice, MaxFavorablePrice, ExitAuditJson: NULL en el 100%
TradingSignalId: NULL en el 100%
```

No hay ningún campo que registre qué vio el motor al momento de entrar. No hay nada que "reconstruir" en el sentido pedido por el Paso 2 — la fila no contiene ni el eco de una decisión real.

### Evidencia E — Estadísticas imposibles para una estrategia real en producción

- **260/260 trades cerraron por `tp_hit`. Cero por `sl_hit`, cero por timeout, cero por cualquier otra razón.** Con `SlMultiplier=1.0` / `TpMultiplier=3.0` / `MinRR=3.0` configurados en el perfil, una estrategia real con 260 entradas a lo largo de 3.5 meses de mercado real tendría, casi con certeza matemática, al menos algunos stops golpeados. Un 100% de winners es la firma clásica de un log que solo registró operaciones "cerradas con éxito" (o al que se le asignó `tp_hit` por default al reconstruir), no de trading real.
- **Trades duplicados casi idénticos, abiertos con segundos de diferencia**, ej. `ARXUSDT` @ 0.1616: 4 aperturas en 2026-07-22 a las 05:22:33 / :38 / :42 / :47 (mismo precio exacto, mismo símbolo, cierres 6 minutos después cada una) — algo que ningún motor real de ejecución produce (y que además violaría el propio `MaxOpenPositions=3` del perfil, que permitiría como máximo 3 posiciones simultáneas, no 4 en el mismo símbolo). Encontrados 15 grupos de duplicados de este tipo sobre 260 trades.

## 5. ¿Se puede extraer una estrategia independiente de Nexus?

**No.** No es que la lógica de Nexus dependa de datos no disponibles en producción (lo cual habría sido un "marcar el problema" y seguir buscando) — es que **no existe ninguna lógica de entrada que reconstruir**: las filas fueron generadas por un script de recuperación de desastre después de perder la base real, no por un motor de decisión. Cualquier "patrón" que apareciera al cruzar contexto de mercado contra estos 260 trades sería, por construcción, un patrón del script de reconstrucción (o del archivo `trades.csv` legacy, de fecha y proveniencia ya desconocidas) — no un patrón de mercado. Extraer una regla de "por qué gana Nexus" sería formalizar un artefacto de recuperación de base de datos como si fuera una estrategia de trading, exactamente el tipo de resultado que las reglas de esta ronda prohíben ("no inventes parámetros para salvarla").

## 6-7. Portfolio engine / TRAIN-VAL-OOS

No se ejecutó. No hay ninguna regla de entrada, SL, TP, sizing o timing genuina que convertir en código — el paso previo (Parte 5) ya cierra la investigación antes de llegar a este punto. Ejecutar el portfolio engine sobre datos reconocidos como no confiables habría producido un número, pero no evidencia de nada real.

## 8. Criterio absoluto — respuesta

**FAILED.** No hay una estrategia ejecutable dentro de "Nexus" para extraer, porque "Nexus" no es una estrategia con historial real: es una tabla de trades sintéticos etiquetados por el propio sistema como reconstrucción no confiable tras la pérdida de la base original. No se inventó ningún parámetro para salvarla.

## 9. Trail-1

No participó en este análisis (no aplica: no hay estrategia base que combinar con Trail-1). Sigue OFF (global y por perfil), sin cambios respecto a R43.

## 10. Respuestas directas (formato pedido)

1. **¿Qué hace Nexus realmente?** No hace nada — sus 264 filas en `SimulatedTrades` son una reconstrucción post-incidente desde un CSV legacy, no la salida de un motor de trading operando.
2. **¿Por qué gana?** No "gana" en ningún sentido operativo: 100% de sus registros están marcados `tp_hit`, un patrón estadísticamente imposible para una estrategia real con SL configurado, y coincide exactamente con la advertencia ya registrada en la memoria del proyecto sobre el PnL "no confiable" de esta reconstrucción.
3. **¿Podemos convertirlo en una estrategia independiente?** No.
4. **¿Cuál es la regla exacta?** No existe — no hay lógica de entrada que reconstruir, solo una etiqueta `{"reconstructed":"trades.csv 2026-09-05"}` en el 100% de las filas.
5. **¿Cuántos trades genera?** 260 limpios (264 totales, excluyendo ONUSDT/BBUSDT) — pero ninguno es una decisión de trading real verificable.
6-9. **PnL TRAIN/VAL/OOS/mensual:** N/A — no se construyó ninguna estrategia para medir.
10. **¿Sobrevive fees/slippage/funding?** N/A.
11. **PASS o FAILED:** **FAILED.**

## Hallazgo adicional, más grave que Nexus en sí: la reconstrucción cubre CASI TODA la tabla, no solo Nexus

Al verificar cuántos trades cerrados en `SimulatedTrades` tienen la misma
etiqueta `{"reconstructed": ...}`, el resultado es que **el problema no es
de Nexus — es de la tabla entera**:

| Perfil | Trades reconstruidos | Trades genuinamente en vivo |
|---|---|---|
| Nexus | 264 | 0 |
| Los otros 18 perfiles con trades cerrados | 178 | 0 |
| **MA Slope Caso 3** | 0 | **2** (hoy, 2026-09-13) |
| **FVG - 15m** | 0 | **1** (hoy, 2026-09-13) |
| **Band Touch 15m** | 0 | **1** (hoy, 2026-09-13) |
| **Total** | **442** | **4** |

**De los ~446 trades cerrados que existen hoy en la base, 442 (99.1%)
llevan la etiqueta `reconstructed: trades.csv 2026-09-05` — no son solo
los 264 de Nexus.** Solo 4 trades en TODO el sistema son genuinamente
posteriores al incidente de reset de Docker y por lo tanto tienen
posibilidad de reflejar decisiones reales del motor actual.

Esto reencuadra el objetivo mismo de R43/R44. El brief de R43 hablaba de
"minar las 3.364 operaciones reales actuales" asumiendo que esa población
era real — **no lo es en su enorme mayoría**. No es que Nexus concentre el
70% del PnL real: es que el 99% de la tabla completa es el mismo import
legacy con PnL ya declarado no confiable desde antes de esta ronda (ver
Evidencia C). El número "3.364" no describe operativa real, describe el
tamaño del archivo `trades.csv` que se reinyectó el 2026-09-06.

**Esto no invalida el trabajo de Trail-1 (R35-R42)**: esa investigación no
confió en los campos calculados de la tabla (`MaxAdversePrice`,
`MaxFavorablePrice`, etc. — también NULL ahí) sino que reconstruyó
MAE/MFE desde klines históricas reales usando solo el precio/hora de
entrada y salida de cada trade como ancla — un enfoque más robusto que
sobrevive aunque el `RealizedPnl` almacenado no sea confiable. La mina de
**entrada** que pedía R43/R44, en cambio, si se hace sobre estos mismos
442 trades, corre el riesgo de estar minando el comportamiento de un
script de recuperación de desastre, no de un mercado real — el mismo
problema que mató a Nexus específicamente, aplicado a cualquier otro
perfil de la tabla.

## Qué hacer con esto (para la próxima ronda)

- **"Nexus" queda cerrado como fuente de estrategia nueva** — no re-investigar sin que aparezca una fuente de datos distinta (ej. si algún día se recupera el log real del agente de esa ventana, cosa que no está garantizada).
- El PnL "limpio" de $3,549.46 de Nexus **debe excluirse de cualquier futuro agregado de "PnL real del sistema"** — no es real, es legacy reconstruido. Esto invalida también la cifra de R43 ("Nexus concentra ~70% del PnL real limpio") — no es que Nexus sea la mejor fuente, es que domina el conteo de filas del legacy reconstruido, nada más.
- **No hay ningún otro perfil de trades cerrados al que "saltar" en su lugar**: los 18 perfiles restantes con historial cerrado están en la misma situación exacta (mismo `ExtraProperties`, mismo origen `trades.csv 2026-09-05`). No es un problema específico de Nexus, es un problema de la tabla completa pre-2026-09-06.
- **La única población genuinamente real hoy son 4 trades** (2 de "MA Slope Caso 3", 1 de "FVG - 15m", 1 de "Band Touch 15m", todos del 2026-09-13). Insuficiente para cualquier minería forense (no alcanza ni para un TRAIN razonable, mucho menos para TRAIN/VAL/OOS).
- **Conclusión operativa: antes de poder cumplir el objetivo de fondo ("encontrar una estrategia nueva minando trades reales"), el sistema necesita acumular volumen de trades genuinamente en vivo post-incidente.** Eso no es un problema de análisis, es un problema de tiempo/calendario — no hay atajo de research que lo resuelva. Recomendado: dejar correr el sistema en vivo un período razonable (semanas, no días) antes de la próxima ronda de minería de estrategia nueva, y en el ínterin (si se quiere seguir usando este tiempo) enfocar el research en algo que SÍ tenga datos históricos genuinos y suficientes — por ejemplo continuar la línea OI/H11 ya documentada en `verge_alpha_research_phase.md`, que no depende de `SimulatedTrades`.
