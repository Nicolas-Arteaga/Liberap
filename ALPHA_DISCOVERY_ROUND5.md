# VERGE — ALPHA DISCOVERY (ROUND 5)

**Fecha:** 2026-09-09
**Misión (nueva):** descubrir 1–3 estrategias **desde cero** que produzcan
**≥ 150 USDT/mes netos** con **≤ 450 USDT de capital** cada una. Asignación de
capital dinámica; no hace falta usar las 3.
**NO** reparar / retunear / rescatar estrategias legacy (MA Slope Caso 3,
FVG-15m, ARROW-PEAK = `LEGACY / FORENSIC / NON-CANONICAL`). El cambio
`MinConfluenceScore 60→70` del Round 5-operativo ya se aplicó y **no** cuenta
como alpha.
**El research corre independiente de producción** (Docker / `Verge.HttpApi.Host`
/ StrategyProfiles / ejecución de órdenes pueden estar caídos — no bloquean).

Este round **no** necesita encontrar la estrategia todavía. El éxito es dejar
el camino correcto armado: **datos → mecanismo → screening → validación →
economía → estrategia.**

---

## Estado de datos (verificado 2026-09-09)

| Dataset | Profundidad | Símbolos | Ventana | Nota |
|---|---|---|---|---|
| `binance_vision_clean.db / klines_5m,klines_clean` | **8.5 meses** | 450 | 2025-12-01 → **2026-08-17** (CONGELADO) | OHLCV limpio (CDN diario, sin lookahead). No avanza. |
| `taker_flow` (en binance_vision) | 8.5 m | 429 | → 2026-08-17 (CONGELADO) | H12 lo agotó como señal continua. |
| `spot_klines` | 8.5 m | 240 | → 2026-08-17 | H10 lo agotó (= funding). |
| `klines_multi_exchange` | ~8 m | 270 | → 2026-07-26 | H9 lo agotó. |
| `klines.db / klines` (cache del agente) | 1h: 2.3 años; 5m: desde 2026-05 | 858 | → hoy | Calidad media (`is_final`, gaps por restarts). Única fuente OHLCV que cubre post-Ago-17. |
| **`open_interest`** | **36 días** | 283 total, **13 con ≥90% cobertura** | 2026-08-04 → hoy | BTC/ETH/SOL presentes pero solo **7 días** (backfill Round 4). Gate H13 = 70 d + ≥20 sym. |
| **`liquidations_research`** (Round 4) | **0.6 días** | 49 | 2026-09-09 00:31 → hoy | Append-only. Bybit WS. No hay backfill histórico posible. |
| `liquidations` (live cache) | 6 días | 150 | rolling, auto-pruned 7d | microcaps; inservible para H14. |
| `funding_rates` | ~2 meses reales | 499 | 2026-07-07 → hoy (+ filas basura 1970) | 8h. |
| `orderbook_ofi` | **30 días** | 509 | 2026-08-10 → hoy | Snapshot ~cada 8 min. OFI ya agregado. FAILED como filtro (AUC 0.46). |
| opciones / on-chain serio / OI multi-venue | **NO EXISTE** | — | — | Requiere decisión de inversión del usuario. |

**Cuello de botella estructural:** el OHLCV limpio termina el **2026-08-17** y
el OI empieza el **2026-08-04** → solo **~13 días** de overlap de alta calidad
entre precio y posicionamiento. Después de Ago-17 hay que usar `klines.db/klines`
(cache del agente, más ruidoso).

---

## A. ALPHA MAP — clases de mecanismo todavía investigables

Ordenadas por ortogonalidad real respecto de lo ya agotado.

### A1. Forced-flow / positioning (ancladas en Open Interest) — **la única clase con ortogonalidad genuina + datos acumulándose**
- **OI / precio divergence** (4 cuadrantes: longs nuevos / short covering / shorts nuevos / capitulación). → **H13**.
- **Continuación confirmada por OI vs divergente** (trend con OI↑ persiste, sin OI↑ se agota). → ángulo A/D de H13.
- **Evento conjunto OI × taker-flow × precio en extremos** (posicionamiento unilateral frágil). → **H15**.
- **Funding extremo × OI crowdeado** (carry insostenible → desarme). → **H16**.
- **Dinámica de OI en perps jóvenes** (mercado inmaduro, primer deleveraging predecible). → **H20**.

### A2. Cascadas de liquidación — flujo forzado **observable directamente**, sin datos usables aún
- **Cascada → reversión por vacío de liquidez SI ΔOI<0** (deleveraging terminado) **vs continuación SI ΔOI≥0** (todavía hay posición forzable). → **H14** (protocolo congelado).
- **Flush direccional de liquidaciones → squeeze** (subconjunto de H14).
- **OFI en la ventana ±N min del evento de flujo forzado** (de qué lado quedó el vacío). → **H19**.

### A3. Cross-sectional / lead-lag — OHLCV, datos profundos, **prior BAJO** (roza momentum)
- **Shock de BTC → catch-up de alts rezagados** (beta dislocation a 1–4h). → **H18**.
- Dispersión / rotación tras movimientos del índice — mecanismo poco claro, no priorizada.

### A4. Transición de régimen de volatilidad — OHLCV, **prior BAJO**
- **Compresión → expansión con persistencia direccional** en el primer tramo. → **H17**.

### A5. Microestructura (order book / OFI) — 30 d, FAILED como filtro continuo
- Solo tiene sentido **dentro de la ventana de un evento de flujo forzado** (= H19). No como señal standalone.

---

## B. EXHAUSTED CLASSES — científicamente agotadas, **NO repetir**

| Clase | Evidencia del agotamiento |
|---|---|
| **Señales continuas de OHLCV** (indicadores técnicos como entrada) | Grid-search 41.369 configs → 0 pasan robustez. ML ranking / meta-labeling → AUC ~0.52 OOS. H1 Regime Router → peor que router aleatorio. |
| **Cross-sectional relative strength** (H8) | "retorno − mediana" es **rank-idéntico** a momentum absoluto (54/54 celdas, es matemático). Vol-adj empeora OOS. Concentrado. |
| **Cross-exchange convergence** (H9.2) | Efecto REAL, monotónico, broad (37–40/40 símbolos), estable en 3 splits — pero **1–5 bp vs 8–16 bp de costo RT → NO MONETIZABLE**. Cerrado. |
| **Cross-exchange lead/lag sub-segundo** (H9.1) | UNTESTABLE a nuestra resolución (15m). |
| **Basis / premium spot-perp** (H10) | La correlación parcial se explica **100% por funding** al controlarlo. Basis = funding re-medido. Cerrado. |
| **Taker flow / CVD como señal continua** (H12) | 0/27 combos señal×horizonte alcanzan \|partial corr\|≥0.03 en 3 splits. Extremos \|z\|>3 sin signo estable; placebo reproduce el 73% del único efecto grande. Cerrado. |
| **OFI como filtro continuo** | AUC 0.46 (join causal a 4.763 trades reales). Cerrado como filtro. |
| **Funding rate como edge standalone** | AUC 0.539 IS → PF 0.98 OOS. Solo mitigador de pérdidas, no fuente. |
| **El motor de backtest para estimar rentabilidad** | Gate V1→FAILED, V4 (Phase 3)→FAILED. Convierte una ganadora real (Caso 3 PF 1.85) en LOSER (replay 0.81), 29.7% de seeds del lado correcto. **No sirve para rankear estrategias por PnL.** El research nuevo NO debe apoyarse en él. |
| **H13 cuadrantes A, B, D** (este round) | El **placebo temporal (+48h) reproduce** el retorno forward positivo a 12–24h → es drift alcista de la ventana, no efecto de OI. FAILED como señales direccionales. |

**Patrón común de todos los FAILED:** techo de tamaño de efecto AUC ≤ 0.54 /
magnitud ≤ ~2 bp; lo que funciona IS se degrada a ~0 OOS; **todo deriva de
OHLCV de Binance** (o de fuentes que resultaron ser OHLCV re-medido). El cuello
de botella es **falta de información nueva (A)**, no metodología ni costos.

---

## C. CANDIDATE HYPOTHESES — ranking

Dimensiones: plausibilidad económica · datos disponibles ahora · magnitud
esperada · monetizabilidad · riesgo de overfitting.

| Rank | ID | Mecanismo | Plaus. | Datos ahora | Mag. esperada | Monetiz. | OF risk |
|---|---|---|---|---|---|---|---|
| **1** | **H13-C** (refinada) | precio↓ + OI↑ = shorts nuevos agresivos → squeeze de 1–4h | **MED-HIGH** | parcial (36d; gate 70d + falta régimen bajista) | ~56 bp raw / ~32 bp incremental (incierto) | **marginal** a slippage realista | MED |
| **2** | **H14** | cascada de liquidación → reversión si ΔOI<0 (deleveraging hecho) / continuación si ΔOI≥0 | **MED-HIGH** | **NO** (0.6d; necesita 60–90d) | **grande** (las cascadas sobre-extienden) | incierta (edge muy buscado) | MED |
| **3** | **H15** | evento conjunto OI↑ × taker-sell × precio↓ en decil extremo → squeeze | MED | gateado (OI depth) **+ taker-flow no se colecta forward** | ~20 bp | incierta | MED-HIGH (multiple testing) |
| 4 | **H16** | funding extremo + OI en máximo de 72h → carry unwind | LOW-MED | thin (~36d overlap) | chica | pobre | HIGH (cerca de H10) |
| 5 | **H18** | shock de BTC → catch-up de alts rezagados | LOW-MED | **SÍ** (8.5m OHLCV) | (screening — sección D) | ? | HIGH (≈momentum) |
| 6 | **H17** | compresión de vol → expansión con persistencia direccional | LOW | **SÍ** (OHLCV) | ? | ? | HIGH (≈breakout, ya falló en grid) |
| — | H19 | OFI en la ventana del evento | LOW | gateado por H13/H14 | chica | pobre | — |
| — | H20 | OI en perps jóvenes | LOW | thin | ? | pobre (ilíquidos) | HIGH |

**Lectura honesta:** la única familia con ortogonalidad real + datos en camino
es **OI / forced-flow (H13/H14/H15)**. Todo lo evaluable *hoy con datos
profundos* (H18/H17) es OHLCV y arrastra prior bajo — se corre como **screen de
sanidad**: si da algo grande, subir el escepticismo (probable overfitting o
re-descubrir momentum/breakout).

---

## D. FAST SCREENING — resultados (hipótesis evaluables ahora)

Dos hipótesis eran evaluables con datos de hoy: **H13-C** (re-screen barato) y
**H18** (OHLCV profundo). Resultado: H13-C sin cambios (PARK), H18 sin veredicto
(host inestable). H16/H14/H15 **no** son evaluables aún (datos insuficientes).

### D1. H13-C — re-screen con 36 días (script `agent/backtest/h13_pilot.py`)

Re-corrida 2026-09-09 con la ventana de OI a 36 d (33 d → 36 d). **Resultado
prácticamente idéntico al piloto del 2026-09-06** — los 3 días extra no mueven
nada, y el script filtra a símbolos con ≥90% de cobertura sobre TODA la ventana,
así que **los majors (7 d de OI) siguen sin entrar**.

| Cuadrante | h | raw (bp) | CI90 | incr vs matched | placebo | mitades | sym mismo signo |
|---|---|---|---|---|---|---|---|
| **C** (precio↓ OI↑) | **1h** | **+56.3** | **[14.6, 99.6]** | +32.2 **[−4, 70]** | **−24.4** | +64/+47 | **0.71** |
| **C** | **4h** | **+58.6** | **[9.5, 107.1]** | +36.1 [−19, 94] | +10.5 | +88/+22 | **0.71** |
| C | 12h | +3.1 | [−76, 87] | +16.8 | +30.8 | +45/−49 | 0.57 |
| C | 24h | −42.0 | [−150, 58] | −92.5 | +52.6 | +92/−207 | 0.33 |
| A / B / D | 12–24h | +77…+193 | — | (grande) | **≈ igual de grande** | inestable | 0.4–0.7 |

- **A, B, D = FAILED** (el placebo reproduce el efecto → drift de ventana).
- **C a 1–4h = el único hilo vivo**: rebote de ~56–59 bp, IC del raw excluye 0,
  **placebo limpio** (a 1h el placebo es −24 bp, signo opuesto), estable en las
  dos mitades, 71% de símbolos mismo signo. **PERO** el incremental sobre una
  muestra matcheada (misma caída previa, misma vol, sin OI↑) tiene **IC que
  incluye 0** → la parte atribuible al OI (vs mean-reversion pura) es incierta
  (+32 bp). A slippage realista para estos nombres (alt/smallcap, y el trade
  ocurre justo tras un movimiento brusco), **no monetizable con confianza**.
- **btc_down: solo 90 de 1517 eventos** — el régimen bajista donde el squeeze
  debería ser más fuerte casi no existe en la ventana.

**Decisión H13-C: PARK.** Sin cambios respecto del 2026-09-06. Re-evaluar con el
protocolo congelado (`H13_PILOT_REPORT.md §8`) cuando OI ≥ 70 d **y** haya un
tramo bajista real.

### D2. H18 — shock de BTC → catch-up de alts rezagados

Scripts: `agent/backtest/h18_btc_shock_screen.py` (completo) + `h18_fast.py`
(agregación barata). Diseño pre-declarado: shock BTC = `|ret_BTC_1h| ≥ p95`
rolling-30d; por alt, `beta_7d` OLS; `residual = ret_alt(shock) − beta·ret_BTC`;
**LAGGARD** = residual opuesto al shock con `|resid| ≥ 0.5·|beta·ret_BTC|`
(no siguió); **FOLLOWER** = `|resid| ≤ 0.25·|beta·ret_BTC|` (siguió). Forward
1/2/4h en la dirección del shock. Placebo +48h. Costo RT 8bp + slippage {0,2,5}.

**Muestra:** 264 shocks de BTC, 360 alts, **14 270 LAGGARD / 16 692 FOLLOWER**
(~45% de los pares alt-shock "no siguen" ⇒ "laggard" ≈ ruido normal de beta,
no evento informativo).

| h | LAGGARD fwd [P5, mean, P95] bp | FOLLOWER mean | placebo | half0/half1 |
|---|---|---|---|---|
| **1h** | **[3.4, +6.2, 9.0]** | −14.9 | −11.0 | +10.3 / +1.9 |
| **2h** | [−6.8, −2.8, 1.4] | −24.5 | −8.5 | −1.3 / −4.2 |
| **4h** | [−19.5, **−13.3**, −6.6] | −25.7 | −2.2 | −5.6 / −21.2 |

**VEREDICTO: FAILED.**
- El único horizonte con laggard > 0 es 1h (+6.2 bp), **3× por debajo del piso
  de costos (~16 bp)**, y se apaga: a 4h el laggard va **−13 bp CONTRA** la
  dirección del shock. **No hay catch-up persistente.**
- El "incr vs follower" (+21 bp a 1h) es un artefacto: los followers revierten
  fuerte (−15 a −26 bp), así que la diferencia es por la reversión del
  follower, no por el catch-up del laggard.
- half0/half1 cambian de signo a 2h/4h → inestable entre períodos.
- Regla PROMISING pre-declarada (laggard CI>0 ∧ placebo<40% ∧ raw≥16 bp ∧ mismo
  signo en las 2 mitades): **no la cumple ningún horizonte.**
- **Confirma el agotamiento de OHLCV.** Cerrado.

---

## E. FAILED HYPOTHESES (este round)

- **H13 cuadrantes A / B / D** — el placebo temporal (+48h) reproduce el
  retorno forward positivo a 12–24h. No es efecto de OI, es drift alcista de la
  ventana. **FAILED como señales direccionales.** El ángulo "confirmación por
  OI" queda abierto **solo dentro del cuadrante C**.
- **H18 (shock de BTC → catch-up de alts) — FAILED.** 14 270 eventos laggard /
  264 shocks / 8.5 m. Laggard forward: +6.2 bp @1h (3× < costo), −2.8 @2h,
  **−13.3 @4h (contra la dirección)**. Sin persistencia, inestable entre
  mitades, no supera costos. El "edge vs follower" es la reversión del follower,
  no catch-up. **Cerrado — confirma agotamiento de OHLCV.**
- H17 (transición de régimen de vol) — **NOT RUN.** Prior LOW; tras el FAILED
  limpio de H18, el slot de "sanidad OHLCV" pasa a **diseñar la colección
  forward de taker-flow para H15** (mejor expected value que otro screen OHLCV).

---

## F. PROMISING HYPOTHESES — justifican investigación profunda

Ninguna hipótesis está hoy en estado "PROMISING" con evidencia positiva. Lo
que hay son **dos hilos vivos-pero-gateados** que merecen la inversión de
seguir esperando/colectando datos:

1. **H13-C** (precio↓ + OI↑ → squeeze 1–4h). PARK. Es el único mecanismo con
   señal cruda **limpia de placebo** + estabilidad entre mitades + 71% de
   símbolos con el mismo signo. Débil hoy (incremental IC cruza 0), pero es la
   mejor pista que produjo todo el research. Gate: OI ≥ 70 d + régimen bajista.
2. **H14** (cascada de liquidación → reversión si el OI ya cayó). PARK. La
   **más plausible económicamente** — evento de flujo forzado observable
   directamente — pero **cero datos usables** (0.6 d). El trabajo real hoy es
   asegurar que se colecte (§H #1).

**Honestidad:** después de H1–H18, el proyecto NO tiene una fuente de alpha
demostrada. Tiene un mapa claro de dónde NO mirar (OHLCV y todo lo derivado) y
dos apuestas gateadas por datos en el plano de posicionamiento/forced-flow. El
Round 5 deja eso explícito y ordenado; no fabrica una estrategia.

---

## G. DATA REQUIREMENTS por hipótesis prometedora

| Hipótesis | Dataset | Período requerido | Cobertura | Disponible | Limitaciones |
|---|---|---|---|---|---|
| **H13-C (test formal)** | `open_interest` + `klines.db/klines 1h` | **≥ 70 d**, ≥ 20 símbolos con ≥ 90% cobertura, **≥ 1 tramo bajista de mercado** | hoy 36 d / 13 sym ≥90% | **~2026-10-13** para 70 d; ≥20 sym ≥90% depende de que el colector mantenga el universo de 63 estable → realista **mediados de octubre**. Majors tienen solo 7 d. | OHLCV post-Ago-17 es el cache del agente (ruidoso). El régimen bajista no se puede forzar — hay que esperar a que el mercado lo dé. |
| **H14** | `liquidations_research` + `open_interest` + OHLCV | **≥ 60 d** continuos, ≥ 100 símbolos, ≥ 90% uptime del colector | hoy **0.6 d** | **≥60 d ≈ 2026-11-08**, **≥90 d ≈ 2026-12-08** — *si* el `liquidation_tracker.py` corre continuo. **Frágil**: es un proceso nohup, muere en reboot, sin Task Scheduler (AUTO-START = UNVERIFIED). | Sin backfill histórico posible (Bybit no da REST). Venue Bybit ≠ OI Binance (mismatch). ¿El feed trae todas las liq o solo grandes? = UNVERIFIED. |
| **H15** | `open_interest` + **taker-flow forward** | ≥ 70 d de overlap OI × taker | overlap actual ~13 d (taker congelado 2026-08-17) | **NO disponible sin acción**: hay que decidir colectar taker-flow hacia adelante (no se colecta hoy). | Multiple-testing alto (evento triple-extremo raro). |
| **H16** | `funding_rates` + `open_interest` | ≥ 90 d de overlap | ~36 d | **≈ 2026-12** | Muy cerca de H10 (que falló). Pocos eventos extremos en 36 d. |
| **H18 / H17** | `klines_5m` (binance_vision) | ya (8.5 m) | 450 sym | **YA** | Prior bajo (OHLCV). Si sobrevive → escepticismo alto. |

---

## ⚠️ Nota de infra descubierta este round (2026-09-09)

Al inspeccionar procesos: **los colectores de research (OI + liquidaciones)
estaban CAÍDOS** desde ~15:30 UTC (mismo momento en que crasheó el agente por
`FATAL: Could not authenticate with ABP Backend`). Último dato: OI 15:30 UTC,
`liquidations_research` 15:36 UTC — ~2.7 h de hueco. **Se relanzaron** (OI PID
15164 con `OI_BACKFILL_DAYS=2`; liq tracker PID 32924). El backfill de la
fuente de OI (Binance retiene ~30 d) tapa el hueco; **el de liquidaciones NO se
recupera** (Bybit sin REST histórico) — se perdieron ~2.7 h de eventos de
liquidación de forma irreversible.

**Causa probable de la caída conjunta:** el agente (`verge_agent.py`) carga
`liquidation_tracker.py` como thread propio; cuando el agente murió, ese thread
murió; y los procesos standalone de Round 4 (`_run_liq_tracker.py` PID 18672,
`open_interest_collector.py` PID 54348) también desaparecieron — reboot del host
o Docker Desktop restart alrededor de las 15:30 UTC. **Confirma que sin Task
Scheduler los colectores no sobreviven** (AUTO-START = UNVERIFIED, Round 4 §5).

---

## H. NEXT RESEARCH QUEUE (máx 3 simultáneas)

1. **[INFRA-GATE — AHORA URGENTE] Asegurar la colección de H14.** Es la
   hipótesis de mayor plausibilidad económica y **cada hora sin colectar es
   irrecuperable** (ya se perdieron ~2.7 h hoy — ver nota arriba). Acciones:
   (a) `research\ops\register_research_tasks.ps1` en **PowerShell elevado** para
   que los colectores sobrevivan reboot (AUTO-START sigue UNVERIFIED); (b) el
   monitor `liquidation_quality_monitor.py` cada 6 h; (c) **desacoplar el
   `liquidation_tracker` del `verge_agent`** — que corra siempre standalone, no
   como thread del agente (si el agente muere, el tracker no debe morir). Sin
   esto, en noviembre descubrimos que perdimos semanas.
2. **H13-C — congelado, esperando datos.** Nada que correr hasta ~2026-10-13.
   Trabajo preparatorio permitido: reescribir `h13_pilot.py` para un
   sub-screen **majors-only** sobre los 7 d de OI de BTC/ETH/SOL (¿el efecto de
   C aparece en nombres líquidos, donde el slippage no lo mata?) — barato,
   informativo, no gastado.
3. **[Slot rotativo] Diseñar la colección forward de taker-flow para H15.**
   H18 ya FAILED (agotamiento OHLCV confirmado otra vez); H17 tiene el mismo
   prior. El expected value del slot está en habilitar H15 (evento conjunto
   OI×taker×precio) — hoy imposible porque `taker_flow` está congelado el
   2026-08-17. Definir un colector de taker-flow que corra hacia adelante en
   paralelo a OI/liquidaciones (fuente: agregación de trades de Binance/Bybit,
   o el archivo diario de data.binance.vision que ya trae taker_buy_volume).

**Regla:** si H13-C y H14 ambas siguen PARK y ningún screening OHLCV sobrevive,
la siguiente acción NO es inventar hipótesis nuevas de OHLCV — es una
**decisión de inversión en datos** (taker-flow forward, liquidaciones pagas de
Coinglass para validar completitud, o exploración de opciones/on-chain). Eso lo
decide el usuario.

---

## Definición de éxito de este round — checklist

| Ítem | Estado |
|---|---|
| Alpha map de clases investigables | ✅ (A) |
| Clases agotadas documentadas | ✅ (B) |
| Hipótesis candidatas rankeadas | ✅ (C) |
| Screening barato de lo evaluable ahora | H13-C ✅ (PARK, sin cambios) · H18 ✅ **FAILED** (sin catch-up monetizable) |
| Failed documentadas | ✅ (E) |
| Promising acotadas | ✅ (F) |
| Data requirements por hipótesis | ✅ (G) |
| Cola priorizada ≤ 3 | ✅ (H) |
| Sistema orientado a FIND NEW ALPHA FROM ZERO | ✅ — legacy congelado, research desacoplado de producción |
