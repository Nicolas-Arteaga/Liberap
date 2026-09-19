## Priorización (Round 21, 2026-09-24)

**Capitulación/liquidación-reversal + selección por score (drop_mag×volp_extra)
en vez de FIFO para slots concurrentes → PARK.** TAKER cap$450/slots5 tocó
$150/mes exacto sobre VAL+OOS (1054 trades), sobrevive fee×2/slippage×3/
remove-best-trade, y bate 10× a un placebo FIFO honesto ($15/mes) — el
perfil de robustez más fuerte de las 21 rondas. **Pero 1ra mitad de VAL+OOS
= −$16/mes, 2da mitad = +$316/mes** — mismo patrón de inestabilidad temporal
que cerró R10/R12/R13/R18, así que NO es PASS. Prioridad #1 para R22: buscar
variable de régimen que separe mar-abr de may-ago; si no aparece, buscar
2da estrategia independiente para combinar con este PARK. Detalle completo:
`CAPITULATION_EXECUTION_ROUND21.md`.

---

## Priorización (Round 37, 2026-09-24) — TRAIL-1: PASS, validado sobre población completa

**El "sesgo" de R36 resuelto por completo: no era sesgo de muestreo, eran
12 trades (ONUSDT×10, BBUSDT×2) con `ClosePrice` corrupto (saltos ~1000x)
que inflaban +$37,378 espurios en la población completa.** Excluyéndolos,
la población limpia (3,271 trades) suma −$2,488.02, consistente con el
baseline de R36. Se recuperó cobertura del 100% de símbolos fusionando
`binance_vision_clean.db` con `agent/data/klines.db` (caché del agente,
antes sin usar para research) — población simulable 2,337→2,985 trades.
**Trail-1/2/3 mejoran el baseline en los 5 cortes (TRAIN/VAL/OOS/ambas
mitades), 11/12 perfiles, ambas direcciones, 67% de 382 símbolos con ≥3
trades, y los 3 regímenes de volatilidad** — robusto a variar el umbral
±25-50bp. **VERDICT: PASS** (matices: TRAIN cerca de breakeven no
positivo; LONG mejora mucho pero no rentable por sí solo). NO
implementado — siguiente paso es diseñar la incorporación a
`risk_manager.py`, pendiente de decisión del usuario. Detalle completo:
`TRAIL1_FINAL_VALIDATION_ROUND37.md`.

---

## Priorización (Round 36, 2026-09-24) — RESULTADO A: trailing stop robusto sobre trades reales

**Simulación contrafactual barra a barra de 12 reglas de gestión de
salida sobre 2,337 trades reales — Trail-1 (BE en +100bp, +50bp
asegurados en +150bp, +100bp asegurados en +200bp) es la única regla que
convierte el baseline de negativo a positivo en TRAIN, VAL, OOS y ambas
mitades temporales** (PF OOS=1.28, 780 trades salvados vs 173 empeorados
en TRAIN). Advertencia de sesgo de muestra documentada: el subconjunto
reconstruible tiene baseline peor que la población completa de
producción (+$34,890 real) — comparaciones relativas entre reglas
válidas, cifras absolutas de PnL/mes no representativas todavía sin
resolver por qué. Desglose de los 1,032 SL con MFE≥100bp: MAE posterior
sistemáticamente grande (−249 a −490bp) en todos los buckets — trades que
necesitan gestión activa, no ruido. NO se tocó producción. Pendiente:
resolver sesgo de cobertura, documentar como propuesta a `risk_manager.py`
(no `portfolio_engine.py`, que gobierna entradas nuevas no gestión de
posiciones existentes), validar por perfil/símbolo. Detalle completo:
`EXIT_MANAGEMENT_SIMULATION_ROUND36.md`.

---

## Priorización (Round 35, 2026-09-24) — AUDITORÍA FORENSE DE TRADES REALES, nueva fuente de datos

**Fuente nueva localizada: tabla `SimulatedTrades` en Postgres
(localhost:5433/Verge), 3,315 trades reales de 17 perfiles de estrategia
(no solo Nexus/`trades.csv`), nunca usada en 35 rondas.** Columnas ricas
del esquema (MAE/MFE, distancia MA7, JSON de decisión) 100% nulas
(incidente de reset de Docker) — contexto reconstruido desde cero con
klines_clean, sin inventar nada. **Hallazgo fuerte: 45.7% de los trades
SL (1,032/2,257) habían alcanzado +100bp de excursión favorable antes de
revertir completamente hasta el stop** — evidencia concreta de que falta
un mecanismo de breakeven/captura parcial, no un problema de señal de
entrada. Estructura MA99 (MA7/MA25 por encima) es 7pp más frecuente en TP
que en SL — señal débil, requiere su propio TRAIN→VAL→OOS. Los 3 setups
del usuario (R34) no muestran ventaja en trades reales tampoco (win rates
8%/16%/12% vs baseline 13.5%). NO se tocó producción ni se convirtió nada
en `portfolio_engine.py` — pendiente simular la regla de salida sobre
ambas poblaciones (TP y SL) antes de proponer un cambio real. Detalle
completo: `FORENSIC_AUDIT_ROUND35.md`.

---

## Priorización (Round 34, 2026-09-24) — 13 setups de price action/MAs, 0/11 sobreviven, diagnóstico por grupo

**Cambio de paradigma a setups discrecionales mecanizados (contexto/
estado/evento/confirmación/entrada/stop/TP/no-trade), no factor mining.**
3 semillas del usuario + 10 nuevos, 11/13 implementados (5 y 9 pendientes,
requieren detección de piernas multi-barra). Ninguno sobrevive TRAIN.
**Diagnóstico específico, no genérico**: 5/7 setups LONG (giro MA7 pre-
pullback, MA7 toca MA99, falsa ruptura+recuperación, 2do giro en tendencia
de fondo, rechazo zona MA25/50) tienen pérdida NEGATIVA y significativa —
coincide con el mercado bajista de la muestra (R25/R31/R33), el problema
es el CONTEXTO (asumen tendencia alcista de fondo) no la entrada. Los 3
SHORT (fade cruce falso, retest fallido, quiebre rápido desde pico) no
muestran ningún efecto, ni siquiera negativo. Setup de compresión→
expansión con MAs reconfirma el cierre ya establecido en R18/R23.
Próximo (R35): endurecer filtro de contexto/régimen de los 5 LONG
significativamente negativos y re-correr solo esos (quirúrgico), o
implementar los setups 5/9 pendientes antes de cerrar la familia
completa. Detalle completo: `MA_SETUPS_ROUND34.md`, spec en
`SETUPS_ROUND34_SPEC.md`.

---

## Priorización (Round 33, 2026-09-24) — geometría TP/SL FAILED, hallazgo metodológico sobre R-múltiplos

**Búsqueda de asimetría de trayectoria (P(TP antes que SL), MFE/MAE) en
vez de retorno medio — 12/36 configuraciones parecían sobrevivir TRAIN→
VAL→OOS en R-múltiplos, pero la conversión a bp reales las mata a todas**:
condicionar en volatilidad alta infla mecánicamente la unidad de riesgo R
(bp), haciendo que R-múltiplos similares representen bp reales similares
o menores. Ninguna configuración supera 5.4bp gross (vs 24bp costo) ni
aporta más de 3.5bp sobre el baseline SHORT incondicional (mismo sesgo de
mercado bajista de R25, visible también en la geometría). **Hallazgo
metodológico reutilizable**: normalizar a bp antes de confiar en
estadísticas de R-múltiplos cuando R varía con la condición testeada.
Refuerza R32: el eje OHLCV+volumen+volatilidad+OI+posicionamiento parece
agotado tanto para retorno medio como para asimetría de trayectoria.
Detalle completo: `TP_SL_GEOMETRY_ROUND33.md`.

---

## Priorización (Round 32, 2026-09-24) — DISCOVERY ENGINE AUTOMATIZADO: 0 candidatos, cierre sistemático del eje OHLCV+volumen+OI+posicionamiento

**384 pruebas automáticas (128 máscaras de 8 features causales × 3
horizontes), incorporando por primera vez con rigor completo
`toptrader_ls_pos`/`global_ls_acct`/divergencia — 0 candidatos
sobreviven.** 70/384 pasan la criba de TRAIN (más de lo esperado por azar,
pero es la misma firma de drift de mercado bajista de R25 repetida vía
features distintas); 82% de los top-15 invierten signo en VAL; de los 5
que confirman VAL, el 100% muere en placebo temporal (magnitud igual o
mayor que la señal real en cada caso). `toptrader_ls_pos`/`global_ls_acct`
— la pista pendiente de R31 — evaluados con rigor completo: **sin
información incremental**, cierra esa sospecha definitivamente. Combinado
con R29/R30/R31, hay evidencia sistemática (no solo intuición) de que
**OHLCV+volumen+OI+posicionamiento sobre el universo superviviente está
agotado para alpha direccional.** NO abrir R33 sobre el mismo eje.
Prioridad de datos nuevos: (1) liquidaciones reales 60-90+ días (bloqueo
operativo reversible), (2) order book histórico (requiere fuente nueva),
(3) on-chain (requiere inversión del usuario). Detalle completo:
`ALPHA_DISCOVERY_ROUND32.md`.

---

## Priorización (Round 31, 2026-09-24) — multi-día FAILED, diagnóstico final: espacio OHLCV+volumen+OI agotado

**6 familias de ranking cross-sectional multi-día (momentum, reversión,
OI acumulación/distribución, OI+momentum alineado/desacuerdo, W∈{3,7,14,
30}d) — todas mueren en el filtro VAL**, con la ventana "ganadora" de
TRAIN perdiendo entre −216bp y −658bp en VAL (momentum W=14d: TRAIN
+$302/mes → VAL −658bp, firma clásica de overfitting a ruido — la ventana
ganadora no tiene patrón consistente entre familias). Canasta aleatoria
sin regla da retorno del mismo orden que el mejor TRAIN de las familias
"inteligentes". **Diagnóstico tras 31 rondas: el dataset OHLCV+volumen+OI
(universo superviviente, mercado mayormente bajista) parece agotado para
una segunda fuente de alpha direccional, intradía o multi-día.** No abrir
R32 repitiendo/combinando lo mismo. Prioridad de datos nuevos: (1)
liquidaciones reales (requiere reiniciar colector), (2) order book
histórico (no disponible), (3) on-chain (requiere inversión del usuario),
(4) `toptrader_ls_pos`/`global_ls_acct` de `oi_metrics` con el rigor
TRAIN→VAL→OOS→placebo actual (nunca aplicado con ese rigor, solo
tangencialmente en R12). Detalle completo: `MULTIDAY_REGIMES_ROUND31.md`.

---

## Priorización (Round 30, 2026-09-24) — motor combinatorio: FAILED, espacio de features parece agotado

**8 combinaciones estado+evento (2-3 features) cruzando precio/volumen/
volatilidad/OI, con disciplina VAL-confirma-antes-de-OOS — ninguna se
acerca al costo de ejecución, y la Fase 5 (distribución completa) muestra
win rates ~0.46-0.51 y dispersión simétrica sin cola explotable en todas.**
Tras 30 rondas cubriendo sistemáticamente precio/volumen/volatilidad/OI
solos, en secuencia, y ahora combinados, el espacio de features causales
de este dataset (OHLCV+volumen+OI Binance USDⓈ-M, universo superviviente)
parece agotado para señal direccional intradía/corto plazo. Próximo
(R31): funding como feature de INTERACCIÓN (nunca combinado) o cambio de
horizonte a régimen semanal/baja frecuencia — no otra variante del mismo
espacio ya cubierto. Detalle completo: `ALPHA_DISCOVERY_ENGINE_ROUND30.md`.

---

## Priorización (Round 29, 2026-09-24) — OI como disparador primario: FAILED

**8 formulaciones predeclaradas (OI expansion/contraction/aceleración/
shock, solas y combinadas con volumen/desacuerdo de precio) sobre 43
símbolos feature-complete (≥120k filas de OI) — NINGUNA sobrevive TRAIN→
VAL→OOS.** Causas distintas por rama: costo+placebo (A), inversión de
signo en OOS (B, F), sin generalización (C, D, G, H). Caso límite E
(expansion+volumen h=8h) tiene OOS net positivo pero VAL rompe la cadena
de confirmación — declarado FAILED sin rescatarlo con el número de OOS.
**OI como disparador primario (nivel/cambio/aceleración) no contiene
información direccional robusta en este universo/ventana.** Próxima
familia (R30): comportamiento relativo entre altcoins vía divergencia de
OI entre pares correlacionados, NO beta-hedge de precio (ya cerrado en
R13). Detalle completo: `OI_EVENT_SEQUENCES_ROUND29.md`.

---

## Priorización (Round 28, 2026-09-24) — CIERRE DEFINITIVO del hilo 22:00-UTC/iliquidez

**Liquidity transition (3 variantes predeclaradas: salida simple, salida+
movimiento extremo, salida+recuperación fuerte) — todas FAILED.** Salida
simple sin señal en ningún horizonte; salida+extremo muere por el mismo
patrón de contaminación por placebo que R24; salida+recuperación fuerte
solo tiene significancia espuria de muestra chica (n=44 en TRAIN) que
colapsa completamente en OOS. **Después de 6 rondas independientes
(R19-R21, R26-R28) sin producir una sola estrategia, el hilo 22:00-UTC/
iliquidez queda CERRADO DEFINITIVAMENTE — no reabrir con otra variante.**
Próxima familia (R29), completamente distinta: secuencias OI+precio+
volumen con el OI como disparador (no capitulación), o comportamiento
relativo entre altcoins vía divergencia de OI (no beta-hedge de precio,
ya cerrado en R13). Detalle completo: `LIQUIDITY_TRANSITION_ROUND28.md`.

---

## Priorización (Round 27, 2026-09-24) — liquidity regime (estado) FAILED limpio

**Iliquidez causal por símbolo (vol_pct decil≤10%), sola o combinada con
movimiento extremo, y el filtro hora==22 re-testeado con esta formulación
— ninguna alcanza CI que excluye 0 en TRAIN, en ningún horizonte
(15m-24h).** Distinto del patrón de R24 (había señal en TRAIN pero el
placebo la reproducía): acá no hay ni siquiera señal aparente. Cerrado
limpio, causa raíz = sin dirección consistente, no problema de
magnitud/costos. Prioridad #1 para R28: TRANSICIÓN de liquidez
(iliquidez→retorno de liquidez) en vez de estado estático — mecanismo
distinto, todavía no probado. Si también falla, cerrar definitivamente el
hilo 22:00-UTC/iliquidez (6 intentos: R19-R21, R26-R28) y pasar a
secuencias OI+precio+volumen o comportamiento relativo entre altcoins con
framing distinto al beta-hedge ya cerrado. Detalle completo:
`LIQUIDITY_REGIME_ROUND27.md`.

---

## Priorización (Round 26, 2026-09-24) — liquidation cascade bloqueada (Caso C), pivote a régimen de liquidez

**Liquidation cascade: CERRADO Caso C** — auditoría directa muestra solo
48.5 horas de cobertura real (colector caído desde 2026-09-11, no
reiniciado), venue Bybit (no Binance, mismatch con el resto del proyecto),
y sin forma de reconstruir histórico (Binance dio de baja el endpoint
globalmente). No reabrir sin que el usuario reinicie el colector y/o
acumule 60+ días limpios. **Pivote a 22:00 UTC con hallazgo nuevo**: la
hora es la segunda más tranquila del día (volumen 0.76× promedio), no una
transición de sesión de alta actividad como se asumía en R19-R21 —
consistente con mecanismo de iliquidez temporal, no evento informado.
Prioridad #1 para R27: testear régimen de liquidez trailing causal
(por símbolo) en vez del filtro rígido de hora. Detalle completo:
`LIQUIDATION_CASCADE_ROUND26.md`.

---

## Priorización (Round 25, 2026-09-24) — SHORT BIAS CERRADO: era beta, no alfa

**El "sesgo bajista de altcoins" de R12/R13/R15/R18/R24, investigado
directamente, resultó ser BETA a un mercado cripto que cayó ~38% durante
toda la ventana del dataset (BTC: $104,545→$64,504, 2025-06→2026-08) —
BTC solo, sin ninguna selección de altcoins, ya es negativo y
significativo en TRAIN/VAL/OOS. No es un mecanismo alt-específico
reutilizable, es la misma familia que "beta betting" (ya FAILED en R13).
**CERRADO definitivamente — no volver a interpretarlo como confound ni
como estrategia.** No se construyó sim económica: el mecanismo quedó
identificado antes de esa etapa. Próximo: R26 = liquidation cascade
(familia 4) o microestructura de 22:00 UTC investigando el fenómeno
subyacente (familia 6) — únicas familias de prioridad sin tocar con el
motor corregido de R23. Detalle completo: `SHORT_BIAS_ROUND25.md`.

---

## Priorización (Round 24, 2026-09-24) — CASO B: confounder recurrente x5, pista fuerte para R25

**5 hipótesis nuevas (evento extremo fade/continuación, doble shock,
drop+recuperación parcial, ruptura fallida vs control, relativo
cross-sectional 4h) — todas FAILED**, pero 3 de las 5 (H1-UP, H1-DOWN, H3)
colapsan al MISMO confounder: un sesgo estructural bajista persistente del
universo de altcoins que el placebo temporal reproduce casi exacto —
**quinta aparición independiente** (R12, R13, R15, R18, R24), esta vez sin
depender de una ventana temporal específica, lo cual lo hace más creíble
como fenómeno real de mercado (emisión/dilución de altcoins chicas) que
como artefacto de 2026Q3. H4 resuelve la pista abierta de R23 (el efecto
era magnitud del movimiento, no la "falla" del breakout específicamente).
Prioridad #1 para R25: testear el drift DIRECTAMENTE como candidato
(canasta short no-condicionada) con el motor corregido de R23, control
LONG-vs-SHORT + partición temporal (no placebo temporal). Detalle
completo: `ALPHA_DISCOVERY_ROUND24.md`.

---

## Priorización (Round 23, 2026-09-24) — LAB ARREGLADO, CAPITULACIÓN SIGUE CERRADA

**Motor corregido**: `agent/backtest/portfolio_engine.py` (regla de
asignación determinística: score desc + symbol ASC tie-break), 6/6 tests
sintéticos PASS, order invariance confirmada (100 seeds, std=$0.00). El
swing de $145/mes de R22.5 se corrige de entendimiento: no era un bug de
orden, era una comparación entre dos reglas de asignación distintas nunca
declaradas explícitamente. **R21 recalculado con funding real (63/357
símbolos con dato propio, resto mediana causal) = $169/mes** — cruza el
umbral numérico, pero los hallazgos de inestabilidad temporal de R22
(walk-forward, régimen, generalización de score) usan la misma regla y
siguen vigentes. **CAPITULACIÓN SIGUE CERRADA, FAILED.** Discovery nuevo
(volatility transition follow-through) también FAILED — dirección mal
orientada ya en TRAIN. Pista sin confirmar: reversión post-ruptura
genérica, misma firma que el drift estructural de R12/R13/R18 — necesita
control de magnitud emparejada antes de creerse. Detalle completo:
`FIX_THE_LAB_ROUND23.md`.

---

## Priorización (Round 22.5, 2026-09-24) — AUDITORÍA, NO ALPHA

**BACKTEST STATUS: C) PARCIALMENTE CONFIABLE — componentes específicos
fallan.** Antes de R23 (liquidation continuation u otra hipótesis) hay que
resolver, en orden: (1) **slot competition FAIL** — el orden de
procesamiento de candidatos concurrentes movió el resultado del candidato
de capitulación de $171/mes a $26/mes (−85%) sin cambiar nada más; toda
sim económica futura con competencia de slots debe reportar ≥2 órdenes de
procesamiento distintos; (2) **funding FAIL** — R18-R22 nunca incluyeron
funding pese a holdings de hasta 24h; (3) **survivorship FAIL** — el
universo de 450 símbolos viene del watchlist ACTUAL del agente, no de una
reconstrucción histórica, así que ningún deslisteado está presente
(documentar esto en todo reporte futuro, no reconstruible sin datos
externos). Lookahead/timestamp/joins de OI-funding = PASS (verificado con
tests automatizados). Real-vs-replay = INSUFFICIENT DATA (no hay operativa
real ni un registro de producción comparable). Detalle completo:
`R22_5_BACKTEST_REALITY_AUDIT.md`.

---

## Priorización (Round 22, 2026-09-24)

**CAPITULACIÓN + SCORE-SELECT (R18→R21) = CERRADA, FAILED.** Auditoría
adversarial (walk-forward 14 meses completos, régimen sin lookahead fit
solo en TRAIN, score-select probado por sub-período separado) mató el
candidato que en R21 había tocado $150/mes: (1) walk-forward completo
muestra 9/14 meses positivos dominados por 5 meses outlier, los otros 9
suman neto negativo; (2) el régimen óptimo-en-TRAIN (BTC-rv trailing-30d)
aplicado hacia adelante activa la estrategia en los 3 PEORES meses de
VAL+OOS — descriptivo, no predictivo; (3) score-select probado por mitad
separada NO es consistentemente mejor que FIFO/random — en la 2da mitad
random-selection le gana. El "10× de mejora" de R21 era artefacto de
mezcla de períodos. No se rescata con otra variable. Prioridad #1 para R23:
familia C (liquidation continuation) o F (secuencia price+OI+volumen+
liquidación, distinta de capitulación) — nunca probadas formalmente.
Detalle completo: `CAPITULATION_AUDIT_ROUND22.md`.

---

# VERGE — ALPHA HYPOTHESIS LEDGER

**Fecha de apertura:** 2026-09-06
**Regla:** cada experimento (incluso los que no llegan a nada) se registra
acá. Ningún edge se declara en Discovery (Fase 3). Un FAILED se cierra; no
hay sub-variantes de rescate salvo hipótesis causal **independiente**.

Numeración: H1–H12 = legacy (ver `RESEARCH_RESET_PLAN.md §1.1`). El reset
abre **H13–H20**.

---

## Formato de cada entrada (obligatorio)

```
ID
Familia de mecanismo
Mecanismo económico (por qué DEBERÍA existir un edge, en términos de flujo)
Predicción causal (dirección + horizonte + magnitud esperada en bp)
Variables (input, todas con su fuente y su lag de disponibilidad)
Horizonte de evaluación
Población (universo de símbolos + filtro de liquidez + período)
Controles (placebo temporal, muestra matcheada sin-evento, residualización)
Hipótesis nula (H0)
Datos requeridos + estado de disponibilidad
Prior de PASS (LOW / MED / HIGH) + justificación
--- se completa al ejecutar ---
Resultado (números crudos, todos los splits)
Decisión (CONTINUE a Fase 4 / FAILED / PARK — gateado por datos)
```

---

## Priorización (actualizada Round 20, 2026-09-23)

**Round 20 (EXECUTION ALPHA + REALISTIC FILL):** `agent/backtest/r20_execution.py`.
Ataca el hallazgo de R19 (hora UTC + compresión) con ejecución realista. Se
encontró y corrigió un bug real de signo (dirección invertida) antes de
reportar. Costo descompuesto explícitamente (1 pata, no el modelo de 2 patas
de R16/R17): taker fee5+spread3+slip4=12bp/lado→24bp RT; maker fee2+resid1=
3bp/lado→6bp RT SI llena.

| Test | Resultado |
|---|---|
| Familia horaria (dirección fijada en TRAIN) | Solo H=22 UTC consistente y creciente en VAL(+6.6bp)/OOS(+14.1bp) de las 6 horas probadas |
| Maker fill mecánico (no asumido) | 71.7% observado; filled-only gross=3.79bp vs taker-todas gross=15.0bp → **selección adversa real y medida (4× más chico)** |
| Timing de entrada | óptimo = exactamente en la señal, ninguna ventana lo rescata |
| TP/SL desde TRAIN | mejora WR a 0.56 OOS pero taker cost sigue devorando gross |
| Sim económica (12 configs) | **TODAS negativas**; mejor caso −$4/mes (maker, $150, 5 slots) |

**VERDICT: FAIL — pero informativo.** Maker realista redujo la pérdida de
−$9/−29 (taker) a −$4/−14 (maker) — la ejecución SÍ importaba, cerró parte
de la brecha, pero no toda. Ni "costo demasiado conservador" ni "señal
demasiado chica" por sí solos explican el fallo — es la combinación, y con
ambos corregidos sigue faltando.

**MAX VALIDATED MONTHLY PNL: $0** (11 rounds consecutivos, R10-R20).

**Próximo experimento (Round 21, único):** re-auditar los mejores casi-PASS
anteriores del proyecto (R18 capitulación N=5/12h, R10 dOI-régimen-UP) bajo
el costo maker AHORA VALIDADO (~6-9bp con fill mecánico + selección adversa
medida, no 24bp genérico) — no requiere señal nueva, solo re-medir economía
conocida con el costo correcto.

---

## Priorización (Round 19, 2026-09-22)

**Round 19 (TEMPORAL MICROSTRUCTURE + EXECUTION):** `agent/backtest/r19_temporal.py`.
Universo ancho, placebo aplicado desde el diseño (lección de R18).

| Track | Efecto | Placebo | Veredicto |
|---|--:|---|---|
| A — hora del día | −7.74bp (22:00 UTC) | **NO reproduce** (shuffle max 2.2-2.4bp, real 3.2× más grande) | **FAIL por magnitud** (<24bp costo) + inestable TRAIN(+0.5)/VAL(−9.9)/OOS(−11.5) |
| B — ventana funding settlement (reloj universal 00/08/16 UTC) | −2.67bp incremental (±15min) | firma limpia, monótona, vol. realizada sin cambio | **FAIL por magnitud** (2bp << 24bp costo) |
| D — hora 22:00 × compresión previa | **−12.32bp** (el mayor de la ronda) | interacción genuina (vs −8.6bp "ninguno") | **FAIL por magnitud** (sigue <24bp) |
| C — reversión sobre-reactores tras shock | +4.77bp CI incl 0 | — | **FAIL sin efecto** |

**Hallazgo central:** a diferencia de R12/R13/R18, el placebo **NO** reproduce
el efecto de Track A — hay estructura horaria genuina (probabilidad de
breakout/expansión de volumen SÍ varía por hora, pico 13-15 UTC). El problema
no es ausencia de mecanismo — es que el mejor efecto de toda la ronda
(−12.3bp) es la mitad del piso de costo (24bp RT). **Confirma que la fricción
de ejecución, no la falta de señal, es el techo real del proyecto.**

**MAX VALIDATED MONTHLY PNL: $0** (10 rounds consecutivos, R10-R19).

**Próximo experimento (Round 20, único):** atacar el COSTO, no la señal —
modelar ejecución con órdenes límite (maker, ~2bp vs 5bp taker) + probabilidad
de fill realista (no 100%) para los candidatos casi-PASS de R18/R19
(capitulación N=5/12h, hora 22:00+compresión). Si el piso baja de 24bp a
~10-12bp, podrían cruzar a positivo sin señal nueva. Nunca se giró esta
palanca en 19 rounds.

---

## Priorización (Round 18, 2026-09-21)

**Round 18 (ALPHA HUNT: BREAK THE FRAME):** `agent/backtest/r18_discovery.py` +
`r18b_capitulation.py`. Universo ancho (357 símbolos). Cambio de modo:
secuencias + MFE/MAE + reacción-no-predicción, no factores aislados.

| Mecanismo | Veredicto |
|---|---|
| Compresión → expansión (breakout) | **FAILED** — no continúa en promedio, control sin compresión ≈ igual, TRAIN/VAL/OOS inestable |
| **Capitulación (drop+volumen climax) → continuación SHORT** | **FAILED tras auditoría profunda** — +87.5bp OOS con altísima frecuencia (n=67k) y baja concentración (quitar top-20 símbolos solo baja a +50bp) parecía el mejor resultado del proyecto, PERO: VAL≈0 (inestable), y el **placebo random-timestamp (SHORT sin ninguna condición) ya da +30bp CI excl 0** — es el mismo drift estructural del universo re-confirmado por 3ª vez (R12→R13→R18). Aun ignorando eso, capital/concurrencia limita la captura a <6% de eventos con NET/mes negativo en 7/8 configs. |
| Rezagados tras movimiento amplio (Familia C) | **FAILED** — sin efecto, cercano a H18 ya fallado |
| Listing events | descartado en minutos (evaluación rápida per brief) — universo de eventos limpios insuficiente (~20-38), ya confirmado en R7/R8 |

**LEAD NUEVO SIN EXPLOTAR:** efectos de hora del día (Familia H) — varias
horas UTC muestran retorno medio con CI excl 0 sobre ~62k observaciones
(18:00 −9.9bp*, 22:00 −9.7bp*, 13:00 −5.7bp*), nunca antes probado, barato de
auditar con el mismo rigor (placebo, TRAIN/VAL/OOS, sim económica).

**MAX VALIDATED MONTHLY PNL: $0** (9 rounds consecutivos, R10-R18).

**Próximo experimento (Round 19, único):** hora del día / sesión con rigor
completo — TRAIN/VAL/OOS, placebo random-timestamp/time-shift (el mismo test
que mató al hallazgo de R18, aplicado desde el principio esta vez), sim
económica ≤450. Si también falla: familias A-I del brief de R18 quedan
agotadas.

---

## Priorización (Round 17, 2026-09-20)

**Round 17 (CHRONIC FUNDING YIELD ATTACK):** `agent/backtest/r17_chronic_funding.py`.
Mismo universo real de R16 (43 símbolos). Histéresis (enter/keep thresholds) en
vez de re-ranking diario — ataca directamente la causa de fallo de R16
(turnover). Holding 7/14/30/60/90d, selección A(threshold)/B(magnitud)/
C(persistencia-score), N=1..10, capital 150/300/450.

**VERDICT: FAIL.** Turnover SÍ se resolvió (15-45 trades en 8.5 meses vs
599-1400 de R16; fees cayeron ~30×, de $20-40/mes a $1-4/mes). **Pero el
funding capturado también cayó a ~$0** — el sesgo "crónico" es real mirando
hacia atrás (t-stats 30-340 en la media rolling) pero NO predice el funding
forward a 30-90 días: **el placebo random-selection reproduce el resultado
casi exacto** (fund/mes $0.0 random vs $0.1 real) → criterio de FAIL explícito
cumplido literalmente. No hay zona de holding rentable en todo el rango 7-90d
(7d: fees dominan de nuevo; 60-90d: fees bajas pero funding también ≈0). No
depende de 2026Q3 (consistentemente ~$0 en TRAIN/VAL/OOS/ex-Q3/solo-Q3).

**Causa exacta:** decaimiento de la señal, no turnover. La correlación
trailing-vs-próximo-settlement de R16 (0.82 a 8h → 0.68 a 7d) sigue cayendo; a
30-90d ya no queda información utilizable, incluso para los símbolos más
"crónicos" del universo.

**Funding carry (ambas variantes, R16 alto-turnover y R17 bajo-turnover)
queda CERRADO — no hay tercera variante que probar.**

**MAX VALIDATED MONTHLY PNL: $0** (8 rounds consecutivos, R10-R17).

**Próximo experimento (Round 18, único):** listing events con fecha verificada
— único mecanismo de ~50 probados nunca refutado por evidencia, solo
bloqueado por calidad de dato (R7/R8: el primer kline no es fecha de listing
confiable). Plan: WebFetch sobre anuncios públicos de Binance (no la API
baneada) para fechas verificadas, cruzar con `klines_clean` para separar
listings reales de artefactos de colección, correr el event-study de
reversión post-listing con fechas limpias.

---

## Priorización (Round 16, 2026-09-19)

**Round 16 (FUNDING CARRY ATTACK):** `agent/backtest/r16_funding_carry.py`.
Universo real (funding∩spot∩perp) = 43 símbolos, 8.5 meses. Estructura A (LONG
SPOT+SHORT PERP, funding positivo) OPERABLE, probada en 20+ configuraciones
(N, rebalanceo, trailing, ponderación, capital, leverage). Estructura B (SHORT
SPOT+LONG PERP, funding negativo) NO OPERABLE (sin borrow-rate), solo
diagnóstico matemático descartado.

**VERDICT: FAIL.** 0/9 meses positivos en TODAS las configuraciones, sin
excepción. Mejor caso: −$7.2/mes (cap $150, lev 1x). Causa exacta: fees (dos
patas spot+perp, 46bp RT) superan al funding capturado por 5-20× en cada
config. Persistencia del funding individual es real (corr 0.82 a 8h) pero el
RANKING cross-sectional rota cada ~36h (duración media de racha de signo),
forzando turnover que las fees castigan. No depende de 2026Q3 (excluirlo
empeora el resultado, −$31.8 vs −$28.2). Placebo random peor que ranking real
(−$38 vs −$28) — el ranking SÍ aporta señal, pero insuficiente para cubrir el
costo estructural de 2 patas.

**MAX VALIDATED MONTHLY PNL: $0** (7 rounds consecutivos, R10-R16).

**Próximo experimento (Round 17, único):** funding carry de BAJO TURNOVER
("chronic yield") — símbolos con funding estructuralmente sesgado durante
MESES (no la última semana), rebalanceo mensual/trimestral en vez de
diario/horario. Ataca directamente la causa raíz de R16 (turnover destruye el
yield) sin cambiar el mecanismo. Si también falla: pivotar a listing events con
fecha verificada (bloqueado en R7/R8 solo por calidad de dato, nunca por
mecanismo).

---

## Priorización (Round 15, 2026-09-18)

**Round 15 (WIDE UNIVERSE DISCOVERY, ~357 pares):** `agent/backtest/r15_wide_discovery.py`.
Primera vez usando el universo ANCHO (no restringido a 45-63 con OI/funding).
6 hipótesis (familias A/B/C del brief), screening vs random + oracle.

**VERDICT: FAILED (las 6).** Ninguna supera el screening pre-registrado en
TRAIN. Limitación de datos real descubierta: `taker_flow` para los ~300 símbolos
fuera del universo OI-completo solo cubre 2025-12→2026-08, y la mayoría listó
en 2026 → el grid ≥50-símbolos-válidos solo arranca en abril-2026 → **el OOS
(jul15-ago17) coincide casi exactamente con 2026Q3**, la ventana anómala ya
aislada en R13/R14. Cualquier lectura OOS "positiva" está contaminada por
construcción, no es evidencia válida per el propio criterio del round.

**Hallazgo confirmado:** el universo ancho SÍ amplifica la magnitud bruta
(momentum TRAIN pasó de +4.5bp/45sym a +42.5bp/357sym) pero NO la estabilidad —
la ganancia sigue viviendo en la pata short dominada por eventos extremos
(mismo patrón "placebo gana" de R13), no en selección real.

**HALLAZGO NUEVO (no una variante de nada anterior):** funding-rate carry
(cash-and-carry, no direccional). Dispersión de funding persistente y grande
entre símbolos (ej. HOMEUSDT −8.5bp/8h ≈ −93%/año, BTWUSDT +4bp/8h ≈ +44%/año)
sobre cientos de observaciones — nunca testeado como fuente de yield (solo como
predictor direccional en H16/R12, que falló). `spot_klines` (240 símbolos)
permite construir el hedge.

**MAX VALIDATED MONTHLY PNL: $0** (sin cambios).

**Próximo experimento (Round 16, único):** funding-rate carry delta-neutral
(spot-perp), portfolio top-N por funding trailing con signo, costos de ambas
patas + financiamiento, TRAIN/VAL/OOS excluyendo 2026Q3 aparte. Si tampoco
alcanza $150/mes: ambas categorías de mecanismo (predictivo y carry) quedarán
agotadas con evidencia — recién ahí corresponde una conclusión formal.

---

## Priorización (Round 14, 2026-09-17)

**Round 14 (ALTCOIN CROSS-SECTIONAL DISCOVERY):** `agent/backtest/r14_discovery.py`,
sin descargas nuevas, 45 símbolos feature-completos. Grid 4h, 1452 rebalanceos.
9 scores de interacción predeclarados + 2 baselines (momentum/vol-only) + 1
oracle (sanity). Screening TRAIN @24h vs random-ranking.

**VERDICT: FAILED (las 10 hipótesis).** Ninguna interacción supera al random-
ranking con signo correcto. Oracle (+298bp) confirma que el motor de ranking
detecta separación real cuando existe → resultado nulo genuino, no bug. Los 2
únicos con CI excl 0 (`S1_expansion_OI`, `vol_only`) tienen signo perdedor. El
único con tendencia OOS "positiva" (`momentum_only` @72h) se desarma por
pata/N (mismo evento de dispersión 2026Q3 aislado en R13, no prima estable).

**MAX VALIDATED MONTHLY PNL: $0.**

**Qué aprendimos:** 14 rounds, ~40 mecanismos (precio/taker/funding/OI nivel-
aceleración/L-S retail-vs-smart/beta/momentum/dispersión/interacciones cross-
sectional) sobre 15m-72h no producen alpha capturable en este universo. El
único "retorno grande" del dataset sigue siendo el evento de dispersión de
2026Q3, que ningún mecanismo anticipa ex-ante.

**Próximo experimento (Round 15, último, 2 partes):** (1) retest acotado de los
mejores candidatos previos (dOI-UP R10/11, momentum_only-72h R14) EXCLUYENDO
2026Q3 — test de robustez, no cherry-pick. (2) Si no produce nada (esperable):
veredicto final con evidencia de que ≥150 USDT/mes no es alcanzable con
datos/universo actuales, y qué inversión de datos haría falta para reabrir la
búsqueda — decisión del usuario, no de otro round.

---

## Priorización (Round 13, 2026-09-16)

**Round 13 (DRIFT ALTS vs BTC — market-neutral):** `agent/backtest/r13_altbeta.py`,
sin descargas nuevas. 45 símbolos, rebalanceo semanal (56 rebalanceos), beta
causal 30d vs BTC + hedge explícito a beta-neto-0, residual-momentum 14d, ambos
sentidos, placebo de bucket aleatorio.

| Hipótesis | Veredicto |
|---|---|
| **Betting-against-beta** (long low-β / short high-β, cubierto) | **FAILED** — OOS −1310 bp inestable (se invierte según dirección elegida); **placebo aleatorio (+149.5bp, PF 1.74) igual o mejor** que el portfolio real; sim económica −$16 a −$48/mes en todas las variantes (1x-3x lev). |
| **Residual-momentum cross-sectional** | **FAILED** — mismo patrón: OOS −506bp inestable, placebo mejor, sim económica −$11 a −$32/mes. |

**Hallazgo:** el drift que contaminó R12 no era beta ni momentum — es
**dispersión cross-sectional extrema concentrada en las últimas 6 semanas del
dataset (2026Q3)**; cualquier book long-short (elegido bien, mal, o al azar) la
captura igual. El componente de *selección* (ranking) no aporta nada; $450 con
11 patas semanales además es capital-ineficiente (nocional $41-123/pata, costo
24bp/sem pesa fuerte).

**MAX VALIDATED MONTHLY PNL: $0** (mejor backtest real: −$11/mes).

**Próximo experimento (Round 14, único):** **dispersion-regime timing** — exponer
el book long-short solo en semanas de dispersión cross-sectional anormalmente
alta (medida causal, ex-ante), plano el resto del tiempo. Ataca directamente lo
que R13 reveló: el edge (si existe) está en el timing de exposición, no en el
símbolo elegido. Mismo rigor, kill inmediato si el placebo lo reproduce.

---

## Priorización (Round 12, 2026-09-15)

**Round 12 (SMART MONEY DIVERGENCE → ECONOMIC ALPHA):** `agent/backtest/r12_smartmoney.py`,
sin descargas nuevas (14.5 meses ya ingeridos). Universo 45 símbolos (igual R11).

| Mecanismo | Verdict Round 12 |
|---|---|
| **Retail vs Smart-Money divergence** (`z(global_ls_acct) − z(toptrader_ls_pos)`, percentiles P90-99, ambos lados) | **FAILED** — signo se invierte TRAIN/VAL/OOS; **placebo positivo explícito** (matched-control/time-shift/random-ranking reproducen el efecto casi exacto); regresión incremental `ΔR²(D)=0.00001` (t significativo solo por n grande, cero economía); sim económica: 15/16 configs pierden dinero, mejor caso +$29/mes con mediana mensual negativa. |
| **OI Acceleration** (2da diferencia de dOI, confirmado/divergente con precio) | **FAILED** — mismo patrón: signo no estable TRAIN/VAL/OOS, mejor caso +$35/mes (dirección fijada por TRAIN, evaluada en VAL+OOS) con mediana mensual negativa. |

**Hallazgo metodológico:** en ambos mecanismos el retorno forward crudo de eventos
extremos es sistemáticamente negativo y **los tres placebos lo reproducen casi
exacto** → es el drift estructural del universo (altcoins medianas/chicas
depreciándose en la ventana), no un efecto de posicionamiento. Confirma que el
protocolo de controles funciona (detecta y descarta correctamente).

**MAX VALIDATED MONTHLY PNL: $0.** Distance to target: $150.

**Próximo experimento (Round 13, único):** testear el **drift altcoin-vs-BTC como
prima de riesgo sistemática** (canasta corta de alta-beta financiada con BTC/USDT,
no un evento de señal) — es la pista que dejaron los placebos de R12. Mismo rigor.
Si tampoco alcanza $150/mes estable → declarar con evidencia que el objetivo no es
alcanzable con los datos/universo actuales antes de considerar fuente nueva.

---

## Priorización (Round 11, 2026-09-13)

**Round 11 (dOI ECONOMIC RESCUE-OR-KILL):** backfill ejecutado AHORA — `oi_metrics`
+ `klines_clean` 15m extendidos a **2025-06-01 → 2026-08-17** (14.5 meses) desde
`data.binance.vision`. Re-corrido EXACTO del test de régimen R10
(`agent/backtest/r11_stationarity.py`) sobre universo restringido a los **45
símbolos que ya cotizaban antes de TRAIN** (drop 18 listados a mitad de muestra,
incluidos LAB/ESPORTS/GIGGLE que eran top-concentración en R10). Estacionariedad
por mes/trimestre/mitad, OLS beta-control, leave-top-k, sim económica causal con
capital ≤450 + funding real.

| Ítem | Verdict Round 11 |
|---|---|
| **dOI efecto (H13-C A/D, SHORT)** | **FAILED** |

**Por qué FAILED (la extensión de historia lo EMPEORÓ, no lo rescató):**
1. **Estacionariedad FAILED:** el signo del efecto @4h cambia mes a mes (−26 bp
   jul-2025 → +46 bp ago-2026, cruza 0 ≥4 veces) y **era del signo opuesto antes
   de 2026**: régimen UP mitad-1 = **−12 bp**, mitad-2 = **+54 bp**; jul-2025 UP =
   −75 bp. Lo de R9/R10 era un fenómeno de la 2ª mitad de 2026.
2. **Concentración FAILED:** aun con 45 símbolos limpios, quitar top-5 baja el edge
   UP∪FLAT@4h de 12.2 → 3.7 bp (−70%).
3. **Magnitud económica FAILED:** sim causal `open[t+1]` + RT 24bp + funding real +
   capital ≤450: TODO pierde dinero salvo "solo UP" (post-hoc), que da máx
   **+$77/mes** < 150, tail-dependiente (P50 mensual +$27, P95 +$382).

**Conocimiento que queda:** existe asociación estadística real dOI↔retorno forward
en régimen UP (OLS `t(dOI) = −7 a −9`, replicada en 14.5 meses, ΔR² +1–2%) pero
con **signo económico NO estacionario** → no operable. **dOI MUERTO** — no se
rescata con features (prohibido por brief; el problema es el signo, no las
features).

**MÁXIMO PnL VALIDADO: $0/mes.** (paper máx ~$77/mes, no estacionario, post-hoc.)

**Próximo experimento (Round 12, único):** divergencia **posicionamiento retail vs
smart-money** — `global_ls_acct` (L/S de CUENTAS = retail) vs `toptrader_ls_pos`
(L/S de POSICIÓN de top traders). Ambos ya ingeridos, 5m, 14.5 meses, 45 símbolos.
Mecanismo económicamente distinto de ΔOI (participante obligado: retail crowdeado
que da liquidez de salida a top traders al liquidarse). Mismo rigor R10/R11, kill
inmediato si falla estacionariedad/capturabilidad. NO variaciones de dOI.

---

## Priorización (Round 10, 2026-09-12)

**Round 10 (dOI REGIME BREAK TEST):** `agent/backtest/r10_doi_regime.py` +
`r10b_econ.py`. Test de régimen de BTC (UP/FLAT/DOWN, threshold ±1.5% sobre BTC
trailing 24h, congelado) del efecto dOI de H13-C A/D. TRAIN/VAL/OOS, cluster
bootstrap, matched control por régimen, residual-BTC, OLS beta-control, placebo
de barras aleatorias por régimen, per-symbol leave-top-k, sim económica
`open[t+1]`.

| Ítem | Verdict Round 10 | Evidencia |
|---|---|---|
| **dOI efecto (H13-C A/D, SHORT)** | **PARK** (sin cambio de etiqueta, pero mecanismo re-entendido) | **La lectura R9 era incorrecta:** NO es beta de régimen bajista. El efecto SHORT vive en **BTC UP y FLAT** (+22/+38/+71 bp @2h/4h/8h, CI excl 0, placebo random-bars ≈ 0) y **desaparece en DOWN** (CI incluye 0). En **UP**: OLS `t(dOI)=−10.2`, ΔR²=+4.8% tras controlar BTC/mercado/momentum/vol → **evidencia incremental más fuerte del proyecto**. En **FLAT**: `t(dOI)≈0` → es beta-timing de la cesta, no dOI. |

**Por qué sigue PARK y no CANDIDATE (dimensiones que faltan):**
1. **Estabilidad temporal (bloqueo #1):** TRAIN (dic-2025→25-abr) ≈ 0 bp a 2h/4h en
   UP y FLAT; todo el efecto está en VAL+OOS (may–ago 2026). Signal no estacionario.
2. **Concentración:** quitar top-7 de 63 símbolos baja el efecto UPFLAT@4h de 42→7.5
   bp (−82%); mediana por símbolo 10 bp < costo 24 bp. FRAGILE.
3. **Magnitud "real":** mediana de trade NEGATIVA, WR<0.5, PF 1.1–1.24 → PnL de cola
   derecha, no edge por trade.
4. **FLAT (75% de eventos) no es dOI** → el dOI-alpha real queda en el régimen UP
   (n=1858, ~25% de eventos).

**Económico:** sim en papel $100–$500/mes @4h, pero mediana negativa + WR<0.5 +
~960 eventos/mes no capturables con ≤450 USDT → **NO se puede afirmar ≥150
USDT/mes**. No promovible.

**Próximo experimento (Round 11, único):** TEST DE ESTACIONARIEDAD. Backfill de
`oi_metrics` + klines 15m **hacia atrás** desde `data.binance.vision` (métricas
existen ≥2025-11; intentar 2025-06→11) y re-correr EXACTAMENTE el test de régimen
R10 con **universo restringido a los ~40 símbolos que ya cotizaban en dic-2025**
(elimina el vaciado de TRAIN por los ~20 listados a mitad de muestra). Criterio
único: si el efecto UP/FLAT-SHORT sigue apareciendo solo post-abr-2026 en ventana
≥12 meses con universo limpio → **FAILED** (no estacionario). Si aparece parejo
TRAIN/VAL/OOS → re-evaluar concentración → recién ahí CANDIDATE. `toptrader_ls_pos`
/ `global_ls_acct` / aceleración OI / ML: **congelados** hasta resolver esto.

---

## Priorización (Round 9, 2026-09-11)

**Round 9 (OI HISTORICAL ALPHA HUNT):** backfill de OI 5m + funding 8h histórico
(dic-2025→ago-2026, 63 símbolos ex-ante) desde `data.binance.vision` a tablas
`oi_metrics` / `funding_hist` en `binance_vision_clean.db` (validado: 0 filas
off-grid, reconciliado vs colector live a <0.01 bp). Panel 15m, 4 experimentos
(`agent/backtest/r9_oi_alpha.py`), TRAIN/VAL/OOS, cluster bootstrap, placebo,
matched control, OLS incremental, costo 20 bp.

| ID | Verdict Round 9 | Razón |
|---|---|---|
| **H13-C A** (p↓+OI↑) / **D** (p↑+OI↓) | **PARK** | efecto incremental de ΔOI real: matched-control (OI plano) ≈ 0 vs cuadrante −13 a −17 bp @2h; OLS `t(dOI)` hasta −7.7; residual-BTC ≈ raw; VAL y OOS mismo signo (ambos → DOWN). PERO: net-positivo solo a 4–8h; **ausente en TRAIN** (posible régimen); `symPos` 0.33–0.49; `conc` ~0.45; placebo filtra 30–40% a ≥8h. Ambos cuadrantes → SHORT (sesgo direccional). |
| **H13-C B** (p↓+OI↓) / **C** (p↑+OI↑) | **FAILED** | plano, CI incluye 0 en todos los horizontes. |
| **H15** (OI×taker×price, 8 estados) | **FAILED** | OLS: `t(z_tbr)` ≈ 0 a todo horizonte → el taker flow **no aporta nada** incremental sobre precio+OI. La premisa (taker discrimina continuación/exhaustion) refutada. Lo que sobrevive = el efecto de `dOI` (= H13-C). |
| **H16** (funding×OI) | **FAILED** | OLS `fwd ~ z_fund + dOI + retlong`: `t(z_fund)` nunca significativo; `retlong` (momentum 24h) domina (t hasta +30). OI aporta efecto residual solo a 15–30m. Funding extremo solo describe momentum del crowd; OI no aporta incremental sobre funding. |
| **M15** (reaction-beta persistente ante shocks BTC) | **FAILED** | persistencia corr(TRAIN,OOS)=0.61 (tendencia real) pero portfolio congelado: spread under−over OOS −2.6 bp @2h ≈ **ranking aleatorio −2.4 bp**; signo cambia por horizonte; `conc`=1.0 `symPos`=0 (los 7+7 símbolos se mueven todos juntos = crash del mercado, sin independencia cross-sectional); solo 21 símbolos califican; 242 shocks correlacionados. |

**Conclusión Round 9: el edge incremental de posicionamiento está 100% en `dOI`
(cambio de Open Interest) — NO en taker flow ni en funding (ambos con t≈0 en OLS).**
El efecto `dOI` (H13-C A/D) es real y reproducible VAL→OOS pero NO alcanza el
umbral económico (net solo ≥4h, ausente en TRAIN, concentrado, short-biased). →
**PARK**. Avance durable: OI histórico 5m ingerido + validado; H15/H16 cerradas.

**Próximo experimento (automático, Round 10):** test de régimen del efecto `dOI` —
recomputar H13-C A/D y el OLS de `dOI` separando barras por régimen de BTC
(up/down/flat). Kill si `dOI` solo predice en down/flat y se apaga/invierte en up
(= beta de régimen). Si sobrevive los 3 → análisis por símbolo + net con funding
real + entrada `open[t+1]` → recién ahí candidata. Sin explorar aún:
`toptrader_ls_pos` / `global_ls_acct` (ratios L/S) y aceleración de OI.

---

## Priorización (Round 8, 2026-09-10)

**Round 8 (M18 KILL-OR-CONFIRM):** reconstrucción causal y paranoica de M18
(`agent/backtest/r8_m18_kill.py`, 5m OHLCV, entrada `open[t0+1]`, universo
ex-ante de 35 accion/ETF US, 2 837 eventos, self-tests DST/feriados, cluster
bootstrap, TRAIN/VAL/OOS, 5 controles + OLS incremental, costos determinados
antes = ~26 bp RT).

| ID | Verdict Round 8 | Razón |
|---|---|---|
| **M18** perp equity tokenizada vs apertura RTH US | **FAILED** | (1) control C4 (misma señal, forward **+24h después**) reproduce el efecto entero (+12 bp @60m) → el open RTH no es incremental; (2) signo **se invierte** TRAIN+ / VAL− / OOS+; (3) `top5_conc` 0.8–1.0 en todos los estratos de liquidez (1–2 símbolos cargan el PnL); (4) mejor gross pooled +8 bp @30m vs costo RT ~26 bp → net −18 bp; (5) OLS `t(β_gap)` = 0.1–1.0 (no significativo); (6) monetización ≈ −$8/mes. NO monotonía en buckets de gap. **Cerrada — no más variantes.** |

**M18 era artefacto de:** barras 15m + entrada en el print de apertura (no
ejecutable, ~7–9 bp del "edge" vivía ahí) + cortes de tercil post-hoc + 3.5
meses dominados por su primera mitad.

**HALLAZGO DATA EXPANSION (verificado en vivo):**
`data.binance.vision/data/futures/um/daily/metrics/<SYM>/<SYM>-metrics-YYYY-MM-DD.zip`
es accesible desde este entorno (200, ZIP, sin tocar api/fapi). Contiene OI 5m
(base + USD) + top-trader L/S ratio + global L/S account ratio + taker buy/sell
vol ratio, para TODOS los perps, en la ventana congelada (dic 2025 → ago 2026).
**Desbloquea H13-C formal, H15 y familia OI HOY** (breadth completo + régimen
bajista real), sin esperar al colector live de octubre. Checklist de validación
en `M18_KILL_OR_CONFIRM_ROUND8.md`.

**Próximo experimento (automático, Round 9):** **M15** — factor de "reaction-beta"
persistente (ranking de over/under-reacción por símbolo ante shocks comunes,
¿persiste entre shocks?). Datos en mano. No es catch-up (H18) ni momentum (H8).

---

## Priorización (Round 7, 2026-09-10)

**Round 7 (BREAK THE SEARCH SPACE) — mecanismos con actor obligado, no indicadores. 4 experimentos:**

| ID | Mecanismo (1 línea) | Verdict Round 7 |
|---|---|---|
| **M10** | absorción de 1 barra: flujo taker masivo unilateral + precio ~0 → release/continuación | **FAILED** — efecto 1–3 bp (≪ 16 bp); matched-control "flujo que SÍ movió" domina (−1.7 a −6.8 bp); quiet-only reproduce; symPos < 0.5. `r7_m10_absorption.py` |
| **M11** | BTC 5m shock → catch-up de alts rezagados en 5–30 min (lead-lag mecánico sub-15m) | **FAILED** — efecto real +4 bp @5m pero `uncond` (todos los alts) ≈ `real` → es beta de mercado continuando, no lead-lag; 4× < costo; decae a 15 min. `r7_m11_btc_leadlag.py` |
| **M8a** | funding extremo en el settlement → unwind contra el lado que paga (exhaustion) | **FAILED** — placebo +48h y matched-control (funding central) reproducen 60–70% del número; es drift de un tramo alcista × convención de signo short; symPos 0.33. `r7_m8_funding_event.py` |
| **M8b** | funding sign-flip (cruce +↔−) → momentum de posicionamiento | **PARK** — hint @24h (+48 bp bruto / +32 bp tras costo, CI excl 0) pero placebo +48h da +24 bp (−50%), decae entre mitades (65→31), sólo 38 d de funding history. Re-testear con ≥90 d. |
| **M1** | listing forced-flow → reversión post-launch | **PARK (datos)** — el dataset no identifica el evento: los first-appearance se agrupan en el día 1 de cada mes (artefacto de colección); sólo ~20 listings crypto-native con firma limpia → n insuficiente. Necesita listing dates verificados (Binance announcements + CoinGecko). |
| **M18** | perp de acción tokenizada vs apertura del cash US (13:30 UTC) → convergencia | **PARK (lead vivo)** — reversión +10 bp @30–60m, CI excl 0, placebo-mediodía limpio, **escala monótonamente con el tamaño del gap** (t2 gap grande: +25 bp @60m). Pero < 16 bp costo genérico, concentrado (top5 ~0.5), decae entre mitades, 3.5 meses. `r7_m18_rth_open.py` |

**Conclusión Round 7: NO PROMISING — 3 FAILED, 3 PARK.** NO es "no alpha found":
M18 es un lead con firma de mecanismo real (efecto escala con el gap, placebo
limpio), sólo bloqueado por el supuesto de costo genérico. M1/M8b/H13-C/H14/H15
están gateadas por datos que se acumulan o son **backfilleables desde
`data.binance.vision`** (metrics/ = OI histórico, fundingRate/ = funding ≥90d)
sin tocar la API baneada. **Próximo experimento decidido:** re-correr M18 en 5m
con fees reales de los contratos de equity tokenizada + subset líquido +
condicionar el signo del gap vs la última sesión RTH. En paralelo: verificar el
backfill de `data.binance.vision/metrics` y `/fundingRate`. Ver
`ALPHA_HUNT_ROUND7.md`.

---

## Priorización (Round 6, 2026-09-09)

**Round 6 (ADVERSARIAL ALPHA HUNT) — 4 hipótesis condicionales nuevas, todas cerradas:**

| ID | Mecanismo (1 línea) | Verdict Round 6 |
|---|---|---|
| **H21** | volume-climax + one-sided + sin follow-through → reversión | **FAILED** — efecto −1.6 a −5.8 bp (el climax continúa, no revierte); CI incluye 0; placebo ≈ real; control CON follow-through +8 a +21 bp (el conditioning es anti-predictivo). `r6_adversarial_screen.py` |
| **H22** | agresión taker vs precio realizado (divergencia) → reversión | **FAILED** — el +72 bp @60m del screen era **LOOKAHEAD** (`np.convolve(...,'full')[W-1:]` sumaba 3 barras futuras de taker). Limpio (`r6_h22_validate.py`, entrada a open[t+1], slippage explícito): BULL inexistente (−0.5 a −8 bp), BEAR +6 bp @15m con CI apenas > 0, front-loaded (tercio 1 = 13 bp, tercios 2-3 = 2-5 bp), symPos 0.56. Monetización BULL ≈ −$28/mes, BEAR ≈ −$20/mes. |
| **H26** | vol-expansion + taker confirmation → continuación | **FAILED** — efecto −1 a −7.3 bp (< costos); el flujo taker no discrimina continuación de reversión (confirmado ≈ divergente). `r6_adversarial_screen.py` |
| **H23** | perp-taker apalancada / spot-price sin respaldo → reversión | **NOT VIABLE** — solo 78 sym con spot+perp+taker; `lev_long` 0 eventos en 7.6 meses, `lev_short` 4. En nombres líquidos perp y spot van arbitrados; la divergencia no se forma a 1h. `r6_h23_screen.py` |
| **H13-C majors** | ¿el squeeze del piloto (precio↓+OI↑) aparece en BTC/ETH/SOL? | **PARK (data-gated)** — 0 eventos: solo ~7 d de OI de majors, ventana z de 2 d no llega a ±1. `r6_h13c_majors.py` |

**Conclusión Round 6: NO ALPHA FOUND.** El plano OHLCV + taker-flow está agotado
también para estructuras **condicionales/interacción** (no solo señales continuas).
Los 3 planos locales (precio, flujo taker, funding/basis) no tienen alpha
monetizable. Falta: profundidad en OI/liquidaciones (en camino, oct–nov) o una
**fuente nueva** (OI multi-venue, opciones/greeks, on-chain serio) = decisión de
inversión del usuario. Próximo experimento decidido: **levantar colector de
taker-flow FORWARD** para desbloquear H15 cuando OI llegue a 70 d. Ver
`ALPHA_ADVERSARIAL_HUNT_ROUND6.md`.

---

## Priorización (Round 5, 2026-09-09)

| Prio | ID | Mecanismo (1 línea) | Estado | Datos | Prior |
|---|---|---|---|---|---|
| **1** | **H13-C** | precio↓ + OI↑ (shorts nuevos agresivos) → squeeze 1–4h | **PARK** — señal cruda limpia de placebo pero incremental IC cruza 0 | 36 d / 13 sym ≥90%; gate 70 d + falta régimen bajista → ~2026-10-13 | **MED** |
| — | H13 A/B/D | otros 3 cuadrantes | **FAILED** (2026-09-06, reconfirmado 09-09) — el placebo +48h reproduce el efecto | — | — |
| **2** | **H14** | cascada de liquidación → reversión si ΔOI<0 / continuación si ΔOI≥0 | **PARK** — protocolo congelado, sin datos | 0.6 d (`liquidations_research`); necesita ≥60 d → ~2026-11-08 | **MED-HIGH** |
| **3** | **H15** | evento conjunto OI↑ × taker-sell × precio↓ → squeeze | **PARK** | overlap OI×taker solo ~13 d (taker congelado 2026-08-17); **requiere colectar taker-flow forward** | MED |
| 4 | **H16** | funding extremo × OI en máx de 72h → carry unwind | PARK | ~36 d overlap; necesita ≥90 d → ~2026-12 | LOW-MED |
| — | **H18** | shock de BTC → catch-up de alts rezagados | **FAILED** (Round 5) — laggard +6bp@1h (<costo), −13bp@4h contra dirección, inestable | ya (8.5 m OHLCV) | — |
| 6 | **H17** | compresión de vol → expansión con persistencia direccional | NOT RUN | ya (OHLCV) | LOW (sanidad) |
| 7 | **H19** | OFI en la ventana del evento de flujo forzado | PARK | gateado por H13/H14 | LOW |
| 8 | **H20** | dinámica de OI en perps jóvenes | PARK | thin | LOW |

**Estado Round 5:** la única familia con ortogonalidad real + datos
acumulándose es **OI / forced-flow (H13/H14/H15)**, y las tres están gateadas
por profundidad de datos. H18/H17 son screens de sanidad sobre OHLCV (prior
bajo). Ver `ALPHA_DISCOVERY_ROUND5.md` para el mapa completo y la cola de
investigación.

---

## H13 — OI / PRICE DIVERGENCE → FORCED DELEVERAGING / CROWDING

- **Familia:** positioning / crowding / forced deleveraging.
- **Mecanismo económico:** el precio dice *dónde* está el mercado; el Open
  Interest dice *cuánta posición apalancada* lo sostiene. Cuatro cuadrantes:
  - precio ↑ + OI ↑ → **longs nuevos entrando** (crowding) → frágil a un
    pullback que los liquida.
  - precio ↑ + OI ↓ → **short covering** → el combustible se agota →
    exhaustion / reversión.
  - precio ↓ + OI ↑ → **shorts nuevos agresivos** → riesgo de squeeze.
  - precio ↓ + OI ↓ → **longs capitulando** (deleveraging) → puede continuar
    hasta que el OI se estabiliza.
  Ninguna de estas lecturas es derivable de OHLCV. Es información de estado
  ortogonal.
- **Predicción causal:** para el cuadrante "precio ↑ + OI ↓" (exhaustion),
  retorno forward a 4–24 h **negativo**, magnitud objetivo ≥ 15 bp neto de
  costos, cross-sectional (long los de OI↑/precio↓ estabilizado, short los de
  OI↓/precio↑). Direccional también evaluable.
- **Variables:** `ΔOI_%` sobre ventanas {1h, 4h, 12h, 24h}; `OI/volume`;
  `OI z-score` (rolling 7 d); retorno de precio sobre la misma ventana; signo
  de la divergencia (4 cuadrantes). Fuente: `open_interest` (5 m) +
  `klines_5m`. Lag: OI del período cerrado, sin lookahead.
- **Horizonte:** 4 h, 12 h, 24 h forward (retorno log, neto).
- **Población:** símbolos con OI ≥ 90% cobertura en el período (**45 hoy**,
  esperar ≥ 20 estables para el full) + liquidez ≥ $1 M / 15 m trailing-7d
  por barra (mismo filtro que H12). Período: todo el disponible al momento
  del run, con split temporal 50/25/25.
- **Controles:** (a) **residualizar** el retorno forward contra el retorno
  pasado de la misma ventana (quitar momentum/reversión pura de precio);
  (b) **placebo temporal**: repetir con OI desplazado +25 barras (si el
  "efecto" sobrevive al placebo, es régimen, no OI); (c) **muestra
  matcheada**: para cada evento de divergencia, un control con misma vol y
  mismo retorno de precio pero SIN divergencia de OI.
- **H0:** `partial_corr(señal_OI, ret_forward | ret_pasado) = 0` en los 3
  splits, y el placebo reproduce cualquier efecto.
- **Datos:** `open_interest` — 33.3 d hoy, **45 sym ≥90%**. Gate del test
  formal: **≥ 70 d, ≥ 20 sym, ≥ 90% cobertura** ⇒ ETA ~mediados oct 2026.
  Piloto de existencia posible ya (NO concluyente).
- **Prior:** **MED.** Es el único plano de datos genuinamente ortogonal con
  historia en camino. Pero el prior de todo el proyecto es bajo (H1–H12) y
  la historia corta limita los regímenes vistos.
- **Resultado:** _(pendiente)_
- **Decisión:** _(PARK hasta gate de datos; piloto permitido)_

---

## H14 — LIQUIDATION CASCADE: CONTINUATION vs LIQUIDITY VACUUM

- **Familia:** liquidation cascades / forced flow / liquidity vacuum.
- **Mecanismo económico:** una cascada de liquidaciones es flujo **forzado y
  observable** (`liquidations` los registra). Dos hipótesis rivales del post-
  cascada: (a) **continuación** — la cascada empujó el precio a un nivel que
  detona más stops/liq en la misma dirección; (b) **reversión por vacío de
  liquidez** — las liquidaciones barren el libro, el precio sobre-extiende y
  hay un rebote mecánico cuando entran los market makers. El signo probable
  depende del **tamaño relativo de la cascada vs la liquidez normal** y de
  si el OI **cayó** (deleveraging real, se agotó) o **no** (todavía hay
  posición forzable).
- **Predicción causal:** para cascadas grandes (suma de qty liquidada en una
  ventana de 5 m ≥ p95 del símbolo) con **caída de OI simultánea**, retorno
  forward 15–60 min con **reversión** ≥ 20 bp neto. Para cascadas sin caída
  de OI, **continuación**.
- **Variables:** intensidad de cascada = `Σ|qty·price|` liquidado en ventana
  de 5 m, normalizado por volumen 15 m trailing; lado dominante (Buy/Sell
  liquidations); `ΔOI` en la ventana; número de eventos discretos. Fuente:
  `liquidations` + `open_interest` + `klines_5m`.
- **Horizonte:** 15, 30, 60 min forward.
- **Población:** símbolos con feed de liquidaciones + OI. Filtro de liquidez.
- **Controles:** placebo temporal (ventana +2 h sin cascada); muestra
  matcheada por vol y retorno reciente sin cascada; separar por régimen de
  BTC (cascada idiosincrática vs market-wide).
- **H0:** el retorno forward tras cascada = el de la muestra matcheada
  sin-cascada (la cascada no aporta información sobre el retorno).
- **Datos:** `liquidations` — **7 d hoy**, 106 sym. Insuficiente. Necesita
  **~60–90 d** de acumulación continua ⇒ requiere que el colector siga
  corriendo y, posiblemente, que el usuario decida ampliarlo (¿captura todas
  las liq o solo un umbral?). **PARK.**
- **Prior:** **MED.** Mecanismo bien fundado y evento observable directo; el
  contra es que este edge es de los más buscados por otros ⇒ puede estar
  arbitrado en símbolos líquidos, vivo solo en la cola.
- **Resultado:** _(pendiente — gateado por datos)_
- **Decisión:** _(PARK)_

---

## H15 — JOINT EVENT: OI↑ × TAKER-SELL DOMINANT × PRICE↓ → SHORT SQUEEZE

- **Familia:** positioning / exhaustion / mean reversion after forced flow.
- **Mecanismo económico:** H12 mostró que el taker imbalance **solo** no
  predice nada. H11 probará OI **solo**. Pero el estado **conjunto**
  "precio cayendo + OI subiendo + los takers son netamente vendedores" =
  **shorts nuevos y agresivos apilándose en la caída**. Ese posicionamiento
  es unilateral y frágil: cualquier rebote fuerza cobertura ⇒ squeeze. El
  edge (si existe) está en la **conjunción**, que ningún test individual
  puede ver.
- **Predicción causal:** tras un evento conjunto (los 3 en su decil extremo
  simultáneamente, ventana 1–4 h), retorno forward 4–12 h **positivo**
  ≥ 20 bp neto.
- **Variables:** `ΔOI_%` (decil alto) ∧ `taker_sell_ratio` (decil alto) ∧
  `ret_precio` (decil bajo), todo sobre la misma ventana. Fuente:
  `open_interest` + `taker_flow` + `klines_5m`.
- **Horizonte:** 4, 8, 12 h.
- **Población:** intersección de símbolos con OI ≥ 90% y taker_flow.
- **Controles:** placebo temporal; muestra matcheada (mismo `ret_precio` y
  vol, sin el estado conjunto de OI+taker); **des-confounding**: verificar
  que el efecto no lo lleva solo el retorno de precio (reversión pura).
- **H0:** el efecto conjunto = suma de los efectos marginales (ya ≈ 0) ⇒
  no hay sinergia.
- **Datos:** gateado por OI (= H13). `taker_flow` sobra.
- **Prior:** **MED-LOW.** La conjunción es genuinamente no testeada, pero
  la tasa base de eventos triples-extremos será baja ⇒ poca muestra ⇒ riesgo
  de multiple-testing alto. Corrección de Bonferroni/BH obligatoria.
- **Resultado:** _(pendiente)_
- **Decisión:** _(PARK hasta H13)_

---

## H16 — FUNDING EXTREME × OI AT LOCAL HIGH → CROWDED CARRY UNWIND

- **Familia:** positioning / crowding / basis dislocation.
- **Mecanismo económico:** funding solo = marginal (AUC 0.539). Pero funding
  en su extremo **significa** que un lado paga caro por mantener la posición
  — y si además el **OI está en un máximo local** (mucha gente en ese lado),
  el carry es insostenible: el desarme (cierre de la posición crowdeada)
  mueve el precio contra ese lado.
- **Predicción causal:** funding en decil extremo positivo ∧ OI en máximo de
  ventana 3 d ⇒ retorno forward 8–24 h **negativo** ≥ 15 bp neto (los longs
  crowdeados que pagan funding se desarman). Simétrico para funding negativo
  extremo.
- **Variables:** `funding_rate` z-score (histórico corto), `OI` percentil en
  ventana 72 h. Fuente: `funding_rates` (8 h) + `open_interest` (5 m).
- **Horizonte:** 8, 16, 24 h.
- **Población:** símbolos con ambas series.
- **Controles:** placebo temporal; controlar por basis (para no re-descubrir
  H10); muestra matcheada por funding extremo **sin** OI alto.
- **H0:** funding extremo condicionado a OI alto no predice mejor que funding
  extremo solo.
- **Datos:** `funding_rates` 2 m ∩ `open_interest` 33 d ⇒ **overlap ~33 d, y
  el funding histórico limpio arranca 2026-07-07**. Muy poca muestra de
  eventos extremos. **PARK** hasta ≥ 90 d de overlap.
- **Prior:** **LOW-MED.** Interacción no testeada, pero cerca de H10 (que
  falló) y con la peor situación de datos del ledger.
- **Resultado:** _(pendiente)_
- **Decisión:** _(PARK)_

---

## H17 — VOLATILITY REGIME TRANSITION (COMPRESSION → EXPANSION) AS EVENT

- **Familia:** volatility regime transitions.
- **Mecanismo económico:** el OHLCV está agotado como señal continua, pero
  la **transición** de un régimen de vol comprimida a uno de expansión es un
  evento estructural (ruptura de rango, cambio de fase). La hipótesis: en el
  primer tramo de la expansión hay **dispersión cross-sectional predecible**
  — algunos símbolos lideran la expansión con dirección persistente.
- **Predicción causal:** cuando la realized vol de 4 h de un símbolo cruza de
  <p20 a >p60 de su distribución 14 d (evento de expansión), la **dirección**
  del primer movimiento de la expansión persiste 2–8 h con ≥ 20 bp.
- **Variables:** realized vol 4 h (Parkinson/close-to-close), percentil 14 d;
  dirección del retorno en la vela de cruce; ancho del rango previo. Fuente:
  `klines_5m` únicamente.
- **Horizonte:** 2, 4, 8 h.
- **Población:** universo completo, filtro de liquidez.
- **Controles:** placebo temporal; muestra matcheada por nivel de vol sin
  transición; **crítico**: comparar contra un breakout de rango puro de
  precio (para no re-descubrir momentum/breakout, ya en el grid FAILED).
- **H0:** el retorno post-transición = el de un breakout de precio de igual
  magnitud sin el componente de vol.
- **Datos:** listos (OHLCV 8.5 m).
- **Prior:** **LOW.** OHLCV está agotado; el framing de evento es lo único
  nuevo. Si da algo grande ⇒ **subir el escepticismo** (probable overfitting
  o re-descubrimiento de vol-targeting). Sirve sobre todo como **test de
  sanidad del pipeline de event-study**.
- **Resultado:** _(pendiente)_
- **Decisión:** _(candidato a arrancar como control de pipeline)_

---

## H18 — ALT CATCH-UP AFTER BTC SHOCK (BETA DISLOCATION, 15m–1h)

- **Familia:** BTC/alt lead-lag / market-wide risk transfer.
- **Mecanismo económico:** H9.1 (lead-lag) falló por resolución (sub-segundo).
  A escala 15m–1h y **condicionado a un shock de BTC** (|ret_BTC_1h| > p95),
  los alts que **no** se movieron con BTC en esa ventana: ¿es lag mecánico
  (van a catch-up) o fuerza idiosincrática (siguen su camino)? La respuesta
  probable depende de si el shock de BTC es risk-on/risk-off market-wide.
- **Predicción causal:** tras shock de BTC, alts con `beta_realizada_1h` muy
  por debajo de su beta 7 d ⇒ catch-up parcial en 1–4 h, ≥ 15 bp en la
  dirección del shock de BTC.
- **Variables:** `ret_BTC_1h` (evento si |·|>p95 30 d); por alt: retorno en
  la misma ventana, beta rolling 7 d, residual = ret_alt − beta·ret_BTC.
  Fuente: `klines_5m`.
- **Horizonte:** 1, 2, 4 h.
- **Población:** todos los alts líquidos.
- **Controles:** placebo (ventanas sin shock de BTC); separar risk-on vs
  risk-off; muestra matcheada por retorno propio del alt.
- **H0:** el residual no predice el retorno forward (los alts "rezagados" no
  hacen catch-up más que los "adelantados").
- **Datos:** listos.
- **Prior:** **LOW-MED.** Solapa con momentum/mean-reversion; el
  condicionamiento a shock de BTC es lo diferencial. También sirve de sanidad
  del pipeline.
- **Resultado:** _(pendiente)_
- **Decisión:** _(pendiente)_

---

## H19 — OFI IN THE EVENT WINDOW (NOT AS A CONTINUOUS FILTER)

- **Familia:** liquidity vacuum / continuation after forced flow.
- **Mecanismo económico:** OFI **como filtro promedio** falló (AUC 0.46). Pero
  en la ventana ±N min de un **evento de flujo forzado** (spike de OI de H13,
  cascada de liq de H14), el desbalance instantáneo del libro
  (`orderbook_ofi`) podría revelar de qué lado quedó el vacío de liquidez y,
  por lo tanto, la dirección del rebote.
- **Predicción causal:** en la ventana [evento, evento+15 min], `ofi` en su
  decil extremo (bid o ask barrido) ⇒ el precio revierte hacia el lado con
  más liquidez residual, ≥ 15 bp en 15–30 min.
- **Variables:** `ofi`, `bid_volume`, `ask_volume` en la ventana del evento;
  sincronizados al evento de H13/H14. Fuente: `orderbook_ofi` (30 d).
- **Horizonte:** 15, 30 min.
- **Población:** intersección de símbolos con OFI y eventos.
- **Controles:** placebo temporal; muestra matcheada de OFI extremo **fuera**
  de eventos (que ya sabemos que no predice — debe seguir sin predecir).
- **H0:** el OFI en la ventana del evento no aporta sobre el evento solo.
- **Datos:** `orderbook_ofi` 30 d, pero **~1 snapshot / 8 min** ⇒ resolución
  pobre para eventos rápidos. Gateado por H13/H14.
- **Prior:** **LOW.** OFI ya falló; la resolución del snapshot es un problema
  serio para timing de eventos.
- **Resultado:** _(pendiente)_
- **Decisión:** _(PARK)_

---

## H20 — OI DYNAMICS IN YOUNG PERPS (POST-LISTING INEFFICIENCY)

- **Familia:** market-wide risk transfer / structural inefficiency.
- **Mecanismo económico:** los perps recién listados tienen mercados
  inmaduros: pocos market makers, OI que se acumula de forma no estacionaria,
  funding volátil. Puede haber una ineficiencia estructural (p. ej. el primer
  gran desapalancamiento tras el listing es predecible) que desaparece cuando
  el mercado madura.
- **Predicción causal:** en los primeros 30 d de vida de un perp, un `ΔOI`
  negativo brusco (≥ p95) ⇒ continuación de la caída ≥ 25 bp en 4–12 h
  (deleveraging en un libro fino no rebota).
- **Variables:** edad del símbolo (desde primera vela), `ΔOI_%`, vol.
  Fuente: `open_interest` + `klines_5m`.
- **Horizonte:** 4, 12 h.
- **Población:** símbolos con < 30 d de historia en el momento del evento.
- **Controles:** comparar con el mismo evento en perps maduros (> 180 d);
  placebo temporal.
- **H0:** el evento en perps jóvenes se comporta igual que en maduros.
- **Datos:** parcial — la cobertura de OI es justamente peor en listings
  nuevos. **PARK** hasta tener más historia y más listings capturados.
- **Prior:** **LOW.** Muestra chica, sesgo de selección, difícil de escalar
  a 150 USD/mes con símbolos ilíquidos.
- **Resultado:** _(pendiente)_
- **Decisión:** _(PARK)_

---

## Reglas de gestión del ledger

- Cada corrida de Discovery agrega una fila de resultado con **todos** los
  splits y **todas** las variantes probadas (no solo la mejor).
- Una hipótesis pasa a Fase 4 solo si: partial corr |·| ≥ 0.03 estable en los
  3 splits **y** sobrevive el placebo temporal **y** sobrevive la muestra
  matcheada **y** la magnitud bruta ≥ 2× el costo round-trip estimado.
- FAILED se escribe en mayúsculas y se cierra. Reabrir requiere un mecanismo
  causal nuevo con su propio ID.
- Multiple testing: cuando se prueban K combinaciones señal×horizonte, aplicar
  Benjamini-Hochberg y reportar el q-value.
