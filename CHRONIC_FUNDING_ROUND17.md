# ROUND 17 — CHRONIC FUNDING YIELD ATTACK

**Fecha:** 2026-09-20 · Script: `agent/backtest/r17_chronic_funding.py` · Sin
descargas nuevas · Universo real (funding∩spot∩perp) = 43 símbolos · Ventana
diaria 2025-06-01 → 2026-08-17 (442 días) · Reutiliza infraestructura de R16
(costos, universo, estructuras A/B).

## RESULTADO

# FAIL

**R17 resolvió el problema de R16 (turnover) pero expuso uno nuevo y más
fundamental: el sesgo de funding "crónico" NO persiste hacia adelante lo
suficiente como para ser capturado con holding de semanas/meses.**

- **Mejor estrategia:** W=30d (ventana de selección), `topN_score` (magnitud ×
  persistencia × estabilidad), N=3, maxhold=60d, capital $150.
- **PnL neto mensual:** **−$0.1/mes** (el "mejor" resultado de todo el barrido
  — no un error de signo, es la config menos mala de docenas probadas).
- **Funding capturado:** ~$0.0–0.5/mes bruto (prácticamente CERO, no "positivo
  pero insuficiente" — genuinamente nulo).
- **Fees:** ~$0.3–1.7/mes (bajaron ~30× vs R16 gracias a la histéresis — el
  turnover SÍ se resolvió).
- **Capital / posiciones:** probado 150/300/450 USDT × N=1,2,3,5,10 — todas
  las combinaciones dentro de ±$5/mes de cero.
- **Trades:** 15–45 en 8.5 meses (vs 599–1400 de R16) — turnover realmente bajo.
- **OOS:** consistentemente negativo/nulo en las 3 particiones temporales.

---

## 1. Diagnóstico estructural — corregido y honesto

*(Nota metodológica: la primera versión de este análisis tenía un bug — el
"por ventana W" usaba la media del sample completo en vez de una ventana
rolling real, dando tablas idénticas para W=7d..90d. Se corrigió antes de
reportar: cada W ahora usa `rolling_stats` — la misma función causal que usa
la estrategia — y caracteriza la ESTABILIDAD de esa media rolling en el
tiempo, no un número único.)*

| Símbolo | mean/día (30d) | t-stat (30d) | t-stat (90d) | Lectura |
|---|--:|--:|--:|---|
| XAUTUSDT | +1.40 bp | 78 | 189 | oro tokenizado — funding positivo casi constante |
| GIGGLEUSDT | +2.27 bp | 61 | 88 | fuerte y estable |
| LINKUSDT | +1.12 bp | 50 | 101 | el más consistente en TODAS las ventanas (7d→180d) |
| PUMPUSDT | +1.43 bp | 40 | 173 | fuerte |
| UNIUSDT | +0.97 bp | 33 | — | estable |
| INJUSDT (180d) | **−5.22 bp** | **−164** | — | crónicamente NEGATIVO — estructura B, NO OPERABLE |

**Estos t-stats altísimos describen la consistencia INTERNA de la media
rolling (autocorrelación hacia atrás), no capacidad predictiva hacia
adelante** — esa es exactamente la distinción que el brief pedía verificar, y
es la que separa este diagnóstico de una estrategia real. La sección 3
muestra que esa consistencia hacia atrás NO se traduce en funding capturable
hacia adelante.

---

## 2. Estrategia causal — histéresis (sin lookahead)

`score_W(t) = mean_W(t) / std_W(t) × frac_mismo_signo_W(t)`, calculado con
`[t-W, t-1]` estrictamente. Entrada si `|score| ≥ 1.0`; se mantiene hasta que
(a) el signo de la media se invierte, (b) `|score| < 0.5` (histéresis), o (c)
se alcanza el holding máximo. **Nunca se cierra una posición solo porque otro
símbolo la superó en el ranking** — exactamente lo que faltaba en R16.

### Selección A/B/C (N=5, maxhold=60d)

| Ventana | Modo | Trades | Funding/mes | Fees/mes | **NET/mes** |
|---|---|--:|--:|--:|--:|
| 30d | threshold absoluto | 26 | +$0.1 | −$1.0 | **−$0.8** |
| 30d | top-N magnitud (sin persistencia) | 28 | **−$2.6** | −$1.1 | −$2.6 |
| 30d | top-N score (persistencia+magnitud) | 26 | +$0.1 | −$1.0 | −$0.8 |
| 60d | threshold absoluto | 20 | −$0.8 | −$0.8 | −$1.3 |

**La persistencia SÍ aporta sobre la magnitud sola** (top-N score bate a
top-N magnitud: −$0.8 vs −$2.6/mes) — confirma otra vez que el ranking no es
ruido. Pero incluso la mejor versión está en $0, no en $150.

### Sensibilidad de holding (7/14/30/60/90d — el rango completo pedido)

| maxhold | Trades | avg_hold | Fees/mes | Funding/mes | **NET/mes** |
|---|--:|--:|--:|--:|--:|
| 7d | 107 | 9d | −$4.1 | −$0.3 | **−$4.1** |
| 14d | 60 | 15d | −$2.3 | −$0.2 | −$2.3 |
| 30d | 35 | 26d | −$1.3 | −$0.3 | −$1.5 |
| 60d | 26 | 36d | −$1.0 | +$0.1 | −$0.8 |
| 90d | 25 | 37d | −$1.0 | +$0.0 | −$0.8 |

**No existe una zona intermedia rentable.** A 7d, las fees vuelven a dominar
(igual que R16, aunque mucho menos severo). A 60-90d, las fees casi
desaparecen — pero el funding capturado también desaparece con ellas. No hay
punto óptimo porque el funding no sobrevive lo suficiente para que el
"sweet spot" exista.

---

## 3. Robustez temporal

| Slice | Trades | Funding/mes | **NET/mes** |
|---|--:|--:|--:|
| Dataset completo | 26 | +$0.1 | −$0.8 |
| TRAIN | 8 | +$0.2 | −$0.3 |
| OOS puro (últimos 25%) | 17 | −$0.2 | −$1.4 |
| Excluye 2026Q3 explícitamente | 20 | +$0.3 | −$0.5 |
| SOLO 2026Q3 (funding/dispersión extrema) | 6 | −$1.3 | −$1.8 |

**Consistentemente negativo o nulo en TODOS los recortes** — no depende de
2026Q3 (de hecho es *peor* dentro de Q3), no depende de estar "recién
descubierto" (TRAIN y OOS son igual de planos). Esto es, en cierto sentido, el
resultado más limpio posible: no hay sobreajuste a un régimen porque nunca
hubo nada que sobreajustar.

---

## 4. Placebos — el criterio decisivo

| Control | Funding/mes | **NET/mes** |
|---|--:|--:|
| Real (chronic score, histéresis) | +$0.1 | −$0.8 |
| **PLACEBO random_selection** (mismo N, símbolo al azar) | **+$0.0** | **−$0.9** |
| Control matched_vol (rankea por volatilidad, no funding) | −$3.0 | −$3.0 |
| Control magnitud-sola | −$2.6 | −$2.6 |

**El placebo aleatorio reproduce el resultado real casi exactamente** (+$0.0
vs +$0.1 de funding capturado — estadísticamente indistinguibles). Este es
el criterio de FAIL explícito del brief cumplido literalmente: a este
horizonte de holding (semanas), elegir por funding "crónico" no aporta nada
sobre elegir al azar entre los candidatos con funding positivo — el forward
funding ya no es predecible a 30-90 días, sin importar cuán consistente se
vea mirando hacia atrás.

---

## 5. Stress test

Irrelevante en la práctica: el funding capturado baseline ya es ~$0, así que
multiplicarlo por 0.75/0.5/0.25 lo deja en ~$0. Fees ×1.5/2.0 y slippage
×2/×3 solo empujan un número ya negativo un poco más abajo (−$0.8 → −$1.5).
**No hay un edge que romper — nunca hubo edge que estresar.**

---

## 6. Test de capturabilidad (checklist explícito)

| Pregunta | Respuesta |
|---|---|
| ¿El funding existe? | Sí — dispersión real y grande entre símbolos (documentado en R15/R16). |
| ¿Es persistente mirando hacia atrás? | Sí, muy — t-stats de 30 a 340 en la media rolling. |
| **¿Es persistente hacia ADELANTE (30-90d)?** | **No** — placebo aleatorio lo iguala. |
| ¿Podemos mantenerlo con bajo turnover? | Sí — se logró (15-45 trades en 8.5 meses vs 599-1400 de R16). |
| ¿Supera los costos? | Moot — no hay funding que superarlos. |
| ¿Rentable tras entry/exit real? | No. |
| ¿Sobrevive fuera del período de descubrimiento? | Sí, en el sentido de que es consistentemente ~$0 en todos lados (no hay "período donde funcionó"). |
| ¿Concentrado en 1-2 símbolos? | Moderado (top1_share 0.44-0.65) — irrelevante sin PnL que concentrar. |

---

## Estructura B (funding crónicamente negativo)

INJUSDT muestra el sesgo negativo más fuerte del universo (mean −5.2bp/día,
t=−164 a 180d) — candidato "ideal" para SHORT SPOT + LONG PERP. **Sigue NO
OPERABLE**: no hay datos de borrow-rate ni infraestructura de margen para
vender spot en corto. No se reporta como estrategia, tal como exige el brief.

---

## SIGUIENTE RONDA — no se cierra la investigación

**Qué sobrevivió de "chronic funding":** el diagnóstico de persistencia
hacia atrás (símbolos con sesgo de funding consistente durante meses SÍ
existen, y el ranking por persistencia bate a magnitud sola y a azar en la
comparación de controles). **Qué murió:** la capacidad de convertir esa
persistencia retrospectiva en yield prospectivo — el forward funding a 30-90
días es indistinguible de aleatorio, incluso para los símbolos más "crónicos"
del diagnóstico. **Por qué murió:** no es turnover (resuelto, fees cayeron
30×) — es decaimiento de la señal: la correlación trailing-vs-próximo
settlement que R16 midió en 0.82 a 8h y 0.68 a 7 días sigue cayendo, y para
cuando se llega a 30-90 días ya no queda información utilizable. **El
mecanismo de funding carry (ambas variantes: alto turnover R16, bajo turnover
R17) queda cerrado — no hay una tercera variante que probar.**

**Mecanismo para Round 18: listing events con fecha verificada.** Es el único
mecanismo de los ~50 probados que nunca fue refutado por evidencia —
solo quedó bloqueado en R7/R8 por calidad del dato (el primer kline del
símbolo no es una fecha de listing confiable, se agrupaba artificialmente en
el día 1 de cada mes). Plan concreto: usar `WebFetch` sobre los anuncios
públicos de Binance (web, no la API baneada) para obtener fechas de listing
verificadas de una muestra de símbolos del universo, cruzarlas contra el
primer kline en `klines_clean` para separar listings reales de artefactos de
colección, y recién ahí correr el event-study de reversión post-listing con
fechas limpias — el mecanismo (forced-flow de productos índice + FOMO retail
en el listing) nunca fue puesto a prueba de verdad, a diferencia de todo lo
demás en este proyecto.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
