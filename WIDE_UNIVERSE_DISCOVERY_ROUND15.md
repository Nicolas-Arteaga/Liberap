# ROUND 15 — FIND 1–3 PROFITABLE ALTCOIN STRATEGIES (universo ancho, ~357 pares)

**Fecha:** 2026-09-18 · Script: `agent/backtest/r15_wide_discovery.py` · Sin
descargas nuevas · Universo **357 símbolos** (todo el venue con klines_clean 15m
+ taker_flow 15m y ≥8000 barras, excluyendo acciones/commodities tokenizadas) —
la palanca "universo ancho" que R9-R14 no habían usado (estaban limitados a los
45-63 con OI/funding/L-S completos).

## Resultado directo

**Ninguna de las 6 hipótesis (familias A/B/C) supera el screening
pre-registrado.** Cero PASS, cero PARK genuino. Pero el round **no termina en
"no hay alpha"**: identificamos con precisión por qué el universo ancho no
ayudó como se esperaba, y encontramos — como derivado directo de la búsqueda —
un **mecanismo completamente nuevo y no testeado en 15 rounds** con evidencia
inicial real: **funding-rate carry / cash-and-carry**, no direccional. Ver §5.

---

## 1. Limitación de datos real del universo ancho (declarada, no oculta)

`taker_flow` (join necesario para señales de flujo) para los símbolos fuera del
universo OI-completo solo tiene su backfill original (**2025-12 → 2026-08**, no
se extendió hacia atrás como sí se hizo para los 63 de R11). Además la mayoría
de los 357 símbolos **listaron durante 2026** (no antes). Resultado: el grid de
rebalanceo con ≥50 símbolos simultáneamente válidos (con 30 días de historia
causal) **solo arranca en la práctica hacia abril-2026**, y el corte
TRAIN/VAL/OOS quedó en:

`TRAIN ≤ 2026-06-15 · VAL ≤ 2026-07-15 · OOS > 2026-07-15`

**El período OOS (2026-07-15 → 2026-08-17, ~5 semanas) coincide casi
exactamente con la ventana de dispersión extrema de 2026Q3 ya aislada en R13 y
R14.** Esto es clave para interpretar los resultados de abajo: cualquier número
grande en OOS es sospechoso por construcción, no por mérito de la señal — el
propio brief pide explícitamente "sin depender exclusivamente de 2026Q3", y
este split no puede cumplirlo con los datos actuales sin re-trabajar el backfill
de `taker_flow` hacia atrás (2025-06→2025-12) para el universo ancho.

---

## 2. TOP 10 candidatos (screening TRAIN, @24h, N=3, long-short, vs RANDOM/ORACLE)

| # | Candidato (familia) | TRAIN bp | CI excl 0 | vs RANDOM (−16.6bp) | N óptimo (train) | Veredicto |
|---|---|--:|:--:|---|---|---|
| 1 | `B1_momentum_wide` N=10 (B) | +93.8 | No | mejor | — | **FAILED** (no CI excl 0) |
| 2 | `A2_taker_aggression` N=1 (A) | +79.0 | No | mejor | — | **FAILED** |
| 3 | `B1_momentum_wide` N=5 (B) | +54.3 | No | mejor | — | **FAILED** |
| 4 | `B2_volume_anomaly_confirm` N=1 (B) | +88.6 | No | mejor | — | **FAILED** |
| 5 | `B1_momentum_wide` N=3 (B) | +42.5 | No | mejor | — | **FAILED** |
| 6 | `A2_taker_aggression` N=3 (A) | +35.0 | No | mejor | — | **FAILED** |
| 7 | `B2_volume_anomaly_confirm` N=3 (B) | +21.2 | No | mejor | — | **FAILED** |
| 8 | `A1_vol_expansion_continue` N=3 (A) | −26.4 | No | peor | — | **FAILED** |
| 9 | `C1_shortterm_reversal` N=3 (C) | +1.0 | No | ≈igual | — | **FAILED** |
| 10 | `C2_shortterm_continuation` N=3 (C) | −1.0 | No | ≈igual | — | **FAILED** |
| — | **RANDOM (control)** | −16.6 | No | — | — | referencia |
| — | **ORACLE (sanity, retorno futuro real)** | **+3115.8** | **Sí** | — | — | *no es estrategia* |

**Ningún candidato tiene CI que excluya 0 en TRAIN.** El oracle (+3116 bp!, muy
por encima del +298bp de R14 — consistente con que el universo ancho SÍ tiene
más dispersión/tail explotable *si supieras el futuro*, confirmando que la
oportunidad de tamaño existe, pero ninguna de las 6 señales ex-ante la
encuentra).

---

## 3. Auditoría TOP 3 (los de mejor lectura superficial en TRAIN)

### `A1_vol_expansion_continue` (expansión de volatilidad + confirmación de dirección — familia A)
| h | train | val | oos |
|---|--:|--:|--:|
| 24h | −26.4 | +53.7 | +70.7 |
| 72h | −43.8 | +84.9 | **+107.8** |

Por pata: `long_top` train=−400 / val=−506 / **oos=−294**; `short_bottom`
train=+347 / val=+614 / **oos=+436**. El long-short combinado se ve "OOS
positivo", pero es enteramente la pata corta arrastrando — y esa pata corta
domina en los TRES períodos con magnitudes de cientos de bp, típico de un
puñado de altcoins colapsando fuerte (el mismo tipo de evento que ya vimos:
dispersión extrema, no una señal de "expansión de vol" funcionando). **FAILED**
— no hay separación real por N (conc 0.66-0.81, sube con N, la selección no
diversifica el riesgo, lo concentra).

### `B1_momentum_wide` (momentum cross-sectional, universo ancho — comparación directa con R14)
| h | train | val | oos |
|---|--:|--:|--:|
| 24h | +42.5 | +108.1 | **+129.0** |
| 72h | **−175.5** | +188.6 | +122.0 |

Nótese que a 72h **el signo se invierte entre TRAIN y VAL/OOS** (−175 → +189 →
+122). Por pata @24h: `long_top` train=−227/val=**−544**/oos=−153;
`short_bottom` train=+312/val=**+760**/oos=+412 — la pata corta, otra vez,
domina y con magnitudes extremas en VAL (+760bp) que ya delatan concentración
en pocos eventos. **Comparación directa con R14 (45 símbolos):** en R14,
`momentum_only` TRAIN @24h fue solo +4.5bp (CI incl 0); acá, con 357 símbolos,
TRAIN sube a +42.5bp — **la amplitud del universo SÍ aumenta la magnitud bruta
observable**, tal como planteaba la hipótesis del round. Pero no aumenta la
*estabilidad*: sigue sin CI excl 0, sigue invirtiendo signo por horizonte, y el
efecto sigue viviendo en la pata short dominada por eventos extremos, no en una
selección diversificada. **FAILED**, pero es el hallazgo más informativo del
round (ver §4).

### `A2_taker_aggression` (agresión taker extrema — familia A/microestructura)
| h | train | val | oos |
|---|--:|--:|--:|
| 24h | +35.0 | −9.8 | −0.7 |
| 72h | +63.5 | +40.1 | **−15.6** |

Único candidato con TRAIN y VAL de signo consistente (ambos positivos o cerca)
en varios horizontes — pero se apaga y **se invierte en OOS**. N=1 train=+79bp
es la lectura más alta de las 6 hipótesis, pero cae a val=−4.6/oos=−7.5 — no
sobrevive. **FAILED.**

---

## 4. Qué aprendimos (respuesta directa a "qué componente falta para $150")

1. **El universo ancho SÍ amplifica la magnitud bruta de los efectos** (momentum
   pasó de +4.5bp en 45 símbolos a +42.5bp en 357) — confirma la intuición
   central del brief. **Pero la fuente de esa magnitud no es selección de
   mejores oportunidades: es concentración en eventos extremos de la pata
   corta**, que aparecen igual con selección real que con las otras 5 hipótesis
   — el patrón es indistinguible del "placebo gana" de R13.
2. **El componente que falta no es "más universo" ni "otra combinación de
   features" — es resolución temporal de datos.** El universo ancho solo tiene
   ~4 meses de historia utilizable (vs 14.5 del universo de 45), y ese OOS cae
   justo en la ventana anómala ya conocida. No se puede juzgar honestamente si
   el universo ancho aporta alpha real sin extender `taker_flow` hacia atrás
   (2025-06→2025-12) para esos ~300 símbolos adicionales — trabajo de
   ingesta, no de research, y coherente con "no inventar una espera de meses":
   es descargable YA si se decide invertir el próximo round en eso.
3. **Ningún mecanismo direccional/predictivo (de precio, flujo, OI, L-S,
   cross-sectional, cualquier interacción) mostró alpha capturable en 15
   rounds.** Eso no significa que no exista una estrategia rentable en este
   universo — significa que **la categoría "predecir el próximo movimiento" está
   agotada** con las herramientas y controles usados. Hay una categoría
   económicamente distinta, nunca testeada, con evidencia inicial real:

---

## 5. HALLAZGO NUEVO — Funding-rate carry (no direccional)

Chequeo rápido de factibilidad sobre `funding_hist` (63 símbolos, 14.5 meses):
existe **dispersión de funding persistente y grande** entre símbolos —
no una anomalía puntual, un promedio sostenido en cientos de observaciones:

| Símbolo | funding medio/8h | anualizado aprox. | n observaciones |
|---|--:|--:|--:|
| BTWUSDT | +4.02 bp | +4 407 bp/año | 529 |
| AKEUSDT | +1.72 bp | +1 880 bp/año | 1 643 |
| ESPORTSUSDT | +1.64 bp | +1 791 bp/año | 2 024 |
| … | | | |
| HOMEUSDT | **−8.53 bp** | **−9 343 bp/año** | 1 988 |
| LABUSDT | −7.54 bp | −8 252 bp/año | 2 032 |
| REUSDT | −7.46 bp | −8 167 bp/año | 445 |

Esto es **cash-and-carry**, no predicción de precio: si el funding de un símbolo
es persistentemente negativo (shorts pagan a longs), estar **LARGO el perpetuo
+ CORTO el spot equivalente** (o viceversa si es positivo) cobra ese funding de
forma aproximadamente delta-neutral — el PnL no depende de acertar la dirección,
depende de que el funding no se revierta más rápido de lo que se cobra, y de
que el costo de financiar/pedir prestado el spot sea menor al funding cobrado.
`spot_klines` cubre 240 símbolos — suficiente solapamiento para construir el
hedge en la mayoría de estos casos. **Nunca se testeó en 15 rounds** — todos los
usos de `funding_hist` hasta ahora fueron como *predictor direccional* (H16,
R12), no como *fuente de yield*.

Esto no es prueba de que funcione — es un hallazgo de factibilidad, no un
backtest. Falta: verificar el costo/margen real de la pata spot (borrow rate si
existe, o el costo de capital si se financia con el mismo colateral), simular
el hedge causal (spot vs perp, basis risk), medir turnover cuando el funding
cambia de signo, y — crítico — comprobar que la dispersión de funding **no es**
simplemente el reflejo de la dirección que ya sabemos que no predice nada (evitar
redescubrir H16/H10 con otro nombre).

---

## CANDIDATAS FINALES

| Candidato | Clasificación |
|---|---|
| `A1_vol_expansion_continue` | **FAILED** — la ganancia aparente es concentración en pata corta, no señal |
| `A2_taker_aggression` | **FAILED** — se invierte en OOS |
| `B1_momentum_wide` | **FAILED** (pero informativo — universo amplifica magnitud, no estabilidad) |
| `B2_volume_anomaly_confirm` | **FAILED** — inestable train/val/oos |
| `C1_shortterm_reversal` | **FAILED** — sin efecto (≈random) |
| `C2_shortterm_continuation` | **FAILED** — sin efecto (≈random) |

Ninguna alcanza ni PARK (§ objetivo: "$75–149 con alpha OOS robusto") — todas
las lecturas OOS positivas están contaminadas por la superposición estructural
con 2026Q3, que el propio criterio de éxito del round excluye explícitamente.

---

## Diseño de Round 16 (NO cierre de la investigación)

**Foco único: FUNDING-RATE CARRY, mecanismo nuevo, no direccional.**

1. Construir el book de carry causal: para cada símbolo con `funding_hist` +
   `spot_klines`, señal ex-ante = funding trailing 14-30d (media y estabilidad,
   no el nivel de un solo settlement — ya sabemos que el nivel puntual no
   predice precio, aquí se usa como *tasa a cobrar*, no como predictor).
2. Portfolio: top-N por |funding trailing| con signo (carry direction), spot-perp
   delta-neutral, rebalanceo cuando el funding se comprime o cambia de signo.
3. Costos: fees de ambas patas (spot + perp), slippage, financiamiento del spot
   (si aplica margen), turnover al rebalancear.
4. TRAIN/VAL/OOS, placebo (rebalanceo en fechas aleatorias, símbolos aleatorios
   ponderados igual), estabilidad temporal explícita excluyendo 2026Q3 aparte.
5. Capital ≤450: el hedge dobla el capital requerido por posición (pata spot +
   pata perp) — esto puede ser la limitación real; cuantificarlo explícitamente
   en vez de asumir viabilidad.

Si el carry tampoco alcanza $150/mes: documentar cuánto rinde, y recién ahí —
con las dos categorías de mecanismo (predictivo Y carry) agotadas con evidencia
— será el momento de una conclusión formal, no antes.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
