# BACKTEST RELIABILITY — PHASE 3 (GOLD STANDARD) — INTERRUMPIDO POR PÉRDIDA DE DATOS

Fecha: 2026-09-05/06
Pregunta única: **¿podemos confiar en que el motor de backtest de Verge clasifica
correctamente una estrategia como ganadora/perdedora y estima su expectancy
agregada de forma robusta para tomar decisiones de investigación?**

Criterios PRE-registrados: `agent/backtest/GATE_V4_CRITERIA.md` (congelado antes de correr).

---

## 0. Qué pasó (contexto obligatorio)

El benchmark de 7 estrategias (`gate_v4.py`) arrancó y completó la **estrategia #1
(MA Slope Caso 3)** contra la config REAL de la DB. Mientras corría la #2
(FVG-15m), la PC se reinició y, al volver, un **reset accidental de Docker
Desktop borró todos los volúmenes**, incluida la base de datos `Verge`
(`SimulatedTrades` + `StrategyProfiles`). No había backup.

**Consecuencia para Phase 3:** el benchmark completo de 7 estrategias **no se
puede reproducir**. Requiere (a) los `PatternParamsJson` reales de cada estrategia
—perdidos, solo sobrevive el de MA Slope Caso 2— y (b) ground-truth confiable de
trades reales por estrategia. El único log de trades en disco (`agent/data/trades.csv`)
está **corrupto para este uso**: valores de PnL basura (reconstruye Nexus a
+$228k, FVG-1m a −$192k), es parcial (70/113 de MA Slope Caso 2), no distingue
sub-estrategias Nexus, y no tiene timestamps exactos ni `AgentDecisionJson`.

**Lo que SÍ sobrevivió intacto (exports a disco, pre-reset):**

| Archivo | Contenido | Confiable |
|---|---|---|
| `scratch_gate_v4_results.json` | **Resultado completo de gate_v4 para MA Slope Caso 3** (50 seeds × grilla de perturbación pre-registrada, contra la config REAL) | **SÍ** |
| `scratch_ma2_real.csv` | MA Slope Caso 2, 113 trades reales, `AgentDecisionJson` completo | **SÍ** |
| `scratch_all_trades_p2.csv` | Todas las estrategias, símbolos + tiempos open/close (sin PnL) | SÍ (solo para máscaras de fidelidad) |
| Datasets SQLite (`binance_vision_clean.db`, `klines.db` con OI/funding/taker) | intactos | SÍ |

Este reporte, por lo tanto, es un **veredicto sobre la evidencia que sobrevivió**,
no sobre el benchmark completo planeado.

---

## 1. Cuestionamiento de la conclusión de Phase 2 (lo que quedó / no quedó demostrado)

Phase 2 cerró sugiriendo "un backtest que diga PF 1.4 significa probablemente
rentable de verdad". **Phase 3 lo refuta con el primer caso que probó.**

Phase 2 solo había probado 1 estrategia **perdedora** (Caso 2) reproducida como
perdedora — un motor que dijera "perdedora" a todo también acertaría eso. La
prueba real era una **ganadora**. Phase 3 la corrió (Caso 3) y el motor la
clasificó **LOSER**.

---

## 2. Benchmark

Pre-declarado (GATE_V4_CRITERIA.md §1): 7 estrategias, PF real de 0.55 a 1.85,
3 familias, duración corta y larga. **De las 7, solo la #1 se completó antes de
la pérdida de datos.** El ground-truth de la #7 (Caso 2) sobrevive por separado.

| # | Estrategia | Familia | PF real | CLASE | ¿corrida completa? |
|---|---|---|---|---|---|
| 1 | MA Slope Caso 3 | MaGeometry | 1.85 | WINNER | **SÍ** (preservada) |
| 2 | FVG - 15m | FVG | 1.29 | WINNER | arrancó, no completó |
| 3 | MA Slope Caso 3 (15m) | MaGeometry | 1.18 | WINNER | no |
| 4 | MA Slope Caso 1 | MaGeometry | 0.91 | NEUTRAL | no |
| 5 | FVG - 1m | FVG | 0.69 | LOSER | no |
| 6 | Compresion ADN - Micro | AdnCompression | 0.58 | LOSER | no |
| 7 | MA Slope Caso 2 | MaGeometry | 0.55 | LOSER | ground-truth preservado; replay = Phase 2 |

---

## 3. Resultados REAL vs REPLAY (lo que sobrevivió)

### MA Slope Caso 3 — la única corrida gold-standard completa

| Métrica | REAL | REPLAY (mediana de 50 seeds × grilla pre-registrada) |
|---|---|---|
| Clase | **WINNER** | **LOSER** ❌ |
| Profit factor | **1.85** | **0.81** |
| Net PnL | +$65.14 | −$8 a −$13 (según costo) |
| Expectancy/trade | +$0.93 | −$0.34 |
| Win rate | 43 % | ~10 % |
| Duración media | 16.7 h | — |
| Max drawdown | −$19.5 | — |

### MA Slope Caso 2 — ground-truth preservado (`scratch_ma2_real.csv`)

| | REAL | REPLAY (Phase 2, `fidelity` completo) |
|---|---|---|
| Clase | LOSER | LOSER ✓ |
| PF | 0.55 | 0.53–0.62 |
| Net | −$116 | −$99 a −$79 |

Es decir: **la perdedora fuerte se clasifica bien; la ganadora fuerte se
clasifica MAL.** Consistente con la hipótesis de que el motor tiene un sesgo
sistemático que *deprime* el resultado (Phase 1/2 ya lo notaron: el motor es
"optimista" para perdedoras — las hacía verse menos malas — y ahora se ve que es
"pesimista" para ganadoras — las hace verse perdedoras).

---

## 4. Distribución Monte Carlo (perturbación del caos) — MA Slope Caso 3

50 seeds × {jitter ±1/±2/±5/±10 s, jitter ±1/±2 velas, desempates}.

| Percentil | PF del replay |
|---|---|
| P5 | **0.33** |
| P25 | 0.54 |
| P50 | 0.81 |
| P75 | 1.05 |
| P95 | **1.61** |

**El PF que el motor le asigna a una estrategia con PF real 1.85 va de 0.33 a
1.61 según la semilla del sorteo de cupos.** Es una moneda al aire. Solo el
**29.7 %** de las seeds la clasificaron del lado correcto (ganadora).

Pre-registro del usuario, textual: *"Si PF 1.4 solamente aparece bajo una
secuencia específica de slots y cae por debajo de 1.0 con pequeños cambios, eso es
FAILED."* — Acá el PF real es 1.85 y el replay mediano es 0.81. Se cumple el
criterio de FAILED.

---

## 5. False positive / False negative

- **FALSE NEGATIVE**: MA Slope Caso 3 — REAL winner (PF 1.85) → REPLAY loser
  (mediana PF 0.81, ≤ 0.90). **Confirmado.** Es el error *menos* peligroso (te
  hace descartar una estrategia buena, no desplegar una mala), pero por
  `GATE_V4_CRITERIA.md` gate E = **FAILED**.
- **FALSE POSITIVE** (REAL loser → REPLAY winner, el error peligroso): **no se
  pudo testear.** Las estrategias perdedoras del benchmark (FVG-1m, ADN Micro)
  no se llegaron a correr y su ground-truth se perdió. **NO PODEMOS CONCLUIR**
  si el motor genera false positives.

---

## 6. Sensibilidad al jitter — MA Slope Caso 3

| jitter | clase replay | PF mediana | P5 | P95 |
|---|---|---|---|---|
| 0 s | LOSER | 0.70 | 0.35 | 1.32 |
| ±1 s | LOSER | 0.69 | 0.23 | 1.56 |
| ±2 s | LOSER | 0.69 | 0.23 | 1.56 |
| ±5 s | LOSER | 0.69 | 0.23 | 1.56 |
| ±10 s | LOSER | 0.69 | 0.23 | 1.56 |

La clase (LOSER) es **estable** entre niveles de jitter — el false negative NO es
ruido de jitter, es **sistemático**. La inestabilidad grande viene del **sorteo
de cupos** (seeds/desempates), no del jitter de segundos.

---

## 7. Sensibilidad a costos — MA Slope Caso 3

| costo/lado | net PnL replay |
|---|---|
| 0 bp | −$8.1 |
| 2 bp | −$10.1 |
| 5 bp | −$12.9 |

El replay dice que la estrategia **pierde plata incluso a costo cero**. La
realidad: +$65.14 neto. No es un problema de costos — es que el motor no
reproduce la economía de esta estrategia.

---

## 8. OOS

No ejecutable — requiere el benchmark completo y la DB. **NO PODEMOS CONCLUIR.**

---

## 9. GATE_V4 — veredictos

| Gate | Estado | Motivo |
|---|---|---|
| A. Fidelidad del signo | **FAILED** (parcial) | Caso 3: replay net −$8/−$13 vs real +$65 → sign flip |
| B. Ranking de estrategias | NO PODEMOS CONCLUIR | requiere ≥ 3 estrategias completas; hay 1 |
| C. Estabilidad Monte Carlo | **FAILED** | Caso 3: 29.7 % de seeds del lado correcto (< 90 %); P25(PF) = 0.54 < 1.0 |
| D. FALSE POSITIVE | NO PODEMOS CONCLUIR | perdedoras del benchmark no corridas / ground-truth perdido |
| E. FALSE NEGATIVE | **FAILED** | Caso 3: REAL winner PF 1.85 → replay mediana PF 0.81 ≤ 0.90 |
| F. Sensibilidad al jitter | (clase estable, pero sobre un resultado ya FAILED) | LOSER en los 5 niveles |
| G. Sensibilidad a costos | **FAILED** (dirección false-negative) | winner net-negativo a 0/2/5 bp en el replay |
| H. Estabilidad OOS | NO PODEMOS CONCLUIR | requiere benchmark completo |

**Regla de veredicto pre-registrada:** *"FAILED si gate D=FAILED **o** gate
A=FAILED **o** gate C=FAILED **o** gate E=FAILED **o** ≥ 3 gates en FAILED."*

Gates A, C, E, G en FAILED (4). → **veredicto = FAILED.**

---

## 10. No se intentó reproducir los trades reales

Se respetó: la selección exacta de trades es no determinista (path-dependence de
cupos). La condición para aceptarla era que **las conclusiones económicas
agregadas fueran estables bajo perturbaciones razonables**. En MA Slope Caso 3
**no lo son**: la clase económica cambia de WINNER a LOSER, y el PF va de 0.33 a
1.61 según la seed. Eso invalida la path-dependence como excusa.

---

## 11. Regla de oro

"El backtest dejó de estar obviamente roto" (Phase 1) y "el agregado se acercó al
REAL en 1 perdedora" (Phase 2) **no** eran "el backtest está validado". Phase 3,
en su primer caso —una ganadora real— mostró que el motor la clasifica como
perdedora con un PF que es una moneda al aire. No está validado.

---

## 12. Qué quedó demostrado / qué sigue sin demostrarse

### DEMOSTRÓ (evidencia sólida, corrida completa contra config real, pre-registrada)

1. Para MA Slope Caso 3 (REAL PF 1.85, ganadora clara), el motor produce una
   **clasificación económica equivocada** (LOSER) en la mediana de 50 seeds.
2. La estimación de PF del motor para esa estrategia **no es robusta**: va de
   0.33 a 1.61 según el sorteo de cupos; solo 30 % de las seeds aciertan la clase.
3. El sesgo es **sistemático**, no ruido de jitter (LOSER en los 5 niveles).
4. No es un problema de costos (pierde a 0 bp en el replay; gana en la realidad).
5. La perdedora fuerte (Caso 2) sí se clasifica bien — el motor parece tener un
   sesgo que **deprime** todos los resultados: hace ver mejores a las perdedoras
   (Phase 1/2) y peores a las ganadoras (Phase 3).

### SUGIERE (no probado con rigor por la pérdida de datos)

- Que el sesgo pesimista para ganadoras se repita en FVG-15m, Caso 3 (15m), etc.
  (el benchmark las incluía; no se llegó).

### NO PODEMOS CONCLUIR

- **False positive rate** (REAL loser → REPLAY winner) — el error peligroso. Sin
  datos.
- Ranking relativo entre estrategias.
- Estabilidad OOS.
- Si el motor sirve para *comparar* dos variantes de la misma estrategia
  (los sesgos podrían cancelarse — no se testeó).

---

## 13. VEREDICTO FINAL

# GATE V4 = FAILED

**El motor puede producir conclusiones económicas engañosas.** En el único caso
gold-standard completo (una estrategia con rentabilidad real, PF 1.85), el motor
la clasificó como perdedora, con una estimación de PF que varía entre 0.33 y 1.61
según el orden aleatorio en que se llenan los 3 cupos.

Esto NO se debe a la pérdida de datos — la corrida de MA Slope Caso 3 se completó
**antes** del reset, contra la config **real**, con la grilla de perturbación
**pre-registrada**. La pérdida de datos impide *ampliar* la evidencia (medir
false positives, ranking, OOS), pero el resultado que sobrevive ya alcanza el
umbral de FAILED que fijamos por anticipado.

### Exactamente qué preguntas económicas puede responder Verge después de esta fase

**Ninguna con confianza para decisiones de rentabilidad.** En concreto:

- ❌ "¿Esta estrategia nueva es rentable?" — NO. El motor convirtió una ganadora
  real en perdedora.
- ❌ "¿Cuál es el PF / expectancy de esta estrategia?" — NO. El rango de PF por
  perturbación es demasiado ancho (0.33–1.61 para un PF real de 1.85).
- ❌ "¿Descarto esta estrategia porque el backtest da PF < 1?" — NO. Podría ser
  una ganadora real (es lo que pasó con Caso 3).
- ⚠️ "¿Esta variante es mejor que aquella?" — **desconocido** (podría servir si
  los sesgos se cancelan, pero no se probó y la evidencia de inestabilidad por
  seed lo hace dudoso).
- ✅ Lo único defendible: el motor **ya no tiene los bugs estructurales** de
  Phase 1 (timeout, filtro BTC, veto diario, funding, cobertura). Eso era
  necesario, no suficiente. Sigue sin ser un instrumento de evaluación económica.

### Recomendación

**No usar el motor de backtest para decidir si un alpha se convierte en
estrategia rentable.** El flujo previsto (confirmar un alpha estadísticamente y
después evaluar rentabilidad con el motor) tiene el segundo paso roto. Cuando
llegue H11/OI, la conclusión sobre si OI *contiene* información se puede sacar del
estudio de correlación parcial (no usa el motor); la conclusión sobre si esa
información es *monetizable* NO se puede sacar de este motor en su estado actual.

Antes de volver a confiar en el motor haría falta una **Phase 4**: reconstruir la
DB con las configs reales (que el usuario re-ingrese las estrategias activas),
re-correr el benchmark completo de 7, y medir sobre todo el **false positive rate**
(perdedoras reales que el motor pinte de ganadoras) — que es el error que hace
perder dinero y que esta fase no llegó a medir.

---

## Estado de la infraestructura tras el incidente

- **DB Verge**: esquema recreado (`Verge.DbMigrator`). 20 `StrategyProfiles`
  reconstruidos (solo MA Slope Caso 2 con config real; el resto aproximado,
  marcado en `Description`). 3.682 `SimulatedTrades` cargados de `trades.csv`
  (marcados `reconstructed` en `ExtraProperties`; **PnL NO confiable** — usar solo
  para que el dashboard no esté vacío).
- **Colector de OI**: reiniciado. 32,4 días de historia intactos en `klines.db`,
  rellenando el hueco del reinicio. **Re-registrar la tarea programada**
  (`register_oi_collector_task.ps1`) para resiliencia a reinicios.
- **Imágenes Docker**: solo `redis`/`postgres` base. Las de la app (y las de
  todos los proyectos) se reconstruyen con `docker compose build`.
- **Datasets grandes** (OHLCV, taker flow, BTC 1m, funding): intactos (son
  archivos de disco, no volúmenes).

## Estado del research de alpha (sin cambios)

H12 = CLOSED/FAILED. H11 = congelado. OI collector acumulando. Sin H13, sin nueva
estrategia. El motor de backtest queda marcado **NO CONFIABLE para evaluación
económica** hasta una Phase 4.
