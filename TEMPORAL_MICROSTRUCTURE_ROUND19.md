# ROUND 19 — TEMPORAL MICROSTRUCTURE + EXECUTION ALPHA HUNT

**Fecha:** 2026-09-22 · Script: `agent/backtest/r19_temporal.py` · Universo
ancho (357 símbolos) · Placebo aplicado **desde el diseño**, no después —
lección explícita de R18.

## Resultado directo

# FAIL (los 4 tracks) — pero con la causa exacta más clara del proyecto: NO ES FALTA DE SEÑAL, ES MAGNITUD INSUFICIENTE FRENTE AL COSTO

A diferencia de rondas anteriores donde el placebo reproducía el efecto
(R12/R13/R18), esta vez **el efecto real bate claramente al placebo** en el
track principal — pero el efecto real, en su mejor versión, es de ~8-12 bp
brutos contra un piso de costo de 24 bp. No es un fantasma estadístico; es
demasiado pequeño.

---

## TRACK A — Hora del día (auditado desde cero)

Retorno medio a 1h por hora UTC, sobre ~247 000 observaciones por hora,
más volatilidad realizada, probabilidad de breakout y probabilidad de
expansión de volumen por hora (no solo dirección).

| Hora peor | Efecto | Hora mejor | Efecto |
|---|--:|---|--:|
| 22:00 UTC | **−7.74bp** (CI excl 0) | 15:00 UTC | +3.75bp |
| 18:00 UTC | −7.63bp | 19:00 UTC | +3.38bp |
| 13:00 UTC | −5.19bp | 14:00 UTC | +2.31bp |
| 23:00 UTC | −5.72bp | | |

**Probabilidad de breakout y de expansión de volumen SÍ varían por hora**
(13:00-15:00 UTC: P(breakout) 0.25-0.28, P(vol_exp) 0.14-0.17 — casi el doble
que a las 20:00-23:00 UTC: P(breakout) 0.15-0.19, P(vol_exp) 0.06-0.07). Esto
confirma la intuición del brief: la hora sí dice "ahora hay más probabilidad
de movimiento", coincidiendo con el solape US/EU (13-15 UTC).

**Placebo — el resultado decisivo (a diferencia de R18):**
Shuffle de etiqueta-hora (3 iteraciones, misma cantidad de observaciones por
bucket falso): máximo |efecto| entre los 24 buckets aleatorios = **2.2-2.4
bp**. El efecto real (22:00 UTC, −7.74bp) es **~3.2× más grande que lo que
produce el ruido de multiple-testing sobre 24 horas.** **El placebo NO
reproduce el resultado — hay estructura horaria genuina.**

**Pero temporalmente inestable, el mismo patrón de siempre:** TRAIN (hasta
2026-01-08) = +0.5bp (CI incl 0, sin efecto) · VAL = −9.9bp · OOS = −11.5bp.
Ausente en la primera mitad del dataset, presente y creciente en la segunda.
Coincide con que el universo ancho tiene muchos menos símbolos activos en
TRAIN (n=74 648) que en OOS (n=153 632) — la composición del universo cambia
con el tiempo, no solo el comportamiento.

---

## TRACK B — Ventana de funding settlement (00/08/16 UTC, reloj universal)

Probado en TODO el universo ancho (no requiere `funding_hist`, solo el
horario de settlement, que es universal para perps USDⓈ-M). Comparado contra
control fuera de cualquier settlement (>120 min de distancia):

| Ventana | ret_1h dentro | vs fuera (−0.62bp) |
|---|--:|--:|
| −60→+60 | −0.94bp | leve |
| −30→+30 | −2.16bp | 3.5× |
| **−15→+15** | **−2.67bp** | **4.3×, el más fuerte** |
| −5→+15 | −2.64bp | similar |
| +15→+60 | −0.22bp | vuelve a la base |

**Patrón limpio y económicamente sensato**: el efecto crece monótonamente al
acercar la ventana al settlement exacto, y se disipa por completo pasados 15
minutos — la firma clásica de un ajuste de posicionamiento alrededor del
cobro/pago de funding. La volatilidad realizada, en cambio, **no cambia**
(43-44bp en todas las ventanas) — no hay expansión de volatilidad, solo un
sesgo direccional pequeño y muy localizado.

**FAIL por magnitud, no por falta de mecanismo:** el efecto incremental
(−2.67 vs −0.62bp fuera = ~2bp neto atribuible al settlement) es real y
limpio, pero **2 bp está muy por debajo del piso de costo de 24 bp**, sin
importar la frecuencia (3 settlements/día × 357 símbolos). No hay forma de
que esta magnitud supere costos de ejecución reales.

---

## TRACK D — Hora 22:00 UTC × compresión/expansión de volumen

| Estado | Efecto |
|---|--:|
| compresión (rv_pct<25%) | **−12.32bp** (el más fuerte de toda la ronda) |
| expansión de volumen (vol_pct≥75%) | −4.23bp |
| ambos | −9.48bp |
| ninguno | −8.55bp |

La compresión previa SÍ amplifica el efecto horario (−12.3 vs −8.6bp
"ninguno") — una interacción genuina, no ruido. Pero **−12.3bp sigue por
debajo de 24bp de costo**, y hereda la misma inestabilidad temporal de Track
A (no se repitió el split TRAIN/VAL/OOS aquí porque el track base ya lo
reprobó).

---

## TRACK C (ligero) — Reversión de sobre-reactores tras shock de mercado

+4.77bp CI[−6.53, 16.74] n=4015 — **sin efecto** (CI incluye 0 ampliamente).
Cerrado sin insistir, tal como con la Familia C de R18.

---

## Por qué esto es distinto de R18 (y de casi todo el proyecto)

En 18 rondas anteriores, cuando un hallazgo parecía prometedor, el problema
casi siempre fue que **el placebo lo reproducía** (era drift disfrazado). Acá
el placebo NO lo reproduce — el efecto horario es 3× el ruido esperado, y el
efecto de settlement tiene una firma temporal limpia y económicamente
coherente. **Esta vez el mecanismo es genuino. El problema es puramente de
magnitud**: el mejor efecto encontrado en toda la ronda (−12.3bp, hora 22:00 +
compresión) es la mitad del costo de ejecución asumido (24bp round-trip).

Esto es información nueva y accionable: confirma que el "piso de fricción" de
~24bp (fee+spread+slippage en ambas patas) es el verdadero techo que ha estado
matando casi todo en este proyecto — no la ausencia de estructura de mercado.
Varios mecanismos con soporte estadístico real (funding settlement, hora del
día) existen pero son categóricamente insuficientes frente a ese costo.

---

## SIGUIENTE RONDA — no se cierra la investigación

**Round 20: atacar el COSTO, no la señal.** Todos los sims económicos del
proyecto (R16-R19) asumieron ejecución 100% taker (fee 5bp + slippage 4bp por
lado × 2 patas = 24bp). Nunca se modeló ejecución con **órdenes límite
(maker)** de forma realista (fee ~2bp en vez de 5bp, sin cruzar el spread) con
una probabilidad de fill explícita (no 100%, para no repetir el error de
asumir fills perfectos). Si el piso de costo baja de 24bp a ~10-12bp con
maker + probabilidad de fill realista, **varios de los "casi-PASS" de R18/R19
(capitulación @5 slots ≈ $19/mes teórico a 24bp; hora 22:00+compresión a
−12.3bp bruto) podrían cruzar a positivo** sin necesidad de encontrar una
señal nueva. Es la única palanca del proyecto que nunca se giró. Si tampoco
alcanza: el mapa de 19 rondas (mecanismo tras mecanismo con edge real pero
sub-costo) empieza a ser evidencia legítima de que el objetivo requiere either
(a) una estructura de costos que no tenemos disponible en este entorno, o (b)
una fuente de datos genuinamente nueva — pero esa conclusión se entrega
formalmente recién si R20 también falla, no antes.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
