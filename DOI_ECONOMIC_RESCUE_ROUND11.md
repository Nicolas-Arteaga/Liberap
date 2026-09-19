# ROUND 11 — dOI ECONOMIC RESCUE-OR-KILL

## ¿TENEMOS UNA ESTRATEGIA ≥150 USDT/MES?

# NO

Con la historia extendida (2025-06 → 2026-08, 14.5 meses, universo restringido a
los 45 símbolos que ya cotizaban antes de TRAIN), la señal `dOI` (H13-C A/D,
SHORT):

- **No es estacionaria.** El signo del efecto @4h **cambia mes a mes** (de −26 bp
  en jul-2025 a +46 bp en ago-2026, cruzando 0 al menos 4 veces) y **era del signo
  opuesto antes de 2026**: régimen UP, primera mitad de la muestra = **−12 bp**;
  segunda mitad = **+54 bp**.
- **Sigue muy concentrada.** Aun con los 45 símbolos limpios (ya sin LAB/ESPORTS/
  GIGGLE de R10), quitar top-5 baja el edge UP∪FLAT@4h de 12.2 → 3.7 bp (−70%).
- **No supera costos de forma capturable.** Sim causal con entrada `open[t+1]`,
  RT 24 bp + funding real, capital ≤450 USDT y concurrencia: **todos los grupos
  pierden dinero salvo "solo UP"**, y "solo UP" da como máximo **+$77/mes** (8h,
  1 slot $450) — por debajo del objetivo y además con selección post-hoc del
  régimen ganador.

---

## MAXIMUM VALIDATED NET PNL

| Categoría | Valor | Comentario |
|---|---|---|
| **validated** (sobrevive estacionariedad + concentración + capturabilidad) | **$0 / mes** | nada sobrevive las tres |
| **paper** (sim causal con costos y capital, pero selección de régimen post-hoc y no estacionario) | **≈ $77 / mes** | UP-only, hold 8h, 1 slot $450, PF 1.82, 9/14 meses positivos, pero P50 mensual +$27 con P95 +$382 → depende de 1-2 meses de cola |
| **statistical** (asociación real pero no operable) | `t(dOI) = −7 a −9` en régimen UP, ΔR² +1–2% sobre la ventana extendida | el vínculo estadístico dOI↔retorno forward en UP es real y se replica; su **signo económico no es estable en el tiempo** |
| **invalid** (lo que se presentó antes como logro y no lo es) | los "$505–$1234/mes" de R10 | eran close-to-close sin restricción de capital, mezclando régimenes y sobre la mitad de la muestra donde el signo estaba "encendido" |

**El máximo PnL mensual realmente considerable como válido bajo el protocolo es
$0.** El mejor número "paper" ($77/mes) no llega a 150 y no es estacionario.

---

## Tablas

### FASE 2 — Matriz Régimen × TRAIN/VAL/OOS (A+D SHORT, bp; `*` = CI bootstrap excl 0)

Corte extendido: TRAIN ≤ 2026-01-22 · VAL ≤ 2026-05-06 · OOS > 2026-05-06.

| Régimen | split | 15m | 30m | 1h | 2h | 4h | 8h | 24h |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| **UP** | train (n~1829) | −4* | −3 | +2 | **−6** | **−12** | **−16** | +28 |
| **UP** | val (n~805) | +1 | +2 | +3 | +12* | +18* | +37* | +91* |
| **UP** | oos (n~676) | +13* | +21* | +35* | +46* | +96* | +173* | +255* |
| **FLAT** | train (n~5585) | +0 | −0 | −1 | +5* | +8* | +23* | +23 |
| **FLAT** | val (n~1094) | +0 | −0 | **−5*** | **−13*** | **−12*** | **−17*** | −8 |
| **FLAT** | oos (n~3001) | +4* | +11* | +13* | +14* | +23* | +28 | +38 |
| **DOWN** | train (n~3086) | −5* | +4 | +6 | +9 | +11 | −3 | +31 |
| **DOWN** | val (n~1163) | +3 | −2 | +4 | +3 | −6 | **−25*** | −11 |
| **DOWN** | oos (n~1831) | −0 | −3 | −5 | −8 | −4 | +26 | +93* |

→ **Ningún régimen mantiene el signo en los tres bloques.** UP: negativo en TRAIN,
positivo en VAL/OOS. FLAT: positivo en TRAIN, **negativo en VAL**, positivo en OOS.
DOWN: sin patrón.

### FASE 3 — Estacionariedad: A+D SHORT @4h por período (ALL | UP | FLAT | DOWN, bp)

**Por mes:**
| mes | ALL | UP | FLAT | DOWN |
|---|--:|--:|--:|--:|
| 2025-07 | **−26*** | **−75*** | −10 | −32 |
| 2025-08 | −5 | −1 | **−24*** | +25* |
| 2025-09 | −2 | −9 | −5 | +20* |
| 2025-10 | +15 | −21 | +9 | +37 |
| 2025-11 | +18* | +9 | +57* | −10 |
| 2025-12 | +44* | +93* | +42* | +14 |
| 2026-01 | +8* | −18 | +34* | −11 |
| 2026-02 | **−9*** | −22 | −0 | −8 |
| 2026-03 | +3 | +27* | −15 | −11 |
| 2026-04 | −8 | +29* | **−35*** | +10 |
| 2026-05 | −0 | +67* | −5 | −13 |
| 2026-06 | +21* | +92* | +45* | −10 |
| 2026-07 | +32 | +128 | +0 | +25 |
| 2026-08 | +46* | na | +59* | +28 |

**Por trimestre (ALL @4h):** 2025Q3 **−12\*** · 2025Q4 +25\* · 2026Q1 +0 · 2026Q2 +9\* · 2026Q3 +36\*
**Por mitad (@4h):** ALL — H1 +5 (CI incl 0), H2 +14\*. **UP — H1 −12, H2 +54\*.**

→ **La respuesta a "¿existía la señal antes de abril de 2026?" es NO.** El signo
oscila mes a mes y en la primera mitad de la muestra (incluido el régimen UP) era
del signo contrario. No es un alpha estacionario.

### FASE 3b — OLS beta-control, ventana extendida (`signed_fwd ~ 1 + dOI + btc_fwd + mkt_fwd + retlong + rv`)

| Régimen | h | t(dOI) | ΔR² |
|---|---|--:|--:|
| UP | 2h | **−9.24** | +0.020 |
| UP | 4h | **−6.94** | +0.011 |
| FLAT | 2h | +4.51 | +0.002 |
| FLAT | 4h | +5.34 | +0.002 |
| DOWN | 4h | +7.27 | +0.004 |

→ El vínculo estadístico dOI↔retorno en **UP** es real y se replica en la ventana
larga (t −7 a −9). Pero es una **asociación con signo económico no estacionario**
(H1 −12 bp / H2 +54 bp): estadísticamente presente, no operable.

### FASE 4 — Concentración (leave-top-k, UP∪FLAT SHORT @4h, universo restringido 45 sym)

| Exclusión | edge (bp) | PF | nSym | net (bp, −24 costo) | n |
|---|--:|--:|--:|--:|--:|
| Ninguna | +12.2 | 1.14 | 45 | −11.8 | 12 990 |
| Top 1 | +9.1 | 1.11 | 44 | −14.9 | 12 811 |
| Top 3 | +5.8 | 1.07 | 42 | −18.2 | 12 397 |
| Top 5 | **+3.7** | 1.05 | 40 | −20.3 | 12 013 |
| Top 7 | +2.2 | 1.03 | 38 | −21.8 | 11 370 |

→ Quitar 5 de 45 símbolos borra el 70% del edge. **FAILED como alpha
cross-sectional generalizable.**

### FASE 6-7 — Sim económica causal (entrada `open[t+1]`, SHORT, RT 24 bp + funding real, capital ≤450, concurrencia)

| Grupo | hold | slots×$ | trades/mo | **NET/mo** | avg bp | med bp | WR | PF | mDD $ | meses +/− | m[P5/P50/P95] |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| UP∪FLAT | 8h | 2×$225 | 131 | **−$22** | −7.4 | −15.7 | 0.47 | 0.94 | 613 | 6/8 | [−215/−34/188] |
| FLAT | 8h | 1×$450 | 59 | −$9 | −3.5 | −18.9 | 0.46 | 0.97 | 637 | 5/9 | [−134/−41/226] |
| ALL | 8h | 3×$150 | 228 | −$28 | −8.3 | −15.9 | 0.46 | 0.94 | 791 | 4/10 | [−196/−26/201] |
| **UP** | **8h** | **1×$450** | **23** | **+$77** | +75.3 | +14.3 | 0.53 | 1.82 | 137 | **9/5** | [−50/**+27**/+382] |
| UP | 4h | 1×$450 | 35 | +$65 | +41.1 | −5.1 | 0.49 | 1.49 | 306 | 7/7 | [−143/−3/432] |
| UP | 8h | 2×$225 | 42 | +$64 | +67.3 | +24.9 | 0.54 | 1.69 | 105 | 8/6 | [−61/+25/+299] |

→ **Todo pierde dinero salvo "solo UP".** El mejor caso (UP / 8h / 1 slot) da
**+$77/mes** — pero (a) < 150, (b) mediana mensual +$27 con P95 +$382 → depende de
1–2 meses de cola, (c) "operar solo el régimen UP" es selección post-hoc del
subconjunto donde el signo estuvo encendido, (d) FASE 3 muestra que UP fue **−12
bp en la primera mitad**.

---

## ROUND 11 VERDICT

# FAILED

`dOI` (H13-C A/D, SHORT) **no es un alpha estacionario ni económicamente
explotable**:

1. **Estacionariedad — FAILED.** El signo del efecto cambia mes a mes y **era
   opuesto antes de 2026** (UP: H1 −12 bp / H2 +54 bp; jul-2025 −75 bp). La
   extensión de historia — ejecutada AHORA como pedía el brief — **empeoró** el
   caso: mostró que lo de R9/R10 era un fenómeno de la segunda mitad de 2026.
2. **Concentración — FAILED.** Quitar 5 de 45 símbolos borra el 70% del edge.
3. **Magnitud económica — FAILED.** Mejor caso capturable = +$77/mes (UP-only,
   post-hoc, tail-dependiente) < 150. El resto pierde dinero.

Lo que queda como conocimiento: existe una **asociación estadística real**
dOI↔retorno forward en el régimen UP (OLS t −7 a −9, replicada en 14.5 meses),
pero con **signo económico no estacionario** → no operable.

**Se mata `dOI`.** No se intenta rescatar con dOI+funding / dOI+taker / dOI+L/S /
dOI+ML / dOI con más thresholds (prohibido por el brief y sin sentido: el problema
es el signo no estacionario, no la falta de features).

## ECONOMIC VERDICT

**NO puede alcanzar razonablemente ≥150 USDT/mes con ≤450 USDT.** Máximo PnL
`validated` = $0. Máximo `paper` = ~$77/mes (no estacionario, post-hoc,
tail-dependiente).

## NEXT ACTION

**Round 12: probar la divergencia posicionamiento retail vs smart-money** —
`global_ls_acct` (skew long/short de CUENTAS = multitud retail) contra
`toptrader_ls_pos` (skew long/short de POSICIÓN de los top traders). Ambos ya
ingeridos, 5m, 14.5 meses, 45 símbolos con cobertura completa. Es un mecanismo
**económicamente distinto de ΔOI** (participante obligado: el retail crowdeado que
provee liquidez de salida a los top traders cuando se liquida), no una variación
cosmética. Mismo rigor que R10/R11: definición congelada ex-ante, régimen BTC,
TRAIN/VAL/OOS sobre los 14.5 meses, beta-control, leave-top-k, sim económica con
capital ≤450 — y **kill inmediato** si falla estacionariedad o capturabilidad,
sin variaciones.

---

## Datos nuevos de este round (durables)

- `binance_vision_clean.db`: `oi_metrics` extendido a **2025-06-01 → 2026-08-17**
  (6.8M filas, 45 símbolos con cobertura completa desde 2025-06, resto desde su
  listing) + `klines_clean` 15m extendido a 2025-06 (6.68M filas). `funding_hist`
  ya cubría desde 2025-12. 9 símbolos sin OI pre-dic-2025 (listaron después).
- Todo desde `data.binance.vision` (CDN), nunca api/fapi.
- Sin tocar producción / perfiles / SL-TP / agente / capital.
