# M18 — KILL OR CONFIRM (Round 8)

**Fecha:** 2026-09-10
**Objetivo del round:** no salvar M18. Determinar si es REAL. Verdict exactamente
uno de PROMISING / PARK / FAILED.
**Script:** `agent/backtest/r8_m18_kill.py` · **Scratch:** `scratch_r8_m18_kill.json`
**Regla aplicada:** costos plausibles determinados ANTES de mirar si M18
sobrevive; todo (universo, buckets, dirección, horizontes, splits) pre-declarado
por construcción — no hay ni un parámetro fiteado sobre el PnL.

---

## VEREDICTO: **FAILED**

M18 no sobrevive a la reconstrucción causal. Se cumplen **todas** las
condiciones de kill del brief simultáneamente:

| Condición de kill (brief §17) | ¿Se cumple? | Evidencia |
|---|---|---|
| El control explica el mismo efecto | **SÍ** | C4 (misma señal, forward **+24 h después**): +5.9 / +9.6 / +12.2 bp @30/45/60 m, CI excluye 0 — **igual o mayor** que el efecto "real". El open RTH no aporta nada incremental. |
| No sobrevive temporalmente | **SÍ** | TRAIN +5.8 bp @10m → **VAL −5.4 @30m / −11.5 @60m** → OOS +17 @30m. El signo **se da vuelta** entre bloques. |
| Depende de pocos símbolos | **SÍ** | `top5_conc` = 0.46–1.0 en todos los cortes; en los estratos de liquidez **0.82–1.0** (1 símbolo carga el estrato hi-liq entero). |
| No supera costos plausibles | **SÍ** | Mejor efecto *pooled* en cualquier horizonte = **+8 bp @30m** (CI apenas excluye 0). Costo round-trip realista = **~26 bp**. Neto ≈ **−18 bp**. |
| No alcanza el objetivo económico | **SÍ** | Aun tomando el bloque/horizonte más favorable (OOS +17 bp @30m, cherry-pick contradicho por VAL): ~300 eventos/mes × $300 × (17−26) bp ≈ **−$8/mes**. |
| El coeficiente incremental del gap es 0 | **SÍ** | OLS `signed_fwd ~ 1 + |gap| + preopen + trail_vol`: `t(β_gap)` = 0.48 / 0.98 / 0.11 @30/45/60m (no significativo); a 5–10 m es **negativo** (t −3.2, wrong sign). Lo poco que predice está en `preopen`, no en el gap. |

M18 era un artefacto de: (a) barras de 15 m, (b) entrada en el **print de
apertura** (no ejecutable), (c) cortes de tercil elegidos post-hoc, (d)
concentración en 3.5 meses dominados por su primera mitad. Con 5 m + entrada
causal + universo ex-ante + controles, el efecto se desarma.

---

## 1. Definición exacta (reconstrucción causal)

Para cada símbolo `S` del universo y cada día hábil NYSE `D`:

- `rth_open(D)` = 13:30 UTC si `D ∈ [2026-03-08, 2026-11-01)` (EDT), si no 14:30 UTC (EST).
- `rth_close(D)` = `rth_open + 6.5 h`; en early-close = `rth_open + 3.5 h`.
- `prevD` = último día hábil con datos antes de `D` (≤ 5 días calendario).
- `prior_close_px` = **close del bar de 5 m que termina en `rth_close(prevD)`**.
- `open_px` = **open del bar de 5 m que empieza en `rth_open(D)`** (bar `t0`).
- `gap = ln(open_px / prior_close_px)` — conocido en el instante `rth_open(D)`.
- **Entrada = `open` del bar `t0+1`** (= `rth_open + 5 min`), estrictamente
  posterior a la señal. `assert t[t0+1] > rth_open`.
- Salidas: `open[t0+1+k]` para `k ∈ {1,2,3,6,9,12}` → holding **5/10/15/30/45/60 min**
  desde la entrada; más `to_close` (close del bar que termina en `rth_close(D)`).
- **Dirección:** `gap > 0` (gap up) → **SHORT**; `gap < 0` (gap down) → **LONG**.
  Retorno con signo `+` = "la reversión pagó". Lados reportados por separado.

**Exclusiones ex-ante:** `|gap| > 15 %` (acción corporativa: 12 eventos
descartados); primeros 5 días hábiles de cada símbolo; cualquier bar faltante
(0 eventos perdidos por esto).

**Self-tests automáticos (pasan):** mapeo DST para 2026-05-06 (EDT 13:30/20:00),
2026-02-09 (EST 14:30/21:00), 2026-07-02 (early close 17:00 UTC); feriados
2026-05-25 / 2026-07-03 y sábados → sin evento; `prior_close_ts < open_ts`;
`entry_ts > signal_ts`; ningún horizonte usa un bar futuro no disponible.

---

## 2. Dataset

`agent/data/binance_vision_clean.db` → `klines_5m` (OHLCV 5 m, `open_time` UTC ms,
grilla :00/:05, 24/7, sin gaps verificado). Ventana **2025-12-01 → 2026-08-17
(congelada)**. Perps de acción/ETF tokenizados listados May 2026 en su mayoría;
algunos desde Feb 2026 (TSLA, INTC, HOOD, AMZN, COIN, CRCL, MSTR, PLTR).

## 3. Universo (reglas ex-ante, congeladas antes del PnL)

- Ticker (sin `USDT`) = acción US listada **o** ETF de equity US.
- **Excluidos:** `XAU`, `XAG` (commodities, mercado ~24 h → sin "cierre" real),
  `SPX` (índice ligado a futuros ~24 h), `COMP` (ambiguo).
- ≥ 25 días hábiles de historia utilizable; salteo de los primeros 5 días.
- Liquidez ex-ante = mediana de `$/5m` en el RTH de los **primeros 20 días
  hábiles** del símbolo; se excluye `< $1 000/5m` (0 símbolos cayeron acá).

**Resultado:** 36 candidatos → **35 usados**, **2 837 eventos** (1 421 gap up /
1 416 gap down), rango de fechas de evento **2025-12-08 → 2026-08-17**.
Terciles de liquidez: 12 hi / 11 mid / 12 lo; umbrales $/5m = 14 427 (q1) /
45 284 (q2).

## 4. Metodología causal

- Todo z-score / percentil / vol trailing es causal (`[t-win, t)`), no se usa
  ningún dato ≥ instante de entrada para definir gap / símbolo / threshold /
  dirección / salida.
- Agregación: **cluster bootstrap sobre símbolos** (3 000 resamples, ponderado
  por nº de eventos por símbolo) → media bp, IC 5–95 %, `frac_sym_pos`,
  `top5_conc`, mitades temporales.
- Splits temporales 50/25/25 por fecha de evento: TRAIN / VAL / OOS. Reglas
  congeladas por construcción (no hay fitting), así que el split mide
  **persistencia del signo**, no generalización de parámetros.

## 5. Costos (determinados antes de mirar el resultado — NO elegidos para salvar M18)

| Componente | Base | Fuente / razonamiento |
|---|---|---|
| Fee taker | **5.0 bp/lado** → 10 bp RT | Binance USDⓈ-M estándar, **sin** asumir descuento BNB/VIP ni promo maker. El brief prohíbe asumir maker fills. |
| Spread (cruzar) | **~5 bp/lado** → 10 bp RT | Perps de equity ~$100, menos líquidos que BTC; medio-spread al cruzar 3–8 bp/lado en la ventana de apertura (volátil). |
| Slippage + impacto + latencia | **~3 bp/lado** → 6 bp RT | $150–450 de nocional en la barra de apertura; market order con fill ~seguro pero a peor precio. |
| **Round-trip realista** | **~26 bp** (banda: 16 optimista / 26 base / 36 pesimista med-lo liq) | |

Maker (limit en la apertura): **no se asume** — adverse selection (te llenan
cuando el mercado va en contra) y no-fill cuando va a favor. Si se modelara
optimista (2 bp/lado maker + 0 slippage) el RT sería ~10 bp — y **M18 igual no
supera** eso de forma estable (ver §6/§7).

## 6. Gross edge

| Corte | Mejor horizonte | Gross bp | IC excl 0 | Comentario |
|---|---|---|---|---|
| Pooled, entrada `open[t0+1]` | 30 m | **+8.1** | sí (apenas: [2.2, 14.3]) | 45 m +7.5 (IC incl 0); resto ≈ 0; `to_close` −15.4 (continuación) |
| **Frictionless** (desde `open[t0]`, NO ejecutable) | 45 m | +16.5 | sí | +7–9 bp del "edge" R7 vivía en los primeros 5 min inalcanzables |
| Gap up (short) | 45 m | +13.3 | sí | 30 m +7.5 (IC incl 0); `symPos` ≈ 0.51 (moneda al aire entre símbolos) |
| Gap down (long) | 30 m | +8.6 | sí | mitades 13.3 → 3.9; `to_close` −23.5 |
| Bucket |gap| 0.5–1.5 % | — | ~0–3.5 | **todos los horizontes IC incluyen 0** — el bucket "medio" está muerto |
| Bucket |gap| 1.5–5 % | 30 m | +15.9 | mitades 25.1 → 6.6; +0.5 @60m; `to_close` −28 |
| Bucket |gap| 5–15 % | 45 m | +31.2 | `conc` 0.80, n=242, IC casi toca 0, signo caótico por horizonte |

**Monotonicidad gap→reversión: NO existe.** Bucket 1 (0.5–1.5 %) es plano;
sólo el bucket 2 muestra algo a 30–45 m y decae a la mitad entre mitades y se
da vuelta a 60 m. La "monotonía en terciles" de R7 era artefacto de barras 15 m
+ entrada en el print + cortes de tercil.

## 7. Net edge

`net = gross_pooled_best − RT_cost = 8.1 − 26 ≈ −18 bp` por trade.
Con costo optimista (10 bp): `8.1 − 10 ≈ −2 bp`. Con el frictionless
inalcanzable (16.5 bp) y costo optimista: `+6.5 bp` — pero es no ejecutable y
sólo en la primera mitad de la muestra.

**Ningún escenario ejecutable y temporalmente estable da net > 0.**

## 8. Controles

| Control | Qué mide | Resultado (30/45/60 m, bp) | Lectura |
|---|---|---|---|
| **C1 pre-open move** | reversión del movimiento de los 90 min PREVIOS al open (sin gap) | −2.1 / −7.8 / −12.4 (IC excl 0 en 45–60 m) | el movimiento pre-open **continúa**; el "edge" no es reversión de nada obvio |
| **C2 pseudo-gap 17:00 UTC** | mismo mecanismo a mitad de sesión | −1.1 / −6.4 / −3.7 | limpio (no reproduce el signo +) |
| **C3 pseudo-gap 02:00 UTC** | mismo mecanismo en hora muerta | −1.2 / −3.8 / −4.1 (IC excl 0) | limpio |
| **C4 mismo gap, forward +24 h** | ¿la "reversión" necesita el open RTH? | **+5.9 / +9.6 / +12.2 (IC excl 0)** | **KILL** — reproduce el efecto entero sin catalizador de apertura |
| **C5 matched (vol + move 18 h)** | ¿el gap aporta sobre "un move grande cualquiera"? | +0.5 / +1.9 / +2.0 (IC incl 0) | el gap **no** aporta incremental |
| **OLS incremental** | `β_gap` con controles | `t` = 0.48 / 0.98 / 0.11 | el gap no es significativo; `β_preopen` sí (t 3.5 @60m) |

C4 + C5 + OLS coinciden: **lo que M18 captura es una mean-reversión lenta y
débil del movimiento overnight que se ve igual con cualquier offset de 24 h y
no es incremental a "un movimiento grande cualquiera".** No hay mecanismo de
apertura RTH.

## 9. Placebo

- **Temporal (C4, +24 h):** reproduce el efecto → placebo FALLA (mata M18).
- **Pseudo-eventos fuera de RTH (C2/C3):** limpios (no dan el signo +), pero eso
  sólo confirma que el número de M18 no es un artefacto puramente horario — no
  lo salva, porque C4 ya mostró que tampoco es del open.
- **Matched (C5):** el evento real **no supera** al control matcheado.

## 10. Temporal stability

| Bloque | n | 10 m | 30 m | 45 m | 60 m | to_close |
|---|---|---|---|---|---|---|
| TRAIN (≤ mediana×0.5) | 461 | +5.8 (excl 0) | débil | — | — | — |
| **VAL** | 899 | −1.8 | **−5.4** | −2.8 | **−11.5 (excl 0)** | **−39.6 (excl 0)** |
| OOS | 1 477 | +2.4 | +17.2 (excl 0) | +17.6 (excl 0) | +11.5 (excl 0) | −11.3 |

**El signo se invierte entre VAL y OOS.** Un efecto real no hace eso. Además el
frictionless muestra mitades h1≫h2 en todos los cortes (ej. 45 m: 25.6 → 7.3):
el "edge" está concentrado en un régimen, no es estacionario.

## 11. Liquidity stratification

| Tercil | n símbolos | 30 m (bp) | IC excl 0 | `top5_conc` | `symPos` |
|---|---|---|---|---|---|
| hi | 12 | +10.3 | sí | **0.82–1.0** | 0.33–0.75 |
| mid | 11 | +7.8 | **no** | 0.84–1.0 | 0.64–0.73 |
| lo | 12 | +5.6 | **no** | **~1.0** | 0.50–0.75 |

En **todos** los estratos la concentración top-5 es 0.8–1.0: uno o dos símbolos
cargan casi todo el PnL. El único estrato con IC que excluye 0 (hi-liq) tiene
`conc` 1.0 y `symPos` 0.33 a 5 m → literalmente un símbolo. Brief: "depende de
pocos símbolos → FAILED".

## 12. Gap buckets

Ver §6. **No hay monotonicidad real.** Buckets absolutos fijados ex-ante
(0.5 % / 1.5 % / 5 % / 15 %): el bucket medio (0.5–1.5 %) está muerto; el bucket
2 (1.5–5 %) tiene algo a 30–45 m que decae a la mitad entre mitades y se da
vuelta a 60 m; el bucket 3 (5–15 %) es ruido concentrado (n=242, conc 0.8).

## 13. Direction

Asimétrico y ambos lados débiles: gap-up (short) sólo significativo a 45 m
(+13.3 bp); gap-down (long) sólo a 30 m (+8.6 bp). El horizonte "ganador"
difiere por lado → multiple-testing. `symPos` ≈ 0.5 en ambos (los símbolos se
reparten mitad y mitad). No surge una asimetría explotable ex-ante.

## 14. Holding period

Grilla 5/10/15/30/45/60 m + to_close. El único horizonte con IC pooled que
excluye 0 es **30 m** (+8.1 bp). 5/10/15 m ≈ 0; 60 m ≈ 0; to_close **negativo**
(−15 bp, el gap continúa hacia el cierre). No hay un holding donde la edge se
concentre de forma robusta — 30 m es el único candidato y no sobrevive §10.

## 15. Monthly monetization

Escenario más favorable defendible (OOS, 30 m, pooled — sabiendo que VAL lo
contradice):

| Ítem | Valor |
|---|---|
| Gross bp/trade | +17 (OOS) / +8 (pooled, honesto) |
| Costo RT | 26 bp (base) / 16 bp (optimista) |
| Net bp/trade | −9 (OOS/base) … −8 (pooled/base) … +1 (OOS/optimista) |
| Eventos/mes (universo ~15 símbolos tradeables × ~21 días) | ~300 |
| Nocional/trade | $300 |
| **PnL mensual** | **≈ −$8/mes** (base) · **≈ +$4/mes** (OOS × costo optimista) |
| Capital | $300–900 (3 slots) |
| Return on capital | ≈ 0 % / negativo |

**No alcanza ≥ 150 USDT/mes con ≤ 450 USDT.** Ni cerca, en ningún escenario
que no sea a la vez cherry-pick de bloque temporal Y de costo.

## 16. OOS

Ver §10. Reglas congeladas por construcción. TRAIN débil-positivo, **VAL
negativo**, OOS positivo. El requisito "supera claramente los controles" no se
cumple: C4 (+12 bp @60m) ≈ OOS (+11.5 bp @60m).

## 17. Verdict — **FAILED**

M18 no es un mecanismo real de apertura RTH. Es una mean-reversión lenta, débil
(~8 bp pooled), no incremental al gap, concentrada en pocos símbolos y en un
régimen temporal, que un placebo de +24 h reproduce entera y que no supera
costos plausibles ni el objetivo económico. **Cerrada. No se buscan más
variantes de M18.**

---

## Siguiente mecanismo (automático, brief §18)

Del ranking de Round 7, el de mayor expected value no ejecutado:

> **M15 — "reaction-beta" persistente ante shocks comunes.**
> Actor: estructura de microliquidez estable por símbolo. Catalizador: shock
> común (BTC o market-wide). Variable: ranking de over/under-reacción de cada
> símbolo al shock. Hipótesis: el ranking **persiste** entre shocks → un símbolo
> que siempre sobre-reacciona es shorteable en el próximo shock (y viceversa).
> Horizonte 1–6 h post-shock. Datos: en mano (klines 5m/15m, 8.5 meses). No es
> catch-up (H18) ni momentum (H8): es un **factor de dispersión de reacción**.

Se ejecuta en Round 9 con el mismo rigor (universo ex-ante, cluster bootstrap,
placebo temporal, matched control, splits temporales, costos plausibles, kill
conditions explícitas).

---

## En paralelo — DATA EXPANSION (auditoría, no ingesta este round)

**Hallazgo principal (verificado en vivo):**
`https://data.binance.vision/data/futures/um/daily/metrics/<SYMBOL>/<SYMBOL>-metrics-YYYY-MM-DD.zip`
**es accesible desde este entorno** (200, ZIP, sin tocar `api/fapi.binance.com`).
Descargado y verificado `BTCUSDT-metrics-2026-08-01.zip`:

| Propiedad | Valor |
|---|---|
| Contenido | `BTCUSDT-metrics-2026-08-01.csv`, 288 filas (5 min, 24 h completo) |
| Columnas | `create_time` (UTC, `YYYY-MM-DD HH:MM:SS`, grilla :00/:05), `symbol`, `sum_open_interest` (unidades base), `sum_open_interest_value` (USD), `count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`, `count_long_short_ratio`, `sum_taker_long_short_vol_ratio` |
| Resolución | **5 min** (igual que el colector live) |
| Qué desbloquea | **OI histórico 5 m para TODOS los perps** en la ventana congelada (2025-12 → 2026-08) + top-trader L/S ratio + global L/S account ratio + taker buy/sell vol ratio |

**Impacto:** H13-C (OI/price divergence → squeeze), H15 (evento conjunto
OI×taker×precio) y toda la familia OI **dejan de estar gateadas por tiempo** —
la historia se baja hoy, del mismo CDN que construyó `binance_vision_clean.db`,
a la misma resolución. No hay que esperar a que el colector live llegue a 70 d
en octubre, y además se obtiene **breadth completo** (todos los símbolos, no los
13 con ≥90 % que tiene el colector) y un **régimen bajista real** (dic 2025).

**Checklist de validación antes de ingerir (brief §15):**
1. ☐ Enumerar cobertura: qué símbolos tienen archivos y fecha más temprana (el
   listado S3 no parseó vía WebFetch; probar fecha por fecha o con cliente HTTP
   propio desde IP no compartida).
2. ☐ Confirmar `create_time` = inicio del bar (no fin) → alinear con
   `klines_5m.open_time`. (Consistente con `openInterestHist period=5m` que usa
   el colector live; confirmar con 1 reconciliación.)
3. ☐ Reconciliar `sum_open_interest` del archivo vs la tabla `open_interest`
   live en un rango que solape (deberían coincidir salvo redondeo).
4. ☐ Verificar `futures/um/monthly/fundingRate/<SYMBOL>/` de la misma forma
   (misma familia de CDN, muy probablemente disponible) → desbloquearía M8b con
   ≥ 90 d de funding history.
5. ☐ Documentar el script de descarga (tipo el de `binance_vision_clean.db`),
   con dedup por `(symbol, create_time)` y checksums `.CHECKSUM` si existen.

**Otras fuentes gratis del inventario de Round 7 (sin cambios, no auditadas este
round):** Binance announcements (listings/delistings — para M1), token unlock
calendars (DefiLlama), spot-ETF flows (Farside), Bybit/OKX archives.

**Colectores live:** OI (`open_interest_collector.py`, PID 15164) y liquidaciones
(`_run_liq_tracker.py`, PID 32924) **vivos y frescos** (ambos a 2026-09-10
15:17 UTC, 0 h de atraso), desacoplados del agente (caído). Sin cambios de
infraestructura este round.
