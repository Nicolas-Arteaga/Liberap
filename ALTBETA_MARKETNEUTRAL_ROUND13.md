# ROUND 13 — DRIFT ALTS vs BTC: ¿PRIMA DE RIESGO SISTEMÁTICA O BETA DISFRAZADO?

**Fecha:** 2026-09-16 · Sin descargas nuevas (14.5 meses ya ingeridos, 45 símbolos
ex-ante de R11-R12) · Script: `agent/backtest/r13_altbeta.py` · Rebalanceo
**semanal** (56 rebalanceos, 2025-06-01 → 2026-08-17), diario resampleado
causalmente desde `klines_clean` 15m.

## ECONOMIC RESULT

`Validated net PnL/month: $0` (mejor backtest real: **−$11/mes**)
`Target: $150/month`
`Target achieved: NO`

---

## 1. Hipótesis testeadas

- **A/B — Betting-against-beta (market-neutral):** LONG N=5 de menor beta
  trailing-30d vs BTC, SHORT N=5 de mayor beta, book cubierto con una pata de BTC
  para llevar el beta neto a 0. Ambas direcciones evaluadas (también N=8 como
  sensibilidad diagnóstica, no elegida post-hoc).
- **C — Cross-sectional residual momentum:** LONG N=5 con mayor momentum
  idiosincrático (retorno no explicado por beta·BTC, 14d), SHORT N=5 con menor.
  Mismo hedge. Ambas direcciones evaluadas.
- **E — Placebo:** bucket aleatorio (mismo N, mismo procedimiento de hedge, sin
  usar beta ni momentum) — control obligatorio para separar selección real de
  drift/dispersión genérica.

## 2. Resultado TRAIN / VAL / OOS (hedged, bp por semana; split 50/25/25 por fecha)

| Portfolio | port_beta medio | TRAIN | VAL | **OOS** | WR | PF |
|---|--:|--:|--:|--:|--:|--:|
| Betting-against-beta (long low-β / short high-β) | −2.07 | +93.3 | +99.8 | **−1310.4** | 0.45 | 0.64 |
| Betting-against-beta INVERTIDO | +2.07 | −93.3 | −99.8 | **+1310.4** | 0.55 | 1.57 |
| Residual-momentum (long fuerte / short débil) | +0.19 | +145.1 | +54.4 | **−506.2** | 0.52 | 0.93 |
| Residual-momentum INVERTIDO | −0.19 | −145.1 | −54.4 | **+506.2** | 0.48 | 1.07 |
| **PLACEBO random-bucket (sin ranking)** | −0.06 | +69.1 | −66.3 | **+561.2** | 0.46 | **1.74** |

**El placebo aleatorio da un resultado igual o mejor que cualquier portfolio con
selección real.** Ninguna dirección (ranking real ni su espejo) supera de forma
consistente al azar.

## 3. Por qué: todo está concentrado en 6 semanas

| Trimestre | Betting-against-beta | Residual-momentum | **Placebo** |
|---|--:|--:|--:|
| 2025Q3 (11 sem) | +337 | +38 | +289 |
| 2025Q4 (14 sem) | +10 | +312 | −82 |
| 2026Q1 (12 sem) | −33 | +5 | −26 |
| 2026Q2 (13 sem) | −552 | +222 | −290 |
| **2026Q3 (6 sem)** | **−1534** | **−1557** | **+1737** |

**Las 6 semanas de 2026Q3 (las últimas del dataset) dominan por completo el
resultado de TODOS los portfolios, real y placebo, en direcciones opuestas según
el sesgo de cada uno.** Eso es la firma de un evento de **dispersión cross-sectional
extrema** (todo altcoin se movió mucho, en direcciones distintas) — no de un
factor de beta o momentum. Un libro aleatorio la captura igual de bien (o mejor)
que uno "inteligente".

## 4. PnL neto mensual, drawdown, trades — Sim Económica (Test F)

Capital ≤450 USDT, N=5+5 patas + 1 pata de cobertura BTC (11 patas), costo
round-trip conservador 24 bp sobre TODO el libro cada semana (cota superior,
turnover completo), funding real incluido, apalancamiento explícito y
contabilizado:

| Variante | Notional/pata | NET/mes | maxDD | WR | Meses +/− |
|---|--:|--:|--:|--:|--:|
| Betting-against-beta 1x | $41 | **−$16** | $317 | 0.46 | 7/7 |
| Betting-against-beta 2x | $82 | −$32 | $633 | 0.46 | 7/7 |
| Betting-against-beta 3x | $123 | −$48 | $950 | 0.46 | 7/7 |
| Residual-momentum 1x | $41 | **−$11** | $255 | 0.45 | 6/8 |
| Residual-momentum 2x | $82 | −$21 | $511 | 0.45 | 6/8 |
| Residual-momentum 3x | $123 | −$32 | $766 | 0.45 | 6/8 |

**Las 6 configuraciones pierden dinero.** El apalancamiento no ayuda — escala
proporcionalmente la pérdida junto con el drawdown (2x duplica la pérdida y el
DD, 3x la triplica). Con $450 y 11 patas, el nocional por pata (\$41–\$123) además
deja el costo de 24 bp/semana pesando fuerte sobre el book: incluso si el
"alpha" fuera cero exacto, el costo solo ya produce −$X/mes por fricción pura.

**Trades:** 56 semanas × 11 patas = 616 ejecuciones sobre la ventana completa
(~40/mes). No hay drawdown catastrófico por posición individual (tamaños
pequeños), pero tampoco hay PnL positivo que lo justifique.

## 5. Controles / placebos aplicados

- ✅ **Ambos sentidos evaluados** ex-ante (A/B y su espejo, C y su espejo) — sin
  elegir dirección después de ver el resultado.
- ✅ **Placebo de bucket aleatorio** con el mismo procedimiento de hedge — **falla
  el criterio explícito**: el placebo iguala o supera al portfolio "real".
- ✅ **Descomposición beta/hedge explícita** (requisito central del round): se
  separó RAW (libro sin cubrir) de HEDGE-LEG (contribución pura de la cobertura
  de BTC) de HEDGED (residual). La cobertura por sí sola mueve cientos de bp —
  confirma que el libro sin cubrir tenía una exposición direccional oculta grande
  (`port_beta` de hasta ±2), y que **incluso después de neutralizarla no aparece
  alpha estable**.
- ✅ **Estabilidad temporal por trimestre** — muestra la concentración extrema en
  2026Q3 en vez de esconderla en un promedio pooled.
- ✅ **Sensibilidad de N** (5 vs 8 patas) — mismo patrón, sin mejorar.
- ⚠️ No se testeó sensibilidad de ventana de beta/momentum (30d/14d fijos,
  predeclarados) — no aplica probar más variantes de un mecanismo ya matado por
  placebo.

## 6. Veredicto por hipótesis

| Hipótesis | OOS | Placebo | Económico | Veredicto |
|---|---|---|---|---|
| Betting-against-beta | −1310 bp (inestable, se invierte) | placebo igual/mejor | −$16 a −$48/mes | **FAILED** |
| Residual-momentum | −506 bp (inestable, se invierte) | placebo igual/mejor | −$11 a −$32/mes | **FAILED** |

# ROUND 13 VERDICT

# FAILED

No PARK: el criterio explícito de FAILED del propio brief ("si el placebo
reproduce el resultado → FAILED") se cumple de forma literal — el placebo
aleatorio (+149.5 bp promedio, PF 1.74) es **mejor** que ambos portfolios con
selección real. No hay "alpha OOS demostrado" que parkear: lo único que hay en
OOS es un evento de dispersión de 6 semanas que un book al azar captura igual.

## 7. Qué aprendimos (lo importante de este round)

1. **El drift bajista estructural que contaminó R12 no era beta ni momentum** —
   era **dispersión cross-sectional extrema concentrada en las últimas 6 semanas
   del dataset (2026Q3)**. Cualquier long-short de altcoins (elegido bien, mal, o
   al azar) queda dominado por ese evento.
2. **La selección (ranking por beta o por momentum idiosincrático) no aporta
   nada** sobre elegir al azar — el componente de *stock-picking* no es donde
   está la información, si es que hay alguna.
3. **$450 con 11 patas y rebalanceo semanal es estructuralmente caro**: ~$41–123
   de nocional por pata deja el costo de fricción (24 bp/semana) pesando fuerte;
   un book market-neutral diversificado no es capital-eficiente a esta escala.
4. Esto reorienta la búsqueda: si hay algo capturable, probablemente está en
   **CUÁNDO estar expuesto** (timing de dispersión/volatilidad), no en **QUÉ
   símbolo elegir** dentro del universo.

## 8. Hipótesis concreta para Round 14

**Dispersion-regime timing (una sola hipótesis, no una lista):** en vez de un
book cross-sectional permanente, testear una estrategia que **solo se expone**
(long-short balanceado y/o mayor tamaño) durante semanas de **dispersión
cross-sectional realizada anormalmente alta** (medida ex-ante y causal: p.ej.
desviación estándar de los retornos semanales de los 45 símbolos, en su propio
percentil histórico causal), y queda **fuera del mercado o con exposición mínima**
el resto del tiempo. Esto ataca directamente lo que R13 reveló: el edge (si
existe) no está en elegir el símbolo correcto, sino en identificar ex-ante los
períodos de dispersión donde CUALQUIER exposición long-short se vuelve rentable
— y filtrar los períodos tranquilos donde solo se pagan costos. Mismo rigor
(TRAIN/VAL/OOS, placebo de calendario aleatorio, sim económica causal ≤450,
kill inmediato si el placebo reproduce el resultado).

Si Round 14 también falla, la evidencia acumulada (13 rounds, ~35 mecanismos
distintos sobre precio/flujo/OI/funding/L/S/beta/momentum/dispersión, todos
FAILED o económicamente nulos) empezará a ser suficiente para considerar,
recién ahí, que el objetivo no es alcanzable con este universo/datos — pero
Round 14 se ejecuta primero.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
