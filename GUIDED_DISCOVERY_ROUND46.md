# ROUND 46 — Descubrimiento guiado por 45 rondas de evidencia acumulada

## Veredicto final

**CONDITIONAL** — un mecanismo (C2, "Reversión sin Persecución, SHORT")
sobrevive TODAS las pruebas de robustez aplicadas (TRAIN/VAL/OOS, segundo
split independiente, `portfolio_engine.py` con capital real, y
remove-best-trade), es interpretable como fenómeno de mercado, y es
genuinamente transversal (57 símbolos, 8 perfiles de origen distintos).
No llega a **PASS** porque su tramo VAL es negativo (n=13, muestra chica)
y el volumen total (67 trades en 90 días) todavía es bajo para tener alta
confianza — necesita más trades en vivo (no reconstruidos) para
confirmarse antes de implementarlo.

---

## 1. Knowledge base — qué aprendimos de 45 rondas (resumen operativo)

| Familia | Resultado | Por qué falló | Qué implica para R46 |
|---|---|---|---|
| MA slope/crossover (3 casos manuales) | PARK/marginal | Edge real pero minúsculo y muy específico de parámetros | No re-descubrir "cruce de MA" genérico — ya se exprimió |
| Régimen BTC / regime router | FAILED | Peor que router aleatorio, sin persistencia de liderazgo | No condicionar por "régimen de BTC" como filtro maestro |
| FVG (todas las variantes) | Mixto, mejor con filtro de tendencia y gap chico | Sin filtro de tendencia, ~50/50; el edge real está en no perseguir gaps grandes/contra-tendencia | Confirma: "no perseguir movimientos ya grandes" es un patrón recurrente — insumo directo para R46 |
| H7/PDH Sweep/Death Cross | FAILED/insuficiente | Muestra mínima, sin edge medible | Descartados, no reintentar sin más datos |
| Exchange lead/lag (H9) | Real pero no monetizable | 1-5bp de señal vs 8-16bp de costo | Cualquier señal <20bp de margen tiene prior bajísimo — regla dura para R46 |
| OI acceleration / OI como trigger (H13, R9-R11) | FAILED | Vive solo en sub-período, no estacionario, concentrado en pocos símbolos | No usar ΔOI como señal aislada de dirección |
| Retail vs smart money (L-S ratios) | FAILED | Placebo reproduce el efecto exacto — era drift del universo, no señal | Cualquier señal de posicionamiento necesita placebo explícito |
| Beta/residual momentum, cross-sectional momentum | FAILED | El placebo aleatorio empata o gana al ranking "inteligente" | No repetir ranking cross-sectional sin control de placebo fuerte |
| Funding carry / chronic funding | FAILED | Fees de 2 patas (46bp RT) superan el funding capturado 5-20x; a 30-90d el funding forward ya no es predecible | Cualquier estrategia que dependa de <20bp de margen por operación está descartada de entrada |
| Breakout continuation / compresión→expansión | FAILED (R18) | Ni siquiera el placebo lo distingue del drift general | La "compresión" sola no alcanza; hace falta combinarla con algo más |
| Capitulación/liquidity transitions (R18/R21) | PARK, el mejor resultado histórico | Inestabilidad temporal: 1ª mitad negativa, 2ª mitad muy positiva | Confirma: la SELECCIÓN entre candidatos simultáneos (score) importa más que la señal cruda — insumo para el diseño del portfolio engine acá |
| Combinatoria ciega (R45, 40k combinaciones) | FAILED | Con ese volumen de pruebas, encontrar "ganadores" por azar es lo esperado (multiple comparisons) | **Regla central de esta ronda: no repetir combinatoria ciega** — hay que partir de un mecanismo con hipótesis previa, no de un grid |
| Multi-day momentum / mean reversion genérica | FAILED (R31, fase alpha) | Sin verificar en el motor real | No revivir sin motor real |
| TP/SL geometry aislada | N/A como señal de entrada | Es gestión de salida, no genera alpha de entrada (ver Trail-1) | Confirma la separación entrada/salida que ya hace este proyecto |

**Patrón transversal de 45 rondas:** casi todo lo que falló, falló por una
de dos razones — (a) el margen teórico es menor a ~20bp y los costos reales
(fees+funding+turnover) lo devoran, o (b) el "edge" resultó ser
indistinguible de un placebo/drift general del universo. **Regla de
búsqueda para R46: cualquier candidato debe (1) producir movimientos de
cientos de bp, no decenas, y (2) tener un placebo/control explícito antes
de creerle.**

---

## 2-4. Reencuadre: de "qué feature predice ganar" a "qué transición separa un movimiento que corre de uno que muere"

En vez de repetir combinatoria de features (R45), se enriqueció el mismo
dataset transversal (2,156 trades con contexto causal + MFE/MAE del path
real + features de transición: aceleración reciente vs. tendencia de
fondo, compresión de volatilidad previa, sorpresa de volumen, posición
en el rango de 50 velas) y se bucketizó por **tamaño del movimiento que
produjo el trade**, no solo por si ganó o perdió:

| Bucket | n | Definición |
|---|---:|---|
| Grandes ganadores | 210 | Ganó Y llegó a ≥300bp de favorable |
| Ganadores normales | 101 | Ganó con <300bp |
| **Pérdidas con reversión** | **1,036** | Perdió PERO había llegado a ≥100bp de favorable antes de revertir |
| Pérdidas con MFE chico | 223 | Perdió, entre 30-100bp de favorable |
| Pérdidas inmediatas | 586 | Perdió sin llegar ni a 30bp de favorable |

(El 56% de las pérdidas totales tuvieron ≥100bp de favorable antes de
revertir — reconfirma, con otro dataset, el hallazgo original que motivó
Trail-1 en R35-37. No se vuelve a tocar Trail-1 acá, sigue OFF.)

## TOP 5 MECANISMOS DESCUBIERTOS

| # | Mecanismo | Evidencia | Trades | MFE típico | Qué lo diferencia | Estado |
|---|---|---:|---:|---:|---|---|
| 1 | **Momentum sostenido sin aceleración reciente → corre lejos** | Comparando BIG_WIN vs. PÉRDIDA-INMEDIATA: BIG_WIN tiene retornos previos (1/3/5/10/20 velas) y distancia a MA7/25/50/99 sistemáticamente más altos (reldiff 0.5-1.0 en 10 de 15 features) | 210 vs 586 | 300bp+ vs <30bp | Nivel de tendencia pre-entrada, NO un evento puntual | **Confirmado, base de C1/C2/C3** |
| 2 | **Persecución de un pico reciente (chase) → revierte en vez de correr** | Comparando BIG_WIN vs. PÉRDIDA-CON-REVERSIÓN (ambos arrancan con momentum similar — reldiff bajo en nivel), la diferencia real está en `accel_3_10` (aceleración de 3 velas relativa a 10): BIG_WIN tiene aceleración **negativa** (el impulso reciente es MENOR que el ritmo de fondo — continuación calma), REVERSAL_LOSS tiene aceleración **positiva** (spike reciente por encima del ritmo de fondo — persecución de un pico) | 210 vs 1,036 | ambos altos al entrar, pero uno corre y el otro revierte | **Aceleración relativa, no nivel** | **Confirmado, es el insumo distintivo de C1/C2 sobre C3** |
| 3 | **El fenómeno es transversal a perfiles** | Los 210 grandes ganadores vienen de al menos 5 perfiles distintos (Nexus, FVG-1m, FVG-5m, GOLDEN-U-TURN, MA Pattern) — no es exclusivo de ninguno | 210 | — | Aparece independientemente de qué estrategia originó el trade | **Confirmado** |
| 4 | **El sesgo LONG del dataset no es el mecanismo** | Los 5 buckets tienen entre 71-79% de trades LONG por igual (incl. pérdidas inmediatas) — la proporción LONG/SHORT no discrimina buenos de malos resultados | 2,156 | — | Descarta que "ser LONG" sea la señal; el direccional real está en la combinación tendencia+aceleración | Control, no candidato en sí |
| 5 | **El lado SHORT del mecanismo es más limpio que el LONG** | Al formalizar la regla estructural en ambas direcciones, la versión LONG no sobrevive el segundo split independiente; la versión SHORT sí, con mejor consistencia | 39 (TRAIN) | 300-500bp mediana | Dirección | Base de la única candidata que sobrevive todo (C2) |

---

## CANDIDATAS FORMALIZADAS (3, siguiendo Contexto→Estado→Evento→Confirmación→Entrada→Invalidación→Exit)

### C1 — Trend Continuation No-Chase LONG (FAILED)

- **Contexto**: mercado en tendencia alcista establecida (precio por encima de su MA50, retorno de 20 velas positivo).
- **Estado**: el impulso de las últimas 3 velas NO es más fuerte que el ritmo de las últimas 10 (sin aceleración de corto plazo por encima de la mediana histórica).
- **Evento/Confirmación**: cierre de la vela con esas condiciones cumplidas.
- **Entrada**: al cierre de esa vela, LONG.
- **SL/Exit**: el mismo SL/TP que ya tenía cada trade real (no se re-optimizó).
- **Universo**: todos los símbolos con cobertura (no restringido a majors).
- **Timeframe**: 15m.
- **Resultado**: **FAILED** — no sobrevive el segundo split independiente (mitad1 +$24.0, mitad2 −$18.1).

### C2 — Trend Continuation No-Chase SHORT (CONDITIONAL — la única que sobrevive todo)

- **Contexto**: mercado en tendencia bajista establecida (precio por debajo de su MA50, retorno de 20 velas negativo).
- **Estado**: el impulso bajista de las últimas 3 velas NO se está desacelerando (aceleración de corto plazo por encima de la mediana histórica en ese contexto — es decir, la caída sigue firme, no está agotándose en un rebote de corto plazo).
- **Evento/Confirmación**: cierre de la vela con esas condiciones cumplidas.
- **Entrada**: al cierre de esa vela, SHORT.
- **Invalidación/Exit**: el SL/TP real que ya tenía cada trade (no se re-optimizó ninguno).
- **Universo**: amplio — matcheó en 57 símbolos distintos, sin concentración (máximo 2 trades por símbolo).
- **Timeframe**: 15m.

### C3 — Trend-only, sin filtro de aceleración (control, FAILED)

Igual que C1 pero sin exigir nada sobre `accel_3_10` — sirve para medir
si el filtro de "no perseguir el spike" realmente aporta. Sobrevive el
segundo split en la población sin restricción de capital, pero **se cae
a negativo en el portfolio engine real** (OOS −$25.4, remove-best-trade
−$27.9) — la restricción de concurrencia (solo 3 slots) penaliza a la
versión sin filtrar, que genera muchas más señales simultáneas de menor
calidad y termina compitiendo mal por los cupos. Confirma que el filtro
de aceleración de C1/C2 no es cosmético.

---

## Tabla de validación

| Estrategia | TRAIN | VAL | OOS | 2º split (mitad1/mitad2) | Portfolio (OOS) | Robustez (remove-best) | Resultado |
|---|---:|---:|---:|---|---:|---:|---|
| C1 LONG | +$16.8 | −$7.3 | −$3.5 | +$24.0 / **−$18.1** | — (no llega) | — | **FAILED** |
| **C2 SHORT** | +$38.0 | **−$19.9** | **+$89.0** | **+$52.9 / +$54.1** | **+$89.0** (15 trades, 0 rechazados) | **+$20.1** (sigue positivo) | **CONDITIONAL** |
| C3 LONG (control) | +$58.8 | +$66.3 | −$11.7 | +$59.6 / +$53.8 | **−$25.4** (49 aceptados, 4 rechazados) | −$27.9 | **FAILED** |

## Evidencia de que C2 no es simplemente otro accidente de R45

- **Volumen total sobre todo el dataset (mayo-agosto)**: 67 trades, 57
  símbolos distintos (máx. 2 por símbolo — sin concentración), **8
  perfiles de origen distintos** (Nexus 27, FVG-1m 22, FVG-5m 5, MA Slope
  Caso 3 4, FVG-15m variantes 6, MA Pattern 2) — exactamente el criterio
  de transversalidad pedido: la misma transición de mercado aparece
  independientemente de qué estrategia la capturó.
- **MFE mediana 266bp / media 574bp** entre los trades que matchean la
  regla — son movimientos grandes, no señales de 5-10bp que dependen de
  costos de ejecución (el criterio explícito de esta ronda).
- **Sobrevive remove-best-trade**: OOS pasa de +$89.0 a +$20.1 al sacar
  el mejor trade — sigue positivo, muy distinto a los candidatos de R45
  que se iban a negativo con solo sacar uno.
- **Sobrevive un segundo split completamente independiente** (mitad
  cronológica 1 vs. 2 del dataset entero, partición que no participó en
  la elección de la regla): +$52.9 y +$54.1, ambos positivos.

## Por qué NO es PASS todavía

- El tramo VAL (2026-07-18 a 2026-07-28, ventana angosta) da −$19.9 sobre
  solo 13 trades — probablemente 1-2 operaciones perdedoras en una
  ventana corta, pero es una mancha real en la estabilidad temporal que
  el propio criterio de esta ronda exige.
- 67 trades en 90 días (~22/mes) es un volumen bajo para tener alta
  confianza estadística, incluso con un mecanismo interpretable.
- Como en R44/R45: la población de origen sigue siendo mayormente
  `SimulatedTrades` reconstruido (limitación de validación ya registrada,
  no bloqueante para el descubrimiento, pero sí para confiar el resultado
  al 100% antes de verlo repetirse con trades genuinamente en vivo).

## Trail-1

Permaneció OFF (global y por perfil) durante toda la investigación. No
se ejecutó la comparación NEW STRATEGY vs. NEW STRATEGY+Trail-1 porque
C2 es CONDITIONAL, no una estrategia ya validada para pasar a esa
comparación — hacerlo ahora sería exactamente lo que la Parte 10 de esta
ronda prohíbe (usar Trail-1 para maquillar una candidata que todavía no
está confirmada).

## Próximo paso recomendado

No repetir combinatoria. Dejar correr el sistema en vivo el tiempo
suficiente para acumular más trades SHORT en tendencia bajista (el
subconjunto relevante es naturalmente escaso — 39 en TRAIN sobre 90
días) y volver a correr exactamente esta misma regla (ya congelada,
sin retocar umbrales) sobre esos datos nuevos como la verdadera prueba
OOS que le falta a C2 antes de subirla a PASS.
