# ROUND 22 — PROVE IT OR BREAK IT

**Fecha:** 2026-09-24 · Script: `agent/backtest/r22_prove_or_break.py` ·
Auditoría adversarial del candidato de R21 (capitulación + score-select,
$150/mes headline) — congelado sin tocar ningún parámetro — más scoping
liviano de una segunda familia independiente.

# VEREDICTO: CAPITULACIÓN + SCORE-SELECT = FAILED

El candidato de R21 no sobrevive un walk-forward honesto ni una prueba de
generalización del régimen ni una prueba de generalización del score. Se
cierra. No se rescata con otra variable. R23 debe atacar un mecanismo
distinto.

---

## Nota de proceso — reproducción no exacta

La reproducción de la Parte 1 dio **$171/mes, n=983** en vez de los $150/mes
n=1054 de R21. Causa identificada: R21 calculaba el corte TRAIN/VAL/OOS
sobre **todos los días calendario** de BTCUSDT; R22 lo calculó sobre **los
días con al menos un evento**, lo cual desplaza levemente los cortes
(TRAIN≤2026-01-23 en vez de TRAIN≤2026-08-17 aprox). El mecanismo (evento,
score, costos, slots) es idéntico — es una diferencia de segmentación, no
de lógica. No se corrigió porque el walk-forward completo (Parte 2) hace
irrelevante el corte exacto: usa los 14 meses completos, no un split fijo.
Ambas cifras ($150 y $171) son consistentes en orden de magnitud y en la
conclusión final.

---

## 1. Walk-forward mes a mes — 14 meses completos (jul-2025 a ago-2026)

| Mes | Trades | PnL | Régimen |
|---|--:|--:|---|
| 2025-07 | 152 | −$194 | train |
| 2025-08 | 142 | +$49 | train |
| 2025-09 | 144 | −$274 | train |
| 2025-10 | 148 | −$78 | train |
| 2025-11 | 143 | +$3 | train |
| **2025-12** | 149 | **+$464** | train |
| 2026-01 | 146 | +$9 | train |
| 2026-02 | 123 | +$53 | val |
| 2026-03 | 137 | −$75 | val |
| 2026-04 | 144 | −$101 | val |
| 2026-05 | 155 | +$342 | oos |
| 2026-06 | 150 | +$337 | oos |
| 2026-07 | 155 | +$315 | oos |
| 2026-08 | 80 | +$174 | oos |

**9/14 meses positivos**, pero el resultado está dominado por 5 meses
outlier (dic-25, may/jun/jul/ago-26 = +$1632 de un total de +$1025 en 14
meses) mientras los otros 9 meses suman **−$607** en conjunto. Esto es
exactamente el patrón "unos pocos meses cargan todo el resultado" que el
proyecto ya vio en R10-R18 — visible ahora también en un tramo (dic-2025)
que R21 nunca había mirado por estar fuera de su ventana VAL+OOS.

## 2. Régimen sin lookahead — descubierto SOLO en TRAIN

Se probaron 2 variables 100% causales (disponibles en tiempo real, sin
mirar el resultado): volatilidad realizada trailing-30d de BTC y del
universo agregado. Para cada una, el umbral se fijó buscando el que
**maximiza el PnL dentro de TRAIN únicamente**, después se aplicó
mecánicamente (sin retocar) a VAL+OOS.

| Variable | Dirección | Umbral (TRAIN) | VAL+OOS: ON | VAL+OOS: OFF |
|---|---|--:|--:|--:|
| BTC rv trailing-30d | above | 0.00224 | **+$139** (mar,abr,jul) | +$907 (feb,may,jun,ago) |
| BTC rv trailing-30d | below | 0.00259 | +$907 | +$139 |
| universo rv trailing-30d | above | 0.00501 | +$826 (jun,jul,ago) | +$219 |
| universo rv trailing-30d | below | 0.00709 | +$1046 (todos ON) | +$0 |

**Resultado decisivo:** el umbral óptimo-en-TRAIN de BTC-rv, aplicado
honestamente hacia adelante, **prende la estrategia exactamente en los
3 peores meses de VAL+OOS** ($139 de $1046 posibles) y la apaga en los 4
mejores. Es lo opuesto de útil — confirma que el régimen encontrado
optimizando solo en TRAIN **no generaliza**, y en este caso activamente
perjudica. La variable de universo-rv por casualidad apunta en la
dirección "correcta" para "above" pero el umbral "below" degenera a
"todo ON" (no discrimina nada) — es decir, entre las 4 combinaciones
variable×dirección, ninguna ofrece una señal consistente y confiable; el
único caso que "funciona" (universo above) es indistinguible de haber
elegido, entre 4 monedas al azar, la que salió cara.

**Conclusión Parte 4 (test de generalización):** *"¿el régimen habría
activado/desactivado la estrategia ANTES de saber que el período iba a
ser bueno o malo?"* — **NO.** Es descriptivo, no predictivo.

## 3. ON/OFF — baseline vs régimen (BTC-rv, el peor caso, para no elegir el ganador post-hoc)

| | Meses | PnL total | PnL/mes | Peor mes | maxDD | %ON |
|---|--:|--:|--:|--:|--:|--:|
| Baseline (siempre ON), toda la historia | 14 | +$1025 | +$73 | −$274 | $352 | 100% |
| Régimen ON, toda la historia | 6 | +$615 | +$103 | −$101 | $176 | 43% |
| Baseline, solo VAL+OOS | 7 | +$1046 | +$149 | −$101 | $176 | 50% |
| **Régimen ON, solo VAL+OOS** | 3 | **+$139** | **+$46** | −$101 | $101 | 21% |

**El régimen EMPEORA el resultado out-of-sample** (de $149/mes a $46/mes).
No cumple ni siquiera el objetivo mínimo de la Parte 6 del brief ("eliminar
períodos sin edge, sin necesitar hacer magia") — elimina períodos CON edge
y deja los sin edge.

## 4. Estrés extremo (candidato headline, VAL+OOS)

| Test | NET/mes |
|---|--:|
| Base | $171 |
| Remove top-1 trade | $139 |
| Remove top-5 trades | $87 |
| **Remove top-10 trades (de 983)** | **$47** |
| Remove mejor mes (2026-05) | $121 |
| Remove mejores 2 meses (2026-05, 06) | $72 |

**10 trades de 983 (1%) sostienen el 73% del resultado.** Esto es más
concentrado que lo reportado en R21 (donde top-5/1054 sostenía "solo" 53%)
— la segmentación distinta de R22 lo revela con más crudeza. Coincide con
la advertencia explícita del usuario: "una estrategia que depende de 20
trades dentro de 1054 no es robusta."

## 5. Generalización de score-select — el hallazgo que mata al candidato

Comparación de 6 métodos de selección de slot (score, FIFO, random, low-vol,
high-vol, raw-signal), corridos por separado en cada mitad de VAL+OOS — no
en el período completo (que es donde R21 vio el "10× de mejora").

**1ra mitad (2026-01-23 a 2026-05-06) — TODOS negativos:**

| Método | NET/mes |
|---|--:|
| fifo | −$29 |
| random | −$30 |
| low_vol | **−$11** (el "mejor", pero negativo) |
| high_vol | −$30 |
| raw_signal | −$23 |
| score | −$21 |

**2da mitad (2026-05-06 a 2026-08-16) — TODOS positivos, y score NO es el mejor:**

| Método | NET/mes |
|---|--:|
| fifo | +$206 |
| **random** | **+$366** (el MEJOR, mejor que score) |
| low_vol | +$94 |
| high_vol | +$333 |
| raw_signal | +$356 |
| score | +$341 |

**Esto invalida la conclusión central de R21.** Dentro de cada mitad por
separado, score-select no es consistentemente el mejor método — en la
2da mitad, hasta la selección **aleatoria** supera a score-select. La
"mejora de 10×" que R21 midió (FIFO $15/mes → score $150/mes) sobre el
período COMPLETO no es una habilidad de selección genuina: es un artefacto
de que el score, cuando se mezclan ambas mitades, termina capturando
proporcionalmente más operaciones de la mitad buena que FIFO — no porque
elija mejor DENTRO de cada mitad, sino porque la composición de candidatos
en competencia varía de forma que ayuda al ranking por accidente de
período. Cuando todo el universo tiene edge (2da mitad), cualquier método
de selección gana; cuando no lo tiene (1ra mitad), ningún método lo
rescata. **El score-select no es un mecanismo reutilizable de asignación de
capital — es un artefacto de la mezcla de dos regímenes de la señal
subyacente.**

## 6. Scoping liviano — segunda familia (failed-breakout)

Evento: ruptura de máximo/mínimo de 20 barras seguida de rechazo >50% del
exceso de ruptura (posible stop-hunt/trampa). Resultado **inconsistente**:

- FADE SHORT (rompe máximo, rechaza) @24h: TRAIN +31.5bp, **VAL −42.1bp**
  (signo invertido), OOS +26.2bp. Rompe la cadena en VAL — no usable.
- FADE LONG (rompe mínimo, rechaza): negativo en casi todos los tramos.

No es un candidato para atacar en serio tal como está definido — mismo
patrón de inestabilidad de siempre. Queda descartado como scoping (no se
gastó una ronda completa en él, tal como pide el brief).

---

## Veredicto final por pregunta del usuario

1. **¿R21 es realmente operable?** No.
2. **¿El $150/mes sobrevive walk-forward?** No — 14 meses muestran 9/14
   positivos pero dominados por 5 meses outlier; los otros 9 suman neto
   negativo.
3. **¿El régimen es predictivo o solo explicativo?** Solo explicativo. El
   umbral óptimo-en-TRAIN, aplicado hacia adelante, activa la estrategia
   en los peores meses de VAL+OOS.
4. **¿Score-selection generaliza?** No. Dentro de cada mitad de VAL+OOS por
   separado, no es consistentemente superior a FIFO/random/raw-signal — en
   la 2da mitad, hasta random-selection le gana.
5. **¿Mejor candidato independiente descubierto?** Ninguno todavía —
   failed-breakout (scoping de esta ronda) resultó inconsistente entre
   TRAIN/VAL/OOS.
6. **¿PnL neto real con $450?** No hay uno defendible — el headline de R21
   colapsa bajo walk-forward, régimen y test de selección.
7. **¿Tenemos STRATEGY #1?** **No.**

# CAPITULACIÓN (R18→R21) = CERRADA, FAILED

**Dónde murió:** en la prueba de generalización del score-select (Parte 6)
y en la prueba de generalización del régimen (Parte 3/4) — ambas
diseñadas específicamente para distinguir "funciona" de "funcionó una
vez, mezclado con la mitad correcta del dataset."

**Qué la mató:** la señal subyacente de capitulación es genuinamente
no-estacionaria mes a mes (9/14 positivos pero con 5 meses outlier
cargando todo); ni el score de selección ni ningún régimen causal simple
(volatilidad trailing de BTC o del universo) logra distinguir de antemano
los meses buenos de los malos. El "10× de mejora" de R21 era un artefacto
de mezcla de períodos, no una habilidad de selección real.

**Qué aprendimos (metodológico, aplica a cualquier ronda futura):**
cualquier mecanismo de "selección entre candidatos concurrentes" debe
probarse SIEMPRE por sub-período, nunca solo en el blend completo — un
mecanismo de selección puede parecer que agrega 10× de valor cuando en
realidad solo está re-empaquetando la composición temporal de qué
operaciones entran. Esta es una lección reutilizable para R23 en adelante.

---

## R23 — mecanismo completamente distinto (no se cierra la investigación)

Descartado en este round: capitulación/reversal (cerrado FAILED),
failed-breakout como se definió acá (inconsistente, no vale la pena
refinarlo con esta forma exacta de evento).

**Dirección concreta para R23:** atacar family **C (liquidation
continuation)** o **F (secuencia de microestructura price+OI+volumen+
liquidación) con una secuencia distinta a capitulación** — son las dos
familias de la lista de prioridad del usuario que NUNCA se probaron
formalmente (a diferencia de compresión→expansión y catch-up de altcoins,
ya FAILED en R5/R18). El colector de liquidaciones lleva corriendo desde
2026-09-10 (~2 semanas) — antes de empezar, verificar cuántos días de
datos limpios hay acumulados; si es insuficiente todavía (el criterio
histórico del proyecto es ≥30-70 días para no repetir el error de
"UNTESTABLE" de H14), usar mientras tanto el archivo histórico de
`data.binance.vision/.../metrics/` (mismo mecanismo que desbloqueó OI en
R9) para reconstruir liquidaciones o un proxy de liquidación (spikes de
volumen+precio con `count_toptrader_ls_ratio`/`sum_taker_ls_vol_ratio`
extremos) sobre los 14 meses ya disponibles, en vez de esperar más al
colector en vivo.
