# GATE V4 — GOLD STANDARD DE CONFIABILIDAD (Phase 3) — criterios PRE-REGISTRADOS

Pre-registro: 2026-09-05, ANTES de correr `gate_v4.py` y ANTES de mirar cualquier
resultado de replay. Pregunta única de la fase:

> ¿Podemos confiar en que el motor de backtest de Verge **clasifica correctamente
> una estrategia como ganadora/perdedora** y **estima su expectancy agregada** de
> forma suficientemente robusta como para tomar decisiones de investigación?

Resultado posible: **FAILED / LIMITED / PASS**. PASS NO es el default.

---

## 0. Qué quedó y qué NO quedó demostrado en Phase 2 (a validar/refutar acá)

**Quedó demostrado (solo para MA Slope Caso 2):**
- El motor dejó de fabricar un sign flip (v1: replay +$43/PF 1.16 vs real
  −$116/PF 0.55). Con `fidelity` completo: replay PF 0.53–0.62 vs real 0.55.
- Los bugs estructurales (timeout, filtro BTC, veto diario, funding, cobertura,
  ocupación cruzada) están cerrados.

**NO quedó demostrado:**
- Que "PF alto en backtest ⇒ rentable de verdad". Solo se vio 1 estrategia
  perdedora reproducida como perdedora. **Un motor que siempre dice "perdedora"
  también acertaría ese caso.**
- Que el motor no convierta perdedoras en ganadoras (false positive) en OTRAS
  estrategias/familias.
- Que el motor confirme ganadoras reales (no las destruya — false negative).
- Que el resultado agregado sea estable bajo la path-dependence de los cupos
  (Phase 2 solo midió 2 realizaciones: V2 y V3).
- Que preserve el ORDEN relativo entre estrategias.
- Nada sobre familias no-MaGeometry (FVG, ADN) a nivel económico.

Phase 3 ataca exactamente esos huecos.

---

## 1. BENCHMARK (pre-declarado, NO elegido para que el motor quede bien)

7 estrategias, todas replayables (StrategyType ∈ MaGeometry/FVG/AdnCompression),
con ≥ 70 trades reales cerrados dentro del dataset (ciclo de vida ≤ 2026-08-16),
elegidas por **spread de PF real y diversidad de familia/duración**:

| # | Estrategia | Familia | n real | PF real | exp/trade real | dur. media | CLASE (ground truth) |
|---|---|---|---|---|---|---|---|
| 1 | MA Slope Caso 3 | MaGeometry | 70 | **1.85** | +$0.93 | 30.1 h | WINNER (fuerte) · larga |
| 2 | FVG - 15m | FVG | 371 | **1.29** | +$0.48 | 5.7 h | WINNER · otra familia |
| 3 | MA Slope Caso 3 (15m) | MaGeometry | 89 | **1.18** | +$0.28 | 17.6 h | WINNER (leve) |
| 4 | MA Slope Caso 1 | MaGeometry | 89 | **0.91** | −$0.23 | 24.1 h | NEUTRAL / perdedora leve (borderline) |
| 5 | FVG - 1m | FVG | 695 | **0.69** | −$0.31 | 1.1 h | LOSER · duración corta |
| 6 | Compresion ADN - Micro (5m) | AdnCompression | 112 | **0.58** | −$0.87 | 8.4 h | LOSER · 3ª familia |
| 7 | MA Slope Caso 2 | MaGeometry | 113 | **0.55** | −$1.03 | 18.2 h | LOSER (fuerte) · ancla Phase 1/2 |

**Ground truth (REAL)** para clasificar:
- **WINNER**: PF ≥ 1.15 **y** exp/trade ≥ +0.05
- **LOSER**: PF ≤ 0.90 **y** exp/trade ≤ −0.05  (*Caso 1: PF 0.91, exp −0.23 → borderline; se trata como NEAR-NEUTRAL: no cuenta como false-positive si el replay lo pone NEUTRAL, sí cuenta si lo pone WINNER*)
- **NEUTRAL**: cualquier otro caso.

Ventana de comparación por estrategia: `[primera señal real, min(último cierre real, 2026-08-15)]`.
Solo se comparan trades reales con ciclo de vida completo dentro de esa ventana.

Ningún cambio a esta lista después de ver resultados. Si una estrategia no se
puede correr (cobertura, timeout de compute), se marca **UNKNOWN** y empuja el
veredicto hacia LIMITED — nunca se reemplaza por otra.

---

## 2. Perturbación del caos (Monte Carlo) — NO se optimiza, es sensibilidad

Se acepta que el sistema de 3 cupos es path-dependent. Se MIDE cuánto afecta.
Manteniendo TODO lo demás idéntico (mismo `fidelity`, misma config, mismo
universo, mismo precómputo del patrón), se introducen perturbaciones pre-fijadas:

- **jitter de admisión**: ±1 s, ±2 s, ±5 s, ±10 s (aplicado al `open_time` antes
  del FIFO de cupos; a resolución de 5 min afecta el orden en empates y cruces
  raros de vela).
- **jitter de liberación de cupo**: ±(mismo set) al `close_time`.
- **desempate**: {símbolo asc, símbolo desc, orden de precómputo, shuffle seeded}.
- **N seeds**: ≥ 150 por (estrategia × nivel de jitter) donde el compute lo permita
  (MaGeometry); ≥ 40 para familias caras (FVG global, ADN). Menos → se reporta
  como cobertura MC reducida y empuja a LIMITED.

Salida por métrica (PnL neto, PF, expectancy/trade, max DD, nº trades, exposición):
**P5 / P25 / P50 / P75 / P95**.

---

## 3. Costos — STATISTICALLY POSITIVE ≠ ECONOMICALLY POSITIVE

Toda estrategia se evalúa en el replay a **0 bp / 2 bp / 5 bp por lado** (+ el
funding real donde hay cobertura). Una estrategia con PF > 1 a 0 bp que cae a
PF < 1 a 2 bp es **económicamente negativa**.

---

## 4. Out-of-sample

Cada ventana de estrategia se parte por TIEMPO en:
- **Discovery** = primer 40 %
- **Validation** = siguiente 30 %
- **Final OOS** = último 30 % — **intocable** hasta que este documento esté congelado (lo está).

Prohibido: tuning, threshold hunting, selección posterior, cambiar universo /
ventana / costos / seeds, eliminar símbolos malos. Si algo falla en Final OOS se
registra FAILED.

---

## 5. GATES cuantitativos (pre-registrados)

Clasificación del REPLAY: se usa la **mediana Monte Carlo** de PF y exp/trade
(o el single-run donde no hay MC), con los mismos umbrales que el ground truth.

| Gate | Métrica | PASS | LIMITED | FAILED |
|---|---|---|---|---|
| **A. Fidelidad del signo** | signo del PnL neto replay (mediana MC) vs REAL, sobre las 7 | 7/7 | 6/7 y el error NO es loser→net-positivo | ≤5/7, **o cualquier REAL loser con replay net > 0** |
| **B. Ranking de estrategias** | Spearman ρ(rank PF real, rank PF replay) sobre las 7 | ρ ≥ 0.85 **y** los 3 winners en la mitad alta y los 3 losers fuertes en la baja | ρ ≥ 0.60 | ρ < 0.60 |
| **C. Estabilidad Monte Carlo** | % de seeds MC que clasifican bien (winner→PF>1 / loser→PF<1), por estrategia | toda estrategia ≥ 90 % **y** winners con P5(PF) > 1.0 **y** losers con P95(PF) < 1.0 | ≥ 75 % **y** winners P25(PF) > 1.0 | alguna estrategia < 75 %, **o** winner P25(PF) < 1.0, **o** loser P75(PF) > 1.0 |
| **D. FALSE POSITIVE** *(peso máximo)* | REAL losers (PF ≤ 0.90) que el replay (mediana MC) muestra como PF ≥ 1.10 | 0 | 0 (requisito duro) — un loser mostrado como NEUTRAL (0.90–1.10) cuenta acá, no en FAILED | **≥ 1** |
| **E. FALSE NEGATIVE** | REAL winners (PF ≥ 1.15) que el replay (mediana MC) muestra como PF ≤ 0.90 | 0 | ≤ 1 winner mostrado como NEUTRAL (no LOSER) | **≥ 1** winner mostrado como PF ≤ 0.90 |
| **F. Sensibilidad al jitter** | ¿la clase (winner/loser) del replay cambia en algún nivel de jitter (±1..±10 s)? + spread (P95−P5)/P50 de PF | clase estable en todos los niveles **y** spread ≤ 0.25 | clase estable **y** spread ≤ 0.50 | clase cambia en algún nivel para alguna estrategia |
| **G. Sensibilidad a costos** | ¿algún REAL loser se vuelve net-positivo en el replay a 0/2/5 bp? ¿algún REAL winner se vuelve net-negativo a 2 bp? | ningún loser positivo a 0 bp **y** todo winner positivo a 5 bp | winners positivos a 2 bp | **algún REAL loser net-positivo a ≥ 2 bp**, o ≥ 2 winners net-negativos a 2 bp |
| **H. Estabilidad OOS** | ¿REAL y REPLAY coinciden en winner/loser en Final OOS? ¿la clase es consistente en los 3 segmentos? | coinciden en Final OOS 7/7 **y** clase consistente en 3 segmentos ≥ 6/7 | coinciden en Final OOS ≥ 6/7 | discrepan en Final OOS ≥ 2/7, **o** cualquier discrepancia loser↔winner en Final OOS |

### Regla de veredicto global (pre-registrada)

- **FAILED** si: gate D = FAILED (cualquier false positive duro), **o** gate A =
  FAILED, **o** gate C = FAILED, **o** gate E = FAILED, **o** ≥ 3 gates en FAILED.
- **PASS** si: A, C, D, E **todos** en PASS; **y** B, F, G, H **todos** al menos
  LIMITED; **y** ningún gate en FAILED; **y** ≥ 5 de 8 gates en PASS; **y** la
  cobertura MC cubre las 3 familias.
- **LIMITED** en cualquier otro caso.

### Mapeo a la respuesta

- **PASS** → el motor es suficientemente confiable para usarlo como instrumento de
  evaluación económica de nuevas estrategias.
- **LIMITED** → sirve para determinadas preguntas, pero todavía NO sirve para
  declarar rentabilidad con suficiente confianza. El reporte debe listar
  exactamente qué preguntas SÍ y cuáles NO.
- **FAILED** → el motor puede producir conclusiones económicas engañosas.

Sin lenguaje ambiguo ("bastante confiable", "parece funcionar"). Si falla, se
declara FAILED sin intentar rescatarlo.
