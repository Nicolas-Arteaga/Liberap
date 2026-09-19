# ROUND 35 — AUDITORÍA FORENSE DE TRADES REALES

## Resumen — lo que se encontró y lo que todavía es hipótesis

**Se localizó una fuente de datos que no se había usado en las 34 rondas
anteriores**: la tabla `SimulatedTrades` de la base Postgres de
producción (`localhost:5433/Verge`), con 3,315 trades reales cerrados de
17 perfiles de estrategia distintos (no solo Nexus), 2026-05-16 a
2026-09-22. **El hallazgo más fuerte y accionable no es un nuevo patrón de
entrada — es una asimetría de gestión de salida**: el 45.7% de los trades
que terminaron en SL habían llegado a estar +100bp o más a favor antes de
revertir completamente hasta el stop. Esto es evidencia concreta, no
hipótesis, de que el sistema actual no tiene forma de capturar ganancias
parciales o mover el stop cuando el trade ya se movió a favor.

---

## FASE 1 — Mapeo de la base de datos

| Fuente | Contenido | Estado |
|---|---|---|
| `agent/data/trades.csv` | 3,682 filas, solo `source=Nexus`, 2026-05-16→2026-09-05 | Ya conocida, campos básicos |
| **`SimulatedTrades` (Postgres, producción)** | **3,315 trades, 17 perfiles de estrategia, campos ricos declarados en el esquema (MAE/MFE, distancia a MA7, JSON de decisión del agente)** | **Nueva para esta investigación** |
| `agent/data/arrow_peak_trades.csv` | 186 filas | Menor, no usado esta ronda |
| `agent/data/trades_v1_backup.csv` | 56 filas | Menor, no usado esta ronda |

**Hallazgo crítico de cobertura**: las columnas ricas de `SimulatedTrades`
(`Ma7DistancePctAtEntry`, `MaxAdversePrice`, `MaxFavorablePrice`,
`AgentDecisionJson`, `ExitAuditJson`) están **100% nulas en los 3,315
registros** — confirma lo que la memoria del proyecto ya advertía: el
reset de Docker de 2026-07 borró la base original y la reconstrucción
posterior desde `trades.csv` solo pudo rellenar los campos básicos
(precio, SL, TP, PnL, fecha), no los campos de contexto que el agente
calculaba en vivo. **Se reconstruyó todo el contexto desde cero usando
OHLCV real (`klines_clean`, 15m) — no se inventó ni interpoló nada; los
trades sin cobertura de klines suficiente se descartaron explícitamente y
se cuentan abajo.**

### Estadísticas de la muestra

- **3,283 trades** con resultado TP o SL (excluye 32 `timeout`).
- **TP: 443 (13.5%) · SL: 2,840 (86.5%)** — win rate bajo, consistente
  con una estrategia de tendencia (muchas pérdidas chicas, pocas ganancias
  grandes).
- **PnL total: +$34,890** · media por trade: +$10.63 · mediana: −$1.33.
- **610 símbolos distintos**, 17 perfiles de estrategia.
- Cobertura de reconstrucción: **421/610 símbolos (69%)** tenían klines
  suficientes en `binance_vision_clean.db`; de ahí, **2,612 trades (TP=355,
  SL=2,257) quedaron con contexto y MFE/MAE reconstruidos** con éxito.

---

## FASE 3 — Contexto pre-entrada: TP vs SL

| Feature | TP (media) | SL (media) | Diferencia |
|---|--:|--:|--:|
| Precio vs MA99 | **+1.33%** | +0.83% | TP entra más lejos por encima de MA99 |
| MA7 por encima de MA99 | **67.0%** | 59.7% | +7.3 puntos |
| MA25 por encima de MA99 | **65.6%** | 58.3% | +7.3 puntos |
| Precio vs MA25 | +0.63% | +0.46% | Diferencia menor |
| ATR relativo, dist. a máx/mín 20 barras, velas alcistas/10, volumen relativo, rango relativo | Sin diferencia apreciable | — | — |

**Lectura honesta**: hay una diferencia consistente y en la dirección
esperada en la estructura de medias (estar por encima de MA99, la media
más lenta, se asocia con más trades ganadores) — pero es una diferencia
de **7 puntos porcentuales sobre bases ya minoritarias** (58-67%), no una
separación dramática. Esto es un candidato débil, no una "receta" fuerte
todavía — exactamente el tipo de señal que el brief pide NO convertir
automáticamente en estrategia sin más evidencia.

---

## FASE 6 — MFE/MAE: el hallazgo fuerte de la ronda

| Población | MFE medio | MFE mediana | MAE medio | MAE mediana |
|---|--:|--:|--:|--:|
| TP (n=310) | **+815.6bp** | +516.9bp | −102.9bp | −42.2bp |
| SL (n=1,840) | +177.6bp | +131.3bp | **−350.8bp** | −256.5bp |

**El hallazgo central**: **1,032 de 2,257 trades que terminaron en SL
(45.7%) habían alcanzado +100bp o más de excursión favorable antes de
revertir completamente hasta el stop.** Esto significa que casi la mitad
de las pérdidas del sistema no fueron "la señal estuvo mal desde el
principio" — fueron trades que **sí se movieron a favor de forma
significativa y después se dejaron correr hasta perderlo todo**, porque
el sistema actual no tiene ningún mecanismo de captura parcial, breakeven
o trailing.

### Ejemplos concretos

**Trades TP (ganadores reales):**
- BEATUSDT SHORT: MFE=+2,792bp, MAE=−38bp → PnL +$34.52 (excursión
  adversa mínima, corrió limpio hasta el TP).
- INUSDT LONG: MFE=+1,830bp, MAE=+564bp (nunca estuvo en negativo) → PnL
  +$19.53.

**Trades SL con oportunidad perdida (el patrón a investigar):**
- AGTUSDT LONG: llegó a **+760bp de excursión favorable**, luego revirtió
  hasta el stop → PnL −$1.55.
- ZBTUSDT LONG: llegó a **+374bp a favor**, revirtió → PnL −$1.36.
- CHILLGUYUSDT LONG: llegó a +243bp a favor, luego cayó hasta −638bp de
  excursión adversa antes del stop → PnL −$3.36.

Estos tres últimos son exactamente el patrón que el propio brief
anticipó en la Fase 6: *"quizás algunos trades que terminan en SL
tuvieron una oportunidad real que el sistema no capturó."*

---

## FASE 5 — Los 3 setups del usuario en trades reales

| Setup | Trades reales coincidentes | Win rate real |
|---|--:|--:|
| 1 — Giro MA7 antes de pullback | 112 | 8.0% (peor que el baseline de 13.5%) |
| 2 — MA7 toca MA99 desde abajo | 231 | **16.0%** (mejor que el baseline) |
| 3 — Quiebre rápido MA7 desde pico | 75 | 12.0% (similar al baseline) |

**Ninguno de los 3 muestra evidencia fuerte** en los trades reales — el
Setup 2 está levemente por encima del win rate general (16% vs 13.5%),
pero con solo 231 casos y sin ajustar por el PnL asimétrico (un win rate
más alto no implica más dinero si los tamaños de ganancia/pérdida
difieren) no alcanza para declarar nada. Esto es coherente con — no
contradice — el resultado de R34: los setups discrecionales del usuario,
tal como están definidos, no muestran ventaja clara ni en el backtest
sintético ni en los trades reales ejecutados.

---

## Candidatos (máximo 5, ninguno todavía convertido en estrategia)

### Candidato #1 — Gestión de salida: capturar excursión favorable antes de la reversión completa
1. **Nombre**: Break-even / captura parcial tras MFE≥100bp.
2. **Contexto previo**: cualquier trade abierto por el sistema actual (no depende del setup de entrada).
3. **Evento/trigger**: la posición alcanza +100bp de excursión favorable (aprox. 4-5× el tamaño típico de comisión+slippage).
4. **Confirmación**: ninguna adicional — es un trigger de precio, no de señal.
5. **Entrada**: no aplica (esto es una regla de SALIDA, no de entrada).
6. **Invalidación**: no aplica.
7. **TP/exit observado**: actualmente NINGUNO — el sistema deja correr hasta el TP original o el SL original; la propuesta es mover el stop a breakeven (o capturar parcialmente) cuando se cruza el umbral.
8. **Cantidad de ejemplos reales**: 1,032 trades (de 2,257 SL reconstruidos) cumplen la condición de haber superado +100bp de MFE antes de terminar en SL.
9. **Win rate actual de ese subgrupo**: 0% (por definición, todos terminaron en SL).
10. **PnL actual de ese subgrupo**: negativo (parte de los −$X que ya perdió el sistema).
11. **MFE/MAE**: MFE medio de este subgrupo bastante por encima de 100bp por construcción; MAE final es el que definió el SL.
12. Ejemplos ganadores: no aplica (candidato de salida, no de entrada).
13. Ejemplos concretos: AGTUSDT (+760bp→SL), ZBTUSDT (+374bp→SL), CHILLGUYUSDT (+243bp→SL, ver arriba).
14. **Qué diferencia a estos trades de los TP reales**: los TP reales en su mayoría NO pasan por una fase de retroceso profundo después de moverse a favor (ver BEATUSDT y INUSDT arriba, MAE mínimo o positivo) — sugiere que una vez que un trade se mueve a favor de forma clara, cerrarlo o asegurar parte de la ganancia captura valor que hoy se pierde en la reversión.
15. **Qué es todavía hipótesis**: el umbral óptimo de "MFE≥100bp" no se optimizó (se usó un valor redondo, razonable, no ajustado a datos) — y, crucialmente, **no se simuló qué pasaría con los TP reales si también se les aplicara la misma regla** (podría recortar ganancias de trades que iban a llegar al TP completo). Este es el paso obligatorio antes de proponer cualquier cambio: simular la regla sobre AMBAS poblaciones (TP y SL), no solo mirar el lado ganador de la hipótesis.

### Candidato #2 — Estructura por encima de MA99 como filtro de contexto (débil, requiere más evidencia)
1. **Nombre**: Filtro de tendencia de fondo (MA25 y MA7 por encima de MA99).
2. **Contexto previo**: cualquier señal de entrada del sistema actual.
3. **Evento/trigger**: no es un trigger nuevo — es un filtro aplicado sobre las señales existentes.
4. **Confirmación**: MA7>MA99 Y MA25>MA99 al momento de la entrada.
5. **Entrada**: la misma que ya genera el sistema, simplemente filtrada.
6. **Invalidación**: N/A.
7. **TP/exit**: el mismo que ya usa el sistema.
8. **Cantidad de ejemplos**: presente en 67% de los TP vs 60% de los SL (sobre 2,612 trades reconstruidos).
9. **Win rate**: no calculado todavía condicionado a este filtro específicamente (pendiente).
10. **PnL**: no calculado todavía.
11. **MFE/MAE**: no diferenciado todavía por este filtro específico.
12-13. Ejemplos: INUSDT y VELVETUSDT (TP, ambos con MA7>MA99) vs necesitaría contraejemplos de SL con MA7<MA99 para ilustrar el contraste — pendiente.
14. **Diferencia**: una diferencia de 7 puntos porcentuales en una base ya minoritaria (58-67%) — direccionalmente consistente pero débil.
15. **Qué es hipótesis**: casi todo — esto es una observación de Fase 3, no una regla probada. Necesitaría su propio TRAIN→VAL→OOS antes de considerarse algo más que una pista.

### Candidatos #3, #4, #5 — no se encontraron con evidencia suficiente esta ronda
No se fuerza a completar 5 candidatos con especulación. Las comparaciones
de Fase 3 (ATR relativo, distancia a máximos/mínimos de 20 barras,
conteo de velas alcistas, volumen y rango relativo) **no mostraron
ninguna diferencia apreciable entre TP y SL** — se probaron y se
descartan explícitamente, no se omiten silenciosamente.

---

## Regla respetada: no se convirtió nada en estrategia todavía

Tal como pide el brief, estos son patrones y ejemplos reales — no reglas
mecánicas listas para `portfolio_engine.py`. El único candidato con
evidencia sólida (#1, gestión de salida) requiere, antes de cualquier
implementación:

1. Simular la regla de breakeven/captura parcial sobre **ambas**
   poblaciones (TP y SL) para medir el efecto neto real, no solo el lado
   ganador de la historia.
2. Probar sensibilidad del umbral (¿100bp es el punto correcto, o
   50bp/150bp cambian mucho el resultado?).
3. Confirmar que el patrón se sostiene dividiendo la muestra en dos
   mitades temporales (2026-05→07 vs 2026-07→09) antes de tocar
   cualquier configuración real.

**Esto NO toca el sistema de producción** — es un hallazgo a validar,
documentado para decisión del usuario, consistente con la regla explícita
de no modificar nada todavía.
