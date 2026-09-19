# GOLDEN STANDARD — ¿el backtester representa el SISTEMA ACTUAL?

**Fecha:** 2026-09-06
**Benchmark:** MA Slope Caso 3 (evidencia de señal potencialmente fuerte).
**Pregunta:** NO "¿qué timeout hace coincidir el backtest con REAL?" sino
**"¿el backtester actual representa correctamente las reglas actuales de
producción?"**
**Regla global impuesta:** `NO ARTIFICIAL TIMEOUT`. Una operación vive hasta TP
o SL. Si no toca ninguno antes del fin del dataset → `OPEN / CENSORED`, jamás
pérdida por agotarse los datos.
**Sin optimizar. Sin tocar parámetros de Caso 3. Sin H13. Sin estrategias
nuevas.**

Scripts: `agent/backtest/golden_caso3.py` (replay sin timeout + censurado),
`agent/backtest/phase_slot_causal.py` (precompute cacheado, config real).

---

## VEREDICTO: **PARTIAL**

Se corrigió lo importante (el replay ya no inyecta timeout; censurados nunca son
pérdida; SL/TP/fees/funding/sizing/slots = código de producción). Pero quedan
**divergencias estructurales conocidas y materiales**, y una de ellas mueve a
Caso 3 entre "ganadora" y "perdedora".

**Hallazgo colateral crítico:** con el timeout correctamente removido, el edge de
Caso 3 **NO sobrevive de forma robusta** la competencia causal por 3 cupos
(sección 4). El PF 1.70 del análisis anterior dependía del cierre artificial a
48 h.

---

## 1. Sistema ACTUAL de producción — auditoría del código

### Apertura, entry, SL, TP (`verge_agent.py::_evaluate_ma_geometry_profile` + `risk_manager.py::_calculate_position_nexus_style`)

| Componente | Regla actual (código) |
|---|---|
| **Apertura** | escaneo cada 5 min (`LOOP_INTERVAL_SECONDS=300`); por perfil MaGeometry, evalúa `PatternParamsJson` sobre todo el watchlist en su timeframe (Caso 3 = 1h). `source = ma_pattern:{profile_id}`, `ma_slope_mode=True` (inyección directa, bypass del matching genérico). |
| **Entry** | `price_at_signal = geo["current_price"]` — **precio vivo al momento del escaneo**. Margen fijo **$150**, leverage **1x** (`DEFAULT_LEVERAGE=1`), `qty = 150 / entry`, nocional $150. Sin slippage. |
| **SL** | estructural: `max(highs[-10:]) * (1 + slBufferPct/100)` = `recentHigh × 1.01` (SHORT). Campo `custom_sl_price`. `sl_dist = |entry − SL|`. |
| **TP** | `rr_target = profile.tpMultiplier (3.0)`, **pero se capa**: `confluence_score = minConfluenceScore = 80` ⇒ `setup_type="Trend Following"` (`>60`) ⇒ `rr_target = min(3.0, TP_MULT_TREND_FOLLOWING_MAX=2.5) = 2.5`. Luego `tp_dist = 2.5 × sl_dist`, y **piso** `min_tp_pct` = 10%: `tp_dist = max(tp_dist, 0.10 × entry)`. En la práctica el piso del 10% domina (por eso 0/2615 disparos tienen RR<4). |

### Salidas — dos rutas, y NO coinciden entre sí

| Ruta | Cierra por | ¿Timeout? |
|---|---|---|
| **`.NET SimulationMarkPriceWorker`** (tick de mark-price cada **1 s**, ejecutor autoritativo del bracket) | `tp_hit`, `sl_hit` (clamp exacto a `TpPrice`/`SlPrice`), `liquidated` | **NO. Ninguno.** |
| **Monitor del agente Python** (loop de 5 min, `verge_agent.py:6440-6545`) | re-chequea TP/SL, **+ `zombie_timeout`** (`candles_open = seconds_open/900 ≥ maxTradeDurationCandles` **y** `pnl_pct < 0` → cierra; si PnL ≥ 0 "se deja correr"), **+ `Max duration exceeded`** (`hours_open ≥ MAX_POSITION_DURATION_HOURS = 720` → cierra incondicional) | **SÍ: zombie + 720 h.** Solo se saltan si `is_diamond` (Golden U-Turn / TOTAL-SWEEP). **Caso 3 NO es diamond → ambos aplican.** |

### ¿Existe actualmente algún timeout automático?

**En el código commiteado (HEAD `4a50492`): SÍ.** El monitor Python de producción
cierra posiciones de Caso 3 por `zombie_timeout` (a `maxTradeDurationCandles ×
15 min` cuando pierden) y por `Max duration exceeded` (720 h).

**En el ejecutor autoritativo .NET: NO.** Solo TP/SL/liquidación.

**→ La premisa "la versión ACTUAL ya NO utiliza ningún cierre por timeout" NO
está reflejada en el código de producción.** Está reflejada solo en el worker
.NET. Si la intención es `NO ARTIFICIAL TIMEOUT`, hay que **alinear
`verge_agent.py:6505-6545`** (quitar los bloques `zombie_timeout` y `Max
duration exceeded` para los no-diamond, o marcarlos legacy).

**Documentado como regla global del motor (objetivo):** `NO ARTIFICIAL TIMEOUT`.
**Estado del código:** DIVERGENCIA ABIERTA — el monitor Python todavía la tiene.

### Fees / funding (`TradingSimulationService.cs`)

- **Fees:** `TakerFeeRate = 0.0004` (0.04%) sobre nocional, entry **y** exit.
- **Funding:** `FundingRate = 0.0001` (0.01%) **plano**, cada 8 h de reloj
  (`_lastFundingTime` global), **siempre pagado** por la posición sin importar
  el lado. NO es funding histórico real, NO es sign-aware.

### Competencia por los 3 slots (`verge_agent.py:2387-2420`)

- `p_max_pos = profile.maxOpenPositions` (default `MAX_OPEN_POSITIONS = 3`).
  Cada perfil es dueño exclusivo de sus candidatos — Caso 3 compite por SUS 3
  cupos, no contra otras estrategias por el mismo cupo.
- Por ciclo de 5 min, por perfil: si `active_count ≥ p_max_pos` → `[LIMIT]
  Profile full. Skipping` (salvo VIP Golden/TOTAL-SWEEP en cola — no aplica a
  Caso 3). **No hay cola de señales pendientes.**
- Si hay cupo: candidatos ordenados por `confluence_score ×
  bucket_calibrator.get_multiplier(profile_id, score)`; se intenta el top-N
  (`AGENT_MAX_CANDIDATES_PER_CYCLE`), entra el primero que pasa `_execute_trade`.
- **Para Caso 3 el `confluence_score` es constante (80)** → el orden se
  degrada a orden de escaneo del watchlist (≈ arbitrario / no reconstruible sin
  el log del scanner).
- **3/3 lleno:** el candidato se descarta ese ciclo; se re-evalúa de cero en el
  siguiente (sin memoria).

---

## 2. Lógica zombie en el backtester — LEGACY / INVALID FOR CURRENT BACKTEST

`agent/backtest/engine.py`:
- `zombie_timeout_decision(open_ms, now_ms, max_candles, pnl_pct_now)` —
  `ZOMBIE_CANDLE_MS = 15 min` fijo, `MAX_POSITION_DURATION_HOURS = 720`.
  Cierra a `max_candles × 15 min` si `pnl < 0`; tope duro 720 h.
- Usado por `_run_generic`, `run_ma_geometry*`, **`ma_slot_sim`** (el que corrió
  Gate V4), `_capital_sim`.

**Es una réplica exacta del monitor Python de producción** — pero NO del sistema
objetivo (sin timeout) ni del ejecutor .NET.

**Decisión aplicada:** para el backtest del sistema actual **NO se usa**. No se
ajusta, no se elige otro valor (48/72/192/209/720 h), no se busca el que
maximice PF. En `golden_caso3.py` está **deshabilitada**: solo `tp_hit` /
`sl_hit`, y lo que no resuelve queda `OPEN_CENSORED`.

**Marca:** `zombie_timeout_decision` y todo `*_timeout` / `48h` / `192h` / `720h`
en el motor = **LEGACY. INVÁLIDO para el backtest del sistema actual.** Mantener
en el código solo si/ cuando el monitor Python de producción también lo tenga;
hoy hay que mantenerlo OFF explícitamente en cualquier corrida de evaluación.

---

## 3. REAL histórico vs reglas actuales vs backtester

| | A. Comportamiento histórico REAL | B. Reglas ACTUALES de producción | C. Reglas ACTUALES del backtester |
|---|---|---|---|
| Salida por tiempo | **SÍ** — 27/45 trades cerrados por timeout (`real_outcome=TIMEOUT`), cluster en 48.0–48.3 h + cola a 209 h. Corrieron bajo una versión con cierre a `maxTradeDurationCandles`. | **Objetivo: NINGUNA.** Código: zombie + 720 h todavía en el monitor Python. | `zombie_timeout_decision` presente pero **deshabilitado** en el golden replay. |
| Entry | precio vivo | precio vivo | close de vela de señal (≤1 vela de staleness) |
| Intrabar | mark-price 1 s | mark-price 1 s | vela 5 m, TP antes que SL |

**A y B/C difieren porque el sistema (o su intención) cambió.** Se documenta.
**NO se modifica B ni C para reproducir A.** Los cierres por timeout del
histórico **no** se tratan como regla válida del sistema actual.

---

## 4. GOLDEN REPLAY de Caso 3 — sin timeout, censurados aparte

Sizing: $450/estrategia, $150/trade, máx 3 simultáneas. Ventana klines
2026-07-10 → 2026-08-23. Señales reales usadas **solo como diagnóstico**.

| Variante | cerrados | net ($450) | PF | WR | maxDD | tp/sl | dur med/máx (h) | **censurados** |
|---|---|---|---|---|---|---|---|---|
| **A. REAL histórico** (trades.csv, reglas viejas c/ timeout) | 45 | +$64.7 | **2.54** | 49% | — | 11/7 | 30 / 209 | (27 cerrados por timeout en la versión vieja) |
| **B. señales reales + lifecycle ACTUAL** (sin slots, sin timeout) | 35 | +$45.9 | **1.81** | 49% | −$16.4 | 17/18 | 22 / 704 | **10** (dur 118–982 h, MTM Σ −$9.5 ≈ break-even) |
| **C. lifecycle ACTUAL + competencia causal 3 cupos** — orden escaneo/símbolo | 24 | +$20.1 | **1.38** | 21% | −$28.7 | 5/19 | 44 / 547 | 3 (dur 160–233 h, MTM +$19.2) |
| C — desempate **aleatorio** ×20 seeds | ~24 | P5 −$70 / P50 −$18 / P95 +$9 | P50 **0.59** | ~15% | — | — | — | **5/20 seeds net-positivos** |
| C — desempate aleatorio + competencia entre-estrategias (`occupied`) | 19 | −$36.1 | **0.29** | 5% | −$50.6 | 1/18 | 6 / 636 | 3 |

Concurrencia máxima verificada: **3 / 3** (nunca supera el cap).

### Lectura

1. **B (lifecycle actual sobre las señales reales, sin competir por cupo):** PF
   **1.81**, WR 49%, net +$46. Al quitar el timeout, los trades que producción
   cerraba a 48 h ahora corren: **TP/SL pasa de 11/7 a 17/18** — la mitad de los
   que antes se cerraban en pequeña pérdida/ganancia ahora llegan al SL. El
   lifecycle sigue siendo ganador sobre las señales reales, pero **más débil**
   que el histórico (2.54 → 1.81).
2. **C (competir causalmente por 3 cupos, pool completo de 2615 disparos):** el
   edge **se degrada fuerte**. Determinista (orden de escaneo): PF 1.38 pero
   **WR 21%** — sostenido por pocos TP al 10%. Aleatorio: **PF mediana 0.59, 5/20
   seeds positivos** → moneda al aire hacia el lado perdedor. Con competencia
   entre-estrategias: **PF 0.29, claramente perdedor.**
3. **Censurados:** 3–10 trades quedan `OPEN` al fin del dataset (dur observada
   118–982 h). Su MTM informativo es ≈ break-even (B: −$9.5 en 10; C: +$19.2 en
   3). **No se convierten en pérdida.** Confirma que son genuinamente no
   resueltos, no perdedores ocultos.
4. **La premisa "Caso 3 contiene una señal potencialmente fuerte" se debilita**
   una vez que la estrategia juega bajo las reglas actuales (sin timeout) y
   compite causalmente por sus 3 cupos. El PF 1.70 reportado antes
   (`CASO3_SLOT_CAUSAL_REPORT.md`) **dependía del cierre artificial a 48 h**, que
   bookeaba como ganancia/pérdida chica lo que sin timeout llega al SL.

---

## 5. Operaciones censuradas — detalle

Nunca cerradas por tiempo. Reportadas como `OPEN_CENSORED` con duración
observada y MTM informativo (no realizado).

| Política | cerrados | censurados | dur censurados (h) | MTM censurados (informativo) |
|---|---|---|---|---|
| B (señales reales) | 35 | 10 | 118 / 151 / 182 / 287 / 695 / 728 / 730 / 933 / 960 / 982 | −1.9…+1.3, **Σ −$9.5** (≈ break-even) |
| C.scan | 24 | 3 | 160 / 199 / 233 | todos verdes, **Σ +$19.2** |

Las duraciones > 720 h en B son artefacto de que producción **sí** las habría
cerrado a 720 h por `Max duration exceeded` (código actual) — otro punto donde
"objetivo sin timeout" ≠ "código actual".

---

## 6. TABLA FINAL — Componente | Producción actual | Backtester actual | ¿Coinciden? | Problema

| Componente | Producción actual | Backtester (`engine.py` / `golden_caso3.py`) | Coinciden | Problema |
|---|---|---|---|---|
| **Entry** | precio vivo al escanear (`price_at_signal`) | close de la vela de señal (1 h) | ~PARCIAL | staleness ≤ 1 vela; ninguno modela slippage |
| **SL** | `max(highs[-10:]) × 1.01` (recentHigh estructural) | idéntico (misma función real en precompute) | **SÍ** | — |
| **TP** | `entry − max(2.5 × SLdist, 10% × entry)` (rr cap 2.5 + piso 10%) | idéntico (misma función real) | **SÍ** | — |
| **Exits** | `tp_hit` / `sl_hit` / `liquidated` (worker .NET, 1 s) | `tp_hit` / `sl_hit` (5 m); liquidación no modelada (irrelevante a 1x) | ~PARCIAL | resolución 1 s vs 5 m |
| **Timeout** | **objetivo: ninguno.** código: `zombie_timeout` + `Max duration 720 h` (monitor Python) | `zombie_timeout_decision` presente, **deshabilitado** en el golden replay | **NO** | el motor trae la lógica (= código Python, ≠ objetivo); hay que mantenerla OFF y alinear producción |
| **Slot limit** | 3 / estrategia ($450, $150 c/u) | 3 (`maxOpenPositions`) | **SÍ** | — |
| **Slot admission** | por ciclo 5 m: top por `score × calibrador_bucket`; sin cola; 3/3 → descartar | por tick 5 m: `score` constante (80) → orden de escaneo; sin cola | ~PARCIAL | orden de escaneo real no reconstruible (sin log del scanner); `bucket_calibrator` no modelado |
| **Sizing** | $150 margen fijo, 1x, `qty = 150/entry` | idéntico | **SÍ** | — |
| **Capital** | $450 / estrategia, bala fija sin chequeo de saldo | $450 base para DD, sin chequeo de saldo | **SÍ** | — |
| **Intrabar handling** | mark-price 1 s, clamp exacto a `Tp`/`Sl` | vela 5 m; si Tp y Sl en la misma vela → **Tp primero** | **NO** | sesgo optimista del backtester en velas de 5 m (para Caso 3, SL ~1.7% vs TP ~10%, el sesgo es chico pero real) |
| **Datos históricos** | tiempo real (Binance, todos los símbolos) | `klines_5m`; **7 símbolos sin datos**; sin 1 m para altcoins | ~PARCIAL | 15% de trades reales irreproducibles; resolución 5 m |
| **Funding** | flat 0.01 %/8 h del nocional, siempre pagado | idéntico (`0.0001/8h`) | **SÍ** | ambos usan un modelo plano irreal (no histórico, no sign-aware) — coinciden entre sí pero no con la realidad |
| **Fees** | 0.04 % taker entry + exit sobre nocional | idéntico (`0.0004 × 2`) | **SÍ** | — |
| **Slippage** | no modelado | no modelado | **SÍ** (por omisión) | riesgo latente no cuantificado |
| **Censored / open** | N/A (producción no termina) | `OPEN_CENSORED` al fin del dataset; nunca pérdida | N/A | correcto; 3–10 trades censurados (dur 120–980 h) |

---

## 7. Por qué PARTIAL y no GOLD ni FAILED

**No FAILED** — el núcleo del lifecycle coincide con el código de producción:
entry (salvo staleness ≤ 1 vela), SL y TP estructural idénticos (misma función
real), sizing, capital, slots, fees y funding coinciden. El manejo de censurados
es correcto (nunca pérdida).

**No GOLD** — quedan distorsiones estructurales **conocidas y materiales**:
1. **`zombie_timeout_decision` sigue en el motor.** Coincide con el monitor
   Python commiteado pero no con la regla objetivo "sin timeout" ni con el
   worker .NET. Hay que mantenerla OFF a mano en cada evaluación y alinear
   `verge_agent.py`.
2. **Intrabar 5 m con TP-antes-SL** vs mark-price 1 s de producción → sesgo
   optimista.
3. **Orden de admisión de slots no reconstruible** (sin log del scanner;
   `bucket_calibrator` no modelado).
4. **15% de trades reales sin datos + resolución 5 m** (sin 1 m para altcoins).
5. **Funding plano irreal** en ambos lados (coinciden entre sí, no con la
   realidad).

Y el impacto es material: quitar el timeout (correcto) **mueve a Caso 3 de
"ganadora robusta PF 1.70" a "moneda al aire, PF mediana 0.59"** bajo
competencia causal de slots. Un backtester GOLD tiene que poder decidir esto sin
que el resultado dependa de una regla legacy.

---

## 8. Qué falta para llegar a GOLD

1. **Alinear producción con la regla objetivo:** quitar `zombie_timeout` y `Max
   duration exceeded` de `verge_agent.py:6505-6545` para los no-diamond (o
   decidir que sí hay timeout y entonces documentarlo como regla actual). Hoy
   "sistema actual" es ambiguo entre .NET (sin timeout) y Python (con timeout).
2. **Eliminar/inhabilitar `zombie_timeout_decision` del motor por defecto**
   (flag explícito, no comportamiento silencioso).
3. **Intrabar:** 1 m para altcoins (o modelar el orden TP/SL con la regla
   conservadora: SL primero) para eliminar el sesgo optimista.
4. **Log del scanner de producción** (timestamp de detección + orden + score)
   para reconstruir la admisión real de slots en vez de aproximarla.
5. **Backfill de los 7 símbolos** sin klines.
6. Decidir si el funding plano 0.01%/8h es aceptable o hay que usar histórico.

---

## 9. Qué NO sabemos todavía

- Si el deployment real de producción tiene el monitor Python con timeout activo
  o fue parcheado a mano (el código commiteado lo tiene).
- El orden real de admisión de slots entre símbolos simultáneos.
- El `maxTradeDurationCandles` real de Caso 3 en la DB actual (se perdió; la DB
  está reconstruida con aproximaciones).
- Comportamiento fuera de la ventana julio–agosto 2026.
- Impacto del slippage (no modelado) y del funding real (vs el plano).
- Si los 3–10 trades censurados habrían terminado en TP o SL con más datos
  (MTM ≈ break-even sugiere que muchos siguen indecisos).
