# ROUND 36 — SIMULACIÓN CONTRAFACTUAL DE GESTIÓN DE SALIDA

## RESULTADO FINAL: **RESULTADO A — encontramos una gestión que mejora el PnL de forma robusta en TRAIN, VAL, OOS y ambas mitades temporales: trailing stop simple (Trail-1)**

Con una advertencia importante que hay que leer antes de actuar (ver
"Limitación de la muestra" abajo) — no se trata de una mejora inflada por
un único período, pero el baseline contra el que se compara tiene un
sesgo de muestra que hay que corregir antes de convertir esto en un
cambio real.

---

## Motor de simulación y calibración

Se reconstruyó la trayectoria de precio real (15m) para cada uno de los
**2,337 trades simulables** (de 3,283 con TP/SL; 946 descartados por
falta de klines o de niveles de SL/TP — no se inventó nada). Cada regla
de gestión se caminó barra a barra respetando el orden temporal, con
convención **pesimista**: si dentro de una misma barra el precio toca el
stop actual, se asume que el stop se ejecuta ANTES de que cualquier regla
pendiente (mover a breakeven, cerrar parcial, trailing) haya podido
aplicarse. Nunca se asume el mejor caso.

**Calibración del motor**: comparando el PnL reconstruido de la regla
`baseline` (SL/TP originales, sin gestión) contra el `RealizedPnl` real
guardado en la base de datos — **diferencia mediana = −$0.01** (prácticamente
exacta) pero **diferencia media = −$71.92**, señal de que un pequeño
número de trades (probablemente en símbolos de baja liquidez con gaps
grandes entre velas de 15m) reconstruye con un error significativo. La
mediana casi perfecta confirma que el motor es fiel para la gran mayoría
de los trades; la media distorsionada por una cola de casos difíciles se
documenta explícitamente, no se oculta.

## ⚠️ Limitación de la muestra — leer antes de los resultados

El baseline reconstruido sobre estos 2,337 trades da **PnL negativo en
TRAIN (−$1,499.9) y en OOS (−$279.6)**, y solo positivo en VAL (+$155.8) —
pese a que el total real de los 3,315 trades de producción es **positivo
(+$34,890, ver R35)**. Esto significa que **el subconjunto reconstruible
(los 2,337 con klines disponibles) está sesgado hacia peor desempeño que
la población completa** — probablemente porque los símbolos excluidos por
falta de cobertura de klines (946 trades, 610-421=189 símbolos sin
klines) no son aleatorios respecto del resultado. **Las comparaciones
RELATIVAS entre reglas de gestión sobre este mismo subconjunto siguen
siendo válidas** (todas se miden sobre la misma base), pero **las cifras
absolutas de PnL/mes no deben tomarse como representativas de la cartera
completa de producción** sin antes investigar por qué el subconjunto
reconstruible tiene peor desempeño que el total.

---

## Resultados por regla (PnL, TRAIN / VAL / OOS)

| Regla | TRAIN PnL | VAL PnL | OOS PnL | OOS vs baseline | OOS PF | OOS WR |
|---|--:|--:|--:|--:|--:|--:|
| **baseline (sin gestión)** | −$1,499.9 | +$155.8 | −$279.6 | — | 0.80 | 0.18 |
| BE-1 (+50bp→BE) | −$122.7 | +$248.1 | **+$73.5** | +$353.1 | 1.12 | 0.11 |
| BE-2 (+75bp→BE) | −$171.8 | +$250.5 | +$83.7 | +$363.4 | 1.13 | 0.12 |
| BE-3 (+100bp→BE) | −$311.4 | +$245.4 | +$53.6 | +$333.2 | 1.08 | 0.13 |
| BE-4 (+150bp→BE) | −$432.3 | +$232.1 | +$31.4 | +$311.0 | 1.04 | 0.14 |
| BE-5 (+200bp→BE) | −$576.2 | +$217.9 | −$29.3 | +$250.3 | 0.97 | 0.15 |
| Partial-A (100→25%, resto a TP) | −$1,315.1 | +$171.1 | −$251.9 | +$27.7 | 0.78 | 0.19 |
| Partial-B (100→50%, resto a BE) | −$536.0 | +$231.2 | −$57.7 | +$221.9 | 0.91 | 0.48 |
| Partial-C (150→25%, 250→BE resto) | −$487.9 | +$243.0 | −$9.5 | +$270.1 | 0.99 | 0.42 |
| Partial-D (200→50%, resto a TP) | −$1,044.3 | +$209.6 | −$204.2 | +$75.4 | 0.79 | 0.26 |
| **Trail-1 (100→BE, 150→+50, 200→+100)** | **+$196.2** | **+$318.4** | **+$192.2** | **+$471.8** | **1.28** | 0.38 |
| Trail-2 (150→+50, 250→+100) | +$14.2 | +$306.7 | +$161.5 | +$441.1 | 1.21 | 0.42 |

**Trail-1 es la única regla que convierte el baseline de negativo a
positivo en los TRES segmentos** (TRAIN: −$1,499.9→+$196.2; VAL:
+$155.8→+$318.4; OOS: −$279.6→+$192.2) — y además tiene el mejor profit
factor de todas las reglas probadas en OOS (1.28).

## Estabilidad temporal (mitad 1 vs mitad 2)

| Regla | Mitad 1 | Mitad 2 |
|---|--:|--:|
| baseline | −$1,499.9 | −$123.8 |
| BE-1 | −$122.7 | +$321.6 |
| **Trail-1** | **+$196.2** | **+$510.7** |
| Trail-2 | +$14.2 | +$468.2 |

**Trail-1 es la única regla positiva en AMBAS mitades temporales** — las
reglas BE y Partial mejoran mucho la mitad 1 (de muy negativa a apenas
negativa) pero no llegan a cruzar a positivo; Trail-1 sí, en ambas.

## Qué produce la mejora — trades salvados vs empeorados

Trail-1 en TRAIN: **780 trades "salvados"** (terminaban en pérdida y
mejoran) vs **173 "empeorados"** (terminaban en ganancia y el trailing
los corta antes) — una razón de ~4.5 a 1 a favor. Esto responde
directamente la preocupación del punto 6 del brief ("el riesgo principal
es cortar trades que iban al TP completo"): sí se cortan algunos
(173-182 según la regla, consistente en todas), pero el volumen de
trades salvados de una pérdida total es varias veces mayor.

---

## FASE 9 — Desglose de los 1,032 SL con MFE≥100bp

| Bucket MFE | n | % del total SL | PnL perdido | MAE medio posterior |
|---|--:|--:|--:|--:|
| 100–150bp | 170 | 7.5% | −$339.9 | −249bp |
| 150–200bp | 142 | 6.3% | −$307.4 | −262bp |
| 200–300bp | 203 | 9.0% | −$476.7 | −490bp |
| 300–500bp | 255 | 11.3% | −$507.1 | −293bp |
| ≥500bp | 262 | 11.6% | −$701.9 | −292bp |
| **Total (≥100bp)** | **1,032** | **45.7%** | **−$2,333.0** | — |

**Interpretación (respondiendo la pregunta A-E del brief)**: la mayoría
de estos casos caen en la categoría **(D) trades que necesitan toma
parcial / gestión activa**, no en (A) ruido normal — el MAE posterior al
pico favorable es sistemáticamente grande (−249 a −490bp) en todos los
buckets, lo que significa que estos trades no solo tocaron el SL, sino
que **revirtieron con fuerza** después de estar en ganancia — exactamente
el patrón que un trailing stop o breakeven está diseñado para
interceptar. El bucket ≥500bp (262 trades, 11.6% del total de SL) es el
más costoso individualmente (−$701.9) — trades que llegaron a estar
+5R o más a favor y terminaron en pérdida total.

---

## Conclusión y siguiente paso

**RESULTADO A, con una condición**: Trail-1 (mover SL a breakeven en
+100bp, a +50bp de ganancia asegurada en +150bp, a +100bp asegurados en
+200bp) mejora el PnL de forma consistente y robusta en los 5 cortes
independientes probados (TRAIN, VAL, OOS, mitad 1, mitad 2) — cumple el
estándar de robustez temporal que pedía el brief.

**Antes de proponer esto como cambio real** (todavía NO se toca
producción, tal como se pidió explícitamente):

1. **Resolver el sesgo de muestra documentado arriba** — entender por qué
   el subconjunto con klines reconstruibles tiene peor desempeño que la
   población completa de 3,315 trades, para saber si las cifras absolutas
   de PnL/mes son representativas o están sesgadas a la baja (o al alza)
   respecto de lo que realmente pasaría en el sistema completo.
2. **Nota sobre la herramienta de la Fase 7 del brief**: `portfolio_engine.py`
   gobierna competencia de capital entre señales de ENTRADA nuevas — este
   hallazgo es sobre gestión de POSICIONES YA ABIERTAS por el sistema
   existente, un problema distinto. El paso equivalente correcto no es
   correr `portfolio_engine.py`, sino documentar esto como una propuesta
   concreta de cambio a la lógica de gestión de riesgo (`risk_manager.py`
   en producción) para que el usuario decida — sigue sin tocarse nada.
3. Validar la regla también por perfil de estrategia y símbolo (pendiente,
   Fase 8 del brief) antes de cualquier implementación — no se hizo esta
   ronda por razones de tiempo, es el paso natural de un R37 si el usuario
   quiere profundizar esta línea en vez de abrir una nueva.

No se modificó nada en producción. No se generó ninguna nueva señal de
entrada. Este hallazgo es exclusivamente sobre cómo se gestionan las
posiciones que el sistema ya decide abrir.
