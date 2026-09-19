# ROUND 43 — Parte 2-8: Búsqueda de estrategia nueva a partir de trades reales

## Respuesta corta (formato pedido)

1. **¿Encontraste una estrategia ejecutable?** No.
2. **¿Cuál?** N/A.
3. **¿Cuánto PnL mensual neto en OOS?** N/A.
4. **¿Después de fees/slippage/funding?** N/A.
5. **¿Con qué capital y restricciones?** N/A.
6. **¿Cuántos trades?** N/A (no llegó a un candidato con criterios completos).
7. **PASS o FAILED:** **`NO HAY ESTRATEGIA VALIDADA`** esta ronda.

Esta ronda no cierra con "hay potencial": no hay ningún candidato, ni
completo ni incompleto, que pase a validación. Lo que hay es un
diagnóstico honesto de por qué no se llegó, más un hallazgo real de
calidad de datos que hay que arrastrar a cualquier intento futuro.

## Qué se hizo realmente esta ronda

El grueso del tiempo de la ronda se fue en la Parte 1 (ver
`TRAIL1_UI_SETTINGS_ROUND43.md`): mover el switch global de Trail-1 de
`appsettings.json` a un ABP Setting administrable desde la UI, con
verificación de compilación y tests. Para la Parte 2-8 solo alcanzó un
**primer pase exploratorio** sobre la tabla `SimulatedTrades` en vivo, no
la reconstrucción forense completa (contexto OHLCV/OI/funding por trade +
TRAIN/VAL/OOS + `portfolio_engine.py`) que pide el brief.

### Hallazgo real (no una estrategia, un problema de datos)

Agregando PnL cerrado por `StrategyProfile` sobre los 3,340 trades
cerrados actuales:

| Antes de excluir símbolos corruptos | Después (excluye ONUSDT/BBUSDT, ver R37) |
|---|---|
| "Nexus": 264 trades, **+$363,260.61** total, +$1,375.99 promedio/trade | "Nexus": 260 trades, **+$3,549.46** total, +$13.65 promedio/trade |
| PnL total de todos los perfiles: ~$364,150 | PnL total de todos los perfiles: **$5,037.72** |

**Confirma exactamente el hallazgo ya documentado en R37** (corrupción de
precio ~1000x en `ClosePrice`/`RealizedPnl` para `ONUSDT`/`BBUSDT`): sigue
sin limpiarse en la tabla real, e infla cualquier agregado en más de
70x si no se excluye explícitamente. Cualquier análisis futuro sobre
`SimulatedTrades` — el propio o el de cualquier otra persona — **debe**
excluir estos dos símbolos (o corregirlos) antes de sacar una sola
conclusión, o el resultado es directamente falso.

Con los datos limpios: **"Nexus" es, de lejos, el perfil con más trades
(260 de 3,340, ~7.8%) y el que más PnL agregado real aporta ($3,549 de
$5,038 totales, ~70%)**, pero con un promedio de solo $13.65/trade — nada
llamativo por sí solo, y **una sola métrica agregada no es una
estrategia** (regla explícita de esta ronda). No se investigó todavía
qué hace "Nexus" distinto (contexto de entrada, símbolos, dirección,
horario) porque no alcanzó el tiempo para la reconstrucción de contexto
por trade que exige la Parte 2 completa.

## Por qué no se llegó a un candidato (honesto, sin rescatar nada)

- **No se hizo la reconstrucción forense completa** de los 3,364 trades
  con contexto de mercado (MA/ATR/volumen/OI/funding en el momento de
  cada entrada) — eso es un trabajo de una magnitud comparable a R35
  (que sí lo hizo, pero para el lado de SALIDAS, no de patrones de
  ENTRADA nuevos) y no entra en el tiempo restante de esta ronda.
- Sin esa reconstrucción, cualquier "patrón" que se proponga a partir
  solo de agregados por perfil/símbolo (como la tabla de arriba) sería
  exactamente lo que la Parte 3 prohíbe: una correlación o métrica
  aislada, no una estructura CONTEXTO→ESTADO→EVENTO→CONFIRMACIÓN→
  ENTRADA→INVALIDACIÓN→SALIDA con las 18 componentes exigidas.
- Tampoco se corrió `portfolio_engine.py` sobre ningún candidato — no
  hay candidato que correr todavía.

## Qué queda pendiente, concretamente, para la próxima ronda dedicada a esto

1. Excluir `ONUSDT`/`BBUSDT` (y correr una verificación general de
   `MaxAdversePrice`/`MaxFavorablePrice`/`ClosePrice` contra klines
   reales para todos los símbolos, no solo estos dos — R38 ya encontró
   corrupción también en `BANKUSDT`/`REDUSDT` del lado del MAE, sin
   investigar a fondo).
2. Reconstruir contexto de mercado real (klines mergeadas de
   `binance_vision_clean.db` + `agent/data/klines.db`, igual que R35-R37)
   para cada uno de los ~3,340 trades limpios: MA7/25/50/99, ATR,
   volumen percentil, distancia a highs/lows, y OI/funding donde exista
   cobertura.
3. Empezar la búsqueda por el perfil "Nexus" específicamente (es el que
   concentra volumen y PnL real) buscando qué diferencia sus entradas
   ganadoras de las perdedoras — siguiendo el orden de prioridades de la
   Parte 6 (patrones en ganadores primero, después en perdedores, etc.),
   no lanzando hipótesis nuevas sin mirar antes lo que ya hay.
4. Cualquier estructura candidata que surja de ahí recién se especifica
   con las 18 componentes de la Parte 3 y se corre TRAIN/VAL/OOS +
   `portfolio_engine.py` antes de llamarla candidata.

## Cumplimiento de las reglas operativas de esta ronda

- ✅ Trail-1 sigue apagado (global y por perfil) durante toda esta
  investigación.
- ✅ No se modificó ninguna estrategia existente ni su lógica de entrada.
- ✅ No se tocó producción salvo el switch de UI de la Parte 1.
- ✅ No se aplicó ninguna migración adicional.
- ✅ No se borraron datos.
- ✅ No se usó Binance/API para inventar datos — todo salió de la DB real
  y de las fuentes OHLCV locales ya existentes.
- ✅ No se declaró éxito por una métrica aislada (el hallazgo de "Nexus"
  se documenta explícitamente como *no* una estrategia).
- ✅ No se inventó una estrategia para cerrar la ronda — veredicto
  honesto: `NO HAY ESTRATEGIA VALIDADA`.
