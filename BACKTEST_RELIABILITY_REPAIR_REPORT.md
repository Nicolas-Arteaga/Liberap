# BACKTEST RELIABILITY REPAIR — PHASE 1

Fecha: 2026-09-05
Alcance: reparar el motor de replay histórico (`agent/backtest/engine.py`) para que
reproduzca la **lógica de decisión** de producción. No es research de alpha. No se
tocó ninguna estrategia, ni H11/H12, ni producción (salvo lectura). Ningún
parámetro se ajustó para hacer coincidir el PnL.

Universo congelado (igual que el gate v1): **MA Slope Caso 2**, 113 trades reales
cerrados, 2026-07-11 → 08-09, config leída de `verge-db`.

---

## 1. Root cause del FAILED (gate v1)

El gate v1 (2026-09-05) dio: real 113 trades / −$116 / PF 0.55 vs replay 1268
señales / +$43 / PF 1.16 — sign flip, 17 % de match, 11.2× de inflación de señal.

Causas raíz, en orden de impacto, **todas verificadas contra el código de producción**:

| # | Causa | Evidencia |
|---|---|---|
| R1 | **Veto macro de BTC desactivado** en el replay: `validate_pre_trade(..., btc_filter=None)` (`engine.py:800`). La "BTC INTELLIGENT BLOCKING (Capa C)" de `verge_agent.py:6249-6284` bloquea todo LONG cuando `BTCMacroFilter.get_regime()=="DUMPING"` sin desacople. El replay no la aplicaba → abría LONGs que producción bloqueó. | `verge_agent.py:6249`, `btc_macro_filter.py` |
| R2 | **Veto diario pump/dump evaluado contra el mercado EN VIVO**: `_fetch_24h_price_change_percent()` pega a la API de Binance con la hora real de ejecución del script, no la del trade histórico, salvo que el caller setee `candidate["historical_daily_change_pct"]` — el replay no lo seteaba. | `setup_validator.py:1199-1214` (comentario del bug ya documentado en el código) |
| R3 | **Timeout mal modelado**: el motor cerraba `zombie_timeout` a las 24 h **gane o pierda**. Producción (`verge_agent.py:6506-6540`) solo cierra por timeout **si el trade está en pérdida**; si está en ganancia "se deja correr" hasta TP/SL. Guillotinaba ganadores que en la realidad corrían 2–4 días hasta el TP (7 de los 19 pares matcheados del gate v1). | `verge_agent.py:6518` (`candle_seconds = 900`), `verge_agent.py:6530` (`if pnl_pct < 0`) |
| R4 | **`has_traded_symbol_today` sin dimensión cruzada**: `_should_skip()` (llamado también por la inyección MA, `verge_agent.py:1375`) descarta un símbolo si **cualquiera** de las ~26 estrategias ya lo operó hoy. El replay solo miraba los trades de MA Slope Caso 2. | `verge_agent.py:2988-2992`, `state_manager.py:94-97` |
| R5 | **Funding = 0** silencioso en `_capital_sim`. | `engine.py::_capital_sim` |
| R6 | **Sin pausa por flash-crash**: producción hace `time.sleep(2h); return` (`verge_agent.py:771`) — el agente entero deja de escanear. | `verge_agent.py:769-773` |
| R7 | **Cobertura histórica incompleta**: 22 símbolos con trade real (25 de 113 trades = 22 %) sin ninguna vela en `binance_vision_clean.db`. | gate v1 §6 |

Efecto compuesto: R1+R2 inflaban las señales ~11×; con 3 cupos de capital y FIFO,
esas señales de más ganaban los cupos y desplazaban a las reales → 17 % de match
y sign flip del PnL.

---

## 2. Correcciones realizadas

Todas en `agent/backtest/engine.py` salvo indicación. **Aditivas** — el
comportamiento por defecto (sin pasar `fidelity=…`) es el de antes; las
correcciones se activan explícitamente.

| Fix | Qué | Dónde |
|---|---|---|
| **F1 — BTC macro filter histórico** | `BTCMacroFilter` real de producción, construido sobre un shim (`_HistBtcShim`) que sirve velas de BTC causales (`get_btc_klines`, 1m/5m/15m/1h/1d). 1m nuevo: `btc_klines_1m` en `binance_vision_clean.db` (112 320 filas, 2026-06-01 → 08-17, 100 % spacing exacto), backfill dedicado `agent/download_btc_1m.py` (solo `data.binance.vision`, nunca `fapi`). `fidelity={"btc_block": True}` replica la Capa C (LONG bloqueado si régimen DUMPING sin desacople) + pausa por flash-crash. Cache de régimen bypaseado por tick (sim-time ≠ wallclock). | `engine.py` `HistoricalFetcher.get_btc_klines`, `_HistBtcShim`, `_run_generic._btc_blocks_long` |
| **F2 — historical_daily_change_pct** | `fidelity={"daily_change": True}` inyecta el cambio 24 h real (base 5m, causal) en cada candidato antes de `validate_pre_trade`, para que el veto `daily_pump/dump_exhaustion` NO pegue a la API en vivo. | `engine.py` `_run_generic._hist_daily_change` |
| **F3 — timeout FIEL a producción** | Helper puro `zombie_timeout_decision(open_ms, now_ms, max_candles, pnl_pct_now)`: (a) antigüedad en velas de **15 m fijas** — verificado: es lo que hace producción a propósito (`candle_seconds = 900`), confirmado contra **34 trades reales de timeout** de esta estrategia, moda 24.0–24.2 h; (b) `zombie_timeout` **solo si el trade está en pérdida**; (c) tope duro `max_duration` a 720 h. Nota: la directiva original ("`candles × timeframe`") se basaba en el diagnóstico del gate v1; al leer el código, 15 m es el unit real de producción, no un bug — el bug era la ausencia del gate por signo de PnL. | `engine.py` `zombie_timeout_decision`, usado en `_run_generic` y `run_fvg_global` |
| **F4 — has_traded_symbol_today cruzado** | `fidelity={"traded_before": {symbol: [opened_ms,…]}}` reconstruido de **trades reales de las 26 estrategias** (`scratch_all_trades_window.csv`, 3 057 trades). Un candidato se descarta si cualquier estrategia abrió ese símbolo antes de `now_ms` en el mismo día local (Argentina), igual que `_should_skip()`. Es reconstrucción con dato real, no un modelo. | `engine.py` `_already_traded_cross_strategy` |
| **F5 — funding real** | `_FundingLookup` lee `agent/data/klines.db::funding_rates` (490 símbolos). Suma causal de `notional × funding_rate` sobre las marcas de funding dentro de la vida del trade; `funding_covered=False` donde no hay cobertura (0, sin inventar). | `engine.py` `_FundingLookup`, `_capital_sim` |
| **F6 — blackout flash-crash** | `fidelity={"blackout": [(a,b),…]}` ventanas de 2 h tras cada flash-crash de BTC (detectado sobre `btc_klines_1m`, umbral `BTC_FLASH_CRASH_PCT_1H`). En la ventana del gate: 1 sola (2026-06-25, fuera del período de trades). | `engine.py` `_run_generic._in_blackout` |
| **F7 — clasificación de cobertura** | `gate_v2.py::coverage_table` → REPLAYABLE / PARTIALLY REPLAYABLE / UNREPLAYABLE por símbolo, con impacto cuantificado. | `gate_v2.py` |

---

## 3. Tests agregados

`agent/backtest/test_engine_timeout.py` — 7 tests del helper `zombie_timeout_decision`:

- no cierra antes del umbral;
- cierra `zombie_timeout` en el umbral **si está en pérdida**;
- **no** cierra en el umbral si está en ganancia (el bug), ni mucho después mientras gane;
- cierra si el trade se vuelve negativo pasado el umbral;
- `max_duration` a 720 h **gane o pierda** (y la pérdida tiene prioridad);
- **independiente del timeframe de la estrategia** (5m / 15m / 1h / 4h dan el mismo resultado — el helper ni recibe el TF; la regla real siempre es 96 × 15 m);
- `maxTradeDurationCandles` chico (16 → 4 h).

`7/7 OK`.

`agent/backtest/validate_btc_filter_repro.py` — prueba reproducible del F1 (ver §8).

---

## 4. Qué queda FAITHFUL

Verificado con evidencia, no asumido.

| Componente | Evidencia |
|---|---|
| **Detección del patrón MA geometry** | En el diagnóstico punto-a-punto (`gate_v2_diagnose_misses.py`), **85 de 88** trades reales replayables → el `candidate_fn` + todo el stack de vetos + el sizing dan `OK_would_open` en el timestamp real de la señal. |
| **Veto macro de BTC** | 110/113 (97.3 %) de acuerdo exacto con `AgentDecisionJson.btc_context.regime` real; los 3 desacuerdos son BULLISH↔NEUTRAL (ambos permiten LONG). **0 errores peligrosos** (ningún caso prod=DUMPING → hist≠DUMPING). |
| **Veto diario pump/dump** | Ya no pega a la API en vivo; usa el cambio 24 h histórico causal. |
| **Timeout** | 15 m units + gate por signo de PnL + tope 720 h, idéntico a `verge_agent.py:6506-6544`; validado contra 34 trades reales de timeout. |
| **Cupos por perfil** | Producción calcula el límite **por `strategyProfileId`** (`verge_agent.py:6166-6182`); el replay ya hacía 3 cupos por estrategia — correcto (no hay cupo a nivel cuenta). |
| **Sizing** | `qty = margin / entry`, leverage 1× — confirmado en 113/113 trades y en `setup_metrics.notional_est`. |
| **Fees** | 0.04 %/lado sobre notional de entrada+salida; Δ mediana vs real 0.24 %. |
| **Anti-lookahead** | `HistoricalFetcher` nunca sirve datos posteriores a `now_ms`; `get_btc_klines` con cutoff causal explícito. |
| **1 trade/símbolo/día por estrategia** | `last_trade_day` con offset Argentina, igual que `has_traded_symbol_today`. |

---

## 5. Qué queda APPROXIMATE (con sesgo cuantificado)

| Componente | Estado | Sesgo |
|---|---|---|
| **Timeline exacto de ocupación de cupos** | APPROXIMATE | **Este es el gap dominante que queda.** El replay abre en la **primera** vela de 5 m en que el patrón + vetos pasan; producción abre más tarde (latencia de escaneo real, `ThreadPoolExecutor` de 10 workers, encolado). Con 3 cupos FIFO, diferencias de timing de minutos → distinto conjunto de ~93 símbolos gana los cupos. El replay abriría 85/88 de los reales **si los cupos estuvieran libres**, pero compite contra ~900 señales propias. Efecto: match rate 9 %, false-positive 69 %, aunque el **número** de trades coincide (93 replay vs 113 real) y el signo del PnL también. |
| **has_traded_symbol_today cruzado** | APPROXIMATE | Reconstruido de trades reales, pero se aplica contra el timing (levemente distinto) del replay → sensibilidad de cascada. Ablación: quitarlo cambia < 3 trades aceptados y no mueve el match rate → **no es el gap dominante**. |
| **Funding** | APPROXIMATE | Real donde hay cobertura (`funding_rates`, arranca ~2026-07-07 y con huecos por símbolo durante julio); 0 donde no. Impacto acotado: funding real total de los 113 trades = **$2.92** (2.5 % del −$116 neto real). |
| **Fill de entrada / slippage** | APPROXIMATE | El replay llena al cierre de la vela de 5 m de la señal; producción, minutos después. Δ precio de entrada mediana **0.24 %** (dentro de tolerancia), Δ timing de entrada mediana **23 min**. Sin modelo explícito de slippage. |
| **Salida intrabar TP/SL** | APPROXIMATE (FAITHFUL para MA Slope) | Resuelve TP antes que SL sobre la misma vela de 5 m (sesgo optimista). En MA Slope: **0 casos** de vela que toque ambos (SL ~2 % vs TP ≥7 %). Para FVG/OrderBlock/scalping (stop ajustado) queda como sesgo optimista latente, **sin cuantificar en este gate**. |
| **Pausa por flash-crash** | APPROXIMATE | Blackout de 2 h por evento (detectado sobre BTC 1m). Producción también deja de monitorear posiciones abiertas en esa ventana; el replay las sigue monitoreando. Irrelevante en el período del gate (0 flash-crash entre 07-11 y 08-09). |
| **Watchlist** | APPROXIMATE | El replay usa la watchlist actual (~285 símbolos ∩ dataset); la de julio era distinta. |
| **Ranking por `bucket_calibrator`** | APPROXIMATE | Producción ordena los candidatos por `score × bucket_multiplier` antes de asignar cupos; el multiplicador se recalcula cada 24 h contra Postgres y no es reconstruible históricamente. Para MA Slope (score fijo 80) el efecto sobre el orden **dentro** de la estrategia es mínimo. |

---

## 6. Qué queda UNTESTABLE

| Componente | Motivo |
|---|---|
| **25 de 113 trades reales (22 %)** sobre 22 símbolos **UNREPLAYABLE** (`4USDT`, `COTIUSDT`, `PENGUSDT`, `RVNUSDT`, `RPLUSDT`, `REDUSDT` (×3), `SAPIENUSDT` (×2), `DUSKUSDT`, `ILVUSDT`, `TZAUSDT`, `UVXYUSDT`, `AVGOUSDT`, `ETHBTCUSDT`, `EWTUSDT`, `ICNTUSDT`, `MAVUSDT`, `MINIMAXUSDT`, `C98USDT`, `ATUSDT`, `COAIUSDT`, `SKHYUSDT`) — sin ninguna vela en `binance_vision_clean.db` (listings nuevos, deslistados, perps de acciones). No están en `data.binance.vision` con el mismo formato o directamente no existen ahí. **Impacto**: esos 25 trades reales suman **−$18.7** de PnL real (16 % de la pérdida). El replay nunca puede reproducirlos. |
| **Latencia real de ejecución y uptime del agente por minuto** | No hay log histórico de cuándo exactamente el agente estuvo arriba / cuánto tardó cada ciclo de escaneo. Sin eso, el timeline de ocupación de cupos (§5) no se puede hacer FAITHFUL. |
| **Estado en memoria del proceso** (equity-curve pause `_EQUITY_CURVE_PARAMS`, `_tier3_index`, cachés de régimen) | No se persiste. Reconstruible solo por simulación, no por dato. Para MA Slope Caso 2 en el período: drawdown < 25 % del pico → la pausa por equity-curve nunca se dispara (no material). |

---

## 7. Nuevo LIVE vs REPLAY gate (V2)

Criterios **pre-registrados** en `agent/backtest/GATE_V2_CRITERIA.md` ANTES de correr
(`gate_v2.py`). Filosofía fijada por el usuario: validar **decisiones**, no PnL.

Resultado mecánico contra las bandas pre-registradas:

| # | Métrica | Valor | Banda |
|---|---|---|---|
| P1 | REAL→REPLAY match rate (símbolos REPLAYABLE) | **9 %** | **FAILED** (<45) |
| P2 | REPLAY→REAL false-positive rate | **69 %** | **FAILED** (>60) |
| P3 | Inflación de señal | 2.6× | PARTIAL (2–4×) |
| P4 | Signo del PnL neto | mismo signo, Δrel 97 % | PARTIAL |
| P5 | Δ profit factor | 0.43 | **FAILED** (>0.40) |
| S1 | Exit reason agreement | 62 % | PARTIAL |
| S2 | Correlación de PnL (r) | 0.52 | **FAILED** (<0.55) |
| S3 | Δ precio entrada (mediana) | 0.24 % | PASS |
| S4 | Δ timing entrada (mediana) | 23 min | PASS |
| S5 | Δ timing salida (mediana) | 1.2 h | PASS |
| S6 | Acuerdo de dirección | 100 % | PASS |
| I2 | Trades sobre UNREPLAYABLE | 22 % | PARTIAL |
| I3 | Reproducibilidad filtro BTC | 97.3 %, 0 peligrosos | PASS |

Agregado: **REAL −$116.28 / PF 0.55 / WR 21 %**  vs  **REPLAY −$3.81 / PF 0.98 / WR 12 %** (93 trades).

Comparación con el gate v1:

| | gate v1 | gate v2 |
|---|---|---|
| señales crudas | 1 268 (11.2×) | 979 (2.6×) |
| trades aceptados | 140 | 93 |
| PnL neto replay | **+$43 / PF 1.16** (sign flip) | **−$3.81 / PF 0.98** (mismo signo) |
| match rate | 17 % | 9 % * |
| Δ precio entrada | — | 0.24 % |

\* El match rate bajó porque, con la inflación cortada de 11× a 2.6×, el
denominador comparable cambió y el timeline de cupos (§5) reparte los 93 trades
entre otros símbolos. La ablación (quitar F4) da el mismo 9 % → **no es la máscara
cruzada; es el timeline de ocupación de cupos.**

---

## 8. Evidencia de concordancia

- **Decisión punto-a-punto** (`gate_v2_diagnose_misses.py`): 85/88 (97 %) de los
  trades reales replayables → el replay los abriría en su timestamp real. Los
  fallos: 1 `no_pattern` (USDCUSDT, stablecoin), 2 `traded_before_cross` (bloqueo
  cruzado legítimo). **Ningún** trade real cae por un veto que el replay aplique de más.
- **Filtro BTC** (`validate_btc_filter_repro.py`): 110/113 acuerdo exacto con el
  régimen registrado por producción, 0 errores peligrosos.
- **Timeout**: 34/34 trades reales de timeout con duración ≥ 24.0 h, moda
  24.0–24.2 h → confirma unidad de 15 m y gate por signo.
- **Economía en los pares matcheados** (n=8): Δ precio entrada 0.24 %, Δ timing
  entrada 23 min, Δ timing salida 1.2 h, dirección 100 %. Las diferencias que
  quedan son de fill/timing, no de lógica.
- **Signo y magnitud agregada**: el sign flip del PnL desapareció. El replay ya no
  dice "estrategia rentable"; dice "perdedora leve" (PF 0.98) contra "perdedora
  clara" real (PF 0.55). Sigue optimista (Δ PF 0.43).

Artefactos: `agent/backtest/gate_v2.py`, `GATE_V2_CRITERIA.md`,
`scratch_gate_v2_trades.csv`, `gate_v2_diagnose_misses.py`,
`validate_btc_filter_repro.py`, `test_engine_timeout.py`,
`download_btc_1m.py`, caches `gate_v2_replay_cache*.json`.

---

## 9. Decisión final

### GATE V2 = **PARTIAL**

Mecánicamente el gate está en **FAILED** (P1, P2, P5, S2 en banda FAILED). Pero la
regla de `GATE_V2_CRITERIA.md` pide además evaluar la **explicabilidad** de las
divergencias, y ahí el cuadro cambia de forma sustantiva:

- La **lógica de decisión** del replay quedó **verificada como fiel** (85/88
  punto-a-punto; BTC, timeout, vetos, sizing todos validados con evidencia).
- Los 4 fallos mecánicos tienen **una sola causa raíz explicada**: el replay no
  reproduce el **timeline exacto de ocupación de los 3 cupos** porque no modela la
  latencia/cadencia real del escáner del agente. Bajo FIFO, ese desfasaje de
  minutos reparte los ~93 trades entre símbolos distintos (P1/P2), lo que a su vez
  descorrelaciona el PnL por-trade (S2) y deja el PF agregado optimista (P5).
- El **sign flip del PnL — el síntoma más grave del gate v1 — está corregido.**

Por eso el veredicto honesto es **PARTIAL**, no FAILED: el motor pasó de
"fabrica PnL ficticio con signo equivocado" a "reproduce las decisiones pero no el
reparto exacto de cupos".

### Qué research soporta el replay reparado (PARTIAL)

**SÍ puede usarse para:**

1. **Preguntas de lógica / dirección**: ¿un filtro nuevo cambia *qué* candidatos
   pasan el stack de vetos? ¿una fuente de señal produce más/menos setups válidos?
   ¿un régimen de BTC dado bloquea más LONGs? — la lógica de decisión es fiel.
2. **Análisis de exposición y régimen agregado**: cuántos trades, en qué
   condiciones de mercado, con qué distribución de símbolos/lado.
3. **Detección de que una señal NO tiene efecto**: si una fuente no cambia el
   conjunto de candidatos válidos ni el PnL agregado ni con el timeline actual,
   es señal robusta de que no aporta (el sesgo del motor es *optimista*, así que
   un "no aporta" es conservador).
4. **Sanidad de vetos**: confirmar que un veto nuevo no rompe el stack.

**NO puede usarse para:**

1. **Afirmar PnL / PF / expectancy precisos.** El PF agregado sigue optimista en
   +0.43 y el PnL por-trade correlaciona r=0.52 con el real.
2. **"La estrategia X hace $N/mes"** o rankear estrategias por PnL de backtest.
3. **Convertir un alpha confirmado en estrategia y confiar en su PF backtesteado.**
   Para eso hace falta Phase 2.
4. **Cualquier conclusión sobre familias de stop ajustado** (FVG, OrderBlock,
   scalping) — la resolución intrabar TP-primero no está cuantificada para ellas.

### Phase 2 (requisito para llegar a PASS)

1. **Timeline de ocupación de cupos**: replay con la cadencia real del escáner
   (un solo reloj, latencia de ciclo, orden de evaluación de estrategias) — idealmente
   simulando las estrategias que comparten `has_traded_symbol_today` en el mismo reloj.
2. **Cobertura**: intentar backfill de los 22 símbolos UNREPLAYABLE desde fuentes
   alternativas; los que no existan, excluir formalmente del universo de todo backtest.
3. **Intrabar TP/SL para stop ajustado**: cuantificar el sesgo optimista en FVG/OrderBlock
   (vela de 5 m que toca TP y SL) o bajar a vela de 1 m para esas familias.
4. **Funding**: completar `funding_rates` para todo el período o declarar el rango
   con cobertura suficiente.

### Estado del research de alpha (sin cambios)

- OI collector sigue corriendo.
- H11 congelado hasta su gate (≥70 días OI + ≥20 símbolos + ≥90 % cobertura).
- H12 = FAILED, cerrado. Sin H13. Sin nuevas estrategias.
- **Prioridad**: (1) Phase 2 del replay → (2) OI acumulando → (3) H11 cuando cumpla
  gate → (4) recién entonces convertir un alpha confirmado en estrategia.
