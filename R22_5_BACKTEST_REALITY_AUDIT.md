# ROUND 22.5 — BACKTEST REALITY AUDIT

**Fecha:** 2026-09-24 · Scripts: `agent/backtest/r22_5_reality_check.py`
(tests automatizados + perturbación) + inspección directa de
`agent/data/binance_vision_clean.db`, `agent/config.py`,
`agent/download_*.py`.

**Objeto de este audit:** el motor de investigación (`agent/backtest/r6_*.py`
a `r22_*.py`, ~17 scripts, la ÚNICA infraestructura usada en las 22 rondas
de esta misión). **NO** es el motor de producción
(`agent/backtest/engine.py` + `SimulationMarkPriceWorker.cs`) — ese es un
sistema completamente distinto, con su propio backtest gate, ya evaluado y
marcado FAILED por separado (`verge_backtest_gate` en memoria). No se
confunden en este reporte.

No se buscó alpha. No se investigó Strategy #2. No se optimizó ninguna
hipótesis.

---

# BACKTEST STATUS: **C) PARTIALLY TRUSTWORTHY — SPECIFIC COMPONENTS FAIL**

No es (A): dos componentes que mueven directamente el número de $/mes que
usamos para decidir PASS/PARK/FAIL están rotos o no auditados (funding
ausente, dependencia de orden de slots). No es (D): la maquinaria causal
central (percentiles, joins de funding/OI, timing de entrada) pasa pruebas
automatizadas rigurosas y sostuvo 22 rondas de placebos que SÍ mataron
falsos positivos reales — eso no es ruido, es evidencia de que la parte
"detectar si una señal tiene persistencia direccional genuina" funciona.
Pero el número exacto de $/mes con el que declaramos PASS (≥150) puede
moverse **$145/mes solo por el orden de procesamiento de slots** — una
magnitud comparable al propio umbral PASS/PARK. Por eso no es (A) ni (B)
limpiamente: es (C).

| Componente | Veredicto |
|---|---|
| DATA | **FAIL** (survivorship confirmado) |
| SURVIVORSHIP | **FAIL** |
| LOOKAHEAD | **PASS** |
| TIMESTAMP ALIGNMENT | **PASS** |
| EXECUTION | PARTIAL (mecánica correcta, supuestos de spread/slip sin verificar) |
| FEES | PARTIAL (fee real verificado, spread/slippage son supuestos) |
| SLIPPAGE | ASSUMPTION (no medible, sin order-book histórico) |
| SPREAD | ASSUMPTION (ídem) |
| FUNDING | **FAIL** |
| CAPITAL | PASS |
| SLOT COMPETITION | **FAIL** |
| INTRABAR LOGIC | PASS (no aplica — no se usa TP/SL intrabar en investigación) |
| OI ALIGNMENT | PASS |
| LIQUIDATION ALIGNMENT | INSUFFICIENT DATA |
| REAL-vs-REPLAY | **INSUFFICIENT DATA** |

---

## 1. DATA REALITY AUDIT

**Mercado exacto:** Binance **USDⓈ-M Futures** (`data.binance.vision/data/
futures/um/...`), confirmado en el código fuente de los 6+ scripts de
descarga (`download_binance_vision_daily_all_v2.py` y otros) — nunca spot,
salvo `spot_klines` (240 símbolos) que se usa exclusivamente como la pata
de cobertura del funding-carry (R16/R17), correctamente separado.

**Cobertura real (medida, no asumida):**

| Tabla | Filas | Símbolos | Rango |
|---|--:|--:|---|
| `klines_clean` (15m) | 6.68M | 450 | 2025-06-01 → 2026-08-17 (~14.5 meses) |
| `taker_flow` (15m) | 9.33M | 429 | **2025-12-01** → 2026-08-17 (~8.5 meses) |
| `spot_klines` (15m) | 5.80M | 240 | 2025-12-01 → 2026-08-17 |
| `oi_metrics` (5m) | 6.80M | **63** | 2025-06-01 → 2026-08-17 |
| `funding_hist` (8h) | 74.9K | **63** | variable por símbolo (listing) |

**Implicación práctica:** cualquier ronda que use `taker_flow`, `spot_klines`,
`oi_metrics` o `funding_hist` está limitada a un universo mucho más chico
(63-429 símbolos, y solo desde dic-2025 para taker/spot) que el que usan
las rondas que solo necesitan OHLCV (klines_clean, 450 símbolos, 14.5
meses) — esto ya estaba documentado round a round, pero nunca se había
consolidado en un solo lugar. R18-R22 (capitulación) solo usan
`klines_clean` (volumen propio, no `taker_flow`) — por eso el walk-forward
de R22 pudo ir hasta 2025-07 sin problema de cobertura.

### Survivorship bias — CONFIRMADO (issue A del brief)

`agent/download_watchlist_vision.py` línea 46: `symbols = config.WATCHLIST`
— el universo entero de 450 símbolos se sembró a partir del **watchlist
actual del agente en producción**, tal como existe HOY, no de una
reconstrucción histórica de qué contratos USDT-M estaban listados en cada
punto del pasado.

Verificación directa: **0 de 450 símbolos terminan sus datos antes del
último timestamp del dataset** (`MAX(open_time) < casi-presente` → 0
resultados). Si el universo fuera históricamente correcto, esperaríamos
encontrar contratos que fueron deslisteados en algún punto de los 14.5
meses y cuyos datos simplemente terminan ahí. No hay ninguno. Esto es
la firma clásica de survivorship: **todo símbolo que Binance deslisteó
antes de que se capturara el watchlist actual está 100% ausente de las 22
rondas de investigación**, incluidas las rondas que ya declaramos FAILED
(el drift negativo de altcoins de R12/R13 podría estar subestimado o
sobreestimado sin saber cuántos "perdedores totales" faltan).

- **A) Survivorship bias:** SÍ, confirmado.
- **B) Lookahead en construcción del universo:** PLAUSIBLE, no cuantificado.
  `config.WATCHLIST` es curado por quien mantiene el agente en base a
  características actuales (liquidez/volatilidad) — es posible que símbolos
  hayan entrado a la watchlist PORQUE mostraron cierto comportamiento
  reciente, lo cual introduciría una forma sutil de selección post-hoc. No
  se pudo verificar sin el historial de cambios de `config.WATCHLIST` (fuera
  de alcance de esta ronda).
- **C) Símbolos históricos excluidos:** SÍ, por construcción — cualquier
  perp deslisteado antes de hoy. No cuantificable sin un registro externo
  de delistings de Binance Futures (no se investigó este round).
- **D) Símbolos incluidos antes de su listing real:** NO — cada array
  por-símbolo (`load_symbol`) solo contiene las barras reales con
  timestamp verdadero de esa moneda; no hay datos sintéticos pre-listing.
  El filtro `MIN_ROWS=8000` de `universe()` sí puede excluir del panel a
  símbolos muy recientes/de vida corta, pero eso es conservador, no un
  lookahead.

**Veredicto DATA/SURVIVORSHIP: FAIL.** No invalida automáticamente los 22
rounds anteriores (el mecanismo de placebo/OOS que mató la mayoría de
hipótesis seguiría matándolas incluso con más símbolos), pero sí significa
que **ninguna magnitud de "edge" o "drift" medida en este proyecto puede
afirmarse como representativa del universo cripto histórico completo** —
solo del subconjunto de monedas que sobrevivieron hasta hoy.

---

## 2. TIMESTAMP / LOOKAHEAD AUDIT — PASS

Se construyó y corrió un test automatizado (`test_causal_percentile_no_
lookahead`, Sección A de `r22_5_reality_check.py`) que inyecta un spike
sintético masivo en el FUTURO de una serie y verifica que `pctile_causal`
(la función usada en absolutamente todos los scripts R6-R22 para
percentiles rolling) no lo "ve" en ninguna barra anterior al spike, y SÍ lo
ve correctamente una vez que el spike entra a la ventana pasada. **PASS.**

Verificación matemática adicional (lectura directa del código): para la
barra de salida `t=win+k`, la ventana usada es `a[k:k+win] = a[t-win:t]` —
excluye estrictamente el valor de la propia barra `t`. Confirmado en
`r12_smartmoney.py::pctile_causal` y replicado idéntico en `r6_
adversarial_screen.py`.

**Entrada de operaciones:** test sintético `test_entry_strictly_after_
signal_close` confirma que el precio de entrada usado en TODOS los scripts
de sim económica es `open[i+1]` (la apertura de la barra SIGUIENTE a la
señal), nunca el close/high/low de la barra de señal misma. **PASS.**

**Join de funding:** test sintético `test_funding_join_causal` confirma
que `searchsorted(calc_time, kline_time, side='right')-1` nunca asigna un
`funding_rate` cuyo `calc_time` sea posterior a la barra. **PASS**
(aplica a R9-R17; ver §5 sobre por qué esto es irrelevante para R18-R22,
que no usan funding en absoluto).

**Join de Open Interest:** `download_oi_metrics.py` línea 43 documenta
`open_time = create_time` (snapshot puntual, grilla de 5 min) — no es una
ventana de agregación con fin posterior al inicio, es una lectura
instantánea, y se empareja 1:1 al mismo timestamp de la vela de 15m. No es
lookahead en el backtest histórico (en vivo sí habría que sumar la
latencia de publicación de la API, un tema operativo distinto, no de
corrección del backtest). **PASS.**

---

## 3. EXECUTION REALISM — PARTIAL

**TAKER:** orden de mercado ejecutada exactamente en `open[i+1]` — no
asume ejecución instantánea en el precio exacto de la señal (que sería
imposible), asume ejecución en la apertura de la barra siguiente. Razonable
y conservador.

**MAKER:** fill MECÁNICO, no asumido — coloca un limit a `LIMIT_OFFSET`
(6bp) del precio de señal y revisa `FILL_WINDOW=4` barras de máximos/
mínimos intrabar reales para determinar si se hubiera tocado. Esto ya se
midió en R20/R21/R22 con fill rates genuinos de 71.7%-83.6% (no un
supuesto arbitrario). **Buena práctica, PASS en cuanto a metodología.**

**Lo que el modelo MAKER asume optimistamente (no probado):** que tocar el
precio del limit garantiza el fill completo. No modela posición en la cola
del libro de órdenes — en un mercado real, otros traders pueden estar
delante en la cola al mismo precio, y el fill real podría ser parcial o
nulo incluso si el precio se tocó. No hay datos de order-book histórico
para corregir esto (ninguno de los datasets de Binance Vision los incluye).
Esto se documenta como supuesto optimista, no se corrige (no hay con qué).

**Perturbación de latencia (medida esta ronda, Sección C):** se re-corrió
el candidato de capitulación con 0/1/2/4 barras extra de delay entre señal
y ejecución (0/15/30/60 min):

| Delay | NET/mes |
|--:|--:|
| 0 min | $171 |
| 15 min | $177 |
| 30 min | $172 |
| 60 min | $156 |

**Solo ~9% de degradación con 60 minutos de latencia añadida.** La
economía del candidato NO es frágil a la velocidad de ejecución — es
frágil a OTRA cosa (ver §6).

---

## 4. COST MODEL AUDIT

| Costo | Fuente | Supuesto | Fórmula | Cuándo se aplica |
|---|---|---|---|---|
| Fee taker | Binance fee schedule real (VIP0 USDⓈ-M) | 5bp/lado = 0.05% | fijo | entrada+salida |
| Fee maker | Binance fee schedule real (VIP0) | 2bp/lado = 0.02% | fijo | entrada+salida (si llena) |
| Spread | **ASUNCIÓN, no medida** | 3bp/lado | fijo | entrada+salida (solo taker) |
| Slippage taker | **ASUNCIÓN, no medida** | 4bp/lado | fijo | entrada+salida |
| Residual maker | **ASUNCIÓN, no medida** | 1bp/lado | fijo | entrada+salida (si llena) |
| Funding | — | **NO APLICADO** | — | nunca, en R18-R22 |

**Fee taker (5bp) y fee maker (2bp) son verificablemente correctos** —
coinciden con la tabla de comisiones estándar (no-VIP) de Binance
USDⓈ-M Futures (0.05%/0.02%). Esta parte del costo es un HECHO, no una
suposición.

**Spread (3bp) y slippage (4bp/2bp para taker/maker) son ESTIMACIONES**,
declaradas como tales desde R20, no medidas contra datos reales de
libro de órdenes (que no existen en el dataset). No hay forma de
verificarlas con lo que tenemos. Los tests de sensibilidad de R21/R22
(fee×1.5/2, slippage×2/3) ya muestran que el candidato sobrevive esos
rangos — pero eso prueba robustez AL RANGO PROBADO, no que el rango sea
correcto.

**Confirmación de estructura (pedido explícito del brief):** el costo de
24bp RT para capitulación es correctamente el modelo de **1 pata
direccional** (`2×(5+3+4)`), NO el de 46bp de 2 patas usado en
funding-carry (R16/R17) — esto ya se había auditado explícitamente en R20
y se reconfirma acá por inspección directa del código: `TAKER_RT` se
aplica una sola vez a la entrada y una sola vez a la salida de una
posición direccional simple. **Correcto.**

---

## 5. FUNDING REALISM — FAIL

Los joins de funding (R9-R17, universo restringido a 63 símbolos con
funding real) son causalmente correctos (test B2, PASS). **Pero los
scripts R18-R22 (capitulación, el único candidato que llegó a sim
económica) NO incluyen ningún término de funding en el cálculo de PnL**,
pese a sostener posiciones hasta 24h (96 barras de 15m) — suficiente para
cruzar 2-3 liquidaciones de funding (cada 8h en Binance).

Esto es una omisión real, no un bug de signo o de timing — simplemente no
está. El dataset (`funding_hist`) existe y se usó correctamente en otras
rondas, así que no es un problema de datos faltantes, es un gap de
alcance entre rondas. Para un short de 24h en un universo de altcoins con
funding típicamente disperso (±1 a 15bp por settlement, medido en R15-R17),
el costo/beneficio de funding no incluido podría mover el resultado varios
puntos básicos por trade — no se sabe en qué dirección sin medirlo.

**Veredicto: FAIL** — no porque el funding esté mal aplicado, sino porque
está completamente ausente en el único candidato que llegó a sim
económica con capital real.

---

## 6. POSITION / CAPITAL ENGINE

**Colisión de slots (test sintético B3):** con 1 slot libre y 2 candidatos
en el mismo timestamp, exactamente 1 ejecuta — no se inventa capital
extra, no se duplica notional. **PASS.**

**Dependencia de orden — CONFIRMADO MATERIAL, la prueba más importante de
esta ronda:**

Se re-corrió el candidato de capitulación con el orden de prioridad
EXACTAMENTE INVERTIDO (peor score primero, en vez de mejor score primero)
— mismos candidatos, mismos costos, mismos timestamps, mismo capital:

| Orden | NET/mes | n |
|---|--:|--:|
| Score (mejor primero) | **$171** | 983 |
| Score invertido (peor primero) | **$26** | 983 |

**$145/mes de diferencia — un 85% del resultado — atribuible EXCLUSIVAMENTE
al orden de procesamiento de candidatos que compiten por el mismo slot.**
Esta magnitud es comparable al propio umbral PASS (≥150) que usa el
proyecto entero para decidir si una estrategia es viable. Confirma
cuantitativamente lo que R21/R22 ya habían mostrado cualitativamente
(score-select vs FIFO = 10× de diferencia) y lo que R22 después demostró
que NO generaliza fuera de muestra.

**Veredicto SLOT COMPETITION: FAIL.** No es que el motor calcule mal un
trade individual — es que el RESULTADO AGREGADO de cualquier estrategia
con capital limitado y candidatos concurrentes depende crítica y
materialmente de una decisión de diseño (el orden/criterio de prioridad)
que hasta ahora nunca se trató como una fuente de riesgo de overfitting
por derecho propio.

---

## 7. REAL TRADE / REPLAY BENCHMARK — INSUFFICIENT DATA

**No existen registros de ejecución real (dinero real) de Binance en este
proyecto.** Verge es, tal como está documentado en `CLAUDE.md` del repo,
un bot de futuros cripto **simulado** — no hay operativa en vivo con
dinero real para comparar.

El registro más cercano disponible es `agent/data/trades.csv` (3.683
filas), generado por el motor de **producción** (backend .NET +
`SimulationMarkPriceWorker.cs`, tick de 1s) — un motor de ejecución
**completamente distinto** al backtester de investigación Python (r6-r22)
auditado en esta ronda: código diferente, lógica de fill diferente, y
sobre todo, **estrategias diferentes** (Nexus/SCAR/LSE/MA-Slope/FVG/Arrow
Peak — ninguna de las hipótesis H1-H22 investigadas en esta misión llegó
nunca a producción). No hay señal en común para hacer una comparación
real-vs-replay pareada trade-por-trade.

Adicionalmente, según la memoria del proyecto (`verge_backtest_gate.md`):
la base de datos `SimulatedTrades` original fue **borrada por un reset de
Docker Desktop sin backup**, y fue reconstruida a nivel de esquema
exclusivamente a partir de este mismo `trades.csv`, con el PnL de esa
reconstrucción marcado explícitamente como **"no confiable"** en su
momento.

**Conclusión: no hay ninguna base honesta para una comparación real-vs-
replay de ninguna de las 22 rondas de esta misión.** No se etiqueta como
FAIL (eso implicaría que se comparó y no coincidió) — es **INSUFFICIENT
DATA**, y seguirá siéndolo hasta que al menos una hipótesis de esta
misión se despliegue en producción (papel o real) y acumule un historial
propio para comparar contra su propia réplica.

---

## 8. SYNTHETIC EXECUTION TESTS

Implementados en `r22_5_reality_check.py`, todos determinísticos con
resultado esperado conocido de antemano:

| Test | Qué verifica | Resultado |
|---|---|---|
| A. `pctile_causal` sin lookahead | spike futuro no afecta percentiles pasados | **PASS** |
| B1. Fórmula de fee/retorno | log-retorno y resta de costo exactos | **PASS** |
| B2. Join de funding causal | nunca asigna funding futuro | **PASS** |
| B3. Colisión de slot | 1 slot + 2 candidatos → ejecuta solo 1 | **PASS** |
| B4. Entrada post-señal | entrada = open[i+1], nunca la barra de señal | **PASS** |

**No cubierto en esta ronda** (reconocido explícitamente, no se inventó
confianza): fills parciales, gap-a-través-del-stop, rechazo por capital
insuficiente más allá del caso de colisión de 1 slot. Se explica en §9 por
qué esto es de prioridad baja: **ninguno de los candidatos de investigación
usa TP/SL ni margen apalancado explícito** — todos salen a horizonte fijo.
Si algún candidato futuro empieza a usar TP/SL o sizing apalancado, estos
tests SÍ se vuelven obligatorios antes de confiar en su sim económica.

---

## 9. OHLCV LIMITATION AUDIT

La ambigüedad clásica "¿tocó primero el TP o el SL dentro de la misma
vela?" **no aplica a ninguno de los 22 rounds de investigación**: ningún
script R6-R22 usa TP/SL basado en niveles de precio — todos salen a un
horizonte de tiempo fijo (`open[i+1+hbars]`). El único uso de datos
intrabar es el chequeo MAKER (¿tocó el high/low el precio del limit?),
que es una condición de un solo sentido, no una carrera entre dos niveles
ambiguos.

**Esto es distinto del motor de producción**, que sí usa SL/TP fijados al
abrir la posición y ejecutados vía tick de mark-price cada 1s (según
`CLAUDE.md`) — ese sistema no se audita en esta ronda (ya tiene su propio
gate, FAILED, documentado aparte).

**Veredicto INTRABAR LOGIC: PASS** (no expuesto a la ambigüedad, para el
motor de investigación).

---

## 10. LIQUIDATION / OI / EVENT DATA ALIGNMENT

**OI:** join point-in-time verificado causal (§2). **PASS.**

**Funding:** join causal verificado con test sintético (§2, §5). **PASS**
en cuanto a mecánica (aunque no usado donde debería, ver §5).

**Liquidaciones:** el colector (`agent/liquidation_tracker.py` /
`_run_liq_tracker.py`) corre desde 2026-09-10 — ~2 semanas de datos al
momento de este audit. Ningún script de investigación las usó todavía.
No se puede auditar alineación de timestamps de un dataset que
prácticamente no existe aún. **Veredicto: INSUFFICIENT DATA**, no FAIL —
es exactamente el motivo por el que R23 (liquidation continuation) tenía
que esperar a que el colector acumule cobertura, o reconstruirse desde el
histórico de `data.binance.vision/.../metrics/` (mismo mecanismo que
desbloqueó OI en R9) en vez de depender del colector en vivo.

---

## 11. PERTURBATION / REALISM TEST

Candidato usado: capitulación + score-select (ya cerrado FAILED en R22,
pero el único candidato que llegó a sim económica con capital real —
el brief pide usar el mejor disponible, no inventar uno nuevo).

- **Latencia de ejecución (§3):** robusto. $171→$156/mes con 60 min de
  delay añadido (~9% de degradación).
- **Orden de procesamiento (§6):** extremadamente frágil. $171→$26/mes
  (−85%) solo por invertir el orden de prioridad entre candidatos
  idénticos.

**Conclusión combinada:** la economía aparente de este candidato dependía
mucho más de **qué candidato gana la competencia por el slot** que de
**qué tan rápido se ejecuta la orden**. Esto es coherente con — y explica
mecánicamente — el hallazgo de R22 de que el score-select "de 10×" no
generalizaba: no es un problema de ejecución lenta, es que el motor de
asignación de capital es, por construcción, una fuente de varianza tan
grande como la señal misma.

---

## 12. STRATEGY RANKING RELIABILITY

Solo hay UN candidato que llegó a sim económica con capital (capitulación,
ya FAILED) — no existe todavía un segundo candidato para hacer un ranking
real A vs B vs C bajo distintos supuestos de ejecución, así que esta parte
no se puede responder al nivel de "estrategia" todavía.

Lo que SÍ se demuestra, al nivel de sub-configuración dentro de la MISMA
estrategia: el ranking entre métodos de selección de slot (score vs FIFO
vs random) es **inestable según qué mitad del período se mire** (medido en
R22 — random le gana a score en la 2da mitad) y **se invierte
completamente si se cambia el orden de procesamiento** (medido en esta
ronda, §6). Es una advertencia directa para cualquier ronda futura: un
"Config A bate a Config B por $X/mes" no es evidencia suficiente sin
verificar que sobrevive un reordenamiento o un resampling.

---

## 13. LO QUE SABEMOS / ASUMIMOS / PODEMOS REPRODUCIR

**SABEMOS (verificado por código o test):**
- El universo se sembró del watchlist ACTUAL del agente, no reconstruido
  históricamente → survivorship confirmado.
- Los percentiles/z-scores causales no tienen lookahead (test automatizado).
- La entrada siempre es `open[i+1]`, nunca la barra de la señal.
- Los joins de funding y OI son causales.
- Las fees taker (5bp) y maker (2bp) coinciden con la tabla real de
  Binance USDⓈ-M.
- El modelo de costo de 1 pata (24bp) es estructuralmente correcto para
  estrategias direccionales, distinto del de 2 patas (46bp) de
  funding-carry.
- El orden de procesamiento de candidatos concurrentes puede mover el
  resultado agregado en $145/mes (85% del headline) sin cambiar ningún
  otro parámetro.
- Ninguna de las 22 rondas de investigación usa TP/SL intrabar (la
  ambigüedad OHLC clásica no aplica a este motor).

**ASUMIMOS (sin forma de verificar con los datos disponibles):**
- Spread (3bp) y slippage (4bp taker / 1bp maker residual) — estimaciones
  razonables pero no medidas contra order-book histórico real (no existe).
- Que tocar el precio del limit en el modelo MAKER garantiza fill
  completo (sin modelar cola de órdenes).

**NO PODEMOS REPRODUCIR:**
- Ninguna comparación real-vs-replay (no hay operativa real, y el único
  registro de producción disponible es de estrategias distintas con su
  propia reconstrucción de dudosa fiabilidad).
- Alineación de datos de liquidación (colector con ~2 semanas de historia,
  insuficiente).
- El universo histórico verdadero de contratos USDT-M listados/
  deslisteados en cada punto del tiempo (no investigado esta ronda).

**SEGURO CONFIAR EN:**
- Que una señal que sobrevive placebo + OOS + cluster-bootstrap en este
  motor tiene una persistencia direccional genuina *dentro del universo
  superviviente* — la maquinaria de detección de falsos positivos es
  sólida y ya demostró funcionar (mató docenas de candidatos reales de
  drift espurio en R12/R13/R18).
- La magnitud de las fees reales (taker/maker) usadas.

**NO SEGURO CONFIAR EN:**
- El número exacto de $/mes de cualquier candidato que dependa de
  competencia por slots de capital (score-select, o cualquier mecanismo
  de asignación entre candidatos simultáneos) sin antes probar que
  sobrevive reordenamiento.
- Cualquier PnL de un candidato con holding ≥8h que no incluya funding.
- Que la magnitud de drift/edge medida en cualquier ronda anterior
  represente el universo cripto histórico completo (solo representa el
  subconjunto superviviente).

---

## 14. REGLA NO NEGOCIABLE — QUÉ HACER ANTES DE R23

No se reanuda investigación de alpha (liquidation continuation ni
cualquier otra) hasta resolver, en este orden de prioridad:

1. **Slot competition (FAIL, §6):** antes de que cualquier futura
   sim económica use "selección entre candidatos concurrentes" como parte
   de su resultado, exigir que se pruebe con AL MENOS 2 órdenes de
   procesamiento distintos (normal e invertido) y reportar ambos números
   — si difieren en más de ~20% del headline, la sim económica no es
   válida sin una defensa causal explícita de por qué ESE orden es el
   correcto (no solo el que da mejor resultado).
2. **Funding (FAIL, §5):** cualquier candidato con holding ≥8h debe incluir
   el término de funding real (`funding_hist` ya existe para 63 símbolos;
   para el resto, estimar con la mediana del universo con datos, declarado
   explícitamente como estimación) antes de reportar su PnL.
3. **Survivorship (FAIL, §1):** documentar explícitamente en cada futuro
   reporte que las magnitudes medidas aplican solo al universo
   superviviente — no intentar arreglarlo reconstruyendo el universo
   histórico completo (fuera de alcance sin un feed externo de
   listados/delistings), pero sí dejar de reportar cualquier cifra como si
   representara "el mercado cripto" en general.

No se manufactura confianza donde no la hay: el estado real es (C), no (A).
