# VERGE — SCIENTIFIC RESEARCH RESET PLAN

**Fecha:** 2026-09-06
**Estado:** MAPA. No se implementó ninguna estrategia. No se tocó producción,
DB ni se corrió backtest.

---

## 0. Objetivo y estándar

**Objetivo final:** descubrir **1–3 estrategias** capaces de producir
**> 150 USDT/mes de PnL neto OOS** con **≤ 450 USDT de capital asignado por
estrategia**. La estructura de capital (3×150 / 2×225 / 1×450 / dinámico) se
decide **después** de demostrar edge (Fase 8).

**Regla fundamental:** no se busca un número (150). Se busca un **mecanismo de
mercado** con edge estadística y económicamente defendible. El PnL es una
consecuencia, no el criterio. Un backtest rentable que no supera el estándar
científico se declara **FAILED**.

**Estándar científico (heredado de H1–H12, endurecido):**
señal existe → es **incremental** al precio → sobrevive **OOS temporal
estricto** → sobrevive **costos reales** (fee + funding + slippage + spread) →
sobrevive **robustez** (MC ordering, perturbación de params/costos/entrada,
subperíodos, símbolos, regímenes) → **economic gate** (PnL/capital/mes).
Cualquier eslabón que falla ⇒ FAILED, sin rescate.

---

## 1. Contexto: por qué un reset

### 1.1 Qué se probó y falló (H1–H12) — NO re-testear sin hipótesis causal nueva

| ID | Mecanismo | Resultado | Causa del fallo |
|---|---|---|---|
| Grid OHLCV | 41.369 configs, lab evolutivo | 0 pasan robustez | fuente agotada |
| ML ranking / meta-label | — | AUC ~0.52 OOS | sin señal |
| Subset baseline (motor real) | MA Slope/OB/FVG/ADN 8.5m | PF colapsa con 2bp slippage | edge = fragilidad de ejecución |
| **H1** Regime Router | conmutar estrategias por régimen | peor que router aleatorio, 0 persistencia de liderazgo | sin estructura |
| **H8** Cross-sectional rel. strength | retorno − mediana | rank-idéntico a momentum absoluto (matemático); concentrado top-5 | redescubre momentum |
| **H9** Cross-exchange | bybit↔binance 15m | H9.2 convergencia REAL, broad, estable — **1–5 bp vs 8–16 bp de costo** | real no monetizable |
| **H10** Basis (spot−perp) | dislocación perp vs spot | partial corr se explica 100% por funding al controlarlo; mean-revierte 1–4 bp | basis = funding re-medido |
| **H12** Taker flow / CVD | imbalance, CVD, aceleración, |z|>3 | 0/27 combos alcanzan |partial corr|≥0.03; extremos sin signo estable; placebo reproduce el efecto | régimen/vol común, no order-flow causal |
| OFI (filtro) | libro en reposo, join a 4.763 trades | AUC 0.46 | sin señal |
| Funding (filtro) | tasa de funding | AUC 0.539 IS → PF 0.98 OOS | solo mitiga pérdidas |
| **H11** Open Interest | ΔOI / OI-vol / extremos | **UNTESTABLE — gateado por datos** (33 d de 70) | falta historia, NO evidencia negativa |

### 1.2 El patrón común de los FAILED

- **Techo de tamaño de efecto en TODO lo probado:** AUC ≤ 0.54, magnitud
  ≤ ~2 bp, lo que funciona IS se degrada a ~0 OOS.
- **Todo deriva de OHLCV de Binance** (o de fuentes que resultaron ser OHLCV
  re-medido: basis = funding; taker-flow = régimen; rel-strength = momentum).
- **Cuello de botella = A (falta de información nueva)**, no metodología, no
  costos (secundarios), no resolución.
- **Metodológicamente, todos los tests fueron de SEÑAL CONTINUA / CORRELACIÓN
  PARCIAL LINEAL.** Los pocos buckets de extremos (|z|>3) probados no tuvieron
  signo estable entre splits.

### 1.3 La tesis del reset

> Lo que **no se probó correctamente** no es una fuente de datos — es una
> **clase de mecanismo**: el **evento de flujo forzado**.
>
> Liquidaciones en cascada, spikes de OI, blow-ups de funding, deleveraging
> forzado — son **eventos discretos con respuesta no lineal y dependiente de
> estado**, no variables continuas. H8–H12 midieron `corr(x_t, ret_{t+h})`.
> Nunca se hizo un **event-study** de episodios de flujo forzado con
> controles apropiados (ventanas placebo, muestras matcheadas sin-evento,
> partición temporal estricta).
>
> Esa es la única región del espacio de hipótesis que sigue **genuinamente
> sin explorar** con los datos que tenemos o que podemos juntar barato.

### 1.4 Qué NO se vuelve a hacer

- OHLCV nuevo / router / grid-search / ML ranking sobre precio.
- Rescatar MA Slope / H8 / H9 / H10 / H12 / OFI / funding-como-edge.
- Señales continuas lineales cross-sectionales de una sola fuente.
- H13.x/H13.y/H13.z para salvar una hipótesis muerta (solo hipótesis causal
  **independiente** justifica un ID nuevo).

---

## 2. Fase 0 — Congelar el legacy (hecho a nivel conceptual)

Todo lo existente se **conserva** y se **reclasifica** como
**LEGACY / FORENSIC / NON-CANONICAL**:

| Recurso | Clasificación | Uso permitido en el reset |
|---|---|---|
| DB `Verge` (3315 trades, 20 StrategyProfiles) | NON-CANONICAL | Solo forensic. **NO** es evidencia de que ninguna estrategia funciona. **NO** restaurar estrategias eliminadas sin razón documental. **NO** reparar PnL histórico para volverlo ground truth. |
| `agent/data/trades.csv` | FORENSIC | Registro de qué operó el agente; PnL aproximado. No es backtest. |
| Reportes `*_REPORT.md`, `RECOVERY_FORENSIC`, `GOLDEN_CASO3`, etc. | LEGACY (evidencia) | Se citan; no se re-ejecutan. |
| Artifacts "Verge Edge Research" / "Post-Mortem" | LEGACY (evidencia) | Referencia de H1–H12. |
| `binance_vision_clean.db`, `klines.db`, colectores (OI, liq, OFI) | **CANONICAL DATA** (crudo) | Fuente primaria del reset. Ver `DATA_INVENTORY.md`. |
| `agent/backtest/engine.py` + scripts | LEGACY TOOLING | Reusable para ejecución, pero el motor tiene fidelidad **PARTIAL** (ver `GOLDEN_CASO3_BACKTESTER_FIDELITY_REPORT.md`): intrabar 5m TP-first optimista, `zombie_timeout_decision` a desactivar, admisión de slots no reconstruible. Cualquier validación nueva usa el protocolo de `VALIDATION_PROTOCOL.md`, no el motor tal cual. |

**Regla:** ningún resultado legacy cuenta como PASS. Los 3315 trades **no**
son evidencia directa. El PnL histórico **no** se repara.

---

## 3. Las fases del reset (resumen; detalle en los otros 4 docs)

| Fase | Qué | Entregable / gate |
|---|---|---|
| **0** Freeze legacy | reclasificar todo como no-canónico | este doc §2 |
| **1** Data inventory | inventario exhaustivo de datos crudos, calidad, lookahead, cobertura | `DATA_INVENTORY.md` |
| **2** Mechanism discovery | hipótesis desde mecanismos económicos/microestructurales, no indicadores | `ALPHA_HYPOTHESIS_LEDGER.md` (secciones de mecanismo) |
| **3** Discovery | exploración amplia, cada experimento en el ledger, **sin declarar edge** | ledger con resultado + decisión por hipótesis |
| **4** Freeze | congelar definición/params/universo/costos/sizing/reglas | snapshot firmado en el ledger |
| **5** Validation | OOS temporal, walk-forward, costos, execution realista, intrabar honesto | `VALIDATION_PROTOCOL.md` |
| **6** Robustness | MC ordering, perturbaciones, subperíodos/símbolos/regímenes — para **destruir**, no tunear | `VALIDATION_PROTOCOL.md` §6 |
| **7** Economic gate | PnL/PF/expectancy/WR/DD/Sharpe/turnover/**PnL por capital asignado por mes** | `VALIDATION_PROTOCOL.md` §7 |
| **8** Portfolio | combinar 1–3 candidatos validados; asignación optimizada en TRAIN, validada OOS | `PORTFOLIO_CAPITAL_PROTOCOL.md` |

---

## 4. Anti-overfitting (contrato, aplica a TODAS las fases)

Prohibido:
- optimizar parámetros mirando el resultado OOS;
- elegir retrospectivamente el mejor período o los mejores símbolos;
- borrar trades incómodos;
- cambiar TP/SL/timeout después de ver resultados;
- introducir un timeout artificial porque mejora el PF;
- usar información futura (incluye `updated_at` de tablas live-derived);
- declarar edge con una sola muestra / un solo split;
- convertir correlación en causalidad sin control (placebo temporal +
  muestra matcheada sin-evento);
- hacer N variantes y reportar solo la ganadora (todas van al ledger).

Si una hipótesis falla ⇒ **FAILED**. Se cierra. No hay sub-variantes de
rescate salvo una hipótesis causal genuinamente **independiente**.

---

## 5. Estado de recursos de investigación al inicio del reset

| Recurso | Estado |
|---|---|
| OI collector | Corriendo. 33.3 d acumulados, 45/188 símbolos ≥90% cobertura. Gate H11 = 70 d ⇒ ETA ~mediados de octubre 2026. |
| Liquidations collector | Corriendo (fuente `liquidations`, 7 d, 106 sym). Demasiado poco para testear. |
| OFI collector | Corriendo (`orderbook_ofi`, 30 d, 499 sym). Ya probado como filtro (FAILED); reusable como insumo de eventos. |
| Whale/on-chain | 3 d, 31 sym. No testeable. |
| Binance Vision (klines/spot/taker/multi-ex) | Estático, 8.5 meses, limpio. Fuentes agotadas o casi. |
| Lab evolutivo | Corriendo (infra del usuario). Grid-search = EXHAUSTED, no se usa para el reset. |

**Único hilo con edge potencial no explorado + datos en camino:** la familia
**Open Interest / flujo forzado** (H13–H15 del ledger). Todo lo demás es
LOW prior o requiere que el usuario decida invertir en colección de datos.

---

## 6. Cronograma realista

- **Ahora → ~mediados oct 2026:** Fase 1–3 sobre lo que YA se puede testear
  como *event-study* (OI 33 d es corto pero permite un piloto de existencia;
  OFI 30 d; multi-exchange). Congelar protocolos H13–H20.
- **~mediados oct 2026 (OI ≥ 70 d):** ejecutar H13/H14/H15 con el protocolo
  congelado.
- **Colección en paralelo (decisión del usuario):** extender liquidaciones,
  evaluar on-chain / opciones / multi-venue OI. Sin iniciar colectores nuevos
  por cuenta propia.
- **Fase 4–8:** solo si algo de Fase 3 sobrevive el escepticismo.

---

## 7. Documentos de este reset

1. `RESEARCH_RESET_PLAN.md` — este.
2. `DATA_INVENTORY.md` — inventario crudo + clasificación de fuentes.
3. `ALPHA_HYPOTHESIS_LEDGER.md` — ledger + 8 hipótesis priorizadas (H13–H20).
4. `VALIDATION_PROTOCOL.md` — el gauntlet de Fase 4–7.
5. `PORTFOLIO_CAPITAL_PROTOCOL.md` — Fase 8.

**Nada se implementa hasta que el usuario apruebe el mapa y elija qué
hipótesis del ledger arrancan Fase 3.**
