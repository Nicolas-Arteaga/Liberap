# VERGE — VALIDATION PROTOCOL (FASES 4–7)

**Fecha:** 2026-09-06
Aplica a **cualquier** candidato que sobreviva Discovery (Fase 3). Se congela
ANTES de correr Fase 5. No se modifica para mejorar un resultado OOS.

---

## FASE 4 — FREEZE

Cuando una hipótesis del ledger muestra señal prometedora en Discovery, se
firma un **snapshot congelado** en el ledger con 8 bloques. A partir de ese
momento, **nada** de esto se toca por resultado:

1. **Definición de la señal** — fórmula exacta, ventanas, deciles/umbrales.
2. **Parámetros** — todos, con su valor numérico. Cero grados de libertad
   abiertos.
3. **Universo** — lista explícita de símbolos + regla de inclusión (liquidez
   ≥ $1 M / 15 m trailing-7d por barra, o el filtro que aplique) + regla de
   entrada/salida de símbolos del universo.
4. **Costos** — fee, funding, slippage, spread (valores en §5.3).
5. **Sizing** — regla exacta ($ fijo, % de riesgo, vol-target...). Máximo
   $450 por estrategia.
6. **Reglas de entrada** — condición, timing (qué vela, qué precio),
   filtros previos.
7. **Reglas de salida** — TP, SL, salida genuina de la estrategia.
   **Prohibido timeout artificial** (ver §5.4).
8. **Gestión de posición** — nº máximo simultáneas, qué pasa si hay señal
   con slots llenos, conflictos con otras estrategias.

El snapshot lleva fecha, hash del código de la señal, y el rango de datos
usado en Discovery. Discovery y Validation **no comparten datos**.

---

## FASE 5 — VALIDATION

### 5.1 Partición temporal

- **Discovery / TRAIN:** bloque más antiguo (~50% de la historia disponible).
- **VALIDATION:** bloque intermedio (~25%). Se mira **una sola vez** por
  candidato congelado.
- **FINAL-OOS:** bloque más reciente (~25%). Se mira **una sola vez en la
  vida del candidato**, al final. Si se mira y falla, el candidato está
  muerto — no se re-congela con otro corte.
- Nunca mezclar futuro con pasado. Ningún estadístico (media, percentil,
  z-score, beta, vol) se calcula con datos posteriores a la barra de
  decisión. Los rolling se calculan **causalmente** (solo hacia atrás).
- Prohibido `updated_at` de tablas live-derived como input.

### 5.2 Walk-forward

- Mínimo **4 bloques temporales** contiguos no solapados.
- En cada bloque: parámetros **congelados** (no re-fit). El walk-forward acá
  NO re-optimiza — mide estabilidad del edge ya congelado a lo largo del
  tiempo.
- Reportar la métrica clave (PF neto, expectancy, PnL/capital/mes) **por
  bloque**. Un edge que solo aparece en 1 de 4 bloques = FAILED.

### 5.3 Costos (obligatorio incluir TODOS)

| Costo | Valor por defecto | Fuente / nota |
|---|---|---|
| **Fee taker** | 0.04% por lado (0.08% round-trip) | tasa real del simulador Verge (`TradingSimulationService`) |
| **Funding** | histórico real de `funding_rates` cuando el símbolo/período tiene cobertura; si no, **declarar la limitación y usar el peor caso del percentil 90 del símbolo** | NO usar el 0.01% plano del simulador |
| **Slippage** | escenarios **0 / 2 / 5 bp** por lado; el gate económico se evalúa a **2 bp** | H1–H12 mostraron que 2 bp mata la mayoría de los "edges" |
| **Spread** | cuando el mecanismo opera en símbolos ilíquidos o en ventanas de estrés (cascadas): medio spread estimado de `orderbook_ofi` si hay dato; si no, +2 bp adicionales | crítico para H14/H19 |

Reportar el resultado a **0, 2 y 5 bp**. Distinguir explícitamente
**estadísticamente positivo** de **económicamente positivo** (neto de todo,
a 2 bp, ≥ 150 USD/mes por estrategia).

### 5.4 Execution realista

- **Capital:** ≤ $450 por estrategia. No asumir capital infinito. Modelar el
  capital realmente disponible (si 3 posiciones de $150 están abiertas, no
  hay una 4.ª).
- **Posiciones simultáneas:** límite explícito de la estrategia. Cuando hay
  señal y no hay slot libre: la señal **se pierde** (no hay cola), salvo que
  la estrategia defina explícitamente una cola causal.
- **Conflictos entre estrategias:** si dos estrategias del portfolio quieren
  el mismo símbolo a la vez, resolver con una regla causal fija (definida en
  `PORTFOLIO_CAPITAL_PROTOCOL.md`), no con hindsight.
- **Entrada realista:** precio de entrada = precio disponible **después** del
  cierre de la barra/evento de la señal (open de la barra siguiente, o
  peor-caso dentro de la barra siguiente). Nunca el close de la barra de
  señal como fill garantizado. Aplicar slippage §5.3.
- **Salida realista:** TP/SL se ejecutan al precio del nivel (clamp exacto,
  como el worker .NET real), con slippage. Una salida "genuina de la
  estrategia" (p. ej. "cerrar cuando el OI se estabiliza") se evalúa con la
  info disponible en cada barra, sin lookahead.
- **NO timeout artificial.** Una posición permanece abierta hasta: **TP**,
  **SL**, **liquidación** (a 1x prácticamente nunca), o una **salida genuina
  definida por la estrategia** (que no sea "pasaron N horas"). Si al final
  del dataset una posición no cerró ⇒ queda **OPEN / CENSORED**, se reporta
  aparte con su duración observada, y **nunca** se cuenta como pérdida.

### 5.5 Intrabar handling

- Con OHLC de 5 m no se conoce el orden intra-vela. **Prohibido asumir
  TP-first favorable.** Reglas:
  - Si existe dato de mayor resolución para esa vela (p. ej. 1 m para BTC, o
    ticks) ⇒ usar la **secuencia conocida**.
  - Si no ⇒ **secuencia conservadora**: si en la misma vela se tocan TP y SL,
    contar **SL** (peor caso).
  - Registrar cuántos trades cayeron en el caso ambiguo y reportar el
    resultado también bajo el supuesto neutro (50/50) como sensibilidad,
    etiquetado **AMBIGUOUS**.
- Para estrategias donde TP y SL están muy separados (≥ 4×) el caso ambiguo
  es raro y el impacto chico; para scalping (TP ≈ SL) el caso ambiguo domina
  ⇒ esas estrategias necesitan 1 m o se declaran **UNTESTABLE** con 5 m.

---

## FASE 6 — ROBUSTNESS (para destruir la hipótesis, no para tunear)

Cada candidato congelado corre TODO esto. Ningún resultado de acá se usa para
elegir mejores parámetros. Si el edge no sobrevive ⇒ FAILED.

| Prueba | Qué se perturba | Criterio de supervivencia |
|---|---|---|
| **MC trade ordering** | orden de ejecución de trades / liberación de slots (≥ 500 permutaciones) | la conclusión económica (PnL/capital/mes ≥ 150, PF > 1.2) se mantiene en **≥ 90%** de las permutaciones; reportar P5/P50/P95 |
| **Perturbación de entrada** | fill ± 1–5 bp / ± 1 vela | el signo del PnL neto no cambia; degradación monótona y suave |
| **Perturbación de slippage** | 0 / 2 / 5 / 10 bp | económicamente positivo a **≥ 5 bp** (colchón sobre el gate de 2 bp) |
| **Perturbación de fees** | ±50% de la tasa base | sin flip de signo |
| **Perturbación de parámetros** | ± pequeño alrededor del valor **congelado** (grid local ±20%) | el edge no depende de un punto exacto; superficie plana, no un pico |
| **Subperíodos** | cada bloque del walk-forward + terceros | positivo en **≥ 3 de 4** bloques, sin un solo bloque que aporte > 60% del PnL total |
| **Símbolos** | drop-one (quitar cada símbolo de a uno) + bootstrap de símbolos | ningún símbolo aporta > 40% del PnL; positivo en ≥ 60% de los bootstraps |
| **Regímenes** | bull / bear / chop de BTC; alta vs baja vol market-wide | positivo (o al menos no-negativo) en ≥ 2 de 3 regímenes; declarar si el edge es condicional a un régimen |
| **Placebo temporal** (repetido) | señal desplazada +25 barras | el placebo NO reproduce el edge |
| **Muestra matcheada sin-evento** | controles con misma vol/retorno sin el evento | el edge del evento supera claramente al de la muestra matcheada |

---

## FASE 7 — ECONOMIC GATE

Objetivo de producción: **≥ 150 USDT netos/mes por estrategia con ≤ 450 USDT
de capital asignado**, sobre el bloque **FINAL-OOS**.

### 7.1 Métricas a reportar (todas, sin cherry-pick)

- PnL mensual (serie, no solo el promedio) y PnL total.
- **PnL / capital asignado / mes** (la métrica del objetivo).
- Profit Factor, expectancy ($/trade), Win Rate.
- Drawdown absoluto ($) y % sobre capital asignado.
- Sharpe / Sortino (si el nº de trades lo hace significativo; si no, omitir y
  decirlo).
- Nº de operaciones, exposición media y máxima, utilización de capital.
- Turnover (volumen tradeado / capital / mes).
- Fees pagados, funding pagado/cobrado, slippage asumido — desglosado.
- Retorno sobre capital (%/mes y anualizado, con la advertencia de anualizar
  una muestra corta).
- Nº de trades OPEN/CENSORED al final del dataset + su duración observada.

### 7.2 Criterio de veredicto

| Veredicto | Condición |
|---|---|
| **PASS** | ≥ 150 USD/mes neto en FINAL-OOS **a 2 bp de slippage**, PF ≥ 1.3, positivo en ≥ 3/4 bloques walk-forward, sobrevive TODA la Fase 6, DD% ≤ 25% del capital, y el mecanismo económico sigue siendo explicable ex-post. |
| **INVESTIGATE** | positivo y robusto pero PnL/mes entre ~80 y ~150, o depende de un régimen. Candidato a portfolio (Fase 8) con sizing mayor, no a producción solo. |
| **FAILED** | cualquier eslabón roto: no supera costos, no es robusto, solo 1 bloque, edge concentrado en 1 símbolo/régimen, placebo lo reproduce, o requiere timeout artificial para ser positivo. **Se cierra aunque el backtest bruto sea rentable.** |

### 7.3 Escepticismo escalado por magnitud (regla del usuario)

- Resultado ~+150 → seguir el protocolo normal.
- Resultado ~+300 → **investigar** el origen: ¿un régimen? ¿pocos símbolos?
  ¿una racha? Doble check de lookahead y de costos.
- Resultado ~+1000 → **asumir que hay un bug o lookahead hasta demostrar lo
  contrario**. Auditar fill, timestamps, survivorship, y el intrabar antes de
  creer nada.

---

## Reglas transversales (recordatorio)

- Un solo split o una sola muestra **no** declara edge.
- Correlación ≠ causalidad sin el control de placebo + muestra matcheada.
- Si se probaron N variantes, van **todas** al ledger; reportar solo la
  ganadora está prohibido.
- El motor `agent/backtest/engine.py` tiene fidelidad **PARTIAL** — cualquier
  uso suyo en Validation exige: `zombie_timeout_decision` **desactivado**,
  intrabar según §5.5, y verificación cruzada de al menos 10 trades contra un
  cálculo manual sobre las klines crudas.
