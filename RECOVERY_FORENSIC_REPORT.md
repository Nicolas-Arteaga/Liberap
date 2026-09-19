# RECOVERY FORENSIC REPORT — 2026-09-06

Objetivo: determinar si las 6 estrategias del benchmark de Gate V4 que NO
terminaron pueden reconstruirse **exactamente** a partir de evidencia existente,
y auditar por qué MA Slope Caso 3 dio REAL PF 1.85 vs replay mediana PF 0.812.

**Sin ejecutar nada largo.** Solo lectura de artefactos existentes.
Regla aplicada: si para recuperar un parámetro hay que adivinarlo, esa
configuración NO está recuperada.

---

## 1. Qué configuraciones se recuperaron — y de dónde

### Evidencia encontrada por estrategia

| # | Estrategia | `patternParamsJson` | side (verificado en datos reales) | Riesgo (minRR / maxTradeDur / margin / slots) | Ground truth REAL |
|---|---|---|---|---|---|
| 7 | **MA Slope Caso 2** | ✅ **completo, textual** en `agent/backtest/gate_out.log` + `gate_out2.log` (Phase 1 lo logueó con `print(json.dumps(...))`) | LONG (113/0) — `scratch_all_trades_p2.csv` | ✅ minRR 3, slMult 0.8, tpMult 3, maxTradeDur 96, margin 150, slots 3 — logueados | ✅ **`scratch_ma2_real.csv`** (113 trades, `AgentDecisionJson` completo) |
| 1 | **MA Slope Caso 3** | ⚠️ recuperable de **9 scripts concordantes de julio** (`agent/run_engine_{test,v2,v3_partial,v4_multiex,v5_5min,v6_zombie,v7_final,week_test}_20260726.py` + `agent/ma_slope_backtest.py`): SHORT-only; `order ma7>ma25>ma50>ma99`; `slope ma7 win3, prior≥+0.2 → current≤−0.2`; `touch/distanceBetweenMas/contextSlope off`; `peakProximity recentHigh lb10 tol1.0`; `exit slReference recentHigh lb10 buffer1.0 tpMinPct10.0`; tpMult 3, slMult 0.8 | SHORT (0/73) — `scratch_all_trades_p2.csv` ✓ concuerda con los scripts | ⚠️ **CONFLICTO**: `minRR 4.0` en los 9 scripts `run_engine_*` / `ma_slope_backtest.py`, pero `minRR 3` en `verify_ma_slope_caso3_calibration.py` y `verify_ma_slope_caso3_full_period.py`. `maxTradeDur 192` (v5/v6/v7/week). **La config REAL en la DB al momento de Gate V4 (2026-09-05) NO se logueó y la DB se perdió** → no verificable | ⚠️ parcial: `scratch_gate_v4_results.json → real_trades` (70 trades: open/close/pnl/reason; **sin símbolo, sin entry/sl/tp**). Coincide con el target de `verify_ma_slope_caso3_calibration.py` ("74 trades reales, +$64.78") |
| 3 | **MA Slope Caso 3 (15m)** | ⚠️ = config de Caso 3 con `timeframe: 15m`. Fuente: PROGRESS_LOG L287 *"clon EXACTO de Caso 3 con timeframe cambiado a 15m, vía SQL directo clonando la fila completa"* | SHORT (0/90) ✓ | idem Caso 3 (hereda el conflicto minRR) | ⚠️ parcial: `scratch_all_trades_p2.csv` (tiempos + side, sin PnL) |
| 2 | **FVG - 15m** | ⚠️ parcial. El perfil ORIGINAL NO tenía filtros activados (`maxGapPct`/`maxTpDistancePct`/`maxUShapeCount` eran opt-in y se agregaron a los CLONES v2/Pulido/GapChico — PROGRESS_LOG L213). → `patternParamsJson` ≈ `{"timeframe":"15m"}`. La detección FVG vive en `python-service/fvg/analyzer.py` (solo toma `symbol, interval`) | BOTH (259 LONG / 105 SHORT) — `scratch_all_trades_p2.csv` | ✅ **minRR 3, maxTradeDur 60** (PROGRESS_LOG L123, *"params reales... ver DB"*). ❌ **margin / slots NO están en ningún artefacto** (asumir 150/3 = adivinar) | ⚠️ parcial: `scratch_all_trades_p2.csv` (tiempos+side); `agent/data/trades.csv` (293 filas con pnl/entry/sl/tp, pero ruidoso) |
| 4 | **MA Slope Caso 1** | ❌ **NO existe en ningún artefacto.** Fragmentos: LONG-only (89/0, verificado); *"filtrar por pendiente de EMA50 < −5°"* (PROGRESS_LOG L348); PF 0.82 en backtest de julio. El `patternParamsJson` (order/slope/exit) **no está en ningún script, log ni reporte** | LONG (89/0) | ❌ nada | ⚠️ parcial: `scratch_all_trades_p2.csv` (tiempos+side); `trades.csv` (59 filas ruidosas) |
| 5 | **FVG - 1m** | ❌ solo `timeframe: 1m` + side BOTH (356/339). **Sin evidencia** de sus minRR / maxTradeDur / margin / slots — no hay confirmación de que compartan los de FVG-15m | BOTH (356/339) | ❌ nada | ⚠️ parcial: `scratch_all_trades_p2.csv`; `trades.csv` (388 filas) |
| 6 | **Compresion ADN - Micro (5m)** | ❌ solo `timeframe: 5m` + side LONG (112/0). `_build_adn_compression_candidate` lee `minConfluenceScore` del perfil (default 80). **Sin evidencia** de ningún parámetro real | LONG (112/0) | ❌ nada | ⚠️ parcial: `scratch_all_trades_p2.csv`; `trades.csv` (57 filas) |

### Clasificación

| # | Estrategia | **Clase** | Justificación |
|---|---|---|---|
| 7 | MA Slope Caso 2 | **A** | Config textual + ground truth completo. |
| 1 | MA Slope Caso 3 | **B** | Geometría/salida/multiplicadores/side recuperados (9 scripts concordantes + datos reales). **PERO** `minRR` (3 vs 4) y `maxTradeDur` (192 vs ?) no verificables → test posible solo si se etiqueta "minRR probado en {3,4}". |
| 3 | MA Slope Caso 3 (15m) | **B** | Hereda la clase de Caso 3 (clon SQL exacto + tf 15m). Misma incertidumbre minRR. |
| 2 | FVG - 15m | **B** | Núcleo recuperado (tf, minRR 3, maxTradeDur 60, side, sin filtros). margin/slots asumidos → etiquetar. |
| 4 | MA Slope Caso 1 | **C — NO RECUPERABLE** | El `patternParamsJson` no existe en ningún artefacto. Reconstruirlo = inventar las reglas de geometría. |
| 5 | FVG - 1m | **C — NO RECUPERABLE** | Solo tf + side. minRR/maxTradeDur/margin/slots desconocidos. |
| 6 | ADN Micro (5m) | **C — NO RECUPERABLE** | Solo tf + side. Ningún parámetro real. |

Git (181 commits) NO tiene ningún dump/seed de `StrategyProfiles` — se crearon por
la UI (filas de DB), nunca versionadas. La migración `20260511072950_AddStrategyProfiles`
no siembra filas.

---

## 2. Qué NO puede recuperarse

- **Caso 1, FVG-1m, ADN Micro**: sus `patternParamsJson` no existen en ningún
  artefacto. No recuperables sin inventar.
- **`minRR` de Caso 3 / Caso 3 (15m)**: 3 vs 4, sin forma de resolver (DB perdida,
  no logueada por gate_v4).
- **`margin` y `maxOpenPositions` de FVG-15m / FVG-1m / ADN**: no en artefactos.
- **La config EXACTA con la que Gate V4 corrió Caso 3**: `gate_v4.py::load_profile`
  la leyó de la DB en runtime y **nunca la imprimió**. La DB ya no existe. →
  **el resultado completo de Caso 3 NO es reproducible** ni siquiera para nosotros.
- **Ground truth con precios**: `scratch_all_trades_p2.csv` tiene tiempos+side pero
  no PnL/entry/sl/tp. `agent/data/trades.csv` tiene PnL pero está corrupto
  (reconstruye Nexus a +$228k, FVG-1m a −$192k; ~2% de `result` mal etiquetado;
  parcial: 57–134 filas vs 70–695 reales).

---

## 3. Evidencia usada para cada recuperación

| Dato | Fuente exacta |
|---|---|
| Config completa Caso 2 | `agent/backtest/gate_out.log` líneas "CONFIG CONGELADA" + "patternParams:" |
| Config Caso 3 (geometría/salida) | `agent/run_engine_v7_final_20260726.py:11-27` + 7 gemelos + `agent/ma_slope_backtest.py:1-25` + `agent/backtest/verify_ma_slope_caso3_{calibration,full_period}.py:20-45` |
| Caso 3 = SHORT-only | `scratch_all_trades_p2.csv` (73 SHORT / 0 LONG) — dato REAL pre-reset |
| Caso 3 (15m) = clon exacto | `.claude/PROGRESS_LOG.md:287` |
| FVG-15m minRR 3 / maxTradeDur 60 | `.claude/PROGRESS_LOG.md:123` |
| FVG-15m sin filtros en el original | `.claude/PROGRESS_LOG.md:213` |
| Caso 1 = LONG-only | `scratch_all_trades_p2.csv` (89 LONG / 0 SHORT) |
| Sides de todas | `scratch_all_trades_p2.csv` |
| Resultado Caso 3 de Gate V4 | `scratch_gate_v4_results.json → "MA Slope Caso 3"` |
| Ausencia de configs de Caso 1/FVG-1m/ADN | grep exhaustivo en `agent/*.py`, `agent/backtest/*.py`, `*.md`, `*.log`, git |

---

## 4. Por qué MA Slope Caso 3 da REAL PF 1.85 vs replay mediana 0.812

### Hallazgo central: la WR

| Vista | n | WR | tp_hit | sl_hit | timeout | net | PF |
|---|---|---|---|---|---|---|---|
| **REAL** (Jul 11–Ago 15, de la DB) | 70 | **53 %** | **30** | 24 | 16 | +$65.1 | 1.85 |
| **Gate V4 baseline replay** (misma ventana, seed 0, det.) | 42 | **9.5 %** | **4** | 29 | 9 | −$22.6 | ~0.7 |
| **`run_ma_geometry` julio** (Dic-2025→Jul-2026, sin MC, sin `occupied`) | 460 | **14.1 %** | — | — | — | +$31.1 | ~1.03 |

**El replay produce ~10–14 % de win rate para una estrategia que en la realidad
gana el 53 % de las veces — en TODAS las versiones del motor desde julio.**

### Comparación con Caso 2 (que "funcionó" en Phase 2)

| Estrategia | Side | REAL WR | REPLAY WR | REAL PF | REPLAY PF | ¿Clasificó bien? |
|---|---|---|---|---|---|---|
| MA Slope Caso 2 | LONG | 21 % | **9–12 %** | 0.55 | 0.53–0.62 | ✅ (loser → loser) |
| MA Slope Caso 3 | SHORT | 53 % | **10–14 %** | 1.85 | 0.81 | ❌ (winner → loser) |

**El motor produce ~10 % de WR para ambas, sin importar la WR real (21 % o 53 %).**
Cuando la estrategia real es perdedora al 21 %, el replay al 10 % igual cae en
"perdedora" y parece funcionar. Cuando la estrategia real es ganadora al 53 %, el
replay al 10 % la convierte en perdedora.

### Separación de causas (A–F)

| Causa | ¿Presente? | Evidencia |
|---|---|---|
| **A. Path dependence legítima por slots** | Sí, pero **secundaria** | MC P5=0.33 / P95=1.61 es dispersión real por el sorteo de cupos. PERO la path dependence da un *subconjunto aleatorio* de las señales de la estrategia, que debería tener ~la misma WR (~53 %). Tiene 10 %. |
| **B. Problema de modelado del replay** | **SÍ — DOMINANTE** | La WR del replay es ~10–14 % vs 53 % real, **consistente en todas las versiones del motor desde julio 2026** (no es ruido corrida-a-corrida). El replay casi nunca llega al TP: **10 % de tp_hit vs 43 % real**. Con `tpMinPct 10.0` (TP lejos) + `slBufferPct 1.0` (SL ajustado), un pequeño error de precio/timing de entrada voltea el resultado de TP a SL — y la entrada del motor es al cierre de la vela de 5 m de la señal, no al precio vivo unos segundos después como producción. |
| **C. Sensibilidad excesiva a jitter** | **NO** | `jitter_by_level`: LOSER en los 5 niveles (0/±1/±2/±5/±10 s), mediana estable ~0.69, P5 0.23–0.35. El jitter de segundos casi no mueve el resultado. La inestabilidad viene del **seed/desempate** (el sorteo de cupos), no del jitter. |
| **D. Diferencia ejecución REAL vs universo replay** | Menor | `coverage 0.879` → 7 símbolos reales (ADBEUSDT, ETHBTCUSDT, RSRUSDT, SUNUSDT, VRTUSDT, XLEUSDT, ZHIPUUSDT) fuera del universo replay. No cuantificable por trade (`real_trades` no guardó símbolo). 88 % de cobertura ⇒ contribuidor chico. |
| **E. Discrepancia residual del motor** | **SÍ** | La brecha de WR desde julio + la brecha de tp_hit (10 % vs 43 %) ES una discrepancia residual: la detección/salida de MaGeometry para setups SHORT del motor no reproduce lo que produccion operó. Se solapa con B. |
| **F. Otra causa verificable** | **SÍ** | `gate_v4.py` **nunca logueó la config** que leyó de la DB. La DB se perdió. → no podemos verificar que el replay de Gate V4 usó la config correcta de Caso 3 (p.ej. minRR 3 vs 4 cambia qué candidatos pasan el veto). Agujero metodológico independiente del caos. |

### ¿"winner real → loser replay" = caos esperable o el replay no representa la economía?

**El replay NO representa la economía de la estrategia. Evidencia:**

1. Si fuera puro caos de cupos, un subconjunto aleatorio de señales con 53 % de WR
   tendría ~53 % de WR. Tiene 10 %.
2. La WR de ~10–14 % es **estable en todas las versiones del motor desde julio** —
   es un sesgo sistemático, no varianza corrida-a-corrida.
3. El replay estructuralmente casi no llega al TP (10 % vs 43 % real) — es un
   problema direccional de calidad de entrada, no aleatoriedad.
4. El caos SÍ existe (P5–P95 = 0.33–1.61) pero es **caos alrededor de un centro
   equivocado** (mediana 0.81 cuando debería ser ~1.85).
5. El mismo motor subestima a Caso 2 (LONG, loser) al mismo ~10 % de WR — invisible
   porque un loser subestimado sigue siendo loser. Phase 2 fue **afortunada por
   supervivencia**: nunca se validó contra una ganadora hasta Phase 3.

**Conclusión: A + B, con B dominante.** El caos de cupos agrega varianza; el
modelado del motor pone el centro en el lugar equivocado.

---

## 5. ¿El problema es path dependence, modelado, o ambos?

**Ambos, pero el modelado es la causa principal.**

- **Modelado (dominante)**: el motor reproduce ~10 % de WR para MaGeometry cuando
  la realidad es 21–53 %. Casi nunca alcanza el TP. Sesgo sistemático desde julio.
- **Path dependence (secundaria)**: agrega la dispersión P5–P95 = 0.33–1.61, pero
  no explica el centro.

El sesgo del motor es **pesimista**: deprime toda estrategia. Con perdedoras es
invisible (loser → loser). Con ganadoras es catastrófico (winner → loser).

---

## 6. Qué distribución debería usar el backtest

**Pregunta:** si la selección de trades es caótica, ¿qué distribución representa
correctamente la expectancy?

**Respuesta:** la **esperanza sobre el ensemble de realizaciones plausibles**, vía
Monte Carlo con órdenes de resolución de cupos equiprobables, reportando:

1. **La MEDIA de la distribución MC de PnL** como estimador puntual de la
   expectancy. NO la mediana. La expectancy es E[PnL], un funcional lineal; la
   media MC es su estimador insesgado. La mediana es sesgada para distribuciones
   asimétricas (y las de PnL lo son). **Gate V4 usó la mediana — doble error:**
   sesgada por asimetría Y sobre realizaciones ya sesgadas.
2. **Percentiles P5–P95 / intervalo de confianza** para comunicar el riesgo de
   path dependence: "el PF realizado podría caer en [P5, P95] según la suerte de
   ejecución".
3. **Fracción de realizaciones net-positivas** como métrica de robustez.

**PERO — condición crítica:** el ensemble MC solo sirve si **cada realización es
una muestra insesgada del proceso real**. Si la detección/salida por realización
está sistemáticamente mal (como muestra la brecha de WR), ningún MC lo arregla:
obtenés una **estimación precisa del número equivocado**. Ese es exactamente el
estado actual: cada realización tiene ~10 % de WR vs 53 % real; promediarlas da
0.81 con poca varianza, pero 0.81 no es la expectancy del proceso real.

**El hecho de que el replay dé mediana 0.812 vs real 1.85 NO prueba por sí solo
que el real sea "la verdad".** Pero acá SÍ hay evidencia independiente de que el
replay está mal: (a) nunca reproduce la WR real en ninguna versión, (b)
estructuralmente no llega al TP. Los trades reales son el ground truth de lo que
produccion hizo; el replay falla en modelar ese proceso.

---

## 7. ¿Gate V4 sigue siendo válido metodológicamente?

**El diseño del protocolo, sí. Su capacidad de dar un veredicto sobre el motor,
NO — porque el instrumento que testea (el replay) tiene un sesgo de modelado
demostrado que hace que el resultado de cualquier estrategia sea predecible desde
antes de correrlo: "el motor la va a pintar como ~loser".**

- Los criterios pre-registrados (`GATE_V4_CRITERIA.md`) son sólidos.
- El benchmark (7 estrategias, spread de PF) está bien elegido.
- El Monte Carlo de perturbación es la metodología correcta en concepto.
- **Falla 1**: usó la mediana en vez de la media (ver §6).
- **Falla 2**: no logueó las configs → resultados no reproducibles + no se puede
  descartar config drift.
- **Falla 3 (la grave)**: mide el motor con el motor. Si el motor tiene un sesgo
  pesimista sistemático (~10 % WR para MaGeometry), Gate V4 no distingue "el motor
  no sabe evaluar rentabilidad" de "el motor tiene este bug de WR puntual". El
  resultado de Caso 3 es consistente con AMBOS.

**Gate V4 como está NO puede dar un veredicto PASS/FAILED limpio del motor.** Lo
que SÍ demostró: el motor NO reproduce la win rate de MA Slope Caso 3 (ni de
Caso 2), y ese solo hecho ya lo descalifica para estimar rentabilidad.

---

## 8. ¿Repetir las estrategias 2–7 tendría valor científico?

**Muy limitado, y solo para 2–3 de ellas.**

- **Caso 1, FVG-1m, ADN Micro (clase C)**: **NO.** Sin sus configs reales,
  cualquier corrida testea una config inventada, no la estrategia. Por la regla
  del usuario: no se ejecutan.
- **FVG-15m, Caso 3 (15m) (clase B)**: valor **bajo**. Ya sabemos, por Caso 3 y
  Caso 2, que el motor produce ~10 % de WR para estas familias. Correr FVG-15m
  con margin/slots asumidos probablemente confirme el mismo sesgo. No agrega
  información nueva sobre "¿el motor sirve para rentabilidad?" — la respuesta ya
  la tenemos.
- **Lo único con valor real**: una corrida de diagnóstico de **por qué** el motor
  da 10 % de WR (comparar trade-a-trade las entradas/salidas del replay de Caso 3
  vs las 70 reales — precio de entrada, timing, qué vela toca SL vs TP). Eso NO es
  "repetir Gate V4", es una auditoría del bug de modelado. Y requiere el ground
  truth con precios de Caso 3, que **no tenemos** (`real_trades` no guardó
  symbol/entry/sl/tp; `trades.csv` es ruidoso).

**Conclusión: repetir 2–7 bajo el protocolo Gate V4 actual NO vale la pena.** El
veredicto sobre el motor ("no reproduce win rates → no sirve para rentabilidad")
ya está soportado por 2 estrategias con datos limpios.

---

## 9. Qué información perdimos definitivamente

1. **Las configs (`patternParamsJson`) de MA Slope Caso 1, FVG-1m, ADN Micro** —
   no están en ningún artefacto. Solo recuperables re-ingresándolas a mano si el
   usuario las recuerda.
2. **`minRR` real de Caso 3 / Caso 3 (15m)** (3 vs 4) y **margin/slots de las FVG**.
3. **La config exacta con la que Gate V4 corrió Caso 3** (leída de la DB, nunca
   logueada) → el único resultado gold-standard completo **no es reproducible**.
4. **El ground truth REAL con precios** de las 6 estrategias (entry/sl/tp/exit por
   trade). Solo sobrevive: tiempos+side (`scratch_all_trades_p2.csv`) y una copia
   corrupta de PnL (`agent/data/trades.csv`).
5. **`SimulatedTrades` completo** (~5000 trades con `AgentDecisionJson` rico) de
   todas las estrategias — salvo Caso 2 (`scratch_ma2_real.csv`) y los 70 trades
   de Caso 3 sin símbolo.
6. **Todas las demás `StrategyProfiles`** (~20 filas) tal cual estaban el 2026-09-05.

---

## 10. ÚNICO próximo paso recomendado

**Ninguna corrida.** Aceptar lo que la evidencia ya dice y decidir el rumbo:

> El motor de backtest tiene un **sesgo de modelado pesimista demostrado**: para
> estrategias MaGeometry produce ~10 % de win rate cuando la realidad es 21–53 %,
> y casi nunca alcanza el TP. Esto es independiente del caos de cupos. Por lo
> tanto **NO puede estimar rentabilidad de una estrategia nueva** — clasificaría
> como perdedora a una ganadora real, igual que hizo con MA Slope Caso 3.
>
> Gate V4 queda **incompleto y no concluyente como veredicto formal del motor**
> (1/7, configs no logueadas, usó mediana en vez de media), pero **la evidencia
> parcial + Caso 2 + los resultados de `run_ma_geometry` de julio ya alcanzan**
> para la decisión práctica: el motor no es apto para evaluación económica.

**Decisión que le corresponde al usuario:**
- (a) Aceptar el motor como NO APTO para rentabilidad y seguir con OI/H11 (el
  estudio de correlación de H11 no usa el motor), o
- (b) Antes de eso, invertir en una **Phase 4 de reparación del bug de win rate**
  del motor — pero eso requiere primero re-ingresar a mano las configs reales de
  las estrategias y reconstruir el ground truth con precios, que en gran parte
  se perdió.

No recomiendo (b) hasta que el usuario confirme que puede re-ingresar las configs
exactas. Sin eso, cualquier reparación se valida contra datos inventados.

---

### Estado de alpha research (sin cambios)

H12 = FAILED cerrado. H11 = congelado (OI a 32 días / 70). OI collector vivo.
Sin H13, sin nuevas estrategias, sin optimización. Motor de backtest marcado
**NO APTO para evaluación económica** hasta reparación verificada.
