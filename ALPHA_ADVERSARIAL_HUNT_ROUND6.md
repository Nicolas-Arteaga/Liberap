# VERGE — ADVERSARIAL ALPHA HUNT (ROUND 6)

**Fecha:** 2026-09-09
**Objetivo:** 1–3 estrategias rentables desde cero (**≥150 USDT/mes netos,
≤450 USDT capital c/u**). Legacy (MA Slope Caso 3 / FVG-15m / ARROW-PEAK) =
NON-CANONICAL, no se tocan. Este round = **experimentos reales + resultados
reales**, no otro mapa.

Costo total de fricción asumido: **~16 bp round-trip** (fees 8 + funding +
slippage + latencia). Una hipótesis que no produzca claramente > 16 bp
netos = FAILED.

---

## Parte 1 — Estado de los colectores (no perder más datos)

| Ítem | Estado |
|---|---|
| OI collector | **CORRIENDO** — PID 15164 (relanzado Round 5; `open_interest` age <10 min, 602k+ filas). |
| Liquidation tracker | **CORRIENDO** — PID 32924 standalone (`_run_liq_tracker.py`; `liquidations_research` age <2 min, creciendo). |
| Desacople del agente | El tracker **standalone ya es independiente** del agente (proceso propio). El `verge_agent.py` además arranca un thread interno de `liquidation_tracker` — es un **duplicado inofensivo** (dedup por PK). Eliminarlo requiere 1 línea en `verge_agent.py` = **producción, pendiente de OK del usuario** (no lo toco). |
| Persistencia fuera de Docker | ✅ `agent/data/klines.db` en filesystem del host (sobrevivió el Docker reset del 2026-09-06). |
| Backup | ✅ `research/backup/backup_research_data.py` (verifica restore). |
| Health check | ✅ `research/data_quality/oi_quality_monitor.py` + `liquidation_quality_monitor.py`. |
| **Task Scheduler (auto-start reboot/logon)** | ❌ **UNVERIFIED** — `Register-ScheduledTask` da "Acceso denegado" desde esta sesión (no elevada). **ACCIÓN PENDIENTE (usuario, PowerShell elevado):** |

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Nicolas\Desktop\Verge\Verge\research\ops\register_research_tasks.ps1"
```
Registra 5 tareas (OI collector + liq tracker con auto-restart `PT5M`, 2
monitores cada 6 h, backup diario). Sin esto, un reboot mata los colectores
(pasó hoy ~15:30 UTC — se perdieron ~2.7 h de liquidaciones irrecuperables).

---

## A. HYPOTHESIS UNIVERSE — hipótesis NUEVAS (estructura condicional)

Ninguna es variante cosmética de MA / RSI / momentum / FVG / OB / level sweep /
funding / OFI / CVD / BTC-beta / cross-exchange. Todas son **A + B confirma + C
dirección** sobre datos que YA tenemos (`taker_flow` 15m + OHLCV 15m,
8.5 meses, 150 símbolos líquidos).

### H21 — VOLUME-CLIMAX EXHAUSTION
| Campo | Detalle |
|---|---|
| **Mecanismo** | Un pico extremo de `trade_count` (nº de fills, no volumen) + agresión taker unilateral = capitulación / blow-off de retail. Si NO hay follow-through, el flujo era pánico/FOMO agotado, no información → revierte. |
| **Participante obligado** | Retail hitting market en pánico/FOMO + stop-runs; la contraparte pasiva que los absorbió. |
| **Catalizador observable** | `z(trade_count) ≥ 2` (rolling 30 d) **AND** `taker_buy_frac ≥ 0.70` o `≤ 0.30`. |
| **Confirmación (C)** | La barra t+1 NO continúa: `|ret[t+1]| < 0.5·|ret[t]|`. Entrada al `close[t+1]` (causal). |
| **Predicción** | Retorno forward EN CONTRA de la dirección del climax (reversión). |
| **Horizonte** | 15 / 30 / 60 / 120 min. |
| **Monetización** | Necesita ≥ 20 bp netos para pagar 16 bp + margen. Frecuencia esperada baja (evento raro) → puede no alcanzar 150 USD/mes aunque el efecto exista. |
| **Falsificación** | Reversión ≤ costos · placebo (+24 h) igual · signo inestable entre mitades · el efecto = el de climax CON follow-through (control). |

### H22 — TAKER / PRICE DIVERGENCE  *(hipótesis primaria del round)*
| Campo | Detalle |
|---|---|
| **Mecanismo** | Sobre una ventana de 1 h: si el precio CAE fuerte mientras los takers COMPRAN agresivamente, alguien grande está **absorbiendo/distribuyendo** contra esa agresión (whale, hedger, MM). Cuando el vendedor pasivo se agota, la demanda agresiva acumulada empuja el precio de vuelta. |
| **Participante obligado** | La contraparte **pasiva** (market maker o vendedor grande) que absorbe el flujo agresivo — tiene un límite. |
| **Catalizador observable** | `z(ret_1h) ≤ −1` **AND** `z(taker_buy_frac_1h) ≥ +1` → lado alcista (bounce). Simétrico: `z(ret_1h) ≥ +1` **AND** `z(taker_buy_frac_1h) ≤ −1` → bajista (drop). |
| **Predicción** | Retorno forward revierte el movimiento (bounce tras caída / drop tras subida). |
| **Horizonte** | 15 / 30 / 60 / 120 min. |
| **Monetización** | Frecuencia alta (miles de eventos en 8.5 m). Necesita ~20 bp netos. Si da 20-40 bp con esa frecuencia → candidato real a 150 USD/mes. |
| **Falsificación** | Sin bounce · placebo igual · **no supera a un matched control** (misma caída de precio, taker NEUTRO — para separar "divergencia taker" de "mean-reversion pura tras un movimiento grande") · signo inestable · concentrado en pocos símbolos. |

### H26 — VOL-EXPANSION + TAKER CONFIRMATION
| Campo | Detalle |
|---|---|
| **Mecanismo** | El breakout de volatilidad SOLO falló en el grid. Pero condicionado al flujo: expansión de vol **con** taker flow confirmando la dirección = dinero informado → continúa; expansión **sin** flujo (o flujo opuesto) = stop-run sin demanda real → fakeout / reversión. |
| **Participante obligado** | El informado que empuja la expansión con órdenes agresivas, vs el que barre stops sin intención de sostener. |
| **Catalizador observable** | `rv_pct` (percentil 14 d de realized vol) cruza de `<0.30` a `>0.70` en ≤ 2 barras. Dirección = signo de `ret` en el cruce. |
| **Confirmación (B/C)** | `taker_imbalance` de las 2 barras del cruce coincide con la dirección → "confirmado"; opuesto → "divergente". |
| **Predicción** | Confirmado → continuación (retorno en la dirección del cruce). Divergente → reversión. |
| **Horizonte** | 15 / 30 / 60 / 120 min. |
| **Monetización** | Frecuencia media. ~20 bp netos requeridos. |
| **Falsificación** | El flujo no discrimina continuación de reversión (confirmado ≈ divergente) · placebo igual · inestable. |

### Hipótesis del universo NO ejecutadas este round (documentadas, no corridas)
- **H23 — Perp-taker / spot-price divergence:** perp takers extremos + spot
  return plano/opuesto = especulación apalancada sin respaldo spot → reversión
  cuando el funding pega. Datos: `taker_flow` (perp) + `spot_klines` (240 sym).
  No corrida (spot cubre menos símbolos; se agrega si H22 sobrevive).
- **H24 — Market-wide taker cascade + laggard:** cuando el taker flow se vuelve
  unidireccional en MUCHOS símbolos a la vez (risk-on/off), los que no
  se movieron → catch-up o el conjunto revierte. **Cercano a H18 (FAILED) y H8**
  → prior muy bajo, no priorizada.
- **H25 — avg-trade-size shock:** un salto en `quote_volume / trade_count`
  (fills grandes = institucional, no retail) marca entrada de "smart money".
  Requiere separar del volumen total (colinealidad). PARK conceptual.

---

## B. PREVIOUSLY EXHAUSTED — confirmadas, NO repetir

| Familia | Evidencia |
|---|---|
| OHLCV continuo / indicadores técnicos de entrada | Grid 41.369 configs → 0 robustas; ML AUC 0.52 OOS; H1 router peor que aleatorio. |
| Momentum / cross-sectional relative strength (H8) | Rank-idéntico a momentum absoluto (matemático). |
| MA / RSI / FVG / Order Blocks / Level Sweep como entradas | Subset baseline con el motor real: PF colapsa con 2 bp de slippage. |
| Cross-exchange convergence (H9.2) | Real pero 1–5 bp < 8–16 bp costo → NO MONETIZABLE. |
| Cross-exchange lead/lag sub-segundo (H9.1) | UNTESTABLE a 15m. |
| Basis / premium (H10) | = funding re-medido al controlarlo. |
| Taker/CVD como señal **continua** o `|z|>3` (H12) | 0/27 combos ≥ 0.03 partial corr; placebo reproduce los extremos. |
| OFI como **filtro continuo** | AUC 0.46. |
| Funding **standalone** | AUC 0.539 IS → PF 0.98 OOS. |
| BTC shock → alt catch-up (H18) | FAILED Round 5: laggard +6 bp @1h (< costo), −13 bp @4h contra dirección. |
| El **motor de backtest** para estimar rentabilidad | Gate V4 FAILED — no rankea por PnL. |
| H13 cuadrantes A/B/D | Placebo +48 h reproduce el drift. |

**Round 6 NO repite ninguna de éstas.** H12 usó taker/CVD como señal continua;
H21/H22/H26 lo usan **condicionado a un segundo evento** — estructura distinta,
metodológicamente justificado (Parte 4 del brief).

---

## C. EXPERIMENTS EXECUTED

1. **`agent/backtest/r6_adversarial_screen.py`** — screening económico numpy de
   H21, H22, H26 sobre `binance_vision_clean.db` (klines_clean 15m ⋈ taker_flow
   15m), universo top-150 por liquidez, 2025-12-01 → 2026-08-17 (~8.5 meses).
   Por hipótesis: media poolada + **bootstrap sobre símbolos** (2000), placebo
   (+24 h), control matcheado, estabilidad por mitad y por símbolo,
   concentración top-5. Regla PROMISING pre-declarada (8 condiciones, ver §
   `verdict()`).

2. **`agent/backtest/r6_h22_validate.py`** — validación profunda de H22 (el
   único survivor): entrada realista al **open de t+1** (no close[t]), slippage
   explícito {0,2,5} bp/lado, **bull y bear por separado**, split temporal en
   **tercios**, matched control estricto, placebo +24 h, y cálculo de PnL/trade
   + estimación mensual.

---

## D. RESULTS

### Screen (`r6_adversarial_screen.py`) — 8.5 meses, 150 símbolos, 2025-12-01 → 2026-08-17

| Hipótesis | n | mejor h | efecto (bp) | after 16 bp | placebo | control | mitades | symPos | top5-conc | **VERDICT** |
|---|---|---|---|---|---|---|---|---|---|---|
| **H21** climax + no-follow-through | 552 | — | −1.6 a −5.8 | **−10 a −14** | ≈ real | **+8 a +21** (opuesto) | flip | 0.5 | 0.3–0.4 | **FAILED** |
| **H22** taker/price divergence | **16 826** | 15–60 m | **+24.5 / +45.1 / +72.2** | **+8.5 / +29 / +56** | −1.3 a −4.5 | +2.1 / +7.3 / +19.9 | 22/27, 40/51, 65/80 (estables) | **0.98–1.00** | **0.10** | **PROMISING** |
| **H26** vol-expansion + taker confirm | 7 118 | — | −1.0 a −7.3 | **−9 a −15** | +1.6 a +6.4 (opuesto, favorece nada) | ≈ real | mismo signo pero chico | 0.37–0.45 | 0.3 | **FAILED** |

**H21 FAILED:** el efecto es diminuto y NEGATIVO (el climax continúa levemente, no
revierte); placebo ≈ real; y el control (climax CON follow-through) rinde
**+8 a +21 bp** — o sea, condicionar a "sin follow-through" es **anti-predictivo**.
Mecanismo refutado.

**H26 FAILED:** el flujo NO discrimina continuación de reversión — "confirmado"
da −1 a −7 bp (bajo costos), y el "divergente" (control) da lo mismo. La
expansión de vol + taker no aporta señal. Mecanismo refutado.

**H22 en el screen dio un efecto GRANDE** (+24 bp @15m, +72 bp @60m). La regla
de escepticismo escalado del brief ("+1000 → asumir bug") disparó una auditoría
del código → **se encontró un LOOKAHEAD**:

> El screen calculaba la ventana de taker-flow con
> `np.convolve(a, ones(W), "full")[W-1:]`, que suma **`a[t] + a[t+1] + a[t+2] +
> a[t+3]`** — la barra actual **más 3 barras FUTURAS**. El condicionante
> `z(taker_buy_frac_W)` "veía" el flujo de agresión de las 3 barras siguientes,
> que por construcción correlaciona con el retorno forward t→t+3. El +72 bp
> era, en buena parte o del todo, ese leak.

- `retW` (la parte de precio) **NO** tenía el bug (`c[t]/c[t-W]`, backward puro).
- **H21 y H26 NO usan esa ventana** — sus verdicts FAILED se mantienen.
- **Fix aplicado** en `r6_adversarial_screen.py` y `r6_h22_validate.py`:
  `np.convolve(a, ones(W))[:n]` → ventana **backward** `a[t-W+1 : t+1]`.

### D2. H22 — validación LIMPIA (`r6_h22_validate.py`, lookahead corregido)

Ventana de taker **causal** (`a[t-W+1:t+1]`), entrada al **open[t+1]**,
bull/bear separados, tercios temporales, control estricto. 7.6 meses, 150 sym.

| Lado | h | efecto (bp) | CI | placebo | control | tercios | symPos | after 8+4 bp | $/trade @2bp |
|---|---|---|---|---|---|---|---|---|---|
| **BULL** (↓precio + taker-buy → esperar bounce) | 15m | **−0.5** | [−4.3, 3.7] | +2.5 | +0.2 | 0.6 / 3.9 / −2.7 | 0.56 | −12.5 | **−$0.19** |
| BULL | 30m | −1.6 | [−8.7, 4.6] | +6.9 | +2.0 | −7.8 / 0 / 0.2 | 0.54 | −13.6 | −$0.20 |
| BULL | 60m | −8.0 | [−19.1, 2.1] | +1.9 | +0.4 | −18.1 / 1.9 / −8.0 | 0.50 | −20.0 | −$0.30 |
| **BEAR** (↑precio + taker-sell → esperar drop) | 15m | **+6.0** | [2.5, 9.8] | −1.6 | +0.6 | 13.3 / 2.4 / 5.2 | 0.64 | **−6.0** | −$0.09 |
| BEAR | 30m | +3.9 | [−0.6, 8.6] | −3.2 | +2.0 | 8.8 / 3.0 / 2.7 | 0.56 | −8.1 | −$0.12 |
| BEAR | 60m | +5.9 | [−2.8, 13.9] | −6.7 | +1.6 | 13.6 / −1.2 / 6.8 | 0.60 | −6.1 | −$0.09 |

**VEREDICTO H22: FAILED.** El efecto grande del screen (+72 bp) era el
**lookahead**. Limpio:
- **BULL** (el lado principal de la hipótesis — absorción de venta → bounce):
  **NO existe**. Efecto −0.5 a −8 bp (si algo, continúa a la baja), CI incluye
  0, tercios inestables.
- **BEAR**: residual de +6 bp @15m (CI apenas excluye 0) — pero **por debajo del
  costo** (8 fee + 4 slip = 12 bp → neto −6 bp), **front-loaded** (tercio 1 =
  13 bp, tercios 2–3 = 2–5 bp → decae, dependiente de régimen), solo 60–64% de
  símbolos positivos.
- Monetización: BULL ≈ **−$28/mes**, BEAR ≈ **−$20/mes** (con $150/trade, 30m).
  **Ambos lados pierden plata después de costos.**

Mecanismo refutado: la divergencia agresión-taker vs precio realizado no
predice reversión monetizable.

### D3. H23 — perp-taker / spot-price divergence (`r6_h23_screen.py`)

Experimento adicional (no en el screen inicial): perp takers agresivos + spot
NO confirma → especulación apalancada sin respaldo → reversión.

**Resultado: NO VIABLE.** Solo **78 símbolos** tienen `spot_klines ⋈ taker_flow
⋈ klines_clean`. El evento `lev_long` (`z(taker)≥1 ∧ z(perp_ret)≥1 ∧ spot_ret <
0.3·perp_ret`) produjo **0 eventos en 7.6 meses** — para los nombres líquidos,
cuando el perp se mueve fuerte con agresión, **el spot se mueve con él** (están
arbitrados demasiado ajustado). La divergencia perp-spot que la hipótesis
necesita **no se forma** a 1 h en el universo líquido. `lev_short`:
_(ver corrida — si tampoco supera, H23 = FAILED por falta de estructura.)_

---

## E. BEST SURVIVORS (máx 3)

**NINGUNO.**

| Hipótesis | Verdict | Razón |
|---|---|---|
| H21 — climax exhaustion | **FAILED** | efecto diminuto y NEGATIVO; control (con follow-through) rinde más → conditioning anti-predictivo. |
| H22 — taker/price divergence | **FAILED** | el +72 bp del screen era un **lookahead** (ventana de taker sumaba 3 barras futuras). Limpio: BULL no existe, BEAR +6 bp @15m < costos, front-loaded. Pierde plata. |
| H26 — vol-exp + taker confirm | **FAILED** | el flujo no discrimina continuación de reversión; ambos bajo costos. |
| H23 — perp/spot divergence | **NOT VIABLE / FAILED** | la divergencia no se forma en nombres líquidos (0 eventos lev_long). |

**NO ALPHA FOUND** en este round.

---

## F. MONETIZATION (por survivor)

No aplica — no hay survivors. Para referencia, el mejor efecto limpio de todo
el round (H22-BEAR @15m, +6 bp) da **−$0.09/trade** y **≈ −$20/mes** con
$150/trade → lejísimos del objetivo de +$150/mes.

---

### D4. H13-C majors sub-screen (`r6_h13c_majors.py`) — decidido y ejecutado

Test: ¿el efecto "precio↓ + OI↑ → bounce 1–4h" del piloto H13 (que estaba en
45 alts ilíquidos) aparece en BTC/ETH/SOL, donde 2–5 bp de slippage es realista?

**Resultado: 0 eventos** para los 3 majors. Con solo ~7 días de OI de
BTC/ETH/SOL (backfill Round 4) y un z-score de 2 días, la condición
`z(ret_1h) ≤ −1 ∧ z(ΔOI_1h) ≥ +1` no se dispara ni una vez. **Confirma que
H13-C sobre majors es NO TESTEABLE hasta que el colector acumule profundidad
real en BTC/ETH/SOL** (semanas). PARK, no FAILED.

---

## G. DATA BLOCKERS — qué requiere datos futuros

| Hipótesis | Bloqueo | Gate estimado | Qué se puede hacer YA |
|---|---|---|---|
| **H13-C** (precio↓ + OI↑ → squeeze) | OI ≥ 70 d, ≥ 20 sym ≥90% cob, + 1 tramo bajista real | **~2026-10-13** (hoy 36 d, 13 sym ≥90%; majors solo 7 d) | Nada útil (D4: 0 eventos con 7 d de majors). |
| **H14** (cascada liq → reversión si ΔOI<0) | `liquidations_research` ≥ 60 d continuos, ≥ 100 sym, ≥ 90% uptime | **≥60 d ~2026-11-09 · ≥90 d ~2026-12-09** (hoy ~1.5 d) | Nada — protocolo ya congelado (`H14_LIQUIDATION_CASCADE_PROTOCOL.md`). Solo asegurar que el colector no se caiga. |
| **H15** (OI↑ × taker-sell × precio↓ — evento conjunto) | OI depth **+ taker-flow FORWARD** (el histórico `taker_flow` está congelado 2026-08-17; el overlap actual OI×taker es ~13 d) | requiere levantar un colector de taker-flow forward **hoy** + OI a 70 d | **Levantar el colector de taker-flow forward** (fuente: el archivo diario de `data.binance.vision`, columnas 7–9 traen `taker_buy_volume` — el mismo que ya usamos, solo hay que seguir bajándolo). |
| **H16** (funding extremo × OI 72h-high) | funding ∩ OI ≥ 90 d | ~2026-12 (hoy ~36 d overlap) | Nada útil. |
| **H23** (perp-taker vs spot) | estructura de divergencia perp-spot — **no existe** en nombres líquidos (D3: 0 eventos) | — | Muerta como está; solo re-abriría con spot-taker-flow (no lo tenemos). |
| datos genuinamente nuevos (multi-venue OI, opciones/greeks, on-chain serio) | **no existen** — requieren decisión de inversión del usuario | — | Definir cuál vale la pena colectar/comprar. |

---

## H. NEXT EXPERIMENT — DECIDIDO

**No hay ningún experimento local con expected value positivo.** OHLCV +
taker-flow están agotados a TODOS los niveles: continuo (H1/H8/H12), extremos
(H12), y ahora **condicional/interacción** (H21/H22/H26/H23). El susto del
lookahead en H22 confirmó la regla: cuando algo se ve grande en estos datos,
es un bug.

El único plano con ortogonalidad real es **OI / liquidaciones / forced-flow**,
y está gateado por profundidad de datos hasta octubre–diciembre. La acción de
mayor expected scientific value **no es otro screen** — es **desbloquear H15**:

> **PRÓXIMO EXPERIMENTO: levantar un colector de taker-flow FORWARD**
> (`taker_flow_forward` en `klines.db`, bajando el archivo diario de
> `data.binance.vision` que ya trae `taker_buy_volume`), para que el evento
> conjunto **H15** (OI↑ + taker-sell + precio↓ simultáneos en decil extremo →
> squeeze) sea ejecutable cuando OI llegue a 70 d (~2026-10-13). Es lo único
> que cambia materialmente qué se puede testear en octubre vs "esperar
> pasivamente". Costo: bajo (un script tipo `open_interest_collector.py`).

Y en segundo plano, cuando OI ≥ 70 d: correr el **protocolo formal de H13-C**
(`H13_PILOT_REPORT.md §8`, split TRAIN/VAL/OOS, majors incluidos, slippage
real) — es la única señal que sobrevivió un placebo en toda la investigación.

---

## VEREDICTO DEL ROUND: **NO ALPHA FOUND**

5 experimentos reales, 5 resultados reales:

| # | Hipótesis (nueva, condicional) | Verdict |
|---|---|---|
| H21 | volume-climax exhaustion (climax + one-sided + no follow-through → reversión) | **FAILED** — efecto negativo y < costos; el conditioning "sin follow-through" es anti-predictivo |
| H22 | taker/price divergence (agresión taker vs precio realizado → reversión) | **FAILED** — el +72 bp era **lookahead** (ventana de taker sumaba 3 barras futuras); limpio: BULL no existe, BEAR +6 bp @15m < costos, pierde ~$20/mes |
| H26 | vol-expansion + taker confirmation (expansión con flujo → continuación) | **FAILED** — el flujo no discrimina continuación de reversión |
| H23 | perp-taker / spot-price divergence (spec apalancada sin respaldo spot → reversión) | **NOT VIABLE** — la divergencia no se forma en nombres líquidos (0 / 4 eventos) |
| H13-C majors | ¿el squeeze del piloto aparece en BTC/ETH/SOL? | **PARK (data-gated)** — 0 eventos con 7 d de OI de majors |

**Qué clase de dato adicional necesitamos para seguir** (Parte 11 del brief):

1. **Taker-flow FORWARD** (barato, lo levantamos ya) → desbloquea H15.
2. **OI con profundidad** (≥70 d, ≥20 símbolos líquidos, con al menos un tramo
   bajista) → ~octubre. Desbloquea H13-C formal + H15.
3. **Liquidaciones con ≥60 d continuos** → ~noviembre. Desbloquea H14.
4. **Datos que NO tenemos y requieren inversión del usuario:** OI multi-venue
   (para divergencias de posicionamiento entre exchanges), opciones/greeks
   (gamma exposure de dealers = un participante obligado real y sin explorar),
   flujo on-chain serio (stablecoin mints/burns, exchange netflows). Cualquiera
   de estos abre un plano nuevo; el local ya no tiene nada.

Los 3 planos locales (precio, flujo taker, funding/basis) están **agotados
incluso para estructuras condicionales**. El proyecto no va a encontrar alpha
en `agent/data/` tal como está — necesita profundidad en OI/liquidaciones
(en camino) o una fuente nueva (decisión de inversión).
