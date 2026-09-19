# VERGE — ALPHA HUNT ROUND 7 — BREAK THE SEARCH SPACE

**Fecha:** 2026-09-10
**Objetivo (sin cambios):** 1–3 estrategias NUEVAS, ≥150 USDT/mes netos, ≤450 USDT
de capital por estrategia. Legacy (MA Slope Caso 3 / FVG-15m / ARROW-PEAK) NO es
la solución y no se toca.
**Metodología de este round:** dejar de derivar familias del mismo plano
(OHLCV + taker). Buscar **mecanismos** con estructura *evento → participante
obligado → desequilibrio → reacción monetizable*, priorizando eventos discretos
y estructurales. Ranking por **expected monetizable alpha**, no por
significancia estadística.

---

## 1. CURRENT STATE — qué sabemos de verdad tras H1–H26 + Round 7

| Plano de datos | Estado | Evidencia |
|---|---|---|
| OHLCV continuo (señales, router, grid, ML) | **AGOTADO** | grid 41k configs, ML AUC 0.52 OOS, H1 |
| Momentum / relative strength cross-sectional | **AGOTADO** | H8 = momentum (idéntico matemáticamente) |
| Cross-exchange (lead-lag / convergencia) | **AGOTADO** | H9.1 untestable @15m; H9.2 real pero 1–5 bp < 16 bp costo |
| Basis / funding como filtro continuo | **AGOTADO** | H10 = funding re-medido; funding standalone AUC 0.539 → PF 0.98 OOS |
| Taker / CVD (continuo, extremos, ventana, 1-bar) | **AGOTADO** | H12 (0/27), H22 (lookahead), **R7-M10 absorción 1-bar FAILED** |
| BTC shock → alts (1h catch-up; sub-15m lead-lag) | **AGOTADO** | H18 FAILED; **R7-M11 sub-15m FAILED** (efecto real ~4 bp = beta, no lead-lag) |
| Funding como **evento discreto** (extremo; flip de signo) | **R7 nuevo** | M8a FAILED (placebo reproduce); **M8b PARK** (hint @24h, datos 38 d) |
| Perp de acción tokenizada vs apertura cash US | **R7 nuevo — LEAD VIVO** | **M18 PARK**: reversión +10 bp @30–60 m, placebo-limpia, escala con el gap; < 16 bp costo |
| Listings como forced-flow estructural | **R7 nuevo — PARK datos** | M1: el dataset no identifica listings limpios (artefactos de colección) |
| OI / precio divergence (squeeze) — H13-C | **PARK datos** | señal cruda limpia de placebo; OI a 36 d (gate 70 d ~2026-10-13) |
| Cascada de liquidación → reversión/continuación — H14 | **PARK datos** | `liquidations_research` ~1.5 d (gate 60 d ~2026-11-09) |
| Evento conjunto OI↑×taker-sell×precio↓ — H15 | **PARK datos** | necesita OI depth + taker-flow forward |

**Conclusión honesta:** los 3 planos *locales continuos* (precio, flujo taker,
funding/basis) no tienen alpha monetizable, ni como señal continua ni como
interacción condicional (Round 6) ni como evento discreto simple (Round 7). Lo
único que sigue produciendo estructura son:
- **eventos con reloj de exchange / mercado externo** (M18 apertura cash US),
- **forced-flow con datos que aún se están acumulando** (H13-C, H14, H15).

No es "no hay alpha". Es "el alpha, si existe, está en un plano de datos que
todavía no tenemos con profundidad, o en eventos estructurales que recién
empezamos a mirar en este round".

---

## 2. EXHAUSTED SEARCH SPACE — qué NO volver a investigar

**Prohibido re-testear sin un mecanismo causal nuevo y su propio ID:**

1. Cualquier señal **continua** sobre OHLCV (MA/RSI/MACD/BB/momentum/breakout/
   vol-target/…), sola o en combinación, con o sin grid.
2. Momentum / relative-strength cross-sectional (= H8).
3. Cross-exchange lead-lag o convergencia como fuente de alpha (H9).
4. Funding / basis como **filtro o score continuo** (H10, H16-continuo).
5. Taker imbalance / CVD: continuo (H12), en extremos |z|>3 (H12), como
   divergencia en ventana (H22), como absorción de 1 barra (**R7-M10**).
6. BTC shock → reacción de alts: catch-up a 1–4 h (H18), lead-lag a 5–30 min
   (**R7-M11**). El efecto sub-15m existe (~4 bp) pero es **beta de mercado
   continuando**, no lead-lag, y es 4× menor que la fricción.
7. Funding **extremo** como señal de exhaustion/reversión (**R7-M8a**): el
   placebo y el matched-control lo reproducen — es drift de régimen.
8. El **motor de backtest** para estimar rentabilidad de estrategias nuevas
   (Gate V4 FAILED — sesgo sistemático que deprime resultados).
9. H13 cuadrantes A/B/D (placebo +48 h reproduce el drift).

**Regla de escepticismo (confirmada 2× este proyecto):** si un screen sobre
estos datos da un efecto "grande" (>50 bp, >+1000 en un ratio), asumir
**lookahead o artefacto de sign-convention × régimen** hasta probar lo
contrario. Round 6 = lookahead en H22. Round 7 = sign-convention × bull-drift en
M8a.

---

## 3. NEW DATA SOURCES — fuentes gratuitas razonables (inventario)

Restricción dura: **NO se puede pegar a `api.binance.com` / `fapi.binance.com`**
desde este entorno (IP compartida con el agente live, ban real 2026-07-12). Todo
lo de abajo evita la API REST de trading.

| Dataset | Histórico | Cobertura | Resolución | Gratis | Backfillable | Mecanismo potencial | Estado |
|---|---|---|---|---|---|---|---|
| **data.binance.vision** `futures/um/daily/metrics/` | ~2 años | ~todos los perps UM | 5 m (OI, long/short acct ratio, taker ratio) | Sí (CDN, no API) | **Sí** (archivos diarios) | **desbloquea OI histórico** para H13-C/H15 sin esperar a octubre | **NO verificado — prioridad 1** |
| data.binance.vision `futures/um/monthly/fundingRate/` | ~2 años | todos los perps | 8 h | Sí (CDN) | **Sí** | **desbloquea M8b** (funding history ≥90 d hoy mismo) | **NO verificado — prioridad 1** |
| data.binance.vision `futures/um/daily/bookDepth/` | ~2 años | perps principales | snapshots | Sí (CDN) | Sí | profundidad de libro real (vs OFI 8-min actual) para H19 / vacío de liquidez | NO verificado |
| Binance **Announcements** (web pública, no API) | archivada | listings / delistings / maintenance / margin changes | evento con fecha | Sí (WebFetch) | Sí (scrape) | **desbloquea M1** (listing dates verificados), M2 (delisting run-in), maintenance halt | NO ingerido — prioridad 2 |
| **Token unlock calendars** (DefiLlama `/unlocks`, token.unlocks) | forward + hist | ~300 tokens grandes | evento con fecha/hora | Sí (API/scrape) | Sí | **oferta forzada**: cliff/linear unlock → presión vendedora anticipable, ventana estructural | NO ingerido — prioridad 2 |
| **DefiLlama** stablecoins / CEX netflows / TVL | ~3 años | agregado + por chain | diario | Sí (API generosa) | Sí | mint/burn de stablecoins = risk-on/off market-wide; CEX netflow = presión | NO ingerido |
| Farside / spot-ETF flow CSVs (BTC, ETH) | desde 2024/25 | BTC, ETH | diario | Sí (CSV) | Sí | creación/redención diaria de ETF = flujo obligado con timestamp | NO ingerido |
| Bybit `public.bybit.com` / OKX archives | ~2 años | cross-venue klines, algunos liq | 1 m / tick | Sí (CDN) | Sí | liquidaciones cross-venue (Binance forceOrder muerto), confirmación de cascadas | NO ingerido |
| CoinGecko / CMC free API | — | `date_added`, market cap, categorías | — | Sí (rate-limited) | Sí | listing dates alternativos + mapa de sector para M1/M16 | NO ingerido |
| US market calendar (pandas-market-calendars / FRED) | décadas | NYSE/NASDAQ | día | Sí | Sí | días hábiles + half-days + holidays para M18 (hoy asumido "todos los weekday = RTH") | NO ingerido |
| `whale_events` (ya en klines.db) | **2 d** | BTC on-chain + 50 ERC20 | evento | — | **No** (real-time) | exchange inflow → sell pressure | acumulando; **acoplado al agente (muerto)** |

**Lo más accionable sin esperar a nada:** verificar `data.binance.vision/metrics`
y `/fundingRate` — si el backfill funciona, **H13-C, H15 y M8b dejan de estar
gateadas por tiempo**. Es la palanca de mayor impacto del inventario.

---

## 4. MECHANISM UNIVERSE — 20 hipótesis (mecanismo, no indicador)

Formato corto: **actor obligado / catalizador / variable observable / predicción
/ horizonte / efecto y frecuencia esperados / falsificación.**

### Exchange mechanics / estructural

- **M1 — Listing forced-flow reversion.** Actor: productos índice/copy-trading
  que deben añadir el constituyente + FOMO retail. Catalizador: listing del perp.
  Variable: barras desde el primer kline. Predicción: pump inicial → underperf.
  multi-día. Horizonte: días 1–7. Efecto: grande (moves 30–100%), frec. baja
  (~15–25/mes en teoría). Falsif.: retorno post-listing ≈ matched no-listing.
  → **RAN → PARK (datos: el dataset no identifica el evento, ver §7).**
- **M2 — Delisting run-in.** Actor: holders forzados a cerrar antes del
  settlement forzado + productos índice que deben salir. Catalizador: anuncio de
  delisting (~1 semana antes). Predicción: underperf. severa en los N días
  previos al último kline. Falsif.: es selección mecánica (se deslista porque
  murió), no tradeable ex-ante sin la fecha de anuncio. → **PARK (sin fechas de
  anuncio; sesgo de selección).**
- **M3 — First-funding-settlement extremity en perps nuevos.** Actor: falta de
  arbitrajistas en las primeras horas. Catalizador: primeros 3–5 settlements de
  un perp recién listado. Predicción: funding extremo + mean-reversion violenta.
  → **PARK (necesita listing dates + overlap con funding).**
- **M4 — Index/basket rebalance (constituent add/drop).** Actor: fondos índice.
  Sin dataset estructurado. → **PARK.**
- **M5 — Funding schedule change (8h→4h / cap change).** Actor: carry traders
  recalibrando. Sin dataset. → **PARK.**

### Forced positioning / crowding

- **M6 — Funding extremo = carry crowdeado → unwind contra el lado que paga.**
  Actor: el lado que paga funding caro. Catalizador: |funding| en decil extremo
  en el settlement. Predicción: fwd 8–24 h **contra** el lado que paga
  (exhaustion). Horizonte 8–24 h. → **RAN como M8a → FAILED** (placebo y matched
  reproducen; es drift de un mercado alcista bajo convención short).
- **M7 — Funding sign-flip = cambio de régimen de posicionamiento.** Actor:
  el lado que empieza a dominar/pagar. Catalizador: funding cruza de + a − (o
  viceversa) entre settlements. Predicción: continuación en la dirección del
  nuevo signo, 8–24 h. → **RAN como M8b → PARK** (hint @24 h: +48 bp bruto /
  +32 bp tras costo, pero placebo +48 h da +24 bp = se come la mitad; decae
  entre mitades; sólo 38 d de datos).
- **M8 — OI en máx local + precio estancado → deleveraging.** = familia H13.
  → **PARK datos** (OI 36 d; gate 70 d ~2026-10-13).
- **M9 — Cluster de liquidación + caída de OI → reversión por vacío.** = H14.
  → **PARK datos** (`liquidations_research` 1.5 d).

### Liquidity events / absorción

- **M10 — Absorción de 1 barra: flujo taker masivo unilateral + precio ~0.**
  Actor: pasivo grande (iceberg / MM con inventario / vendedor institucional).
  Catalizador: `z(taker_buy_frac)` ≥ ±2 con `|barret|` ≤ 0.35× su media rolling.
  Predicción (2 rivales): informed (continúa en la dirección del pasivo) vs
  release (rebota al agotarse el pasivo). Horizonte 15–120 min. → **RAN →
  FAILED** (efecto 1–3 bp << 16 bp; matched-control "flujo que SÍ movió" domina;
  quiet-only reproduce; symPos < 0.5).
- **M11 — BTC 5m shock → catch-up de alts rezagados en 5–30 min.** Actor:
  latencia mecánica (motor de liq, MMs recotizando, bots perp-perp).
  Catalizador: `|z(bret_5m)|` ≥ 3. Variable: residual del alt vs su beta 7 d.
  Predicción: el alt rezagado hace catch-up hacia BTC. → **RAN → FAILED**
  (efecto real +4 bp @5m pero `uncond` ≈ `real` → es beta continuando, no
  lead-lag; 4× < costo; decae a 15 min).
- **M12 — Overreacción en hora de baja liquidez → reversión en la próxima
  ventana líquida.** Actor: MMs que se retiran → libro fino → un taker
  sobre-extiende. Catalizador: move grande en 02:00–06:00 UTC / fin de semana.
  → **NO run** (prior bajo: el slippage en horas finas se come el efecto;
  screen barato para más adelante).
- **M13 — Stablecoin mint/burn / exchange inflow → risk-on/off market-wide.**
  Actor: emisor de stablecoin + ballenas moviendo a exchange. Catalizador: mint
  grande de USDT/USDC o inflow on-chain. → **PARK** (`whale_events` 2 d,
  DefiLlama no ingerido).

### Cross-sectional stress

- **M14 — BTC quieto + move idiosincrático grande de un alt → continuación.**
  Actor: el que movió el alt (no es beta, es flujo con razón). Catalizador:
  rv(BTC,1h) en decil bajo + `|aret|` grande. → **NO run** (adversarialmente
  cerca de momentum/H8; prior bajo).
- **M15 — "Reaction-beta" persistente ante shocks comunes.** Actor: estructura
  de microliquidez estable por símbolo. Catalizador: shock común (BTC o
  market-wide). Variable: ranking de over/under-reacción de cada símbolo al
  shock. Predicción: el ranking **persiste** entre shocks → un símbolo que
  siempre sobre-reacciona es shorteable en el próximo shock (y viceversa).
  Horizonte: 1–6 h post-shock. → **NO run este round — prior MEDIO, next-tier**
  (es un factor de dispersión, no un catch-up; genuinamente no testeado).
- **M16 — Co-listing sectorial: N perps de una narrativa listan juntos → la
  cesta se mueve.** → **PARK** (necesita listing dates + mapa de sector).

### Structural event windows

- **M17 — Drift viernes→lunes en perps (sin ancla CME para alts).** → **NO run**
  (prior bajo, conocido, probablemente arbitrado).
- **M18 — Perp de acción tokenizada vs apertura del cash US.** Actor:
  arbitrajista con hedge en la acción real + emisor del token (creación/
  redención). Catalizador: campana de apertura NYSE = 13:30 UTC (EDT).
  Variable: `closed_ret` = move del perp mientras el cash estuvo cerrado.
  Predicción: reversión parcial del `closed_ret` tras la apertura (convergencia
  al fair del subyacente). Horizonte 15–60 min. Efecto esperado: proporcional al
  gap; frec.: ~1/día/símbolo × ~20 símbolos líquidos. → **RAN → PARK / LEAD
  VIVO** (ver §7: +10 bp @30–60 m, placebo-limpio, monótono en tamaño de gap,
  pero < 16 bp costo y concentrado).
- **M19 — Micro-oscilación ±30 min alrededor del settlement de funding, escalada
  por |funding|.** → plegado en el diseño de M8; el horizonte de 8 h dominó; un
  corte de ±30 min no se corrió aparte (prior bajo, muy arbitrado).
- **M20 — Spike mark-vs-index → convergencia.** → **PARK** (sin feed real de
  mark/index).

---

## 5. ECONOMIC RANKING — por Expected Monetizable Alpha

Criterio: `E[net_monthly_pnl] ≈ edge_neto_bp × eventos/mes × capital_efectivo`,
penalizando concentración, decaimiento e incertidumbre de datos. **No** por
p-value.

| Rank | Hip. | Edge bruto (obs./esperado) | Frec. | ¿Puede llegar a 150 USD/mes con ≤450 USDT? | Bloqueo | Acción |
|---|---|---|---|---|---|---|
| 1 | **M18** apertura cash US | **+10 bp @30–60 m (real, placebo-limpio)** | ~20/día hábil | **Quizá** — si la reversión se concentra en los primeros 5–10 min y/o con fee real de estos contratos el neto pasa ~8 bp: 20/día × 21 d × 300 USDT × 0.08% ≈ **$100/mes** por nombre-grupo; con 2–3 grupos, alcanza | costo genérico 16 bp lo tapa; concentración | **RE-CORRER en 5m con fees reales + subset líquido (§9)** |
| 2 | **M1** listing reversion | grande (moves 30–100%; edge de reversión 3–8% si existe) | ~2–3/mes (crypto-native limpios) | Sí en magnitud, **no** en frecuencia con n≈20 | dataset no identifica el evento | ingerir listing dates (Binance announcements + CoinGecko) → re-correr |
| 3 | **M15** reaction-beta factor | desconocido (no testeado) | alto (cada shock) | desconocido | ninguno (datos en mano) | correr next round |
| 4 | **M8b** funding sign-flip | +32 bp @24 h tras costo, pero placebo −50% | ~7/símbolo en 38 d | Marginal; datos insuficientes para afirmarlo | funding history 38 d; colector acoplado al agente | backfill `data.binance.vision/fundingRate` → re-correr con ≥90 d |
| 5 | H13-C squeeze | +56 bp @1 h (piloto, placebo-limpio) | baja-media | Sí si el efecto sobrevive OOS | OI 36 d (o backfill vision) | protocolo formal cuando OI ≥ 70 d |
| — | M10, M11, M8a | 1–4 bp / regime | — | **No** (4× < costo o placebo reproduce) | — | **FAILED — cerradas** |

---

## 6. TOP 3 EXPERIMENTS (los que se ejecutaron)

Se ejecutaron **4 experimentos reales** (3 del ranking + M18 que subió a prio 1
al inspeccionar datos), todos con controles adversariales, cluster-bootstrap
sobre símbolos, entrada realista (open[t+1]) y costo 16 bp round-trip:

1. **M10 — Taker absorption (1 barra).** `agent/backtest/r7_m10_absorption.py`.
   Universo 150 símbolos líquidos, 8.7 meses, 15m. n = 14 291 (up) / 12 411 (dn).
2. **M11 — BTC 5m shock → alt lead-lag sub-15m.**
   `agent/backtest/r7_m11_btc_leadlag.py`. 120 alts, 8.7 meses, 5m. 1 156 barras
   de shock BTC, 21 223 eventos de under-reacción.
3. **M8 — Funding como evento discreto (a: extremo, b: flip).**
   `agent/backtest/r7_m8_funding_event.py`. 311 símbolos, ~38 d de overlap
   funding×klines. 11 000 eventos extremos, 2 221 flips.
4. **M18 — Perp acción tokenizada vs apertura cash US.**
   `agent/backtest/r7_m18_rth_open.py`. 39 perps de equity/ETF, ~3.5 meses,
   3 711 eventos de apertura.

Común: `agent/backtest/r7_common.py` (z causal, media rolling causal, cluster
bootstrap). Scratch JSON: `scratch_r7_{m10,m11,m8,m18}_*.json`.

---

## 7. EXECUTED RESULTS

### M10 — Taker absorption → **FAILED**

| lado | h | real (bp) | CI excl 0 | mitades | symPos | placebo | quiet-only | matched (flujo movió) | tras 16 bp |
|---|---|---|---|---|---|---|---|---|---|
| absorb_up | 15m | −1.0 | sí (apenas) | −0.2 / −1.8 | 0.43 | −0.9 | −0.1 | **−1.7** | −15.0 |
| absorb_up | 60m | −2.2 | sí (apenas) | −0.2 / −4.3 | 0.43 | −1.1 | −1.2 | **−4.5** | −13.8 |
| absorb_up | 120m | −2.8 | no | −0.9 / −4.7 | 0.41 | −0.9 | −3.1 | **−6.8** | −13.2 |
| absorb_dn | 60m | +1.3 | no | −0.1 / +2.6 | 0.50 | +0.9 | **+3.2** | 0.0 | −14.8 |
| absorb_dn | 120m | +2.3 | no | +1.1 / +3.5 | 0.57 | +1.1 | **+4.3** | +1.3 | −13.7 |

Refutado: (a) efecto 1–3 bp, **5–15× por debajo del costo**; (b) el
matched-control "mismo flujo unilateral pero que SÍ movió el precio" tiene el
**mismo signo y más magnitud** → el driver es el flujo direccional, no la
absorción; (c) el quiet-only (barra tranquila, flujo neutro) **reproduce o supera**
el efecto en absorb_dn → es comportamiento de barra de baja vol, no absorción;
(d) symPos < 0.5 en absorb_up (la mayoría de símbolos con signo contrario);
(e) mitades inestables.

### M11 — BTC 5m shock → alt lead-lag sub-15m → **FAILED**

| h | real (bp) | CI excl 0 | mitades | symPos | placebo | matched (se movió c/BTC) | **uncond (todos los alts)** | tras 16 bp |
|---|---|---|---|---|---|---|---|---|
| 5m | +3.95 | sí | 3.0 / 4.9 | 0.78 | −2.1 | +2.4 | **+3.0** | −12.1 |
| 10m | +3.84 | sí | 2.8 / 4.9 | 0.64 | −1.0 | +2.3 | **+2.8** | −12.2 |
| 15m | +2.69 | sí | 1.8 / 3.6 | 0.57 | −0.4 | +1.6 | **+2.0** | −13.3 |
| 30m | +2.92 | sí | 3.4 / 2.4 | 0.59 | −0.3 | +3.0 | **+2.9** | −13.1 |

Hay un micro-efecto real y limpio de placebo (~+4 bp @5m, decae a 15 m). Pero
`uncond` (cualquier alt tras un shock de BTC, sin el filtro de "rezagado") ≈
`real` → **lo que se mide es beta de mercado continuando**, no un catch-up
específico de los rezagados. El filtro de under-reacción aporta ~1 bp sobre
nada. Y tras costo, **−12 a −13 bp** en todos los horizontes. Económicamente
muerto incluso en su versión sin fricción.

### M8a — Funding extremo → exhaustion → **FAILED**

| h | real (bp) | mitades | symPos | placebo (+48h) | matched (funding central) | tras 16 bp |
|---|---|---|---|---|---|---|
| 8h | −55.6 | −75 / −36 | 0.37 | **−38.0** | **−32.7** | −39.6 |
| 16h | −117.1 | −156 / −78 | 0.33 | **−70.9** | **−54.7** | −101.1 |
| 24h | −165.5 | −210 / −121 | 0.33 | **−91.8** | **−75.8** | −149.5 |

El "real" gigantescamente negativo NO es un efecto: la convención de signo es
`−sign(funding)` (apuesta short cuando funding es positivo, que es casi siempre),
y la muestra (2026-07-09 → 2026-08-16) fue un tramo **alcista**. El placebo +48 h
y el matched-control (settlements con funding en su rango central) **reproducen
el 60–70% del número**. symPos 0.33. Es drift de régimen × convención de signo,
exactamente el modo de falla que el brief advierte. Sin señal de exhaustion.

### M8b — Funding sign-flip → momentum de posicionamiento → **PARK / UNKNOWN**

| h | real (bp) | CI excl 0 | mitades | symPos | placebo (+48h) | tras 16 bp |
|---|---|---|---|---|---|---|
| 8h | −7.1 | no | −31 / +17 | 0.50 | +10.9 | +8.9 |
| 16h | +25.4 | no (roza) | +42 / +8 | 0.58 | +18.9 | +9.4 |
| 24h | **+48.2** | **sí** [16, 83] | +65 / +31 | 0.56 | **+24.2** | **+32.2** |

Hay un hint a 24 h: tras un flip a funding negativo, el precio continúa a la baja
~+48 bp brutos / +32 bp tras costo. Pero: (a) el placebo +48 h da +24 bp → se
come la mitad; (b) decae fuerte entre mitades (65 → 31); (c) sólo **38 días** de
funding history (mediana 22 d/símbolo) → imposible afirmar estabilidad temporal;
(d) n = 1 636 con ~7 flips por símbolo en toda la ventana. **No es PROMISING**
(falla placebo < 0.4× y estabilidad). Es un candidato razonable esperando datos.

### M18 — Perp acción tokenizada vs apertura cash US → **PARK (lead vivo)**

| h | real (bp) | CI excl 0 | mitades | symPos | conc top5 | placebo mediodía | tras 16 bp |
|---|---|---|---|---|---|---|---|
| 15m | +4.5 | sí | 6.6 / 2.5 | 0.59 | 0.54 | −1.4 | −11.5 |
| 30m | +10.6 | sí | 15.5 / 5.7 | 0.69 | 0.46 | −3.2 | −5.4 |
| 60m | +10.5 | sí | 13.0 / 8.0 | 0.67 | 0.45 | −8.3 | −5.5 |

`by |closed_ret|` tercil (reversión, bp): t0 (gap chico) ≈ 0 · t1 +9→+12 ·
**t2 (gap grande) +5 / +21 / +25**. → el efecto **escala con el tamaño del gap**,
firma de mecanismo real. El placebo de mediodía (17:00 UTC) **no lo reproduce**.

Contra: (a) bruto ~10 bp < 16 bp de costo genérico; (b) `pre_open` (12:30→13:30)
= −26 bp → el drift nocturno **sigue** hasta la campana y sólo revierte
parcialmente después (la reversión es más chica que la continuación previa);
(c) concentración top-5 ≈ 0.45–0.54; (d) mitades decaen (15.5 → 5.7 @30m);
(e) 3.5 meses de datos, calendario de trading US aproximado (todos los weekday =
RTH, sin holidays/half-days).

**Es el único mecanismo de Round 7 con efecto real + placebo-limpio + firma de
escalado.** No monetiza como está, pero merece una segunda pasada (§9).

---

## 8. VERDICT

| Hip. | Clasificación | Razón |
|---|---|---|
| **M10** taker absorption 1-bar | **FAILED** | efecto ≪ costo; matched-control domina; quiet-only reproduce |
| **M11** BTC sub-15m lead-lag | **FAILED** | efecto real ≈ beta de mercado (uncond ≈ real), 4× < costo |
| **M8a** funding extremo exhaustion | **FAILED** | placebo + matched reproducen; drift de régimen × signo |
| **M8b** funding sign-flip | **PARK** | hint @24 h pero placebo −50%, decae, 38 d de datos |
| **M1** listing reversion | **PARK** | el dataset no identifica el evento (artefactos de colección) |
| **M18** cash-open reversion | **PARK** | efecto real y coherente (+10 bp, escala con gap) pero < costo, concentrado, decae |

**Veredicto del round: NO PROMISING este round — 3 FAILED, 3 PARK.**

**No es "NO ALPHA FOUND":** M18 es un lead vivo con firma de mecanismo real, y
M1/M8b/H13-C/H14/H15 están bloqueadas por datos que (a) se están acumulando o
(b) son backfilleables desde `data.binance.vision` sin tocar la API. El espacio
razonable **no está agotado** — está desplazado hacia eventos estructurales y
hacia un plano de datos (OI/funding histórico, listing dates, unlocks) que
todavía no ingerimos.

---

## 9. NEXT MOVE — decidido automáticamente

**Próximo experimento (mayor expected scientific value): re-correr M18 con
ejecución realista y resolución fina.**

Justificación: es el único mecanismo nuevo de Round 7 que produjo un efecto
real, placebo-limpio y con escalado monótono en el tamaño del gap. El único
motivo por el que es PARK y no PROMISING es que ~10 bp brutos no superan el
supuesto genérico de 16 bp de costo. Ese supuesto puede estar mal para estos
contratos específicos, y la reversión puede concentrarse en los primeros
minutos (invisible en barras de 15m). Plan concreto:

1. **Resolución 5m** (`klines_5m` tiene los 39 tickers): entrada 13:30 UTC,
   salidas a 5 / 10 / 15 / 20 / 30 / 45 / 60 min. Localizar dónde se concentra
   la reversión (hipótesis: 5–15 min).
2. **Fees reales** de los perps de equity tokenizada en Binance UM (taker
   ~4.5 bp/lado; con entrada límite en la apertura, maker ~2 bp o rebate) →
   recalcular el neto con 9 bp y con 4 bp round-trip, no 16.
3. **Subset líquido** (≈12 nombres: COIN, NVDA, TSLA, MSTR, AAPL, HOOD, PLTR,
   AMZN, META, MSFT, GOOGL, AVGO) para atacar la concentración y el slippage.
4. **Condicionar el signo del gap** contra la dirección de la última sesión RTH
   real del perp (proxy de "dónde está la acción de verdad"): la reversión
   debería ser máxima cuando el drift nocturno fue **en contra** de la última
   sesión.
5. Gate: si el neto (fees reales + 2 bp slippage) supera ~8 bp en ≥ 10 nombres,
   con mitades estables y ≥ 25 eventos/mes → escalar a validación completa
   (walk-forward, TRAIN/VAL/OOS). Si no → **FAILED** y cerrar M18.

**En paralelo (sin bloquear, prioridad de infraestructura mínima):**

- **Verificar `data.binance.vision/futures/um/.../metrics/` y `/fundingRate/`.**
  Si el backfill funciona: OI histórico (desbloquea H13-C formal y H15 **ya**, no
  en octubre) + funding ≥ 90 d (desbloquea M8b). Es la palanca de mayor impacto
  del proyecto ahora mismo. Un script de descarga tipo el que armó
  `binance_vision_clean.db`.
- Los colectores de **OI (PID 15164)** y **liquidaciones (PID 32924)** siguen
  vivos y frescos (OI a 2026-09-10 01:23, 36.4 d; liq a 01:26). Desacoplados del
  agente (que está muerto). **No se toca nada más de infraestructura este round.**

**Next-tier (si M18 refinado falla):** correr **M15** (factor de reaction-beta
persistente) — datos en mano, no testeado, prior medio. Después: ingerir
**listing dates** (Binance announcements + CoinGecko `date_added`) para M1, y
**token unlock calendars** para una hipótesis de oferta forzada nueva.

---

## Data blockers — registro

| Bloqueo | Qué desbloquea | ¿Se puede hacer YA? | ETA si se espera |
|---|---|---|---|
| OI histórico (hoy 36 d live, 13 sym ≥90%) | H13-C formal, H15, M8-familia | **Sí — backfill `data.binance.vision/metrics`** (no verificado) | ~2026-10-13 (live) |
| Funding history (hoy 38 d, colector acoplado al agente muerto) | M8b, M3 | **Sí — backfill `data.binance.vision/fundingRate`** (no verificado) | ~2026-12 (live, si vuelve el agente) |
| `liquidations_research` (1.5 d) | H14, M9 | No (Bybit no da histórico REST) | ~2026-11-09 (60 d) |
| Listing dates verificados | M1, M3, M16 | **Sí — Binance announcements (web) + CoinGecko** | — |
| Token unlock calendar | hipótesis de oferta forzada (nueva) | **Sí — DefiLlama /unlocks** | — |
| Calendario de trading US (holidays/half-days) | M18 (precisión) | **Sí — pandas-market-calendars** | — |
| Feed real mark/index | M20 | No con fuentes gratis obvias | — |
