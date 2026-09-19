# ROUND 9 — OI HISTORICAL ALPHA HUNT

**Fecha:** 2026-09-11
**Enabler:** backfill de métricas históricas 5m (Open Interest + L/S ratios + taker
ratio) desde `data.binance.vision` para toda la ventana dic-2025 → ago-2026.
**Objetivo:** ¿hay información nueva y reproducible en **OI + flujo + precio** con
magnitud suficiente para una estrategia de ≥150 USDT/mes netos con ≤450 USDT?

---

## 1. INGESTA HISTÓRICA — hecha y validada

**Descargado** (`agent/download_oi_metrics.py`, `agent/download_funding_hist.py`,
solo `data.binance.vision`, nunca api/fapi):

| Tabla nueva (en `binance_vision_clean.db`, aditiva) | Filas | Símbolos | Ventana | Resolución |
|---|---|---|---|---|
| `oi_metrics` (`sum_oi`, `sum_oi_value`, `global_ls_acct`, `toptrader_ls_pos`, `taker_ls_vol`) | 4 342 798 | 63/63 | 2025-12-01 → 2026-08-17 | 5m |
| `funding_hist` (`funding_rate` 8h) | 74 890 | 63/63 | 2025-12-01 → 2026-08-31 | 8h |

**Universo:** EX-ANTE congelado `research/universe/oi_universe.json` (63 = BTC/ETH/SOL
+ top-60 perps cripto por liquidez; ventana de selección 2026-07-18→08-17). **No se
modificó.** Perps de acción/commodity ya excluidos ahí.

**Validación (todo OK):**
- Timestamps: `create_time` UTC, grilla 5m exacta — **0 filas fuera de grilla**.
- `create_time` = inicio de barra (alineado con `klines_5m.open_time`).
- Duplicados: PK `(symbol, open_time)` + `INSERT OR IGNORE` → 0.
- Gaps: 3–4 barras por símbolo en 8.5 meses (MRVL 15). Cobertura 100% desde el
  listing de cada símbolo. **~48/63 tienen los 8.5 meses completos**; el resto son
  listings posteriores, 100% desde su fecha.
- Unidades: reconciliado `sum_oi` vs el colector live (`open_interest` en klines.db)
  en el único solape disponible (CAPUSDT, 3 831 puntos 5m) → **diferencia media
  −0.7 ppm** (< 0.01 bp). Misma serie, mismas unidades, mismos timestamps.
- Velas incompletas: ninguna (288 filas/día siempre).

**Panel de análisis** (`agent/backtest/r9_oi_alpha.py`): 15m (base de `taker_flow`),
63 símbolos, `klines_clean` + `taker_flow` + `oi_metrics`(→15m) + `funding_hist`
(step causal) + BTC/beta. W lookback = 4 barras (1h). z causal 30d. Horizontes
15m/30m/1h/2h/4h/8h/24h. Retorno crudo close-to-close + variante residual-BTC.
Costo screen conservador **20 bp round-trip**. TRAIN/VAL/OOS 50/25/25 por fecha.
Bootstrap por símbolo (cluster, 3000) + mitades + concentración top5.

---

## 2. RESULTADOS

| Hipótesis | Eventos | Símbolos | Gross (mejor h) | Net (20bp) | OOS | Placebo | Concentración | Veredicto |
|---|---:|---:|---|---|---|---|---|---|
| **M15** reaction-beta persistente | 242 shocks | 21 califican | spread under−over ≈ −13 bp @2h (signo contra hipótesis) | < 0 | spread −2.6 bp @2h ≈ **random −2.4** | ranking aleatorio reproduce | conc 1.0 / symPos 0 | **FAILED** |
| **H13-C A** (p↓ + OI↑) | 5 200 | 63 | −13 bp @1h · −37 @4h · −66 @8h (continúa BAJANDO) | +7 @4h · +47 @8h (como SHORT) | −34 @1h, −70 @2h (fuerte) | +24h: 30–40% del efecto a ≥8h; limpio ≤2h | 0.42–0.46 / symPos 0.41–0.48 | **PARK** |
| **H13-C D** (p↑ + OI↓) | 5 568 | 63 | −7.5 bp @1h · −23 @4h · −39 @8h (REVIERTE abajo) | −12 @1h · +3 @4h · +19 @8h (como SHORT) | −20 @1h, −55 @4h | limpio ≤4h; leak a 24h | 0.38–0.59 / symPos 0.33–0.49 | **PARK** |
| **H13-C B** (p↓ + OI↓) | 8 679 | 63 | +0.3…+4 bp, CI incluye 0 en todo | — | plano | — | — | **FAILED** (sin efecto) |
| **H13-C C** (p↑ + OI↑) | 7 570 | 63 | −0.4…+4 bp, CI incluye 0 en todo | — | plano | — | — | **FAILED** (sin efecto) |
| **H15** OI×taker×price (8 estados) | 32 813 | 62 | el mejor estado ≈ H13-C-A refinado | igual que H13-C | igual | — | — | **FAILED como hipótesis propia** (ver §3) |
| **H16** funding×OI | 29 135 | 63 | funding-solo −4 bp @1h, −19 @4h (momentum del crowd) | < 0 en todo | negativo (momentum) | — | 0.5–0.8 | **FAILED** |

### Detalle decisivo — los tests incrementales (§7 del brief)

**H15 OLS** `fwd ~ 1 + retW + dOI + z_tbr + |retW| + btc_ret` (n=32 813):

| h | t(retW) | **t(dOI)** | t(z_tbr) |
|---|---|---|---|
| 15m | −1.4 | **−7.7** | 0.7 |
| 30m | −2.2 | **−3.2** | 0.4 |
| 1h | −4.8 | **−5.5** | 1.6 |
| 2h | −4.0 | **−3.5** | 1.0 |
| 4h | −2.2 | **−2.5** | 0.5 |

→ **`dOI` (cambio de OI) es la variable con más información incremental — más que
`retW` a horizontes cortos.** **`z_tbr` (agresión taker) NO es significativa a
ningún horizonte** → el taker flow **no aporta nada** sobre precio + OI. La premisa
de H15 ("el taker distingue continuación de exhaustion") queda **refutada**.

**H16 OLS** `fwd ~ 1 + z_fund + dOI + retlong` (n=29 132):

| h | t(z_fund) | t(dOI) | t(retlong = momentum 24h) |
|---|---|---|---|
| 15m | −1.0 | −3.6 | **+3.9** |
| 1h | −0.4 | −1.4 | **+5.7** |
| 4h | −0.3 | 0.1 | **+14.8** |
| 8h | −0.3 | 0.9 | **+21.0** |

→ **`z_fund` (funding extremo) NUNCA es significativo.** Una vez controlado el
momentum de precio, funding no describe ni predice nada incremental. **`retlong`
(momentum) domina todo.** OI aporta un efecto residual solo a 15–30m. → **H16
FAILED: OI no aporta incremental sobre funding, y funding no aporta sobre
momentum.**

**M15 controles:** persistencia corr(TRAIN,OOS) = **0.61** (un símbolo que
sobre/sub-reacciona tiende a seguir haciéndolo — hallazgo positivo aislado). Pero
el **portfolio congelado** (under-reactors vs over-reactors, post-shock): spread
OOS −2.6 bp @2h ≈ **ranking aleatorio −2.4 bp**; signo cambia por horizonte
(+3.3/−2.6/−9.1/−10.5); `conc`=1.0, `symPos`=0 (los 7+7 símbolos se mueven todos
juntos = es el crash del mercado, no un spread cross-sectional independiente). 242
shocks en 8.5m ≈ 28/mes, todos correlacionados. **No hay spread monetizable.**

---

## 3. ¿QUÉ VARIABLE APORTA EL EDGE?

Comparación pedida en §7 (screening, fwd 1h, cluster-bootstrap):

| Señal | ¿aporta algo? | evidencia |
|---|---|---|
| price sola (`retW`) | sí, momentum débil / mean-rev corto | OLS t(retW) −1.4…−4.8 |
| **OI sola (`dOI`)** | **SÍ, es la principal** | OLS t(dOI) hasta −7.7; matched-control con OI plano ≈ 0 vs cuadrante real −13 bp |
| taker flow (`z_tbr`) | **NO** | OLS t(z_tbr) ≈ 0 a todo horizonte |
| funding (`z_fund`) | **NO** (sobre momentum) | OLS t(z_fund) ≈ 0 |
| price + OI | = OI (dOI domina) | cuadrantes A/D vs matched |
| price + OI + taker | = price + OI | z_tbr no mueve la aguja |
| + funding | = lo anterior | z_fund no mueve la aguja |

**El edge incremental está 100% en `dOI` (cambio de Open Interest).** Ni taker ni
funding agregan información sobre precio + OI. Ése es el resultado científico
central de Round 9.

---

## TOP MECHANISM

**El único con evidencia real: el efecto incremental de `dOI` — consolidación de
H13-C cuadrantes A (p↓ + OI↑) y D (p↑ + OI↓).**

**1. Qué fenómeno captura.** Cuando el Open Interest **se mueve fuerte junto con un
movimiento de precio significativo**, el drift multi-hora siguiente es
sistemáticamente **negativo** en esta ventana (dic-2025 → ago-2026), *sin importar
la dirección del precio*: un drop con OI↑ (A) sigue cayendo; un rally con OI↓ (D)
revierte a la baja. Un movimiento igual de fuerte pero **con OI plano** (matched
control) no drift-ea (≈ 0 bp). Taker flow y funding no cambian nada.

**2. Por qué debería existir.** ΔOI mide creación/destrucción neta de posición
apalancada. La lectura que sobrevive los datos: la construcción agresiva de
apalancamiento (OI↑) marca exceso que el mercado corrige a la baja en horas; el
desapalancamiento en un rally (OI↓ en D) quita el combustible y el precio cede.
Es información de *estado de posicionamiento*, ortogonal a OHLCV, que sólo el OI
histórico permite ver.

**3. Qué variable aporta alpha incremental.** `dOI` (z-score causal 30d del cambio
de OI sobre 1h). t hasta −7.7 en OLS controlando precio, |precio|, taker y BTC.
Taker y funding: cero.

**4. Cuánto produce neto.** Como SHORT sobre A o D, close-to-close, costo 20 bp RT:
net ≈ **−12 a −7 bp** @15–60m (no cubre costo), **+3 a +17 bp** @4h, **+19 a +47
bp** @8h. El grueso del efecto monetizable está a 4–8 h de holding.

**5. En cuántos símbolos.** 63 en el pool, pero **`frac_sym_pos` 0.33–0.49** — la
mayoría de símbolos *no* muestran el efecto individualmente; lo cargan una minoría.
`top5_conc` 0.42–0.46 (cerca del umbral de riesgo serio del brief, 50%).

**6. Estabilidad temporal.** **Débil.** TRAIN (dic-2025 → ~abr): plano o
ligeramente positivo (sin efecto). VAL: negativo. OOS: negativo fuerte y creciente.
Mismo signo VAL/OOS, pero **ausente en TRAIN** → posible dependencia de régimen (la
segunda mitad tuvo más downside).

**7. Controles que sobrevivió.** matched-control (OI plano) ≈ 0 → el efecto **es**
de OI, no de "un movimiento grande cualquiera". residual-BTC ≈ raw → no es beta de
BTC. Placebo temporal +24h: limpio a ≤2h, pero **filtra 30–40% del efecto a 8–24h**.

**8. Qué falta para promoverlo a estrategia (→ Round 10).**
- **Decisivo:** descomponer el efecto por **régimen** dentro de la muestra (BTC
  uptrend / downtrend / chop). Si el drift-negativo solo aparece en régimen
  bajista/lateral y se apaga o invierte en alcista → es beta de régimen, **FAILED**.
  Si es negativo en los tres → efecto estructural, se construye.
- Análisis **por símbolo**: ¿son 5 nombres o 40? (arregla la pregunta de
  concentración). Si depende de <10 → penalizar fuerte.
- Net con **funding real** incluido (holding 4–8 h cruza settlements): usar
  `funding_hist` ya ingerido.
- Ejecutable: entrada `open[t+1]`, no close-to-close.
- Ventana con un **régimen alcista limpio** (extender klines/OI hacia atrás si
  Binance Vision lo permite, o esperar más historia forward).

---

## 4. VEREDICTO DEL ROUND

**¿Encontramos información nueva y reproducible en OI + flujo + precio con magnitud
suficiente para una estrategia económicamente relevante?**

**Parcialmente — y la respuesta económica es NO (todavía).**

- **SÍ hay información nueva y reproducible:** `dOI` predice el drift forward de
  forma incremental (t −7.7), sobrevive matched-control y residual-BTC, y el signo
  es consistente VAL→OOS. **Taker flow y funding NO aportan nada incremental** —
  eso cierra H15 y H16 como hipótesis y ahorra trabajo futuro.
- **NO alcanza el umbral económico:** el efecto solo es net-positivo a 4–8 h de
  holding, está **ausente en TRAIN** (posible régimen), tiene `symPos < 0.5`,
  `conc ≈ 0.45`, y el placebo filtra 30–40% a horizontes largos. No es promovible a
  CANDIDATE.

**Clasificación:**
- `dOI` incremental effect (H13-C A/D consolidado) → **PARK** (real, reproducible
  VAL/OOS, mecanismo explicable; bloqueado por: prueba de régimen pendiente,
  concentración, TRAIN vacío).
- H13-C B, C → **FAILED** (sin efecto).
- H15 (taker como discriminador) → **FAILED** (taker no incremental).
- H16 (funding×OI) → **FAILED** (funding no incremental; momentum domina).
- M15 (reaction-beta persistente) → **FAILED** (spread ≈ random; sin independencia
  cross-sectional).

**El gran avance durable de Round 9 no es una estrategia: es que el OI histórico 5m
de los 63 símbolos está ingerido y validado**, y que sabemos que **el edge de
posicionamiento, si existe, está en `dOI` y no en taker ni funding**.

---

## 5. NEXT MOVE (automático, Round 10)

**Test de régimen del efecto `dOI`** — el único que decide si PARK pasa a CANDIDATE
o a FAILED:

1. Clasificar cada barra por régimen de BTC (p.ej. pendiente de la media 7d de BTC:
   up / down / flat; o realized-vol tercil).
2. Recomputar H13-C A y D (y el OLS de `dOI`) **por régimen**.
3. Criterio de kill: si `dOI` solo es predictivo (signo negativo) en régimen
   down/flat y se apaga o invierte en up → **FAILED, es beta de régimen**.
   Si mantiene signo y magnitud (>costo a 4–8h) en los tres → construir: análisis
   por símbolo, net con funding real, entrada `open[t+1]`, y recién ahí candidata.
4. En paralelo: análisis de concentración por símbolo del efecto `dOI` (¿5 o 40
   nombres?).

Si el test de régimen mata `dOI`: quedan **sin explorar con el OI nuevo** —
`toptrader_ls_pos` / `global_ls_acct` (ratios long/short de posición y de cuentas,
que son un ángulo de posicionamiento distinto de ΔOI y **no se tocaron este
round**) y la **aceleración** de OI (2ª derivada). Ésos serían Round 11.

---

## Infraestructura

Colectores live OI (`open_interest_collector.py`, PID 15164) y liquidaciones
(`_run_liq_tracker.py`, PID 32924) **vivos**, desacoplados del agente. El backfill
de este round vive en `binance_vision_clean.db` (research, no producción). **Sin
tocar producción, StrategyProfiles, agente, SL/TP, capital.**
