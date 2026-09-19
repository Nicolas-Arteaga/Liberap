# DIAGNÓSTICO CAUSAL — sesgo de Win Rate del motor (MA Slope Caso 3)

**Fecha:** 2026-09-06
**Objetivo:** aislar exactamente qué componente del motor convierte operaciones
que realmente fueron ganadoras en perdedoras. No es una reparación. No se
optimizó nada. No se ajustó ningún parámetro contra el ground truth.

**Veredicto: DIAGNOSTICADO.**
Existe una causa cuantitativamente demostrada, y NO es la que asumía el
progress-log (entrada a cierre de vela 5m que voltea TP→SL). Esa hipótesis
queda **REFUTADA**. La causa real está en la **capa de selección de
candidatos / competencia por cupos**, aguas abajo de la detección del patrón
y aguas arriba del ciclo de vida del trade.

---

## 1. Waterfall causal — REAL WR ~53% → REPLAY WR ~10%

Caída total a explicar: **−43 pp** de win rate (net-positivo), y PF 1.85 → 0.81.

| # | Capa del motor | WR tras esta capa | PF | Contribución | Evidencia |
|---|---|---|---|---|---|
| 0 | **REAL (producción, ground truth)** | ~53% | 1.85 | — | `scratch_gate_v4_results.json` (n=70, net +$65.14) |
| 1 | **Detección del patrón** (`_evaluate_ma_geometry_profile`) | ~53% | — | **0 pp** | `diag_caso3_detection.py`: el motor dispara Caso 3 **en el bar exacto de la señal (±2 min) en 37/38 trades reales con datos**. La detección NO pierde las señales. |
| 2 | **Ciclo de vida del trade** (entrada + SL/TP intrabar + granularidad 5m) | ~50% | ~2.7–3.9 | **≈ −3 pp** | `diag_caso3_wr.py` factorial (n=38): alimentar las señales REALES al código de entrada/SL/TP del motor da PF 3.5–3.96, net +$81–87. Los 4 modelos de entrada (cierre de vela, next-open, prev-close, precio real) dan el mismo resultado (PF 2.77–3.96). **Sigue siendo GANADORA.** |
| 3 | **Modelado de salida / profit-lock** (motor mantiene hasta zombie-timeout 48h; producción tiene monitor 5-min que bloquea ganancia) | ~42% | ~1.8 | **≈ −8 pp** | 4/19 ganadores reales → perdedores en el replay, **todos por zombie-timeout**, con MFE mediana 2.3% que producción capturó y el replay devolvió. Contribuidor **secundario**. |
| 4 | **Competencia por 3 cupos + veto stack + máscaras occupied/BTC** | **~10%** | **0.81** | **≈ −32 pp** | El replay completo llena sus 3 cupos con un conjunto de 42 trades **casi disjunto** del real: solo **3 de 45 pares (símbolo, día) reales sobreviven**. Esos 42 trades de reemplazo son 90% perdedores (38L/4W). **PRIMARIA — explica ~75% de la caída total.** |

**Lectura:** si el motor simplemente ejecutara las señales reales de Caso 3
(mismo símbolo, misma hora, mismo SL/TP estructural), reproduciría una
**ganadora PF ~2.7–3.9**. La ganadora se destruye porque el motor **no opera
esas señales** — su pipeline de cartera (detectar ~200 candidatos por loop →
3 cupos → orden FIFO/prioridad → máscara occupied → máscara BTC → stack de
vetos) admite un conjunto distinto, mayoritariamente perdedor.

---

## 2. Tabla REAL vs replay por trade (resumen)

Fuentes: `scratch_caso3_gt.json` (45 trades reales, join de
`scratch_all_trades_p2.csv` [tiempos exactos] + `agent/data/trades.csv`
[precios]) vs `scratch_gate_v4_results.json → baseline_trades` (42 trades,
replay determinista sym_asc seed 0).

| Métrica | REAL (n=45 subset / n=70 full) | REPLAY baseline (n=42) |
|---|---|---|
| Net PnL | +$61 (subset) / +$65.14 (full) | **−$22.6** |
| PF | 2.73 (subset) / 1.85 (full) | 0.81 (mediana MC) |
| Win rate (net-positivo) | ~50% / ~53% | **9.5%** (4/42) |
| Exit TP / SL / timeout | 11/45 / … / … (subset) — 30/24/16 (full) | **TP 4 / SL 29 / zombie_timeout 9** |
| Símbolos operados | 38 | 34 |
| **Símbolos en común** | — | **4** (MSFT, NVDA, TRX, XMR) |
| **Pares (símbolo, día) en común** | — | **3 de 45** |
| Duración media | 16.73 h | — |
| Cobertura de datos | — | 0.879 (7 símbolos sin klines) |

**Los conjuntos de trades son distintos, no versiones ruidosas del mismo
conjunto.** Un proceso caótico de cupos con el MISMO pool de candidatos
dejaría solapamiento parcial (los ganadores reales, estando en el pool
elegible, ganarían un cupo *a veces*). 3/45 ≈ las señales propias de la
estrategia casi no entran.

---

## 3. Análisis de los TP reales

De los 19 ganadores reales del subset con datos completos:

- **REAL_WIN → replay_TP:** mayoría — cuando el motor *sí* opera la señal
  real, llega al TP estructural.
- **REAL_WIN → replay_LOSS:** **4/19**, **todos por zombie-timeout a las
  48 h**, no por SL. MFE mediana 2.3% — producción bloqueó esa ganancia con
  el monitor de 5 min; el replay la mantuvo abierta y la devolvió. **Ninguno
  fue REAL_TP → replay_SL.**
- **Desplazamiento de entrada −0.2% → +0.2%** (test de microestructura):
  WR 37% → 45%, net +$21 → +$58. **La estrategia sigue ganadora en todos los
  offsets probados.** No es un caso de "diferencia mínima de entrada voltea
  TP→SL sistemáticamente" — eso queda **REFUTADO**.

**Conclusión de la sección 4 del pedido (los 70 TP reales):** cuando el motor
opera la señal real, la respeta. El daño no ocurre en la mecánica entrada/SL/TP.

---

## 4. Contribución de la ENTRADA

**≈ −3 pp de WR. NO es la causa.**

- Offset de entrada del motor (cierre de vela 5m) vs precio real: mediana
  **−0.02%**, |offset| > 0.5% en solo 2/38 trades.
- Factorial de 4 modelos de entrada: PF 2.77–3.96, todos ganadores.
- El progress-log 2026-09-06(4) atribuía el sesgo a "entrada al cierre de
  vela 5m que, con `tpMinPct 10` + `slBufferPct 1.0`, voltea TP→SL". **Los
  datos lo refutan:** el offset es demasiado chico y ningún modelo de entrada
  cambia el signo del resultado.

---

## 5. Contribución del SL/TP

**≈ 0 pp por el nivel/estructura; ≈ −8 pp por el modelado de la SALIDA.**

- SL/TP estructural (recentHigh lb10 +1.0% buffer / tpMinPct 10%): idéntico
  en real y replay, tomado del mismo `patternParamsJson`. No introduce sesgo.
- Chequeo intrabar (TP primero `low<=tp`, luego SL `high>=sl`) en velas de
  5m: favorable-a-nada, sin resolución de 1m para altcoins no se puede
  refinar, pero el impacto es chico (los trades que llegan a TP lo hacen con
  margen, no rozando).
- **El gap real está en la política de salida por tiempo:** producción cierra
  con un monitor de 5 min que puede bloquear ganancia antes de las 48 h; el
  motor mantiene hasta `zombie_timeout` (48 h, solo si pnl<0) o tope 720 h.
  4/19 ganadores reales se pierden acá.

---

## 6. Contribución del TIMING / selección de cupos

**≈ −32 pp de WR. ES LA CAUSA PRIMARIA.**

- El replay determinista abre 42 trades; **solo 3 de 45 (símbolo, día)
  reales** coinciden. El motor opera 20+ símbolos que Caso 3 nunca tocó
  (1000FLOKI, AKT, ASTER, ATH, AXS, BABA, CAKE, CRV, DASH, DOT, EIGEN, ENA,
  LINK, …).
- Esos 42 trades de reemplazo: net −$22.6, **38 perdedores / 4 ganadores**,
  salidas SL 29 / zombie 9 / TP 4.
- La detección **sí** enciende Caso 3 en el bar real (37/38 con datos) — pero
  esa señal compite contra ~200 candidatos de 26 estrategias por 3 cupos,
  y la ocupación de cupos es un proceso caótico path-dependiente sembrado por
  los tiempos de cierre TP/SL de otras estrategias, algunos sobre símbolos
  **irreproducibles** (sin klines). El resultado: las señales reales de Caso 3
  casi nunca ganan un cupo en el replay, y los cupos se llenan con otra cosa.
- Esto es **A (path dependence legítima por slots)** del pedido de auditoría,
  pero con una precisión nueva: no es que "el orden de los mismos trades
  cambie" — es que **el conjunto de trades es otro**, porque la competencia
  se resuelve a favor de candidatos distintos.

---

## 7. Datos históricos disponibles (inventario, sin descargar nada nuevo)

| Recurso | Contenido | Resolución | Cobertura Caso 3 |
|---|---|---|---|
| `binance_vision_clean.db → klines_5m` | OHLCV 5m todos los símbolos | **5 min** | 38/45 símbolos reales |
| `binance_vision_clean.db → klines_clean` | OHLCV 15m | 15 min | ídem |
| `binance_vision_clean.db → btc_klines_1m` | OHLCV 1m **solo BTCUSDT** | 1 min | no aplica a altcoins |
| `binance_vision_clean.db → taker_flow` | flujo taker agregado | 5 min | parcial |
| `klines.db → open_interest` | OI colector | 5 min | 167 símbolos, desde 2026-08-04 |
| `klines.db → funding_rates` | funding | 8 h | parcial |
| **trades / quotes (tick)** | **NO EXISTE** | — | — |
| **1m para altcoins** | **NO EXISTE** | — | — |
| MAE/MFE por trade | perdido con la DB (`MaxAdversePrice`/`MaxFavorablePrice`) | — | reconstruido aprox. de klines 5m |

**Resolución mínima necesaria para cerrar el diagnóstico:** ninguna adicional.
La causa (selección de trades, no mecánica intrabar) se demuestra con los
datos actuales. 1m/tick solo refinaría el término #2–3 que ya es chico.

**7 símbolos genuinamente irreproducibles** (sin klines en ninguna fuente):
ADBEUSDT, ETHBTCUSDT, RSRUSDT, SUNUSDT, VRTUSDT, XLEUSDT, ZHIPUUSDT
(coincide con `missing_syms` de Gate V4) → 15% de los trades reales no se
pueden replayar en absoluto.

---

## 8. Causa principal

**La capa de simulación de cartera del motor (competencia por 3 cupos entre
~200 candidatos, con ocupación de cupos caótica y path-dependiente, más el
stack de vetos pre-trade y las máscaras occupied/BTC) no admite las señales
ganadoras reales de Caso 3 y las reemplaza por un conjunto de trades distinto
y mayoritariamente perdedor.**

Demostración cuantitativa:
1. La detección enciende en 37/38 señales reales con datos (±2 min).
2. Alimentar esas señales al ciclo de vida del motor → PF 2.7–3.9 (ganadora).
3. El replay completo comparte solo 3/45 (símbolo, día) con el real, y su
   conjunto de reemplazo es 90% perdedor → PF 0.81.
4. Por lo tanto la transformación ganadora→perdedora ocurre **entre (1) y (3)**,
   en la asignación de cupos, no en el modelado del trade.

---

## 9. Causas secundarias

1. **Gap de política de salida por tiempo (≈ −8 pp):** el motor no modela el
   profit-lock del monitor de 5 min de producción; mantiene ganadores hasta
   zombie-timeout y devuelve ~2.3% de MFE en 4/19 casos.
2. **Cobertura de datos (15% de trades irreproducibles):** 7 símbolos sin
   klines — no sesga dirección pero reduce la muestra y mete ruido en la
   comparación agregada.
3. **Granularidad 5m en el chequeo intrabar SL/TP (≈ −3 pp):** menor, no
   direccional de forma sistemática en esta estrategia.

---

## 10. Qué habría que reparar (NO lo hacemos ahora)

Para que el motor pueda estimar la expectancy de una estrategia, en orden de
impacto:

1. **Sembrar el replay con el estado REAL de cupos de producción en cada
   punto de decisión**, en vez de re-simular desde cero la competencia de las
   26 estrategias. Es decir: replayar las señales de UNA estrategia contra la
   cartera real (posiciones abiertas reales por timestamp), no contra una
   cartera reconstruida caóticamente.
   *Alternativa:* evaluar cada estrategia **aislada** (sus propios 3 cupos,
   sin competencia cruzada) — pero eso cambia lo que se mide (expectancy
   marginal, no la que produjo producción).
2. **Modelar la salida por tiempo como producción:** monitor cada 5 min con
   la lógica real de profit-lock, no zombie-timeout binario.
3. **Completar datos:** 1m para altcoins + los 7 símbolos faltantes.
4. **Loguear el `patternParamsJson` efectivo** en cada corrida de gate (el de
   Gate V4 se perdió con la DB — nunca se persistió).

---

## 11. Qué NO sabemos todavía

- **Por qué exactamente** las señales reales de Caso 3 pierden la carrera de
  cupos: ¿porque producción tenía otra ocupación cruzada en esos instantes
  (la máscara `occupied` se reconstruye de la DB, ~88% de cobertura, algunos
  cierres sobre símbolos irreproducibles)? ¿o porque el orden de prioridad de
  candidatos del replay difiere del de producción? No se puede separar sin
  los **logs del scanner de producción**, que no existen.
- Si `minRR` 3 vs 4 (conflicto no resuelto en los artefactos) cambia el pool
  de candidatos vía el veto de sizing. No se testeó.
- El impacto real de los 7 símbolos irreproducibles sobre el PF agregado
  (podrían ser ganadores o perdedores).
- Si la reconstrucción de `occupied` en los 45 timestamps coincide con la
  ocupación real de cupos de producción (solo verificable parcialmente).
- MAE/MFE exacto por trade (la DB con `MaxAdversePrice`/`MaxFavorablePrice` se
  perdió) — se usó una reconstrucción aproximada de klines 5m.

---

## Coherencia con el progress-log

Este diagnóstico **refina y corrige** la auditoría 2026-09-06(4):

- Lo que sigue en pie: el motor tiene sesgo pesimista sistemático de WR para
  MaGeometry; Gate V4 usó mediana (error); el motor no sirve hoy para estimar
  rentabilidad.
- **Corrección:** el sesgo NO está en la entrada a cierre de vela 5m
  volteando TP→SL (refutado: offset mediana −0.02%, todos los modelos de
  entrada dan ganadora). Está en la **capa de cupos/selección** — el motor
  opera trades distintos a los de producción. Es **path dependence de slots
  (causa A)**, pero en su forma fuerte: conjunto de trades disjunto, no
  reordenamiento del mismo conjunto.
