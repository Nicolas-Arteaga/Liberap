# ROUND 14 — ALTCOIN CROSS-SECTIONAL ALPHA DISCOVERY

**Fecha:** 2026-09-17 · Sin descargas nuevas · Script: `agent/backtest/r14_discovery.py`
· Grid de rebalanceo cada 4h (2 460 timestamps posibles, 1 452 usables con
≥20 símbolos válidos) · TRAIN ≤ 2026-04-16 / VAL ≤ 2026-06-15 / OOS > eso.

## Cobertura de datos (declarada, no escondida)

El venue tiene ~400+ perps con precio+taker-flow (`taker_flow`, 429 símbolos). Pero
**OI + funding + L/S histórico solo existen para el universo ex-ante de 63**
(el mismo que backfilleamos desde `data.binance.vision` en R9-R11), de los cuales
**45 tienen los 14.5 meses completos** (el resto listó después). Este round usa
esos **45 símbolos feature-completos** — es donde viven `dOI`, `funding_z`,
`toptrader/global_ls`, `taker_imb`, no solo precio. Ampliar a ~400 pares
exigiría re-derivar todas esas señales para 350+ símbolos sin historia de
OI/funding (no existe en Binance Vision para la mayoría antes de su propio
listing) — no es "esperar más datos", es un límite real y documentado del venue,
no del proyecto.

---

## Metodología (resumen)

1. Features causales por símbolo (15m): momentum 1h/4h/24h, vol realizada 24h +
   percentil causal (compresión), volumen anómalo, ΔOI 1h/4h, funding z, taker
   imbalance z.
2. **Estandarización CROSS-SECCIONAL en cada timestamp** (z-score entre los
   símbolos válidos de ESE bar) — separa señal idiosincrática de drift común del
   universo, la lección explícita de R13.
3. **9 scores candidatos predeclarados** (interacciones de 2+ features, ejemplos
   del brief) + 2 baselines (momentum-only, vol-only) + **1 oracle** (retorno
   futuro real — sanity check, jamás usado como estrategia).
4. Por score: LONG top-decile, SHORT bottom-decile, LONG-SHORT — sin asumir
   dirección.
5. Screening en TRAIN @24h vs **random-ranking** (control obligatorio).
6. Ningún candidato pasó el screening → no hay "candidato prometedor" al que
   aplicarle sim económica de $450 (Fase 7 es condicional a eso).

---

## Las 10 hipótesis (screening TRAIN, @24h, N=5, long-short)

| # | Score (mecanismo) | TRAIN bp | CI excl 0 | symPos | vs RANDOM (+6.5bp) | Veredicto |
|---|---|--:|:--:|--:|---|---|
| 1 | `S5_relmom_OI_confirm` (momentum relativo + ΔOI confirma) | +5.5 | No | 0.43 | ≈ igual | **FAILED** |
| 2 | `momentum_only` (baseline) | +4.5 | No | 0.45 | ≈ igual | **FAILED** |
| 3 | `S2_compression_pending` (compresión + ΔOI) | +2.9 | No | 0.52 | ≈ igual | **FAILED** |
| 4 | `S8_funding_extreme_fade` (fade funding extremo) | +0.9 | No | 0.44 | ≈ igual | **FAILED** |
| 5 | `S4_funding_taker_disagree` (taker vs funding) | +0.7 | No | 0.52 | ≈ igual | **FAILED** |
| 6 | `S6_volume_OI_breakout` (volumen anómalo + ΔOI) | −4.0 | No | 0.45 | peor | **FAILED** |
| 7 | `S3_price_OI_divergence` (precio/OI en cross-section) | −11.2 | No | 0.40 | peor | **FAILED** |
| 8 | `S7_outlier_convexity` (outlier multi-feature) | −11.6 | No | 0.43 | peor | **FAILED** |
| 9 | `S1_expansion_OI` (expansión de vol + ΔOI) | **−14.9** | **Sí** | 0.26 | **peor, signo equivocado** | **FAILED** |
| 10 | `vol_only` (baseline) | **−18.5** | **Sí** | 0.36 | **peor, signo equivocado** | **FAILED** |
| — | **RANDOM (control)** | +6.5 | No | — | — | referencia |
| — | **ORACLE (retorno futuro real, sanity)** | **+298.0** | **Sí** | — | — | *no es estrategia* |

**Ningún candidato supera el criterio pre-registrado** (CI excluye 0, supera al
random por ≥5 bp, y supera el costo bruto de 24 bp) **con el signo correcto**.
Los dos únicos con CI que excluye 0 (`S1`, `vol_only`) tienen el **signo
equivocado** (long-top/short-bottom pierde; ganaría invertido, pero invertir
después de ver el resultado es exactamente el cherry-picking que el round
prohíbe — no cuenta).

**El oracle confirma que el motor funciona:** cuando se rankea por el retorno
futuro REAL (información imposible de tener ex-ante), la separación es enorme
(+298 bp, CI [235,370]). Esto descarta que el resultado nulo sea un bug del
pipeline de ranking/portfolio — es una ausencia genuina de señal en las 9
interacciones testeadas.

---

## Detalle de los 3 con mejor lectura superficial (transparencia — NINGUNO gana)

Por horizonte (bp, train/val/oos) y por variante/N (para exponer la
inestabilidad que el agregado esconde):

**`momentum_only`** — el único con tendencia OOS positiva creciente:
| h | train | val | oos |
|---|--:|--:|--:|
| 1h | −2.2 | −1.8 | −1.0 |
| 4h | −4.8 | +1.5 | +9.6 |
| 12h | −2.2 | +26.8 | +36.3 |
| 24h | +4.5 | +32.6 | +48.3 |
| 72h | +12.6 | +19.6 | **+99.8** |

Se ve prometedor en el agregado — **pero por pata se desarma**: `long_top`
train=−30.8 / val=**+69.3** / oos=**−29.2** (se invierte dos veces);
`short_bottom` train=+39.8 / val=**−4.2** / oos=**+125.8**. Ninguna pata sola es
estable. Y `N=1` da OOS=**+203 bp** — típico de que una o dos operaciones
extremas (el mismo evento de dispersión de 2026Q3 aislado en R13) dominan el
promedio. **No es una prima de momentum estable: es el mismo evento de R13
reapareciendo.**

**`vol_only`** y **`S1_expansion_OI`**: mismo patrón — CI excl 0 en TRAIN pero
signo perdedor, y por pata/N totalmente inestable (`vol_only` N=1: train −35 /
val +3.5 / oos **−227**; `S1` N=1: train −34 / val +51 / oos **−175**). Cero
capturable.

---

## Fases no ejecutadas y por qué

- **Fase 5 (concentración N=1..10) y Fase 7 (sim económica $450):** se hicieron
  para los 3 casos de "mejor lectura superficial" únicamente con fines
  diagnósticos (arriba) — no se corrió la simulación económica completa de
  costos/funding/slippage porque **ningún candidato pasó el screening
  pre-registrado**; correrla sobre un candidato que ya perdió en TRAIN sería
  gastar rigor en confirmar lo que el screening ya mostró.
- **Liquidaciones anormales:** documentado — `liquidations_research` solo tiene
  ~2 días de historia (el colector sigue corriendo, research únicamente). No
  alcanza para una feature cross-sectional sobre 14.5 meses. Sigue PARK por
  datos, no se fuerza.

---

# ROUND 14 VERDICT

# FAILED (las 10 hipótesis)

Ninguna interacción cross-sectional predeclarada (ni los 2 baselines) supera al
ranking aleatorio con el signo correcto. El oracle confirma que el motor de
ranking/portfolio detecta separación real cuando existe — así que esto es un
resultado nulo genuino, no un fallo de metodología.

**MAX VALIDATED MONTHLY PNL: $0** (no hay candidato al que aplicarle sim
económica).

## Qué aprendimos (el componente que limita el resultado)

1. **No es un problema de selección de features aisladas — ya lo sabíamos de
   R1-R12.** R14 fue más lejos: probó **interacciones y combinaciones**
   (compresión+OI, funding+taker, momentum+OI, outlier multi-feature) de forma
   sistemática y **tampoco hay separación**. El espacio de "combinar 2-3 señales
   conocidas con z-score cross-seccional a horizontes de 1h-72h" está agotado.
2. **El único patrón con apariencia de señal (`momentum_only` a 72h) es, otra
   vez, el evento de dispersión de 2026Q3** que R13 ya aisló — no una prima
   nueva. Confirma que esa ventana de 6 semanas sigue siendo la única fuente de
   "retorno" grande en el dataset, y que ningún mecanismo testeado hasta ahora
   (ni cross-sectional) la anticipa ex-ante; solo la atraviesa por casualidad de
   estar largo/corto en el momento correcto.
3. Con esto, **14 rounds, ~40 mecanismos distintos** (precio, taker, funding, OI
   nivel/aceleración, L/S retail-vs-smart, beta, momentum, dispersión,
   interacciones cross-sectional) sobre precio+flujo+posicionamiento a
   15m-72h no producen alpha capturable en este universo.

## Hipótesis concreta para Round 15

**Round 15 (último, dos partes obligatorias, en ese orden):**

1. **Retest final, acotado:** repetir el mejor candidato de cada round anterior
   (dOI-UP-régimen de R10/R11, `momentum_only`-72h de R14) **excluyendo
   explícitamente 2026Q3** de TRAIN/VAL/OOS (no como cherry-pick de resultado —
   como test de robustez: ¿sobrevive el efecto sin la única ventana anómala del
   dataset?). Si sí → hay algo real y acotado para escalar. Si no (lo esperable
   dado 14 rounds de evidencia) → confirma que no hay edge fuera de ese evento.
2. **Conclusión final con evidencia**, no una hipótesis 41: si (1) no produce
   nada, Round 15 entrega el veredicto formal — con la tabla completa de los 14
   rounds — de que **≥150 USDT/mes no es alcanzable con los datos y el universo
   actuales** (15m-72h, 45-63 símbolos, sin L2 order-book / opciones / on-chain),
   y qué inversión de datos (no de tiempo) sería necesaria para reabrir la
   búsqueda — decisión que le corresponde al usuario, no a otro round de
   research.

No se propone una hipótesis 41 más porque el patrón de 14 rounds ya es
consistente y las herramientas de control (placebo, oracle, cross-sectional,
regímenes) están agotadas dentro de este dataset.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
