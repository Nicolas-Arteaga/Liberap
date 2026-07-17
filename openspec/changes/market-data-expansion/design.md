## Context

Verge corre 14 estrategias activas, todas derivadas 100% de OHLCV (velas cerradas): posición/pendiente de medias móviles (MaGeometry), gaps de 3 velas (FVG), compresión de medias (ADN Compression), etc. Auditoría con el motor de backtesting (`agent/backtest_engine.py`, `agent/fvg_backtest.py`) sobre ~2.5 meses de historia cacheada mostró que solo una (MA Slope Caso 3) tiene margen real (profit factor 1.13-1.31); el resto empata o pierde. Investigación de mercado 2026 (ver Sources en la conversación que originó este change) confirma que ese tipo de edge basado puramente en price action está mayormente absorbido por el mercado, y que la ventaja real hoy está en datos que Verge nunca capturó: order flow/order book, funding rates, liquidaciones, on-chain.

Restricciones reales del proyecto (no ignorar en el diseño):
- Es un proyecto de una sola persona, corriendo local (Docker Compose: `redis`, `db` Postgres, `market-data` FastAPI, `market-ws`), sin presupuesto de infraestructura institucional.
- Capital operado real: $150 USDT por trade, 3 posiciones concurrentes (`MarginPerTrade=150`, `MaxOpenPositions=3`) — esto acota qué inversión de infraestructura tiene sentido (ej. MEV serio requiere $10M+ de capital según la misma investigación — explícitamente fuera de alcance).
- Nada tiene hot-reload (agente Python, python-service, backend .NET) — cualquier pieza nueva hereda esa restricción de reinicio manual.
- Ya existe un patrón real de "placeholder que parece real pero no lo es" (XGBoost nunca entrenado, ballenas por keyword-matching) — el diseño debe evitar repetir esa clase de bug (fallback silencioso sin indicarlo).

## Goals / Non-Goals

**Goals:**
- Agregar order flow/order book imbalance, funding rate, liquidaciones, y on-chain real como señales/features NUEVAS, sin tocar las 14 estrategias existentes.
- Que cada señal nueva sea evaluable en el motor de backtesting ANTES de crear cualquier StrategyProfile en producción que la use — mismo proceso que ya reveló que Caso 1/2/FVG no sirven.
- Entrenar por primera vez el modelo XGBoost de Nexus-15/Nexus-5, con validación out-of-sample real.
- Que cualquier fallback (fuente no disponible, rate-limited) sea auditable y visible, nunca un valor inventado en silencio.

**Non-Goals:**
- No se busca MEV ni arbitraje de latencia (requiere capital e infraestructura fuera de alcance para este proyecto).
- No se reemplaza ninguna de las 14 estrategias existentes — son capacidades aditivas.
- No se apunta a un modelo de "sentimiento LLM + razonamiento en loop cerrado" (Trading-R1/Meta-RL-Crypto) en esta primera vuelta — es la pieza más ambiciosa de la investigación y la que menos encaja con la escala actual del proyecto; queda fuera de este change.
- No se decide todavía el proveedor on-chain de pago (CryptoQuant u equivalente) — ver Open Questions.

## Decisions

**Orden de implementación: order book imbalance primero.**
De las 4 fuentes nuevas, es la única que (a) no depende de un proveedor de pago — Binance expone profundidad de order book y liquidaciones (`forceOrder`) gratis vía WebSocket — y (b) tiene el respaldo académico más sólido y reciente (arXiv 2602.00776, 2506.05764) de las cuatro. Funding rate es el segundo paso natural porque reutiliza la misma infraestructura de WebSocket/exchange ya wireada. On-chain real y el entrenamiento del modelo quedan para después porque dependen de decisiones externas (proveedor de datos, tamaño real del dataset de entrenamiento).

**Reusar el patrón de caché existente, no inventar uno nuevo.**
`kline_cache.py` (SQLite) ya resuelve "cachear datos de mercado sin pegarle de más al exchange, servir lo cacheado primero, backfill on-demand". Order book/funding/liquidaciones deberían perseguir el mismo patrón (tablas nuevas en el mismo SQLite o uno separado, mismo criterio de freshness/staleness que ya usa `get_klines_for_nexus`), no un mecanismo de storage paralelo.

**Las señales nuevas son FEATURES, no estrategias propias — al menos al principio.**
En vez de crear "StrategyType=OrderFlow" como una estrategia aislada, se exponen como valores adicionales en el `geo`/contexto que ya reciben `_evaluate_ma_geometry_profile` y equivalentes — permite usarlas como FILTRO de las estrategias que ya tienen edge conocido (ej. exigir OFI a favor para las entradas de Caso 3) en vez de apostar a que la señal nueva sola alcanza. Evaluable inmediatamente con A/B en el backtester: mismo perfil, con y sin el filtro nuevo.

**Fallbacks explícitos, nunca silenciosos.**
Mismo espíritu que el fix de 2026-07-15 en `SimulatedTradeAppService.CloseTradeAsync` (rechazar un precio resuelto que se desvía demasiado de `MarkPrice` en vez de confiar ciegamente): si una fuente nueva no responde, el sistema debe devolver `None`/estado explícito y loguearlo — nunca un número por defecto sin indicación (el bug de `whaleScore` y del `g6=0.5` de Nexus son exactamente el antipatrón a no repetir).

## Risks / Trade-offs

- **[Riesgo] Rate limits de exchange al agregar 2 streams de WebSocket nuevos (order book + liquidaciones) sobre ~400-700 símbolos.** → Mitigación: reusar el mismo circuit breaker (`agent/circuit_breaker.py`) ya arreglado esta sesión (cupo único de prueba en HALF_OPEN), y limitar la suscripción inicial a un subconjunto (ej. los símbolos con mayor volumen, ya identificados por `VolatileSymbolsService`) en vez de los 400+ completos de entrada.
- **[Riesgo] Overfitting al entrenar el modelo XGBoost con solo ~2.5 meses de historia cacheada.** → Mitigación: validación out-of-sample obligatoria (spec `nexus-ml-model-training`), y no desplegar si el resultado en el período de validación no sostiene lo visto en entrenamiento. Si la historia disponible resulta insuficiente, esto se documenta como bloqueante explícito, no se fuerza un modelo con datos de más.
- **[Riesgo] Proveedor on-chain de pago fuera de presupuesto para un proyecto personal.** → Mitigación: evaluar alternativas gratuitas/freemium (CryptoQuant tiene tier gratuito limitado; hay alternativas más chicas mencionadas en la investigación) antes de comprometer presupuesto — ver Open Questions.
- **[Trade-off] Agregar señales como "features/filtros" en vez de estrategias propias es más lento de ver resultados** (no hay un "profit factor de order-flow-imbalance" aislado, solo el efecto de filtrar con él) **pero evita repetir el error de esta sesión** (crear un perfil nuevo — el clon de 15m — antes de validarlo, en vez de después).

## Migration Plan

1. Order book imbalance: nuevo módulo de fetch (WebSocket) + cómputo de OFI + tabla de caché → exponer como feature → correr backtest A/B (Caso 3 con y sin filtro de OFI) antes de tocar cualquier StrategyProfile real.
2. Funding rate: mismo patrón, reutilizando la conexión de exchange ya existente.
3. Liquidaciones: mismo patrón, stream `forceOrder` de Binance.
4. On-chain real: bloqueado hasta decidir proveedor (ver Open Questions) — reemplaza el placeholder de `whaleScore` recién cuando haya una fuente real conectada, nunca antes (para no dejar la UI peor que hoy, mostrando un dato real intermitente sin indicarlo).
5. Entrenamiento de Nexus-15/5: en paralelo a los anteriores (no depende de ellos) — dataset desde klines ya cacheados, validación out-of-sample, backtest comparativo antes de desplegar.

Rollback: todas las señales nuevas son aditivas y opt-in por perfil — desactivar un filtro nuevo es un cambio de configuración (`patternParamsJson` del perfil afectado), no requiere revertir código.

## Open Questions

- ¿Qué proveedor on-chain usar para `onchain-whale-tracking`? (CryptoQuant, alternativa gratuita, o un nodo propio ligero) — pendiente de decidir según presupuesto real disponible.
- ¿Cuánta historia adicional hace falta backfillear (más allá de los ~2.5 meses ya cacheados) para que el entrenamiento de Nexus-15/5 tenga chance real de generalizar, sin sobreajustar?
- ¿El filtro de order-flow/funding/liquidaciones se evalúa primero sobre MA Slope Caso 3 (la única con edge conocido) antes de considerarlo para cualquier otra estrategia?
