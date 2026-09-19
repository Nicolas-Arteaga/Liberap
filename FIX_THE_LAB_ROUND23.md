# ROUND 23 — FIX THE LAB, THEN HUNT ALPHA

**Fecha:** 2026-09-24 · Scripts: `agent/backtest/portfolio_engine.py`
(motor central nuevo), `r23_fix_lab_and_hunt.py` (objetivo A), `r23_
discovery.py` (objetivo B).

---

# OBJETIVO A — MOTOR CORREGIDO Y VALIDADO

## Motor central de asignación: `portfolio_engine.py`

Un solo punto de verdad (Parte 3 del brief) reemplaza la lógica de
slot-filling que cada script R18-R22 reimplementaba por separado. Regla
determinística: **score descendente, tie-break por símbolo alfabético
ascendente** — nunca el orden de iteración del diccionario/lista de
entrada. Toda sim económica futura debe importar `allocate_timestamp` /
`run_portfolio` de este módulo en vez de reescribir su propio loop.

## Tests sintéticos del motor (Parte 9) — 6/6 PASS

| Test | Verifica | Resultado |
|---|---|---|
| 1. 2 candidatos idénticos, 2 slots | ambos entran, en cualquier orden de entrada | PASS |
| 2. 3 candidatos, 1 slot | gana siempre el de mayor score (probado en las 6 permutaciones) | PASS |
| 3. Posición cruza 1 settlement de funding | funding se aplica exactamente 1 vez | PASS |
| 4. Símbolo listado después de la fecha de entrada | no genera señales antes de su primer timestamp real | PASS |
| 5. Símbolo deslisteado | no genera señales después de su último timestamp real | PASS |
| 6. Orden aleatorio, 100 seeds | PnL idéntico en las 100 corridas (regla determinista) | PASS |

## Parte 1/2 — Order invariance sweep (candidato R21, VAL+OOS)

| Orden de entrada | NET/mes |
|---|--:|
| Cronológico | $171 |
| Cronológico inverso | $171 |
| Alfabético | $171 |
| Por score (feed) | $171 |
| Random (100 seeds) | mean=$171 median=$171 p5=$171 p95=$171 **std=$0.00** worst=$171 best=$171 |

**Order invariance CONFIRMADA bajo la misma regla determinística.**

## Hallazgo importante — corrección a lo que R22.5 reportó

R22.5 había medido un swing de $145/mes comparando "score-select" contra
"orden invertido de score" (peor candidato primero). Ese test, re-examinado
esta ronda, **no era un test de orden de entrada — era una comparación
entre dos REGLAS DE ASIGNACIÓN DISTINTAS** (mejor-candidato-gana vs
peor-candidato-gana), no un bug de iteración de diccionario. Esta ronda lo
separa explícitamente: bajo la MISMA regla (score desc + symbol ASC), 100
semillas de orden aleatorio de entrada dan **std=$0.00** — cero varianza.
La fila de referencia `worst_first_RULE` reproduce el número de R22.5
($26/mes) precisamente porque ES la regla "peor primero", no un accidente
de orden. **Conclusión corregida: nunca hubo un bug de iteración de
diccionario — lo que había era una regla de asignación mal definida
(ninguna regla EXPLÍCITA existía antes de R23; "FIFO" y "score" competían
sin que se hubiera declarado cuál es la regla correcta de antemano).**
Con la regla ahora fijada y declarada ANTES de ejecutar (Parte 2), el
resultado es 100% reproducible.

## Parte 4 — Funding

Cobertura real: **63/357 símbolos (18%) tienen `funding_hist` propio.**
Para el resto se usa la mediana cross-sectional causal de los símbolos que
sí tienen dato en ese mismo settlement — asunción declarada explícitamente,
no un hecho medido para esos símbolos.

Funding aplicado a TODA posición que cruza ≥1 settlement de 8h (00:00/
08:00/16:00 UTC) durante su holding.

## Parte 7/8 — R21 original vs R21 corregido

| Paso | NET/mes |
|---|--:|
| 1. Original (orden crono, sin funding, alloc determinista) | $171 |
| 2. + funding real/estimado por settlement cruzado | **$169** |

Delta de funding: **−$3/mes** (insignificante para este candidato — el
holding de 24h con SHORT en un universo de funding disperso no genera un
sesgo material una vez promediado sobre 983 trades).

**Veredicto numérico de Parte 8: $169/mes → "PASS (auditar)" por el
umbral solo.**

### Pero esto NO reabre la capitulación como estrategia viable

El motor ahora es confiable (order-invariance confirmada, funding
incluido) — pero **el número $169/mes es prácticamente el mismo $171/$150
que R21/R22 ya midieron**, porque el "bug" que parecía explicar el swing
de $145/mes no era un bug del motor, era una comparación entre reglas.
**Todo lo que R22 encontró contra este candidato usando ESTA MISMA regla
(score desc) sigue vigente sin cambios:**

- Walk-forward de 14 meses: 9/14 meses positivos, dominados por 5 meses
  outlier (dic-2025, may-ago-2026); los otros 9 suman neto negativo.
- Régimen óptimo-en-TRAIN (BTC-rv trailing) aplicado hacia adelante activa
  la estrategia en los 3 peores meses de VAL+OOS — no generaliza.
- Score-select probado por mitad separada: en la 2da mitad, random-
  selection le gana a score-select — la ventaja de score no es un
  mecanismo reutilizable, es un artefacto de mezcla de períodos.
- Top-10 trades de 983 (1%) sostienen 73% del resultado.

**Ninguno de esos cuatro hallazgos depende del bug de orden de iteración
que se corrigió esta ronda — dependen de la ESTABILIDAD TEMPORAL de la
señal subyacente, que no cambió.** Corregir el motor no repara una señal
que ya se demostró inestable mes a mes con un mecanismo de selección que
no generaliza dentro de sub-períodos.

# VEREDICTO FINAL: CAPITULACIÓN SIGUE CERRADA, FAILED

No se resucita. El motor está ahora arreglado y es confiable — y
precisamente por eso confirma, con más precisión que antes, que el
problema de este candidato nunca fue el motor: es la no-estacionariedad
de la señal misma (ya cerrada en R22) y una regla de asignación que
—ahora que existe explícitamente y es reproducible— sigue siendo, en el
fondo, una elección de diseño sin justificación causal más fuerte que
"maximiza el PnL de TRAIN", el mismo patrón de sobreajuste que mató el
régimen en R22.

---

# OBJETIVO B — BÚSQUEDA NUEVA (motor corregido desde el inicio)

**Mecanismo probado:** Volatilidad en transición — compresión sostenida
(percentil causal de volatilidad realizada ≤15%, ≥8 barras / 2h) seguida
de 1 barra de ruptura (percentil causal de |retorno| ≥85%) → dirección =
continuación del signo de la ruptura → **medido desde la SEGUNDA barra en
adelante** (follow-through), no la barra de ruptura misma (eso ya lo midió
y cerró R18 como FAILED). Solo etapa DISCOVERY (Parte 15: no se corrió sim
económica, no se mezclan etapas).

## Resultado: FAILED — la hipótesis de continuación está mal orientada desde TRAIN

| Horizonte | TRAIN | VAL | OOS |
|---|---|---|---|
| 1h | +1.7bp (ci_excl0=No) | **−4.1bp (ci_excl0=Sí)** | −0.1bp (No) |
| 4h | **−18.5bp (Sí)** | **−13.8bp (Sí)** | +2.1bp (No) |
| 12h | **−78.5bp (Sí)** | **−22.1bp (Sí)** | +2.9bp (No) |
| 24h | **−150.9bp (Sí)** | −19.9bp (No) | −0.7bp (No) |

La hipótesis (continuación) se congeló ANTES de mirar los resultados, tal
como pide el protocolo. **Pero TRAIN mismo contradice la hipótesis**: a
4h/12h/24h el efecto en TRAIN es fuerte, negativo y con CI que excluye 0
— es decir, la ruptura después de compresión **revierte**, no continúa,
y con una magnitud creciente en el horizonte (hasta −151bp a 24h en
TRAIN). Como la dirección declarada de antemano (continuación) resultó
incorrecta ya en TRAIN, el protocolo se cierra acá — no se re-testea con
el signo invertido en este mismo round (eso sería exactamente el
sobreajuste post-hoc que prohíbe la Parte 16 del brief, usando datos que
ya vi de VAL/OOS para decidir el signo).

## Hallazgo colateral — requiere su propio protocolo limpio antes de creerlo

El **control** (ruptura sin compresión previa, sin restricción de
mecanismo) muestra reversión significativa y consistente en TRAIN, VAL y
OOS a casi todos los horizontes (CI excluye 0 en 10 de 12 celdas). Esto
podría ser un candidato de "failed-breakout genérico" (familia 2 del
brief) — **pero el placebo temporal (mismo evento, ventana desplazada +25
barras sin relación causal) también da negativo y significativo a 24h
(−34bp neto, ci_excl0=Sí)**, lo cual es la firma exacta del drift
estructural negativo de altcoins medianas/chicas que ya contaminó R12,
R13 y el primer intento de R18 tres veces de forma independiente. No se
declara ni PASS ni PARK — se registra como pista para R24, con la
advertencia explícita de que necesita un control de magnitud emparejada
(no solo placebo temporal) antes de tomarse en serio, dado el historial
de este exacto patrón siendo un falso positivo.

---

## Próximo paso (R24)

1. **No volver a capitulación.** Cerrada definitivamente — el motor
   corregido confirma, no refuta, el cierre de R22.
2. Si se quiere perseguir el hallazgo colateral de "reversión post-
   ruptura sin compresión", el protocolo correcto es: aislar el efecto
   del drift estructural con un control de MAGNITUD emparejada (mismo
   tamaño de movimiento, símbolos aleatorios, sin condicionar en
   ruptura) — no solo el placebo temporal ya usado — antes de darle
   crédito.
3. Familias todavía no tocadas con el motor corregido: liquidation
   cascade (familia 4, bloqueada por cobertura de datos — el colector
   lleva ~2 semanas), relative altcoin events con framing distinto a
   beta-neutral/residual-momentum (familia 5), microestructura de
   22:00 UTC investigando el FENÓMENO subyacente en vez de usar la hora
   como feature (familia 6).
