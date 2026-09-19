# ROUND 18 — ALPHA HUNT: BREAK THE FRAME

**Fecha:** 2026-09-21 · Scripts: `agent/backtest/r18_discovery.py` +
`r18b_capitulation.py` · Universo ancho (357 símbolos, solo OHLCV+taker,
igual R15) · Sin descargas nuevas.

## Resultado directo

**B — NUEVO MAPA DE ALPHA.** No apareció una estrategia ≥150 USDT/mes. Pero
esta ronda SÍ produjo el hallazgo más fuerte y mejor evidenciado del proyecto
hasta ahora — que resultó, tras auditarlo a fondo (como pide el brief para
cualquier candidato prometedor), ser una reconfirmación independiente del
drift estructural del universo (R12/R13), no un mecanismo nuevo. Y dejó un
lead genuinamente nuevo sin explotar: efectos de hora del día.

---

## 0. Listing events — evaluado y descartado en minutos (como pedía el brief)

WebFetch a los anuncios públicos de Binance confirma que el dato existe y es
real (fechas verificadas, categorizable por tipo). Pero: (a) requiere paginar
~10+ meses de historial mixto (cientos de páginas) para reconstruir un
calendario limpio, y (b) R7/R8 ya establecieron que aun con fechas perfectas
el universo de listings crypto-nativos limpios en esta ventana es de ~20-38
eventos — insuficiente para un backtest robusto sin importar la calidad del
dato. Se descarta aquí, sin gastar la ronda, tal como exige el brief.

---

## 1. SECUENCIA 1 — Compresión → Expansión (Familias A+B+D+E)

Evento: ≥2h de compresión de volatilidad sostenida (percentil causal <25%) 
seguida de la primera barra de ruptura (percentil de retorno >85% o <15%).
Dirección = continuación de la ruptura. MFE/MAE medidos con high/low intrabar
(no solo cierre), a 1h/4h/12h/24h.

| h | final_mean | final_med | WR | MFE p50 | MAE p50 |
|---|--:|--:|--:|--:|--:|
| 1h | −1.3bp | −4.3bp | 0.46 | +46bp | −49bp |
| 4h | −2.8bp | −6.9bp | 0.47 | +86bp | −91bp |
| 12h | −2.3bp | −9.5bp | 0.48 | +156bp | −163bp |
| 24h | −5.7bp | −7.9bp | 0.49 | +226bp | −235bp |

**FAILED.** La ruptura NO continúa en promedio (retorno final negativo, WR
<50%). Hay mucho movimiento intrabar en ambas direcciones (MFE/MAE grandes y
casi simétricos) pero sin sesgo direccional explotable. El control "ruptura
sin compresión previa" da números casi idénticos (−2.4 a −6.0bp) — la
compresión previa **no añade nada**. TRAIN/VAL/OOS inestable en signo a
12h/24h (train +13.1bp, val +2.2bp, oos −6.6bp @12h). Cerrado.

---

## 2. SECUENCIA 2 — Capitulación/Climax → Reacción (Familias A+D+I)

Evento: caída en decil bajo (percentil causal ≤3%) + volumen en decil alto
(percentil ≥90%) en la misma barra. Se midió la reacción real (ambos
sentidos, sin asumir) — Familia I.

| h | LONG (bet rebote) | SHORT (bet continuación) |
|---|--:|--:|
| 1h | −1.4bp, WR 0.52 | +1.4bp, WR 0.47 |
| 4h | −9.5bp, WR 0.50 | +9.5bp, WR 0.49 |
| 12h | **−45.3bp**, WR 0.47 | **+45.3bp**, WR 0.53 |
| 24h | **−87.5bp**, WR 0.45 | **+87.5bp**, WR 0.55 |

**El bounce inicial es débil y se revierte: la continuación domina y crece
con el horizonte.** SHORT-tras-capitulación parecía, a primera vista, el
mejor resultado de 18 rondas: efecto grande (+87.5bp @24h), creciente con el
horizonte, **muy poco concentrado** (quitar los 20 símbolos con más PnL solo
baja el promedio de +87.5 a +50.3bp — 335 de 355 símbolos siguen aportando),
n=67 045 eventos (altísima frecuencia). Se congeló y se auditó a fondo, como
exige el brief para cualquier candidato con pinta de PASS.

### Auditoría (lo que lo mata)

**TRAIN/VAL/OOS @24h:** train +117.3bp, **val −0.1bp**, oos +89.4bp — el
efecto desaparece por completo en VAL y solo reaparece en OOS. Patrón ya
visto muchas veces en este proyecto (R9-R15): fuerte en un sub-período,
ausente en otro, sin explicación de régimen limpia.

**Placebos — el veredicto decisivo:**
| Control | @24h |
|---|--:|
| Real (climax) | +87.5bp |
| Control (drop SIN volumen climax) | **−2.5bp** |
| **Placebo random-timestamp (SHORT cualquier barra, sin condición)** | **+30.0bp, CI[22.5,37.9] excl 0** |
| **Placebo time-shift +24h (mismos eventos, ventana desplazada)** | **+73.2bp, CI[56.3,90.7] excl 0** |

**El placebo random-timestamp — shortear una barra cualquiera del universo,
sin ninguna condición de capitulación — ya tiene valor esperado positivo
(+30bp, CI excluye 0) a 24h.** Esto es la **misma deriva bajista estructural
del universo de altcoins medianas** documentada de forma independiente en
R12 y R13 (¿recuerdan? "el placebo aleatorio iguala o supera a la selección
inteligente"). El placebo time-shift (+73bp) confirma que gran parte del
efecto "real" (+87.5bp) es ese mismo drift, no la capitulación en sí — el
climax aporta un incremento (87.5 vs 30-73 del placebo) pero no es la
historia completa, y con TRAIN/VAL/OOS inestable no se puede aislar con
confianza cuánto es mecanismo genuino vs deriva de régimen.

**Sim económica (capital ≤450, concurrencia real):** aun ignorando el
problema del placebo, la restricción de capital es fatal por sí sola. De
67 045 eventos disponibles, con 1-5 posiciones concurrentes solo se capturan
398-3 697 (0.6%-5.5%) — el resto pasa de largo porque los slots están
ocupados. Y esa muestra capturada (sesgada por FIFO temporal, no por calidad
de señal) da **NET/mes negativo en 7 de 8 configuraciones**: −$140 a −$16/mes
(1-3 slots), apenas **+$19/mes** en el mejor caso (5 slots, 12h) — muy lejos
de 150.

**Veredicto: FAILED como estrategia standalone.** Es la tercera vez
independiente (R12 → R13 → R18) que un mecanismo aparentemente fuerte sobre
este universo de altcoins resulta ser, total o parcialmente, el mismo drift
estructural — cuando el placebo apropiado (aleatorio o desplazado en el
tiempo) lo reproduce. Eso SÍ es información: la deriva es real, grande, y
**consistentemente no explotable con el capital y la concurrencia
disponibles**, no un artefacto de medición.

---

## 3. Diagnósticos ligeros (mapa, no backtests completos)

### Familia H — retorno medio 1h por hora UTC (lead nuevo, sin explotar)

Varias horas muestran retorno medio con CI que excluye 0 sobre ~62 000
observaciones cada una — **18:00 UTC −9.9bp\***, **22:00 UTC −9.7bp\***,
13:00 UTC −5.7bp\*, 23:00 UTC −5.2bp\*, 19:00 UTC +4.9bp\*, 15:00 UTC
+4.4bp\*, 17:00 UTC +3.2bp\*. No se investigó más allá del escaneo (fuera de
alcance de esta ronda) — **es el candidato más limpio para Round 19**: no es
un factor de precio/OI/funding ya probado, tiene n grande, y es barato de
testear con rigor completo (placebo de calendario, TRAIN/VAL/OOS, sim
económica).

### Familia C — reacción de rezagados tras movimiento amplio del universo

−2.95bp CI[−9.35, 3.28] — sin efecto. Cerrado, no se insiste (evita repetir
H18/residual-momentum).

---

## TOP 5 mecanismos — mapa de alpha actualizado

| # | Mecanismo | OOS | Placebo | Veredicto | Por qué / qué falta |
|---|---|---|---|---|---|
| 1 | **Hora del día (Familia H)** | no testeado aún | no testeado aún | **LEAD — Round 19** | Único hallazgo de esta ronda sin explicación de drift conocida; barato de auditar con rigor completo. |
| 2 | Capitulación (drop+volumen) → continuación SHORT | +89.4bp bruto, pero VAL≈0 | **placebo lo reproduce en 30-70%** | **FAILED** | Mayormente el mismo drift estructural de R12/R13; y aun ignorando eso, capital/concurrencia no permite capturar el edge teórico (NET/mes negativo en 7/8 configs). |
| 3 | Compresión → expansión (breakout) | inestable, signo cambia | control sin compresión ≈ igual | **FAILED** | La compresión previa no aporta información; la ruptura no continúa en promedio. |
| 4 | Drift estructural del universo altcoin (re-confirmado 3ª vez: R12/R13/R18) | consistente | — | **Confirmado, no explotable** | Real y grande, pero R13 ya demostró que ningún book long-short lo captura de forma estable, y R18 muestra que ni siquiera "solo shortear todo" lo hace con capital limitado y buena selección de timing. |
| 5 | Rezagados tras movimiento amplio (Familia C) | sin efecto | — | **FAILED** | Cercano a H18 (ya falló); confirma el patrón, no se insiste más. |

---

## Qué aprendimos (para no repetir el error)

1. **El "cambio de marco" (secuencias, MFE/MAE, reacción-no-predicción)
   funcionó como metodología** — encontró un efecto de +87.5bp con altísima
   frecuencia y baja concentración, algo que 17 rondas de factores aislados
   nunca habían producido. El problema no fue el método, fue que el efecto
   resultó ser (otra vez) el drift del universo.
2. **Cualquier hallazgo nuevo sobre este universo de altcoins DEBE pasar
   primero por el placebo random-timestamp / time-shift antes de
   entusiasmarse** — es la única forma confiable de separar "mecanismo
   genuino" de "deriva estructural disfrazada de evento". Se aplicó
   correctamente acá y evitó reportar un falso PASS.
3. **La restricción de capital/concurrencia es, independientemente del
   placebo, una limitación real**: con eventos tan frecuentes (67 045 en 8.5
   meses) y solo 1-5 posiciones de $450, se captura <6% de las oportunidades,
   y encima con sesgo FIFO no óptimo. Si algún día aparece un mecanismo
   genuino de alta frecuencia, hace falta una lógica de selección
   (priorizar la mejor señal disponible cuando compiten varias por un slot),
   no solo "primero que llega".

## SIGUIENTE RONDA — no se cierra la investigación

**Round 19: efectos de hora del día / sesión (Familia H), con rigor completo.**
Es el único hallazgo de R18 que no colapsó al primer placebo, es barato de
testear (ya tenemos el escaneo inicial), y es genuinamente distinto de todo
lo probado en 18 rondas (no es precio, OI, funding, cross-sectional, ni
drift). Diseño: TRAIN/VAL/OOS, placebo de calendario (desplazar la hora
aleatoriamente), verificar que no sea simplemente el mismo drift estructural
disfrazado de patrón horario (aplicar el mismo test random-timestamp/
time-shift que mató al hallazgo de esta ronda), sim económica con capital
≤450. Si también falla: quedan agotadas las familias A-I del brief de R18;
recién ahí valdría la pena reconsiderar si el objetivo requiere una fuente de
datos que hoy no tenemos (order book L2, opciones, on-chain) — decisión del
usuario, no autocierre.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
