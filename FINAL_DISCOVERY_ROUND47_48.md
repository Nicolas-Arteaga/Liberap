# ROUNDS 47-48 — Intento final de C2 + última ronda de descubrimiento

## Veredictos

- **R47: FAILED.** C2 no alcanza capacidad económica real.
- **R48: `NO HAY EVIDENCIA SUFICIENTE DE UNA NUEVA ESTRATEGIA ECONÓMICAMENTE ÚTIL`.**

**Discovery TERMINADO**, tal como se pidió explícitamente si R48 no producía PASS.

---

## R47 — ¿Podemos acercar C2 a 150 USDT/mes?

Fórmula de C2 congelada exactamente como salió de R46 (sin retocar ningún
umbral): `side=SHORT AND price_vs_MA50<0 AND ret_20<0 AND accel_3_10 >=
mediana(TRAIN)`. SL/TP/exit: el que ya traía cada trade real. Timeframe
15m. Entrada al cierre de la vela que cumple la condición.

| Candidato | Trades/mes | PnL OOS | PnL/mes OOS | 2º split | Remove-best | Remove-top3 | Resultado |
|---|---:|---:|---:|---|---:|---:|---|
| **V1 — C2 SHORT (congelado)** | 22.5 | +$89.0 | **$133.5** | +$52.9 / +$54.1 ✓ | +$20.1 | **−$11.1** | **FAILED** |
| V2 — mirror LONG (misma fórmula espejada, n=408) | 49.5 | +$1.1 | $1.7 | −$78.1 / −$40.1 ✗ | −$14.8 | −$42.8 | FAILED |
| V3 — SHORT sin filtro de aceleración (más frecuencia) | 72.0 | +$27.5 | $41.2 | +$16.8 / −$12.6 ✗ | −$4.8 | −$49.5 | FAILED |

V1 es la única que se acerca al número objetivo en superficie, pero:

- **No sobrevive el gate explícito de esta ronda** (quitar los 3 mejores
  trades de OOS): pasa de +$89.0 a **−$11.1**.
- Está dominado por **un solo mes calendario**: julio −$5.5, agosto
  +$94.5 — no es una tasa mensual sostenida, es la suerte de haber caído
  en una ventana con 2-3 trades grandes.
- Muestra total: apenas 15 trades en 20 días de OOS.

Ensanchar la frecuencia (V3, sin el filtro de aceleración) o espejar a
LONG (V2) no rescata nada — ambas empeoran en todos los ejes a la vez.

**Conclusión de R47**: el mecanismo de R46 es real e interpretable (56%
de las pérdidas del sistema muestran reversión desde favorable, y dentro
de C2 los ganadores grandes tienen una firma pre-entrada distinta de los
mediocres), pero su **capacidad económica techa muy por debajo** de lo
que hace falta para 450 USDT / 3 slots. No es "esperar más datos" — la
combinación de condiciones que define C2 ocurre con tan poca frecuencia
(≈22 veces/mes, y la mayoría mediocres) que ni en su mejor ventana
histórica produce un resultado robusto a la prueba de quitar unos pocos
trades.

---

## R48 — última ronda de descubrimiento (2 mecanismos nuevos, sin combinatoria)

Usando el mismo dataset transversal enriquecido de R46-R47 (2,156 trades,
contexto causal + MFE/MAE + features de transición), se formalizaron **2
mecanismos nuevos** (no probados con este rigor en 47 rondas previas),
ninguno derivado de combinatoria ciega:

### D1 — "Capitulación-Reversión"

**Contexto → Estado → Evento → Entrada**: precio en el extremo de su
rango de 50 velas (piso para LONG, techo para SHORT) + el mercado venía
comprimido (`compression_ratio` bajo) + aparece una sorpresa de volumen
(`vol_surge` en el 20% más alto) — la idea de trader: "compresión, evento
de volumen en un extremo, agotamiento del movimiento previo → reversión".

**Resultado: la combinación de las 3 condiciones es demasiado rara**
(6-11 eventos en TODO el dataset de 5 meses, tanto LONG como SHORT) —
insuficiente para evaluar, ni siquiera llega a tener un TRAIN con
volumen razonable. **FAILED por frecuencia insuficiente**, uno de los
criterios explícitos del gate de esta ronda.

Se probó una versión relajada (solo extremo + sorpresa de volumen, sin
exigir compresión previa) para no descartar el concepto solo por
escasez — con más volumen (55-119 trades por dirección), el resultado es
**decisivamente negativo** en TRAIN, VAL, OOS y ambas mitades del
segundo split (ej. SHORT: OOS wr=0%, PnL −$119.1 sobre 27 trades). No es
ruido: comprar/vender en un extremo con volumen alto es, en este
dataset, "agarrar el cuchillo que cae" — sigue cayendo, no revierte.
**FAILED con evidencia fuerte y clara.**

### D2 — "Expansión tras Compresión" (breakout direccional)

**Contexto → Evento → Entrada**: el mercado venía comprimido y la vela
de entrada ya muestra expansión de rango + volumen, siguiendo la
dirección de esa vela (breakout). **También demasiado raro** (1-3
eventos en todo el dataset) — insuficiente para evaluar. **FAILED por
frecuencia insuficiente.**

---

## Tabla final R48

| Mecanismo | Trades totales | OOS PnL | 2º split | Resultado |
|---|---:|---:|---|---|
| D1 Capitulación-Reversión LONG (3 condiciones) | 11 | −$0.7 | −$9.2 / −$7.5 | FAILED (frecuencia insuficiente) |
| D1 Capitulación-Reversión SHORT (3 condiciones) | 1 | −$0.1 | 0 / −$0.1 | FAILED (frecuencia insuficiente) |
| D1b Extremo+Volumen LONG (relajado, sin compresión) | 93 | −$12.6 | −$27.9 / −$113.6 | **FAILED (negativo con evidencia fuerte)** |
| D1b Extremo+Volumen SHORT (relajado) | 60 | −$119.1 | −$24.9 / −$152.1 | **FAILED (negativo con evidencia fuerte)** |
| D2 Expansión-tras-Compresión | 3 | 0 (sin trades OOS) | −$4.1 / +$15.8 | FAILED (frecuencia insuficiente) |

## Veredicto final

**`NO HAY EVIDENCIA SUFICIENTE DE UNA NUEVA ESTRATEGIA ECONÓMICAMENTE ÚTIL`**

- El único mecanismo con evidencia real y transversal encontrado en 48
  rondas (C1/C2 de R46) no alcanza capacidad económica ni siquiera en su
  mejor ventana histórica, y falla el gate de robustez explícito de R47.
- Los dos mecanismos nuevos de esta ronda (reversión en extremo,
  expansión tras compresión) o son demasiado raros para evaluar, o —
  cuando se relajan para tener volumen suficiente — resultan
  decisivamente negativos, no ambiguos.
- **Discovery termina acá**, según lo pedido explícitamente. No se
  genera una R49 repitiendo esta misma evidencia.

## Trail-1

Permaneció OFF (global y por perfil) durante R47 y R48 completos. No se
ejecutó ninguna comparación NEW STRATEGY vs. NEW STRATEGY+Trail-1 porque
ninguna estrategia llegó a PASS.

## Qué haría falta para reabrir esta línea en el futuro (no una acción para hoy)

1. Volumen de trades **genuinamente en vivo** (no reconstruidos) — la
   limitación de validación de R44 sigue sin resolverse y sigue siendo
   la explicación más simple de por qué las señales encontradas son
   frágiles: la población de origen es en un ~99% el import legacy.
2. Si en el futuro se agregan fuentes de datos genuinamente nuevas (no
   probadas en 48 rondas: liquidaciones, on-chain, derivados de opciones
   — todas mencionadas y descartadas por falta de datos, no por
   resultado negativo, en la fase alpha original R1-R22), ahí sí habría
   una hipótesis nueva legítima, no una repetición de lo ya hecho.
