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

## 2026-09-20 22:03:00 -03:00 — Clasificación solicitada de `TIMEOUT`

- Consulta ejecutada contra PostgreSQL `Verge`, tabla `SimulatedTrades` unida a `StrategyProfiles`, campos `ExitReason` y `AgentDecisionJson`/`exit_audit.close_reason_raw`; evidencia exportada en `lab/runs/f2-timeout-classification-20260920-2200/postgres_ma3_band.csv`.
- No se puede clasificar causalmente los 27 `TIMEOUT` de `scratch_caso3_gt.json`: ninguno tiene identificador de trade y no hay correspondencia temporal utilizable con PostgreSQL. Las coincidencias sólo por símbolo están separadas por miles de minutos y representan posiciones distintas.
- PostgreSQL actual sí conserva categorías normalizadas para su propio conjunto MA3/Band (`sl_hit`, `tp_hit`, `btc_dump`, `timeout`), y 9 filas timeout actuales; `close_reason_raw` no está presente en el JSON de entrada exportado para esas filas. Por ello esas 9 filas no explican ni reclasifican los 27 del scratch.
- Veredicto: `TIMEOUT` del scratch permanece una etiqueta agregada/no desambiguable. Se requiere un ID común de posición o un ledger de salida por ciclo para asignar causa real; no se infiere desde duración o PnL.

## 2026-09-20 22:10:00 -03:00 — Fase 2 condicional, primera entrega de trayectoria

- Smoke y corrida `f2-path-metrics-20260920-2210` terminaron exit 0. Método: velas locales 5m, sin TP/SL, timeout, PnL USD ni decisión del motor. Calcula MFE, MAE, giveback hasta 48h, tiempo a MFE y retornos a 6/12/24/48h.
- Cobertura: 103 entradas de fuente (MA3 45 + Band Touch PostgreSQL 58); 38 con velas, 65 sin cobertura (MA3 7; Band 58). Band Touch queda **NO MEDIDO** en esta primera entrega: sus operaciones PostgreSQL son de septiembre y el almacén local no contiene esas velas.
- MA3 SHORT, n=38: MFE medio +3,369% (IC bootstrap 95% +2,630 a +4,219), MAE medio -2,656% (IC -4,039 a -1,529), giveback medio +2,681% (IC +1,779 a +3,699), tiempo a MFE medio 25,193h. Retorno medio: 6h +0,443%; 12h +0,820%; 24h +0,300%; 48h +0,688%. Todo es HIPÓTESIS descriptiva; no hay p-values ni PnL USD.
- Evidencia: `lab/runs/f2-path-metrics-20260920-2210/result.json` y `progress.json`; script `agent/backtest/fase2_path_metrics.py`.

## Propuesta (no implementada) — ledger de escaneo por ciclo

- Ubicación propuesta: inmediatamente después de `VergeAgent._run_ma_geometry_scan` y antes/después del ranking/`_execute_trade` en `agent/verge_agent.py`.
- Campos: ciclo/timestamp, perfil y hash de parámetros, símbolo, fuente, lado, precio de señal, score, ranking, cupos antes/después, candidatos simultáneos, cada veto con código/métricas, decisión final, motivo de no ejecución y versión del agente.
- Riesgo: bajo si es append-only y asíncrono/batcheado; principal riesgo es I/O/crecimiento de DB. No tocar producción sin aprobación.

## 2026-09-21 00:55:00 -03:00 — Fase 2, corrección interpretativa y preregistro N amplio

- Corrección explícita solicitada: los resultados de `f2-censoring-metrics-v4-20260920-2232` para las 38 entradas MA3 con velas son **descriptivos**, no evidencia a favor ni en contra de una regla de salida. En vida real: 21/38 llegaron a MFE >=2% y 9 de esos devolvieron >=50%; 6/38 llegaron a >=5% y 3 de esos devolvieron >=50%. Con N=38 no se concluye nada.
- Las ventanas fijas de 96 h y 208 h no se interpretarán como “oportunidad perdida”: el máximo favorable sólo puede crecer al prolongar una ventana. Se reportan únicamente como sensibilidad de horizonte y censura.
- Población preregistrada para la medición amplia: se generará el **stream bruto de señales** de MA Slope Caso 3, sin cupos, sin cooldown, sin ranking ni salida, sobre 2025-12-01T00:00:00Z inclusivo a 2026-08-01T00:00:00Z exclusivo (243 días). Se elige el stream bruto, no los ~1.225 trades admitidos con slots ilimitados, porque la segunda cifra ya depende de una política de admisión/vida de posición; el stream es la población causal limpia de entradas. No representa la selección real de producción.
- Cortes temporales fijados antes de calcular métricas: TRAIN 2025-12-01T00:00:00Z a 2026-04-26T00:00:00Z; VALIDATION 2026-04-26T00:00:00Z a 2026-06-14T00:00:00Z; OOS 2026-06-14T00:00:00Z a 2026-08-01T00:00:00Z. No se modificarán según resultados.
- Matriz preregistrada: baseline y variantes TP corto, giveback 10/25/50%, break-even, trailing ATR, SL por ATR y timeout. Cada variante se evaluará con timeout incondicional 48 h y condicional con techo 720 h, y con sesgo de fill TP de -2 pp / +2 pp (cuatro escenarios). Se informan únicamente retornos porcentuales netos de costos modelados, diferencias contra baseline y conteos; nunca PnL USD. Una mejora sólo se etiqueta HIPÓTESIS si mejora OOS, resiste quitar los tres mejores trades y costos +50% en los cuatro escenarios.

## 2026-09-21 01:00:00 -03:00 — Auditoría del supuesto “153 con +30 USDT flotantes”

- Fuente inspeccionada: PostgreSQL `Verge`, tabla `SimulatedTrades`, columnas `MaxFavorablePrice`, `EntryPrice`, `Size`, `OpenedAt`, unida a `StrategyProfiles`. Comando: `docker compose exec -T db psql -U postgres -d Verge -At -F '|' -c <consulta de conteo por perfil>`.
- El campo que podría representar el pico es `MaxFavorablePrice`, actualizado por `agent/position_manager.py:648`; no se encontró un campo/csv confiable que respalde el número exacto 153 ni el umbral textual “+30 USDT flotantes”.
- Después del reset, MA Slope Caso 3 tiene 55/55 filas con `MaxFavorablePrice` y Band Touch 15m 64/64, únicamente entre 2026-09-13 y 2026-09-21. Aplicar ingenuamente `abs(MaxFavorablePrice-EntryPrice)*Size >= 30` da 5 MA3 y 3 Band, no 153. Los perfiles previos al reset tienen en general el campo nulo (por ejemplo Nexus 0/1.927).
- Veredicto: el contador 153 no es reproducible ni confiable para giveback histórico grande. No se usará en Fase 2 ni para afirmar cobertura de ambas estrategias. El ledger nuevo es el mecanismo prospectivo para que ese dato quede trazable por ciclo/cierre.

## 2026-09-23 — Fase 2 (población amplia) ejecutada por Claude tras corte de Codex por límite de uso

- La corrida `f2-ma3-broad-20260921-0104` había fallado (exit 1). Causa: `split_for()` con `StopIteration`; 4 de 9.400 señales abren exactamente en END (2026-08-01T00:00:00Z) y el corte era exclusivo. Corrección de borde en `agent/backtest/fase2_ma3_broad_matrix.py` (solo `ts == END` va al último split); los cortes TRAIN/VAL/OOS preregistrados NO cambiaron.
- Bug hallado en la variante `sl_atr_1r`: su fórmula `entry + (original_sl - entry) * 1.0` es un no-op (== SL original), por eso daba idéntico al baseline en los 4 escenarios. NO se redefinió post-hoc. Queda EXCLUIDA de la matriz (7 variantes) y pendiente de iteración aparte con preregistro y serie ATR real.
- Omisión corregida: el resumen `path_metrics_48h` guardaba solo `n`; ahora agrega media/mediana de MFE, MAE, giveback, tiempo a MFE y retornos a 6/12/24/48 h por split.
- Resultado (resultado en `agent/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/result.json`; 9.400 señales brutas, 243 días; TRAIN 4.236 / VAL 2.536 / OOS 2.628; HIPÓTESIS, no es selección de producción):
  - MFE mediana 2,41 / 2,10 / 2,43 %; giveback mediana 2,27 / 2,18 / 1,61 %; tiempo a MFE mediana 23,8 / 22,8 / 31,8 h. Estable entre splits.
  - Matriz vs baseline (OOS, 4 escenarios: timeout incondicional/condicional × sesgo fill TP ±2 pp): break_even_1r y giveback_50 empeoran en los 4; giveback_10, giveback_25 y trailing_2r cambian de signo según escenario (no robustos); tp_short_50 cambia de signo con el sesgo de fill (no usable sin calibrar fill real).
  - Baseline: media OOS pequeña positiva (0,06 a 0,51 %), mediana ≈ -1,3 % en todos los escenarios.
- Ledger de escaneo (worktree `Verge-ledger`, rama `feat/scan-ledger-isolated`): diff revisado por Claude, cumple los tres pedidos (razón de cada rechazo, eventos de revisión/cierre de posición, flush por tiempo + fsync + rotación). Sin tocar lógica de decisión. NO desplegado. Falta verificar si la ruta `agent/data/scan_ledger.jsonl` es volumen persistente en el despliegue real del agente (no está en el docker-compose local).

## 2026-09-23 — PREREGISTRO Fase 2b (escrito ANTES de correr; Claude)

**Población y cortes: idénticos a Fase 2** (stream bruto MA3, 9.400 señales, TRAIN/VAL/OOS fijos, mismos 4 escenarios timeout×sesgo fill TP, costo base 0,08 %). Baseline se recomputa con el mismo código y se verifica contra `result.json` previo (OOS unconditional|tp_bias_-2 = 0,30710306548 %); si no coincide, la corrida se invalida.

**Variantes nuevas (7, todas definidas aquí antes de ver resultados):**
- SL por ATR, ATR = promedio simple de los últimos 14 True Range de velas 1h CERRADAS antes de la apertura (mismo criterio que producción, sin Wilder). SL_dist = min(distancia SL original, k·ATR) (solo "estricto": nunca más amplio que el original), TP original intacto. k ∈ {1,0; 1,5; 2,0} → `sl_atr_1.0`, `sl_atr_1.5`, `sl_atr_2.0`. Trades sin 15 velas 1h previas usan el SL original y se reportan aparte.
- Salida por tiempo (motivada por MFE mediana a 22–32 h): cierre al cierre de vela a las T horas si no salió antes por SL/TP: `time_exit_12h`, `time_exit_24h`, `time_exit_36h`; y `time_stop_24h_if_losing` (a las 24 h cierra solo si el retorno es negativo). Orden intra-vela: SL, TP, luego reglas de tiempo (como el baseline).

**Criterio de éxito (fijado ahora):** una variante solo se etiqueta HIPÓTESIS de mejora si, en LOS CUATRO escenarios: (a) Δ OOS vs baseline > 0; (b) Δ OOS sin los 3 mejores trades > 0; (c) Δ > 0 en al menos 2 de los 3 splits (TRAIN/VAL/OOS). Costos +50 % se reportan (el desplazamiento es constante para todas las variantes, por lo que no altera el ranking relativo).

**Conteo de familia (anti-sobreajuste):** con estas 7 + las 6 no-baseline de Fase 2 (tp_short_50, giveback_10/25/50, break_even_1r, trailing_2r) = **13 variantes de salida probadas** sobre esta población. Un "ganador" entre 13 vale menos que uno entre 1: se reportará el conteo junto a cualquier hallazgo.

**Band Touch:** las velas de septiembre SÍ existen en la base viva del agente (`agent/data/klines.db`, montada `:ro` en `/app/live-research/klines.db`; 15m con ~90 % de cobertura, 5m parcial). La conclusión previa "sin cobertura" solo miró `binance_vision_clean.db` (termina en agosto). Se hará trayectoria descriptiva de las entradas reales de Band Touch con velas 15m, sin descargar nada. N chico (≈58): HIPÓTESIS descriptiva, sin conclusiones.

**Ledger:** el agente vivo corre en el HOST (no en Docker); `agent/data/` es disco local persistente (mismo directorio de `positions.json`). Desplegar el ledger exige reiniciar el agente en vivo (sin hot-reload): NO se hace sin OK explícito del usuario.

## 2026-09-23 — Fase 2c: Band Touch, trayectoria descriptiva (Claude)

- Entradas: 82 trades cerrados de Band Touch en PostgreSQL (`lab/runs/f2c-band-path-20260923/input_band_trades.csv`). Velas: 15m de la base viva del agente (`klines.db`, solo lectura, sin descargar nada). Script `agent/backtest/fase2c_band_path_metrics.py`.
- Corrección de método (propia, antes de reportar): la primera versión usaba las velas de entrada y de cierre completas; esas velas contienen precios anteriores a la entrada o posteriores al cierre e inflaban el MFE. Se corrigió a velas 15m completamente dentro de la vida del trade (cota INFERIOR de MFE). 17 trades quedan fuera por durar menos de 2 velas completas (no por falta de datos; sesgo posible: probablemente SL rápidos, así que el MFE medio puede estar levemente sobreestimado).
- Resultado (n=65, HIPÓTESIS, sin PnL USD): MFE medio +5,21 % (IC bootstrap 95 %: 3,78 a 6,98), giveback medio +4,62 % (3,62 a 5,57), retorno final medio +0,58 %, vida media 10,5 h, tiempo a MFE medio 5,9 h. MFE ≥2 %: 36 trades, 24 devolvieron ≥50 %; ≥5 %: 22, 12 devolvieron ≥50 %; ≥10 %: 10, 3 devolvieron ≥50 %. Por motivo de salida: SL n=41 con MFE medio +2,35 % y final −3,24 %; TP n=9; timeout n=11.
- Lectura: el patrón "la entrada tiene ganancia flotante y luego se revierte" también aparece en Band Touch (41 trades cerraron por SL habiendo llegado en promedio a +2,4 %), consistente con MA3. Con N=65 y sin población amplia ni matriz de salidas, NO hay conclusión sobre qué salida corregiría esto.

## 2026-09-23 — Fase 2b: primera corrida INVALIDADA por el chequeo de regresión (Claude)

- La primera corrida completa de `fase2b_ma3_exit_variants.py` devolvió `regression_ok: false`. Sus veredictos "NO pasa" NO se usan. Causa: error de transcripción propio en `exit_new`, el signo del sesgo de fill del TP estaba invertido respecto de `fase2_ma3_broad_matrix.exit_trade` (los escenarios `tp_bias_-2` y `tp_bias_+2` salían intercambiados; los valores del baseline coincidían con los de Fase 2 pero cruzados).
- Corregido, y agregado `--selftest`: compara `exit_new(baseline)` contra `exit_trade(baseline)` en 400 trades × 4 escenarios = 1.600 comparaciones, 0 diferencias. El criterio de éxito preregistrado no se modificó. Se relanza la corrida completa.

## 2026-09-23 — Fase 2b: RESULTADO válido (Claude; `lab/runs/f2b-ma3-exit-variants-20260923/result.json`)

- Chequeo de regresión OK (baseline OOS unconditional|tp_bias_-2 = 0,30710306548 %, idéntico a Fase 2). 9.400 señales, 0 sin ATR. Criterio preregistrado (commit 841a4f0): Δ OOS > 0, Δ OOS sin top-3 > 0 y Δ > 0 en ≥2 de 3 splits, en LOS CUATRO escenarios.
- **Ninguna de las 7 variantes pasa** (sl_atr_1.0/1.5/2.0, time_exit_12h/24h/36h, time_stop_24h_if_losing). Con las 6 de Fase 2, son **13 variantes de salida probadas y 0 hallazgos robustos** sobre esta población.
- Patrón notable: casi todas mejoran en TRAIN y VAL y empeoran en OOS (p. ej. time_exit_24h, unconditional|-2: TRAIN +0,108, VAL +0,125, OOS −0,271 pp). Una búsqueda que mirara solo TRAIN habría "encontrado" salidas por tiempo que no sobreviven fuera de muestra; es la razón de preregistrar y reservar OOS. Excepción aislada: conditional|-2 time_exit_36h da OOS +0,113 pero falla en los otros tres escenarios.
- Los SL por ATR (solo "estrictos") empeoran OOS en los cuatro escenarios: recortar el SL saca más operaciones que las que protege.
- Lectura: NO hay evidencia de que una salida simple (SL por ATR, salida por tiempo, giveback, break-even, trailing, TP corto) corrija el giveback de MA3 en OOS. El giveback existe (Fase 2) pero estas reglas no lo convierten en mejora robusta. Es HIPÓTESIS sobre el stream bruto, no sobre la selección real de producción. Siguientes caminos honestos: (a) entradas más selectivas (filtro de régimen/símbolo) en vez de salidas; (b) esperar datos del ledger para calibrar timeout/selección reales.

## 2026-09-25 11:40:00 -03:00 — Verificación independiente de Fase 2b (Codex)

- Compilación previa: `python -m py_compile agent/backtest/fase2b_ma3_exit_variants.py` y la misma compilación dentro de `verge-backtest`; ambas exit 0.
- Primer selftest inválido: se invocó sin los argumentos obligatorios `--output` y `--cache`; exit 2, sin comparaciones. Se registra, no se usa como evidencia.
- Selftest repetido con cache congelado `/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl`: exit 0, `selftest_total=1600`, `selftest_mismatch=0`. Evidencia persistida: `agent/backtest/lab_artifacts/f2b-selftest-20260925.stdout.log` y `.exitcode` (no se agregan al commit: son artefactos locales).
- Reproducción de un número del resultado: `lab/runs/f2b-ma3-exit-variants-20260923/result.json`, ruta `scenarios[unconditional|tp_bias_-2].baseline.oos.mean` = `0.30710306548436167`, consistente con el valor esperado `0.30710306548`.

## PROPUESTA PREREGISTRADA, NO INICIADA — Fase 2d: diagnóstico de selección de entradas MA3

- Objetivo: medir si el resultado del stream bruto congelado de 9.400 señales MA3 se concentra de forma reproducible por contexto de entrada; no modificar reglas de salida, perfiles ni producción.
- Datos y cortes: exactamente el cache/stream de Fase 2; TRAIN 2025-12-01..2026-04-26, VALIDATION 2026-04-26..2026-06-14, OOS 2026-06-14..2026-08-01; cuatro escenarios existentes (`timeout` incondicional/condicional × fill TP -2/+2 pp), costo base 0,08 % y sensibilidad +50 %.
- Cortes a probar, fijados antes de correr (15 vistas, sin búsqueda adicional): 4 bloques UTC de hora de entrada (00-05, 06-11, 12-17, 18-23); 3 regímenes BTC de retorno 24 h al ingreso (bajista < -2 %, plano [-2 %, +2 %], alcista > +2 %); 3 terciles de volatilidad realizada 24 h del símbolo, cuyos bordes se calculan sólo en TRAIN; y 5 símbolos con mayor cantidad de señales TRAIN (cada uno por separado). Las otras categorías se reportan agregadas, no se convierten en cortes adicionales.
- Métrica: retorno porcentual neto baseline, media/mediana, N, concentración sin top-3 y distribución de MFE/MAE/giveback a 48 h. No PnL USD. Se reporta la superficie completa de las 15 vistas por TRAIN/VALIDATION/OOS y los cuatro escenarios.
- Regla de selección antes de ver OOS: una vista queda “candidata de contexto” sólo si tiene N >= 50 en TRAIN y >= 25 en VALIDATION, media neta positiva en TRAIN y VALIDATION, y el mismo signo en los cuatro escenarios. OOS no participa en esa selección.
- Gate diagnóstico: una candidata se etiqueta solamente **HIPÓTESIS de filtro de entrada** si además tiene media OOS positiva, OOS sin top-3 positiva y la misma dirección en los cuatro escenarios. Si ninguna pasa, veredicto: “no hay contexto simple robusto en estas 15 vistas”. Esta fase no habilita cambios de estrategia.

## 2026-09-25 — ENMIENDA Fase 2d (aprobada antes de correr)

- HOLDOUT2: antes de generar el stream se verificará, sólo con bases locales, la cobertura posterior a 2026-08-01T00:00:00Z en `binance_vision_clean.db` y `agent/data/klines.db` (montada read-only como `/app/live-research/klines.db`). Si permite señales MA3, se congelará como HOLDOUT2 y no se mirará hasta que TRAIN/VALIDATION/OOS seleccionen candidatas. Si no hay cobertura suficiente, se reportará como limitación.
- Dependencia: todo IC de Fase 2d usará bootstrap por bloques de día UTC. Cada tabla reportará N de señales y N efectivo de días.
- Criterio relativo: además de los criterios anteriores, una vista debe superar la media neta de todas las señales complementarias del mismo split (delta > 0) en TRAIN y VALIDATION. Se reportarán delta e IC bootstrap por días; OOS no participa en la selección.
- HOLDOUT2 se observará una sola vez, al final y sólo para candidatas fijadas con TRAIN/VALIDATION/OOS. Debe conservar media positiva, ventaja relativa, OOS sin top-3 positiva y dirección consistente en cuatro escenarios.
- Anti-sobreajuste: todo hallazgo reportará 28 hipótesis: 13 variantes de salida + 15 vistas de contexto. No se agregan nuevos cortes.

- Nota de auditoría: el primer intento de registrar esta enmienda no modificó el archivo porque la revisión automática devolvió `401 Unauthorized: Incorrect API key provided`; el reintento dejó esta enmienda completa antes de cualquier corrida de Fase 2d.

## 2026-09-25 — Fase 2d: cierre

- Smoke PASS: `python /app/backtest/fase2d_ma3_context.py --smoke ...`; 2 señales y 8 filas de escenario. Compilación previa host y contenedor con `python -m py_compile` exit 0.
- Corrida: `f2d-ma3-context-20260925`, evidencia local `/app/backtest/lab_artifacts/f2d-ma3-context-20260925/{progress.json,result.json}`. Recorrió 9.400 señales; regresión baseline `unconditional|tp_bias_-2` = `0.30710306548436167`, igual al valor preregistrado, `regression_ok=true`.
- HOLDOUT2: no se abrió. Cobertura local medida con `agent/backtest/inspect_local_coverage.py --probe-symbol BTCUSDT`: canónica 5m post 2026-08-01 termina en `1787010900000` (2026-08-17), mientras la viva llega a `1790261700000` (2026-09-25). El motor MA3 requiere además la tabla canónica 15m, ausente en la viva; no hay una fuente homogénea para evaluar los cuatro escenarios, por lo que se registra como limitación y no se usa un hold-out incompleto.
- Resultado: 15 vistas fijas, 28 hipótesis contabilizadas (13 salidas + 15 contexto), y **0 candidatas antes de OOS**. En consecuencia no se inspeccionó OOS para candidatas ni HOLDOUT2. Veredicto: no hay filtro de contexto que cumpla el criterio preregistrado en TRAIN/VALIDATION bajo los cuatro escenarios. HIPÓTESIS sobre stream bruto, no selección real de producción.
