# ROUND 45 — Minería transversal de los ~19 perfiles (todos, sin distinguir Nexus)

## Corrección a R44 (antes de arrancar)

Al construir el dataset de esta ronda encontré que mi conteo de R44
("Nexus: 260/260 tp_hit, cero SL") estaba mal por un bug propio: filtré
por `Status=1`, que en este esquema **no significa "cerrado"** sino
específicamente "cerrado por TP" (0=abierto, 1=tp_hit, 2=sl_hit/timeout).
Nexus en realidad tiene 1,919 trades (260 TP + 1,641 SL + 18 timeout),
**PnL neto real: −$1,536.37** (perdedor, no ganador). El resto de la
evidencia de R44 (perfil creado después de sus propios trades, etiqueta
`reconstructed` en el 99%+ de la tabla, `AgentDecisionJson` vacío) sigue
siendo válida y no depende de ese bug. Queda registrado como limitación
de validación, tal como pediste, sin detener esta ronda por eso.

## Tabla final

| Candidato | Trades | TRAIN | VAL | OOS | OOS neto/mes | Costos | Resultado |
|---|---:|---:|---:|---:|---:|---|---|
| Momentum-Wick LONG | 139 | +$107.0 | +$74.4 | **+$11.0** | ~$8.4 | incluidos (fees/funding reales por trade) | **FAILED** (no sobrevive remove-best-trade) |
| Volume-Body LONG | 263 | −$39.6 | +$80.2 | **+$11.1** | ~$8.5 | incluidos | **FAILED** (magnitud económica nula) |
| Momentum-Body LONG | — | — | — | — | — | — | Descartado en 2º split (mitad1 negativo) |
| Fade SHORT | — | — | — | — | — | — | Descartado en 2º split (mitad1 negativo) |
| Momentum-LowerWick LONG | — | — | — | — | — | — | Descartado en 2º split (mitad1 negativo) |

## Veredicto: **NO HAY ESTRATEGIA VALIDADA**

Ninguno de los 5 candidatos generados por la minería sobrevive un
estándar económico serio. Los dos que llegaron más lejos (positivos en
TRAIN y VAL, positivos en OOS, positivos en un segundo split temporal
independiente, y positivos después de pasar por `portfolio_engine.py`
con capital=450/3 slots/fees/funding reales) **fallan en la última
prueba de robustez que este proyecto usa consistentemente desde R20/R21:
remover el mejor trade de OOS**.

---

## Cómo se llegó hasta acá (resumen del proceso, no 100 páginas)

### Paso 1 — Dataset transversal, sin distinguir perfil

Se tomaron **3,296 trades limpios** (todos los perfiles, `tp_hit`+`sl_hit`,
excl. ONUSDT/BBUSDT) y se reconstruyó contexto 100% causal (última barra
CERRADA antes de `OpenedAt`) desde `klines_clean` (15m) + `oi_metrics` +
`funding_hist` de `binance_vision_clean.db`: retornos 1/3/5/10/20 velas,
pendiente y relación de MA7/25/50/99, distancia a cada MA, distancia a
high/low de 5/10/20/50 velas, ATR relativo, volumen relativo y percentil,
forma de la vela de entrada (body/wicks), RSI14, cambio de OI 1h,
posicionamiento top-trader/global L-S, funding — **2,611 trades**
quedaron con contexto completo (685 descartados explícitamente por falta
de cobertura de klines, no rellenados). El nombre del perfil de origen
**no se usó en ningún punto del descubrimiento** — solo se recuperó al
final para reportar de dónde salió cada trade.

### Paso 2-3 — Minería de combinaciones, ganadores vs. perdedores

Split cronológico TRAIN (60%, may-jul)/VAL (20%, jul-ago)/OOS (20%,
ago-sep). Se generaron 246 condiciones binarias (percentiles 20/40/60/80
de cada feature continua + flags booleanas de estructura de MAs) y se
evaluaron **40,075 combinaciones** (individuales + pares) con soporte
mínimo 40 trades en TRAIN. Ranking inicial por lift de win-rate en TRAIN:
**las 25 mejores reglas de TRAIN se desploman en OOS** (la enorme mayoría
a win-rate 0% u OOS negativo) — el patrón de "data-dredging" ya visto en
40 rondas anteriores de este proyecto.

Re-ranking exigiendo soporte real (≥15 trades) simultáneo en VAL **y**
OOS (no solo en TRAIN) redujo el universo a reglas con lift combinado
positivo. De ahí salieron **5 candidatos** positivos en TRAIN, VAL y OOS
a la vez — casi todos girando en torno a la misma idea conceptual:
**"retorno de 3 velas en el 20% más alto (momentum reciente) + vela de
entrada con cuerpo dominante / mecha superior chica (conviction, no
agotamiento)"**, del lado LONG.

### Paso 4 — Las 5 candidatas

| # | Nombre | Contexto/trigger | Confirmación | Entrada | Dirección |
|---|---|---|---|---|---|
| 1 | Momentum-Wick LONG | retorno 3 velas ≥ p80 | mecha superior < p40 (poca presión vendedora en la vela) | al cierre de la vela de entrada | LONG |
| 2 | Volume-Body LONG | volumen relativo ≥ p60 | cuerpo de vela ≥ p60 (vela de convicción, no doji) | ídem | LONG |
| 3 | Momentum-Body LONG | retorno 3 velas ≥ p80 | cuerpo ≥ p60 | ídem | LONG |
| 4 | Fade SHORT | precio vs MA7 < p40 (ya débil) | mecha inferior < p60 | ídem | SHORT |
| 5 | Momentum-LowerWick LONG | retorno 3 velas ≥ p80 | mecha inferior < p60 | ídem | LONG |

SL/TP/sizing: se usó el **SL/TP/margen que cada trade real ya tenía**
(no se re-optimizó ninguno) — la pregunta de esta ronda es si FILTRAR los
trades existentes por este contexto de entrada mejora el resultado
agregado, no diseñar un SL/TP nuevo.

### Paso 5 — Anti-leakage

Todas las features usan exclusivamente datos hasta la última barra
cerrada antes de `OpenedAt` (mismo método causal de R35, verificado por
construcción — `find_bar_index` usa `searchsorted(...,'right')-1`, nunca
mira hacia adelante). El resultado del trade (`win`/`pnl`) no entra en
ninguna feature. Ningún parámetro (percentiles) se recalculó mirando
VAL/OOS — todos los umbrales salen exclusivamente de TRAIN.

### Segundo split temporal independiente (mitad1 vs. mitad2 del dataset completo)

De las 5, solo **2 sobrevivieron** siendo positivas en ambas mitades con
soporte ≥10: **Momentum-Wick LONG** y **Volume-Body LONG**. Las otras 3
(Momentum-Body, Fade SHORT, Momentum-LowerWick) dieron negativo en la
primera mitad — descartadas ahí mismo, sin forzarlas a portfolio_engine.

### Paso 6 — Portfolio engine real (capital 450, 3 slots, notional 150/slot)

Corridas con `portfolio_engine.py` (asignación determinística de slots
por score+orden cronológico, rechazo explícito por concurrencia cuando
no hay slot libre). El PnL usado es el `RealizedPnl` real de cada trade
aceptado — ya neto de `EntryFee`/`ExitFee`/`TotalFundingPaid` reales
registrados en cada fila.

- **Momentum-Wick LONG**: 108→100 aceptados en TRAIN (8 rechazados por
  concurrencia), 23→22 en VAL, 17→17 en OOS. PnL: TRAIN +$107.0 / VAL
  +$74.4 / **OOS +$11.0** (~$8.4/mes).
- **Volume-Body LONG**: 230→203 en TRAIN, 57→45 en VAL, 19→15 en OOS.
  PnL: TRAIN −$39.6 / VAL +$80.2 / **OOS +$11.1** (~$8.5/mes).

Por la letra del gate ("PnL neto positivo en OOS después de costos y
restricciones"), **ambos pasan**. Pero antes de llamarlos estrategia se
aplicó la prueba de robustez que este proyecto exige desde R20/R21:
**quitar el mejor trade de OOS**.

| Candidato | OOS con todos los trades | OOS sin el mejor trade | ¿Sobrevive? |
|---|---:|---:|---|
| Momentum-Wick LONG | +$11.0 (17 trades) | **−$3.4** | **NO** — un solo trade explica el 100%+ del resultado |
| Volume-Body LONG | +$19.5 antes de rechazo por concurrencia (+$11.1 después) | **+$3.6** | Sobrevive apenas, pero económicamente nulo (~$2.7/mes con $450 de capital) |

## Por qué esto es FAILED, no "hay potencial"

1. **Momentum-Wick LONG** no es una estrategia: es 16 trades perdedores
   compensados por 1 trade ganador grande. Eso es exactamente lo que las
   reglas de esta ronda prohíben ("no me interesa... resultado dominado
   por outliers").
2. **Volume-Body LONG** sobrevive técnicamente todas las pruebas
   (TRAIN+VAL+OOS+segundo split+portfolio engine+remove-best-trade) pero
   su magnitud —**~$2.7 a $8.5 netos por mes sobre $450 de capital
   (0.6%-1.9%/mes)**— no es una estrategia económicamente viable, es
   ruido con signo positivo. Además decae fuertemente de VAL (+$80) a
   OOS (+$11), el mismo patrón de "alpha decay" que mató R10/R12/R18/R21
   en rondas anteriores.
3. Ninguno de los dos alcanza remotamente el estándar histórico de este
   proyecto (≥$150/mes) ni siquiera antes de la prueba de robustez.

## Evidencia de que no es overfit "por casualidad de que encontramos 2"

Se probaron 40,075 combinaciones — con ese volumen de pruebas, encontrar
por puro azar un puñado de reglas "positivas en 3 splits" es exactamente
lo esperado estadísticamente (problema de comparaciones múltiples), no
evidencia de señal real. El hecho de que **ninguna** sobreviva con
magnitud económica significativa, y que la única que sobrevive
remove-best-trade lo haga por apenas $3.6, es la confirmación de que el
proceso de minería no encontró una estructura de mercado real transversal
a los ~19 perfiles — encontró el ruido estadístico esperable de buscar
en 40 mil combinaciones sobre un dataset cuya población de origen (R44)
ya está marcada como reconstrucción no confiable.

## Limitación de validación (registrada, no bloqueante)

Como en R44: el dataset de origen es en su enorme mayoría (`~99%`) el
import legacy `trades.csv` reconstruido tras el incidente de Docker —
usado aquí explícitamente para DESCUBRIMIENTO por instrucción directa de
esta ronda. Cualquier candidato que hubiera pasado el gate económico
igual habría necesitado una validación final posterior con datos vivos
antes de ir a producción — no aplica acá porque ningún candidato llegó
tan lejos.

## Trail-1

No participó (permaneció OFF global y por perfil durante toda la
investigación) — no hay estrategia base a la que combinarlo todavía.

## Qué sigue

No hay estrategia para pasar a la comparación con Trail-1. Antes de una
próxima ronda de minería sobre `SimulatedTrades`, hace falta acumular
volumen de trades genuinamente en vivo (ver R44) — seguir mimando la
misma tabla reconstruida con más combinaciones no va a producir un
resultado distinto a este.
