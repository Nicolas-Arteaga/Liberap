# ROUND 33 — GEOMETRÍA MFE/MAE Y TP-ANTES-QUE-SL

## Veredicto: **FAILED** — pero con un hallazgo metodológico genuino, no un cierre vacío

No se encontró ningún setup con esperanza matemática positiva después de
costos. Lo más importante de esta ronda no es la lista de resultados —
es que **el framing en R-múltiplos, sin convertir a puntos básicos reales,
generó una falsa señal de asimetría explotable que se hubiera reportado
como PASS si no se hubiera hecho la Fase B de conversión económica.**
Documentar esto es en sí mismo un resultado útil para todas las rondas
futuras que usen R-múltiplos.

---

## Fase 1 — Geometría baseline (sin condicionar)

Unidad de riesgo (1R) = volatilidad realizada causal del propio símbolo
(`rv`) en la barra de entrada. SL fijo en 1R, TP en {1R, 2R, 3R}, horizonte
de barrido 24h, entrada muestreada cada 4h en las 357 altcoins.

**LONG es negativo en R-múltiplos en los 3 segmentos y los 3 TP** (hasta
−0.06R neto en TRAIN a TP=3R). **SHORT es positivo en R-múltiplos en casi
todos los casos** (hasta +0.058R en OOS a TP=2R) — **exactamente el mismo
patrón de R25**: el mercado cayó durante toda la ventana del dataset, así
que cualquier apuesta SHORT sin condicionar ya tiene expectativa positiva
en términos de R-múltiplo. Esto no es nuevo — es la confirmación de que
el sesgo de mercado se filtra incluso en la geometría de trayectorias.

## Fase 2 — Condicionar en 6 estados simples (rv/vol/ret1, alto/bajo)

De 36 configuraciones posibles (6 estados × 2 lados × 3 TP), **12
"sobreviven" TRAIN→VAL(confirma)→OOS con CI que excluye 0** — todas del
lado SHORT (ninguna LONG sobrevivió, consistente con el sesgo de mercado
de la muestra). En R-múltiplos, algunas parecían notablemente mejores que
el baseline (ej. `rv_hi+SHORT TP=3R`: OOS mean_R=+0.101 vs baseline
+0.056 — un 80% más).

**Esto es exactamente el punto donde una ronda menos cuidadosa hubiera
declarado un candidato prometedor.** No se hizo esa declaración — se pasó
a la Fase 2B (conversión a bp real), que es la que decide.

## Fase 2B — Conversión a bp real (el paso que revela el artefacto)

**Hallazgo metodológico central de la ronda**: condicionar en `rv_hi`
(volatilidad en el percentil 90+) selecciona mecánicamente barras donde
`R` (la unidad de riesgo, medida en bp) es mucho más grande — en este
caso, R_avg pasa de 62.2bp (baseline OOS) a 157.3bp (rv_hi OOS), **2.5×
más grande**. Un R-múltiplo idéntico o incluso mayor en esas condiciones
representa, en bp reales, prácticamente lo mismo o menos que el baseline,
porque el "tamaño de la apuesta" (R) también creció.

Al convertir todo a bp reales (`gross_bp = r_múltiplo × R_bp`):

| Configuración | OOS gross | OOS net (−24bp) | Delta vs baseline mismo TP |
|---|--:|--:|--:|
| Baseline SHORT TP=1R | +1.22bp | −22.78bp | — |
| Baseline SHORT TP=2R | +2.15bp | −21.85bp | — |
| Baseline SHORT TP=3R | +1.96bp | −22.04bp | — |
| rv_hi+SHORT TP=1R | −1.07bp | −25.07bp | **−2.29bp (peor que el baseline)** |
| rv_hi+SHORT TP=2R | +1.86bp | −22.14bp | −0.29bp (igual al baseline) |
| rv_hi+SHORT TP=3R | +4.14bp | −19.86bp | +2.18bp (marginal) |
| ret1_hi+SHORT TP=1R | +3.24bp | −20.76bp | +2.02bp (marginal) |
| ret1_hi+SHORT TP=2R | +4.63bp | −19.37bp | +2.48bp (marginal) |
| ret1_hi+SHORT TP=3R | +5.39bp | −18.61bp | +3.43bp (marginal, el mayor de todos) |

**Ninguna de las 12 configuraciones se acerca al costo de 24bp** — el
gross más alto de toda la tabla es +5.39bp, menos de un cuarto del costo
de ejecución. **Ninguna aporta más de +3.5bp de información incremental
sobre simplemente estar SHORT sin condición alguna** — muy por debajo de
cualquier umbral razonable para considerarlo señal real y no ruido de
muestreo.

---

## Por qué esto no es un cierre superficial

Esta ronda SÍ cambió el objetivo de búsqueda como se pidió — no buscó
"¿el retorno medio es positivo?" sino "¿existe una asimetría de
trayectoria (TP antes que SL) explotable?" — y encontró que la respuesta
honesta es: **la única asimetría real detectada es, otra vez, el sesgo
direccional de mercado de esta muestra (SHORT > LONG en R-múltiplos),
no una propiedad de la geometría de trayectorias en sí**. Ningún estado
de volatilidad/volumen/retorno extremo cambia esa geometría de forma
económicamente relevante una vez normalizado correctamente a bp.

## Fase 4 — economía real

**No se llevó nada a `portfolio_engine.py`.** Ninguna de las 12
configuraciones se acerca al costo de ejecución — hacerlo hubiera sido
simular una estrategia con expectativa neta negativa conocida de antemano.

---

## Conclusión y siguiente paso

**FAILED** — no existe, en el universo de 357 altcoins y el horizonte de
24h probado, un setup TP/SL con esperanza matemática positiva neta de
costos, ni siquiera relajando el requisito de retorno medio positivo a
favor de asimetría de trayectoria. El hallazgo metodológico (normalizar a
bp antes de confiar en cualquier estadística en R-múltiplos cuando el
denominador R varía con la condición que se está probando) queda
documentado para uso de rondas futuras que trabajen con TP/SL.

Esto se suma a la evidencia acumulada de R29-R32: el eje
OHLCV+volumen+volatilidad+OI+posicionamiento sobre el universo
superviviente de Binance USDⓈ-M Futures parece agotado tanto para señal
direccional de retorno medio (R29-R32) como para asimetría de trayectoria
explotable (R33). La recomendación de R32 sobre necesitar datos nuevos
(liquidaciones con cobertura real, order book histórico, on-chain) se
mantiene sin cambios y se refuerza con esta ronda adicional.
