# H13 PILOT — OI / PRICE DIVERGENCE EVENT STUDY

**Fecha:** 2026-09-06
**Naturaleza:** PILOTO. **No concluyente por diseño.** 33 días de OI, un solo
régimen de mercado, 45 símbolos todos alt/smallcap. El objetivo era dimensionar
el efecto y decidir si vale re-testear con ≥ 70 días, no demostrar rentabilidad.
Script: `agent/backtest/h13_pilot.py`. Salida: `scratch_h13_pilot.json`.

---

## VEREDICTO: **PARK**

- **A, B, D → FAILED** (por la regla pre-declarada): el **placebo temporal
  reproduce el efecto**. El retorno forward positivo a 12–24 h no depende del
  evento OI/precio: es **drift alcista market-wide** de la ventana. Un bar
  cualquiera 48 h después muestra lo mismo o más.
- **C (precio ↓ + OI ↑) a 1–4 h → PARK.** Es el único cuadrante/horizonte con
  un efecto **específico del evento**: el placebo NO lo reproduce (placebo 1h =
  −24 bp, signo opuesto), signo estable en las dos mitades del período (+63/+49
  a 1h), mismo signo en 71 % de los símbolos. Pero el **efecto incremental vs
  la muestra matcheada tiene IC que incluye 0** ⇒ no se puede afirmar que el
  bar-evento supere a un bar con la misma caída previa y misma vol pero sin
  expansión de OI. La mayor parte del rebote puede ser mean-reversion genérica
  tras una caída fuerte; el componente "OI ↑" **aporta un +30 bp incierto**.

No alcanza para CONTINUE. No merece FAILED (mecanismo plausible, señal cruda
limpia de placebo, estable). **Se re-evalúa con el protocolo congelado cuando
OI ≥ 70 días** (§ "Qué necesitamos").

---

## 1. Parámetros (pre-declarados, congelados antes de ver resultados)

| Param | Valor | Razón |
|---|---|---|
| Barra | **1 h** | OI nativo 5 m → resampleado a 1 h (último valor ≤ cierre); `klines.db` 1h cubre 99 % de los 45 símbolos en la ventana |
| Lookback del evento | **4 h** | ventana de shift de posicionamiento accionable |
| Ventana z-score | **7 d (168 barras)**, rolling **causal** | estandarizar dOI% y ret_prior contra su propia historia reciente |
| Umbral | **\|z(dOI%)\| ≥ 1.0 AND \|z(ret_prior)\| ≥ 1.0** | mov de precio **y** de posicionamiento, ambos no triviales |
| Cooldown | **4 h** por símbolo | evitar autocorrelación de eventos solapados |
| Cuadrantes | A(r+,OI+) B(r+,OI−) C(r−,OI+) D(r−,OI−) | interpretables económicamente, sin grid |
| Horizontes | **1, 4, 12, 24 h** forward (log-ret desde close[T]) | fijos; no se agregó ninguno por dar mejor |
| Placebo | evento + **48 h** | si reproduce ⇒ es drift, no OI |
| Matched control | ≤ 3 barras del mismo símbolo, sin evento, `rv_24h` ±25 % y `\|ret_prior\|` ±25 %, a ≥ 24 h de cualquier evento | aísla "¿fue la divergencia o solo que el mercado se movía?" |
| Costos | fee RT 8 bp + slippage/lado {0, 2, 5} bp | |
| Bootstrap | 2000 resamples sobre eventos **y** sobre símbolos | IC; el de símbolos respeta la correlación cross-sectional |

**Nada de esto se tocó después de mirar resultados. Sin grid search.**

---

## 2. Descripción de la muestra

| Ítem | Valor |
|---|---|
| Ventana OI | 2026-08-04 → 2026-09-07 (**33.3 días**) |
| Símbolos | **45** con ≥ 90 % de cobertura de OI. **Todos alt/smallcap/stock-perp.** NO hay BTC/ETH/SOL en el colector. |
| Precio | `klines.db` 1h, `is_final=1`, 99 % de cobertura en la ventana |
| Barras escaneadas | 34 404 |
| **Eventos totales** | **1 516** (tasa 4.4 % de barras) |
| Por cuadrante | **A 595 · D 493 · B 213 · C 215** |
| Por régimen BTC (ret 24 h) | flat 1 111 (73 %) · up 315 (21 %) · **down 90 (6 %)** |
| Concentración | top-5 símbolos = 16 % de los eventos (no patológica) |
| Distribución temporal | eventos repartidos sobre los 33 días; sin clustering en pocos días |
| Taker flow | disponible solo los primeros ~13 días y 38/45 símbolos (`taker_flow` de Binance Vision termina 2026-08-17) → registrado donde había, **no usado en el veredicto** |

**Limitación estructural dominante:** un solo régimen (risk-on suave, 73 % flat
/ 21 % up / 6 % down). Cualquier "efecto" a 12–24 h que sea signo-positivo es
sospechoso de ser el drift de la ventana.

---

## 3. Resultados por cuadrante (bp = puntos básicos, 1 bp = 0.01 %)

Formato: **raw** = media del retorno forward de los eventos; **CI90** =
percentiles 5/95 del bootstrap sobre eventos; **incr** = evento − media de sus
matched controls; **placebo** = mismo cálculo desde T+48 h; **half0/half1** =
media en la 1.ª / 2.ª mitad del período; **sym_same** = fracción de símbolos
(con ≥ 5 eventos) cuyo signo coincide con el pooled.

### Quadrant A — precio ↑ + OI ↑ (longs nuevos entrando)

| h | raw (bp) | CI90 | incr vs matched (bp) | incr CI | placebo (bp) | half0/half1 | sym_same | tras 5 bp slip |
|---|---|---|---|---|---|---|---|---|
| 1h | +11.6 | [−19.5, 42.7] | +50.8 | [20, 81] | +23.1 | +24 / +3 | 0.62 | −6.4 |
| 4h | +34.6 | [−34.6, 98.9] | +105.9 | [32, 182] | +53.0 | −16 / +69 | 0.67 | +16.6 |
| 12h | +129.8 | [34, 226] | +221.0 | [93, 350] | **+138.3** | +97 / +152 | 0.67 | +111.8 |
| 24h | +192.5 | [63, 319] | +330.3 | [156, 510] | **+155.9** | +182 / +200 | 0.64 | +174.5 |

**Lectura:** raw y "incr" enormes a 12–24 h, IC excluye 0. **Pero el placebo
también es enorme** (+138 / +156 bp) — 72–81 % del raw. La regla pre-declarada
dice: si el placebo reproduce el efecto ⇒ **FAILED**. El "incr vs matched" tan
grande, con placebo igual de grande, indica que la **muestra matcheada está
sesgada a la baja** por una razón no-OI (probablemente: los bars con gran
subida previa pero sin trigger de OI son sistemáticamente de peor calidad de
datos / menor liquidez). No es evidencia de edge de OI. **A = FAILED.**

### Quadrant B — precio ↑ + OI ↓ (short covering / exhaustion)

| h | raw | CI90 | incr | incr CI | placebo | half0/half1 | sym_same |
|---|---|---|---|---|---|---|---|
| 1h | −4.0 | [−25, 18] | +32.1 | [1, 62] | +22.6 | +13 / −32 | 0.57 |
| 4h | +51.4 | [1, 107] | +40.9 | [−15, 96] | +64.9 | +103 / −35 | 0.71 |
| 12h | +77.2 | [−12, 168] | +8.8 | [−115, 132] | +110.2 | +181 / −95 | 0.67 |
| 24h | +148.2 | [22, 280] | +141.0 | [−16, 297] | +198.8 | **+359 / −202** | 0.76 |

**Lectura:** placebo ≥ raw en casi todos los horizontes. `half0/half1` se da
vuelta violentamente (+359 → −202 a 24 h). El "exhaustion" predicho (retorno
forward **negativo**) **no aparece** — de hecho es positivo, y es drift +
inestabilidad. **B = FAILED.**

### Quadrant C — precio ↓ + OI ↑ (shorts nuevos agresivos → squeeze)  ← el único vivo

| h | raw (bp) | CI90 | incr vs matched (bp) | incr CI | placebo (bp) | half0/half1 | sym_same | tras 5 bp slip (sobre raw) |
|---|---|---|---|---|---|---|---|---|
| **1h** | **+56.3** | **[14.6, 99.6]** | +32.2 | **[−4, 70]** | **−24.4** | **+63 / +49** | **0.71** | +38.3 |
| **4h** | **+58.6** | **[9.5, 107.1]** | +36.1 | **[−19, 94]** | +10.5 | **+90 / +27** | **0.71** | +40.6 |
| 12h | +3.1 | [−76, 87] | +16.8 | [−84, 118] | +30.8 | +36 / −30 | 0.57 | −14.9 |
| 24h | −42.0 | [−150, 58] | −92.5 | [−222, 38] | +52.6 | +94 / −181 | 0.33 | +24.0 |

**Lectura:** a **1–4 h** hay un rebote de **+56–59 bp**:
- IC90 del raw **excluye 0** en ambos horizontes.
- **El placebo NO lo reproduce** (1h: placebo −24 bp, signo opuesto; 4h:
  placebo +10 bp, ≈ 1/6 del raw). Esto es lo que distingue a C de A/B/D.
- Signo **estable en las dos mitades** (1h: +63/+49; 4h: +90/+27, decae).
- Mismo signo en **71 %** de los símbolos.
- A 12–24 h **se apaga** (raw +3, luego −42) → efecto de corto plazo, no drift.
- **Pero el incremental vs matched tiene IC que incluye 0** ([−4, 70] y
  [−19, 94]). Es decir: una caída fuerte de precio rebota ~24 bp **igual sin
  expansión de OI**; el componente "OI ↑" añade un **+30–36 bp incierto**.

**Mecanismo compatible:** shorts nuevos y agresivos entrando en la caída (OI ↑
mientras precio ↓) quedan en un posicionamiento unilateral y frágil ⇒ cualquier
rebote fuerza cobertura ⇒ squeeze de 1–4 h. Es exactamente la hipótesis de
`ALPHA_HYPOTHESIS_LEDGER.md § H15`, visible acá en el margen.

### Quadrant D — precio ↓ + OI ↓ (longs capitulando / deleveraging)

| h | raw | CI90 | incr | incr CI | placebo | half0/half1 | sym_same |
|---|---|---|---|---|---|---|---|
| 1h | −3.6 | [−22, 15] | −19.3 | [−45, 4] | −3.2 | −1 / −6 | 0.44 |
| 4h | +4.2 | [−36, 44] | −56.3 | [−107, −5] | +20.9 | −2 / +9 | 0.56 |
| 12h | +59.5 | [−4, 122] | −1.4 | [−89, 86] | +38.3 | +72 / +49 | 0.68 |
| 24h | +120.3 | [26, 213] | +12.0 | [−118, 140] | **+132.6** | +130 / +112 | 0.71 |

**Lectura:** el "incr" a 1–4 h es **negativo** (el evento D rinde **peor** que
un matched down-move) — leve señal de continuación de la caída, pero IC roza 0
y a 24 h el raw positivo = placebo positivo = drift. **D = FAILED** como fuente
direccional; el retazo de continuación a 4 h (incr −56 bp, CI [−107, −5])
queda anotado como sub-hallazgo débil.

---

## 4. Relevancia económica

Costo round-trip estimado = fee **8 bp** + 2 × slippage. Para estos 45 símbolos
(alt/smallcap, y el trade ocurre **justo después de un movimiento brusco**, el
peor momento de spread), 5 bp/lado es **optimista** — el número real es
probablemente 10–20 bp/lado.

| Señal candidata | efecto usable | tras 8 bp fee | tras +2 bp/lado | tras +5 bp/lado | veredicto económico |
|---|---|---|---|---|---|
| C 1h (raw) | +56 bp | +48 | +44 | +38 | positivo sobre el raw |
| **C 1h (incremental, lo que aporta OI)** | **+32 bp, IC [−4, 70]** | +24 | +20 | **+14, IC cruza 0** | **NO MONETIZABLE con seguridad** |
| C 4h (incremental) | +36 bp, IC [−19, 94] | +28 | +24 | +18, IC cruza 0 | **NO MONETIZABLE con seguridad** |

**El efecto crudo de C sobrevive costos; el efecto incremental (la parte que
realmente atribuible a OI) no lo hace con certeza.** Y con slippage realista
para estos nombres, ni el crudo es seguro. ⇒ **NOT MONETIZABLE** en el estado
actual de datos; el mecanismo merece re-test, no despliegue.

---

## 5. Estabilidad

- **Entre símbolos:** C 1h/4h → 71 % de los símbolos (n=21 con ≥5 eventos)
  mismo signo. A/D en 0.44–0.68 (ruido). B razonable pero domina el placebo.
- **Entre períodos (mitades de 33 d):** C 1h estable (+63/+49). C 4h mismo
  signo, decayendo (+90/+27). Todo lo demás a 24 h se da vuelta o es drift.
- **Entre regímenes BTC:** no se pudo particionar con sentido — solo 6 % de los
  eventos en `btc_down`. **Este es el hueco más grande:** el mecanismo de
  squeeze debería ser más fuerte en caídas de mercado, y esa muestra casi no
  existe en la ventana.

---

## 6. Entregables pedidos — checklist

| Ítem | Dónde |
|---|---|
| cantidad total de eventos | § 2 — **1 516** |
| eventos por cuadrante | § 2 — A 595 / D 493 / B 213 / C 215 |
| símbolos | § 2 — 45, todos alt/smallcap, sin majors |
| cobertura | § 2 — OI ≥ 90 %, precio 99 % |
| distribución temporal | § 2 — repartida, sin clustering |
| retorno posterior / previo / volatilidad | § 3 (tablas) + `scratch_h13_pilot.json` |
| controles (matched) | § 3 columna "incr vs matched" |
| placebo | § 3 columna "placebo" |
| efecto bruto | § 3 columna "raw" |
| efecto incremental | § 3 columna "incr" |
| intervalos de incertidumbre | § 3 columnas CI (bootstrap 2000, sobre eventos y sobre símbolos) |
| estabilidad entre símbolos | § 5 |
| estabilidad entre períodos | § 5 |
| efecto en bps / tras costos / sensibilidad 0-2-5 bp / fee RT | § 4 |
| decisión | § 0 — **PARK** |

---

## 7. Qué necesitamos para el test formal (cuando OI ≥ 70 d)

1. **≥ 70 días de OI** (hoy 33). ETA ~mediados de octubre 2026 si el colector
   sigue continuo. El único cuadrante vivo (C) tiene solo 215 eventos ⇒ con
   ~2× historia, ~450 eventos ⇒ IC del incremental se aprieta y recién ahí se
   puede afirmar/negar que OI aporta sobre la mean-reversion pura.
2. **Al menos un régimen bajista real en la muestra.** La ventana actual es
   93 % flat/up. El mecanismo de squeeze de C se prueba en caídas.
3. **Majors en el colector de OI.** Hoy no hay BTC/ETH/SOL. Sin un ancla
   líquida, todo el universo es de nombres donde el slippage real mata el
   efecto. **Acción sugerida:** agregar BTC/ETH/SOL + top-20 por volumen al
   `open_interest_collector.py` (no toca producción; es el colector de research).
4. **Medición de spread/slippage real** en la ventana post-movimiento para
   estos nombres (usar `orderbook_ofi` o el spread de las klines) para reemplazar
   el supuesto de 5 bp.
5. Congelar el protocolo del test formal **ahora** (§ 8) para no re-derivar
   parámetros con el resultado a la vista.

---

## 8. Protocolo formal H13 — CONGELADO (ejecutar solo con OI ≥ 70 d)

Idéntico al piloto (§ 1) salvo:
- **Universo:** símbolos con ≥ 90 % de cobertura de OI sobre **todo** el
  período de ≥ 70 d, **más** BTC/ETH/SOL si el colector los tiene para entonces.
- **Splits temporales:** 50 % TRAIN (define nada — params ya congelados) /
  25 % VALIDATION / 25 % FINAL-OOS. Los tres se calculan; VALIDATION y
  FINAL-OOS se miran una sola vez.
- **Foco:** Quadrant **C** a **1 h y 4 h** como hipótesis primaria (el resto
  como control/exploración, con corrección BH sobre las 16 celdas).
- **Costos:** slippage real medido, no supuesto. Gate económico a ese valor.
- **Regla de veredicto formal:** CONTINUE a Fase 4 (freeze de estrategia) solo
  si C 1h **y** C 4h tienen **incremental vs matched con IC 90 % que excluye 0**
  en VALIDATION **y** FINAL-OOS, mismo signo en ≥ 60 % de símbolos, y el efecto
  incremental tras costos reales ≥ 15 bp. Si no ⇒ FAILED (H13 y H15 juntas se
  cierran; no hay H13.x de rescate).

---

## Conclusión del piloto

- **H13 no muere, pero no habilita nada todavía.** 3 de 4 cuadrantes son drift
  de una ventana risk-on (el placebo los reproduce).
- **El único hilo real es Quadrant C (precio ↓ + OI ↑) a 1–4 h:** rebote de
  ~56 bp, limpio de placebo, estable — pero la fracción atribuible a OI (vs
  mean-reversion pura tras una caída) es **incierta** (+30 bp, IC cruza 0) y
  **no monetizable con confianza** a costos realistas.
- **Decisión: PARK.** Re-test con el protocolo congelado del § 8 cuando haya
  ≥ 70 días de OI y al menos un tramo bajista. Prioridad de infraestructura:
  agregar majors al colector de OI.
