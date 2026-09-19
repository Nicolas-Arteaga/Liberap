# ROUND 34 — 13 SETUPS DE PRICE ACTION / MEDIAS MÓVILES

## Veredicto general: **0/11 implementados sobreviven TRAIN. 2 no se implementaron esta ronda.**

Ningún setup pasó siquiera el primer filtro (TRAIN con CI que excluye 0 Y
signo positivo) — la mayoría no por falta de significancia sino por
**significancia negativa clara**, lo cual es un diagnóstico distinto y más
útil que "no hay señal": varios setups SÍ tienen un efecto sistemático,
pero en la dirección contraria a la esperada.

Especificación completa de los 13 setups (contexto/estado/evento/
confirmación/entrada/stop/TP/invalidación/no-trade/hipótesis) en
[`SETUPS_ROUND34_SPEC.md`](SETUPS_ROUND34_SPEC.md).

---

## Ranking final (11 de 13 implementados y testeados)

| # | Setup | Dirección | Eventos | TRAIN net | CI excl 0 | STATUS |
|---|---|---|--:|--:|---|---|
| 8 | Compresión→expansión | L/S | 2,675 | −7.9bp | No | FAILED (sin señal) |
| 10 | Cruce MA7 sin confirmación (fade) | SHORT | 8,139 | +1.9bp | No | FAILED (sin señal) |
| 3 | Quiebre rápido MA7 desde pico | SHORT | 1,576 | −38.0bp | No | FAILED (sin señal, n chico) |
| 6 | Ruptura MA25 + retest fallido | SHORT | 42,763 | −4.9bp | No | FAILED (sin señal) |
| 11 | Precio cruza MA25, estructura aguanta | LONG | 9,007 | −17.6bp | No | FAILED (sin señal) |
| 4 | Pullback MA25 + rechazo | LONG | 2,979 | −17.7bp | No | FAILED (sin señal) |
| 2 | MA7 toca MA99 (soporte) | LONG | 9,713 | **−27.9bp** | **Sí** | **FAILED (señal negativa clara)** |
| 7 | Falsa ruptura MA25 + recuperación | LONG | 9,776 | **−35.3bp** | **Sí** | **FAILED (señal negativa clara)** |
| 12 | 2do giro MA7, tendencia de fondo | LONG | 41,952 | **−34.2bp** | **Sí** | **FAILED (señal negativa clara)** |
| 1 | Giro MA7 antes de pullback MA25 | LONG | 53,410 | **−34.7bp** | **Sí** | **FAILED (señal negativa clara)** |
| 13 | Rechazo zona MA25/MA50 | LONG | 14,003 | **−38.7bp** | **Sí** | **FAILED (señal negativa clara)** |
| 5 | Pullback de 2 piernas a MA50 | LONG | — | — | — | **No implementado esta ronda** |
| 9 | Separación fuerte + 1er pullback a MA7 | LONG | — | — | — | **No implementado esta ronda** |

**Ninguno califica para VAL/OOS** — el filtro exige TRAIN con signo
positivo Y CI que excluya 0; ninguno lo cumple.

---

## Diagnóstico por parte de la lógica (no un FAILED genérico)

### Patrón dominante: los setups LONG pierden dinero de forma sistemática y significativa

**5 de los 7 setups LONG implementados (1, 2, 7, 12, 13) tienen pérdida
negativa Y estadísticamente significativa en TRAIN** — no es ruido, es un
efecto real y consistente. Esto coincide exactamente con el hallazgo ya
establecido en R25, R31 y R33: **el período de TRAIN de este dataset es
un mercado mayoritariamente bajista.** Comprar pullbacks, rebotes en
soportes dinámicos o rupturas falsas que se recuperan pierde dinero de
forma sistemática cuando el contexto de fondo es bajista — no importa cuán
preciso sea el disparador de entrada, **el problema no está en la
ENTRADA de estos 5 setups, está en el CONTEXTO**: todos asumen
implícitamente una tendencia alcista de fondo (comprar retrocesos), y la
muestra de TRAIN no la tuvo con suficiente consistencia.

Esto es distinto de "las MAs no sirven" — la lógica de entrada (giro de
pendiente, toque de soporte dinámico, rechazo de zona) podría ser
razonable en un régimen alcista; el diagnóstico correcto es que **el filtro
de contexto de cada setup (ej. "MA99 con pendiente positiva") no está
excluyendo suficientes períodos donde el contexto de fondo en realidad ya
se había roto**, o que el propio dataset no ofrece suficientes tramos
alcistas sostenidos para que estos setups muestren su mejor cara.

### Los setups SHORT (3, 6, 10) no tienen señal, ni siquiera negativa

A diferencia de los LONG, los 3 setups SHORT implementados (fade de
cruce falso, retest fallido tras ruptura, quiebre rápido desde pico) **no
muestran ningún efecto significativo** — ni a favor ni en contra. Esto es
un diagnóstico distinto: el problema acá no es el contexto (irían a favor
del sesgo bajista de la muestra, si acaso), sino que **la entrada
específica no está capturando nada distinguible del ruido**. El Setup 3
en particular tiene muy pocos eventos (n=220 en TRAIN) — la definición de
"pico" + "quiebre rápido" es demasiado restrictiva para este universo, no
necesariamente porque la idea esté mal, sino porque el umbral de
"velocidad" (percentil 80 causal) puede ser demasiado exigente.

### El Setup 8 (compresión→expansión) reconfirma R18

Compresión de medias seguida de expansión con cierre direccional fuerte —
esto es, en esencia, la misma familia que R18 (compresión de volatilidad
→ ruptura) y R23 (volatility transition), ya cerradas como FAILED. No es
sorprendente que tampoco funcione acá con la variante de medias móviles.

---

## Limitaciones declaradas de esta ronda

- **Setups 5 y 9 no se implementaron.** Ambos requieren detección de
  estructura multi-pierna (dos mínimos ascendentes con separación mínima
  de barras, o distancia MA7-MA25 en régimen extendido combinada con un
  retroceso "ordenado") que no se codificó con suficiente rigor dentro del
  tiempo de esta ronda. No se inventó una versión simplificada para
  completar el número — se declara explícitamente pendiente en vez de
  reportar un resultado poco fiel a la especificación.
- **Barrido de TP/SL con precisión horaria, no de 15 minutos.** El stop y
  el TP se evalúan sobre high/low de velas de 1H, no de 15m — un
  movimiento que toca y revierte dentro de una misma hora podría no
  detectarse en el orden correcto. Esto es una limitación conocida de usar
  el timeframe de la señal (1H) también para la ejecución; no se estimó
  su impacto cuantitativo esta ronda.
- **Solo se probó 1H**, tal como pedía el brief ("solo si un setup muestra
  señal real, probar 15m/4H") — como ninguno mostró señal real, no se
  escaló a otros timeframes.

---

## Siguiente paso

No se recomienda simplemente "ajustar los stops" o "probar otro TP" de
los 5 setups LONG que fallaron con significancia — el diagnóstico apunta
al CONTEXTO (régimen de tendencia de fondo), no a la mecánica de entrada.
Dos caminos concretos para R35, si se quiere seguir esta línea de
price-action/MAs:

1. **Endurecer el filtro de contexto** de los 5 setups LONG que fallaron
   con significancia (exigir, por ejemplo, que MA99 lleve pendiente
   positiva sostenida por más barras, o agregar un filtro de régimen de
   mercado agregado — no símbolo por símbolo) y volver a correr SOLO esos
   5, sin generar variantes nuevas — es una corrección quirúrgica sobre un
   diagnóstico específico, no una nueva ronda de exploración.
2. **Implementar los Setups 5 y 9 pendientes** con el rigor declarado
   (detección de piernas real) antes de descartar la familia completa —
   quedaron genuinamente sin probar, no fallaron.

Si después de eso la familia completa de 13 setups sigue sin producir un
candidato, se sumaría a la evidencia ya extensa (R29-R33) de que el
universo/ventana de datos disponible limita más que la elección de
mecanismo — pero esa conclusión no está garantizada todavía porque el
diagnóstico de esta ronda (contexto de tendencia, no lógica de entrada)
apunta a algo específico y corregible, no a un agotamiento genérico.
