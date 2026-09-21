# Misión — Laboratorio de Diagnóstico

## 2026-09-20 19:07:52 -03:00 — Fase 0

- Leído `MISION_LAB_DIAGNOSTICO.md` y los seis documentos de evidencia requeridos.
- Medido inventario de fuentes de trades para MA Slope Caso 3 y Band Touch 15m, en solo lectura.
- Resultado: la base PostgreSQL actual contiene perfiles reconstruidos tras el reset; sus campos de PnL no se usarán como ground truth de calibración.
- Resultado: `scratch_caso3_gt.json` conserva 45 trades de Caso 3 con entrada, SL, TP, salida, PnL y horarios; es la fuente de mayor fidelidad encontrada para sus señales/entradas. La confiabilidad de su PnL queda parcial hasta rastrear su procedencia original.
- No se ejecutó replay, no se tocó producción, VIRE ni configuración de estrategias.

## 2026-09-20 19:36:51 -03:00 — Fase 1, baseline y ground truth

- Rama aislada: `feat/lab-diagnostico-fase1`; baseline inicial commit `36d9a0b`.
- Consulta PostgreSQL de solo lectura, período 13–20/09 UTC: MA Slope Caso 3 tiene 54 filas con `Side`, `Amount` y `EntryPrice`, 51 con `ClosePrice`; Band Touch 15m tiene 60 y 57 respectivamente. Ambas tienen filas de fees y funding.
- El replay cacheado `agent/backtest/ma_geometry_cached.py` aplica timeout **incondicional**: recorre hasta `max_bars=192` (48 h en velas de 15 min) y, si no tocó SL/TP, cierra en la última vela. No usa el modelo condicional de 720 h.
- Siguiente medición: recalcular PnL desde precios, lado, tamaño, fees y funding; los campos `pnl` y `result_csv` de `scratch_caso3_gt.json` quedan excluidos.

## 2026-09-20 19:42:40 -03:00 — Fase 1, resultado de ground truth

- Corrida `f1-caso3-ground-truth-20260920-1937`, exit 0, 1.26 s. Artefacto: `lab/runs/f1-caso3-ground-truth-20260920-1937/ground_truth.json` (SHA-256 `FB9AC86DB7B4E293163E631C18F7E4394C9E90E9D3FFDA5A16443E381681C0C0`).
- Fórmula aplicada a PostgreSQL cerrado: `gross = Size*(ClosePrice-EntryPrice)` para LONG o `Size*(EntryPrice-ClosePrice)` para SHORT; `net = gross - EntryFee - ExitFee - TotalFundingPaid`.
- Ground truth utilizable: MA3 PostgreSQL 54 señales/entradas y 51 cierres/PnL recalculables; Band PostgreSQL 60 y 57. Scratch Caso 3: 45 señales/entradas/salidas, 0 PnL exactos porque le faltan lado, tamaño y fees; sus `pnl` y `result_csv` se excluyeron.
- Baseline Caso 3 congelada en `lab/baselines/ma-slope-caso-3-v1.json`; parámetros de señal están reconstruidos y etiquetados como tales.

## 2026-09-20 19:49:00 -03:00 — Fase 1, fallo de lanzador

- La corrida background `f1-caso3-signal-detection-20260920-1945` quedó con estado `running` pero el proceso lanzador ya no existía, no dejó stdout ni proceso hijo observable. Se marca `failed` con exit code 1: no produjo una medición y no se usará como evidencia.
- Próxima acción: ejecutar el mismo comando bajo una sesión controlada y capturar su código de salida, evitando el wrapper que falló.

## 2026-09-20 20:15:16 -03:00 — Fase 1, comparación de señales Caso 3

- Smoke test del runner: un trade (`CBRSUSDT`) procesado, señal detectada a -2 min, `RUNNER_EXIT=0`.
- Corrida `f1-caso3-signal-detection-20260920-2014`, exit 0, 35.94 s. Artefacto: `lab/runs/f1-caso3-signal-detection-20260920-2014/signal_detection.stdout.log`.
- Resultado de detección sobre 45 trades: 37/45 dispara en el bar de la señal (criterio actual del script: ±1 h); 7/45 no tienen klines y 1/45 no dispara. Esto aún no es el Gate 1: faltan cupos, salida, orden intrabar y comparación de PnL recalculado.

## 2026-09-20 20:25:47 -03:00 — Fase 1, replay autónomo Caso 3

- Smoke test del nuevo replay/comparador pasó con exit 0 y JSON válido antes de la corrida completa.
- Corrida `f1-caso3-autonomous-replay-20260920-2024`, exit 0, 32.98 s. Resultado SHA-256 `E9235A430F837EE1676393DA9EA34734668B20C9AAE1DE07FB06F6CDF8A604A9` en `lab/runs/f1-caso3-autonomous-replay-20260920-2024/replay_compare.json`.
- Baseline autónoma: 65 trades, 1/45 match total (2.22%), 1/38 en cobertura medible (2.63%), 64 falsos positivos; motivo de salida 0/1. No cumple Gate 1.
- Cobertura como causa aislada: reservar los siete trades sin klines como cupos reales baja 65 a 63 trades, pero conserva 1/45 match. Por tanto no explica la brecha principal.
- Próxima iteración causal: sustituir sólo la generación cacheada de señales por el evaluador de producción ya usado en la medición 37/45, preservando cupos, 48h, salida y costos; medir de nuevo antes de tocar otra variable.

## 2026-09-20 21:16:36 -03:00 — Fase 1, cupos compartidos y admisión

- Smoke test y corrida de `fase1_caso3_shared_slots.py` terminaron exit 0. La máscara `scratch_occ_mask.json` contiene 567 símbolos y 3.108 intervalos, frente a 3.057 aperturas en `scratch_all_trades_window.csv`.
- Base del runner: 1/45 matches; reserva global por máscara: 0/45 y 2 trades. La máscara es más restrictiva que el historial y no reproduce cupos compartidos fielmente; se usa como sensibilidad, no como baseline.
- El código vigente calcula `maxOpenPositions` por perfil (`agent/verge_agent.py:6168`), no como un pool global; por lo tanto no confirma la hipótesis de tres cupos compartidos para el período histórico.
- `AgentDecisionJson` disponible corresponde sólo a trades que abrieron; el ejemplo MA3 contiene `setup_validation=ok` y `cycle_candidates_rejected=[]`. No hay logs históricos de señales rechazadas ni orden de prioridad, por lo que no se puede reconstruir causalmente score/prioridad/cadencia de admisión.
- El reporte `CASO3_SLOT_CAUSAL_REPORT.md` se confirma en dos puntos: minRR 3 vs 4 es inerte en el replay y el orden/prioridad real no es reconstruible. Se refuta para este Gate como explicación suficiente: ni 3 cupos, ni cupos ilimitados, ni la máscara compartida alcanzan la tasa de match requerida.

## 2026-09-20 21:20:00 -03:00 — Fase 1B, gate fijado antes de correr

- Gate 1B: sobre entradas reales con klines, motivo de salida coincidente ≥80% y al menos 80% de los retornos porcentuales de precio por trade dentro de ±0,25 puntos porcentuales. La tolerancia y su fracción se fijan antes de observar la corrida; esta segunda condición se aclara tras detectar que el cierre inicial omitió la fracción, no cambia el resultado: 21/38 (55,3%) falla ambos criterios razonables.
- Baseline: entrada, lado, SL y TP reales; timeout incondicional 48 h; evaluación intrabar SL antes que TP; velas 5m locales. No se usa PnL, `result_csv` ni sizing heredado.

## 2026-09-20 21:25:13 -03:00 — Fase 1B, fidelidad de salida

- Smoke test exit 0. Baseline completo exit 0: 38/45 entradas tienen klines; 32/38 motivos coinciden (84,2%), pero sólo 21/38 retornos están dentro de ±0,25 pp (55,3%; umbral ≥80%).
- Intrabar TP antes de SL: 32/38 y 21/38, sin cambio. Timeout 192h: 18/38 y 13/38, empeora; 48h queda como baseline.
- El fill no es una variante aplicable en 1B: por definición la entrada real (hora y precio) se fija como input. La brecha restante es salida real no reconstruible con velas 5m/timeout fijo, no selección.
- Filtros deterministas confirmados en código: `validate_pre_trade` (incluye minRR y vetos configurables), una operación por símbolo por día en el slot simulator, y cap por perfil. `ma_precompute` ya aplica `validate_pre_trade` antes de generar el stream; el reporte causal previo confirma minRR inerte para esa geometría. `AgentDecisionJson` sólo contiene aprobados y no permite medir vetos históricos sin logs de rechazo.

## 2026-09-20 21:30:00 -03:00 — Fase 1B-1, preregistro de fill

- Una única variable: modelo de precio de fill al detectar TP/SL. Se medirán, sin cambiar entrada, SL, TP ni timeout: `level`, cierre de vela de cruce, open de vela siguiente, peor y mejor entre nivel/cierre.
- Gate sin cambios: motivo ≥80% y ≥80% de retornos dentro de ±0,25 pp. Se informará error firmado por motivo y los TP individuales.
- Los cinco desajustes ZAMA/EGLD/FIL/HU/GOOGL se anotan como candidatos de tick/redondeo; no se abre una iteración específica para ellos.

## 2026-09-20 21:47:00 -03:00 — Fase 1B-2, preregistro de timeout causal

- Se fija `fill=close` para esta iteración: empata como mejor modelo de fill con `next_open` (25/38 dentro de tolerancia), y es el que representa el precio observado en el ciclo que detecta el cruce. La única variable nueva es timeout.
- Modelo a medir: al llegar a 192 velas de 15m (48h), cerrar sólo si el retorno de precio es negativo; si no, continuar hasta TP/SL o el tope duro de 720h. Es la semántica de `zombie_timeout_decision` del agente, no una optimización.
- Gate sin cambios: motivo >=80% y >=80% de retornos dentro de +/-0,25 pp. Se conservarán las métricas por motivo y JUP se reportará por separado.

## 2026-09-20 21:50:00 -03:00 — Fase 1B, resultados de fill y timeout

- `f1b-1-fill-model-20260920-2145` terminó exit 0: todos los fills conservan 32/38 (84,2%) de motivos. Retornos dentro de tolerancia: nivel 21/38, cierre 25/38, próxima apertura 25/38, peor 23/38, mejor 23/38. El mejor resultado es 65,8%, por debajo del 80% fijado.
- Con `fill=close`, errores firmados por motivo real: SL n=6, media +0,128 pp; TP n=10, media -0,840 pp; timeout n=22, media +0,215 pp. Los cuatro TP fuera de tolerancia en nivel eran COMP -0,286, MSFT -0,288, COMP -0,362 y JUP -7,402 pp; JUP no es un fill TP sino un timeout erróneo del replay.
- Timeout de producción confirmado por `agent/verge_agent.py:6519-6558`: al llegar a `maxTradeDurationCandles`, cierra sólo con PnL negativo; positivos se dejan correr, con máximo duro de 720h (`agent/config.py:119`). La configuración MA3 versionada en `agent/backtest/verify_ma_slope_caso3_full_period.py:28` usa 192 velas de 15m (=48h).
- De los 45 trades, 22 superaron 48h (20 timeout, 2 TP); sus retornos de precio se calcularon desde entrada/salida, sin usar PnL legado. JUP duró 208,644h y cerró TP +10,311 pp.
- `f1b-2-conditional-timeout-20260920-2148` terminó exit 0: JUP se corrige a TP (diferencia de cierre +2 min; retorno replay +9,903 pp vs real +10,311 pp), pero el conjunto empeora a 29/38 motivos y 23/38 retornos. La aplicación retrospectiva de timeout condicional no reproduce 20 timeouts reales que ocurrieron aun después de 48h; falta el precio/ciclo exacto que el agente observó y/o la configuración histórica efectiva por posición.
- Los cinco desajustes ZAMA/EGLD/FIL/HU/GOOGL quedan anotados como candidatos de tick/redondeo y no se persiguieron. No se abre Fase 2: Fase 1B falla el gate de fidelidad de salida.

## 2026-09-20 — ENMIENDA A LA MISIÓN (acordada entre el usuario y Claude)

- Fase 2 se autoriza en MODO CONDICIONAL con Fase 1 en FAIL caracterizado.
- Entradas: las reales (Caso 3: los 38 con klines; Band Touch: las de PostgreSQL con cierre) más la población amplia de candidatos del motor para Caso 3 (unos 1.225 sobre 243 días) para tener N suficiente para TRAIN/VAL/OOS temporal.
- Primera entrega, independiente del motor y de los timeouts: MFE, MAE, giveback, tiempo hasta MFE y retorno a 6/12/24/48 h desde la entrada, calculados solo con velas. Por estrategia y por lado, con distribución por símbolo.
- Matriz de variantes de salida (TP corto, giveback, break-even, trailing, SL por ATR, señal opuesta): reportá solo diferencias relativas contra el baseline. Cada resultado se corre con dos modelos de timeout (incondicional 48 h y condicional con tope 720 h) y con sesgo de fill en TP de ±2 pp. Una mejora solo cuenta si se sostiene en los cuatro casos.
- Con N chico (38 a 57) usá tamaños de efecto e intervalos bootstrap, sin p-values. Todo hallazgo se etiqueta HIPÓTESIS hasta confirmarse con datos del ledger.
- Sin PnL absoluto en dólares en ninguna tabla.

## Propuesta (no implementada) — ledger de escaneo por ciclo

- Ubicación propuesta: inmediatamente después de `VergeAgent._run_ma_geometry_scan` y antes/después del ranking/`_execute_trade` en `agent/verge_agent.py`.
- Campos: ciclo/timestamp, perfil y hash de parámetros, símbolo, fuente, lado, precio de señal, score, ranking, cupos antes/después, candidatos simultáneos, cada veto con código/métricas, decisión final, motivo de no ejecución y versión del agente.
- Riesgo: bajo si es append-only y asíncrono/batcheado; principal riesgo es I/O/crecimiento de DB. No tocar producción sin aprobación.
