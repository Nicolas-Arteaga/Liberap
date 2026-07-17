## Why

Auditamos las 14 estrategias activas de Verge (backtest histórico + datos en vivo, sesión 2026-07-15/16): la única con margen real y sostenido es MA Slope Caso 3 (profit factor 1.13-1.31); el resto (Caso 1, Caso 2, FVG en las 3 temporalidades) empata o pierde en conjunto sobre ~2.5 meses de historia. Todas las 14 son variantes de lo mismo: reglas escritas a mano sobre posición/pendiente de medias móviles derivadas de OHLCV — la misma clase de señal, una y otra vez, con distintos disfraces (FVG, ADN Compression, Arrow Peak). Investigación de mercado (2026) confirma que ese tipo de edge basado puramente en price action ya está absorbido por el mercado — la ventaja real hoy viene de datos que Verge nunca miró: order flow/microestructura del order book, funding rates como señal (no solo costo), dinámica de liquidaciones, y datos on-chain reales. Además, encontramos que el único componente "de IA" del sistema (XGBoost en Nexus-15/Nexus-5) nunca fue entrenado — el archivo del modelo no existe en ningún lado (disco, imagen Docker, contenedor corriendo), así que ese 15% del score cae siempre a un valor neutro fijo (0.5) sin que nadie lo notara. Y el widget de "ballenas" del dashboard resultó ser matching de palabras clave en texto, no datos on-chain reales — mismo patrón de "la interfaz existe, el dato real detrás no".

## What Changes

- Agregar una fuente de datos de **order flow / desequilibrio del order book** (Binance expone esto gratis) como señal nueva, independiente de las velas OHLCV que ya usa todo el resto del sistema.
- Agregar **funding rate** como señal de entrada/filtro (no solo como costo de mantener posición) — predicción del próximo funding vía desequilibrio del order book, y/o arbitraje de funding entre exchanges.
- Agregar **dinámica de liquidaciones/apalancamiento** (liquidation heatmap / concentración de apalancamiento) como filtro de contexto — los movimientos fuertes vienen de cascadas de liquidación, no de cruces de medias.
- Reemplazar el widget de "ballenas" (hoy: keyword-matching en texto) por **datos on-chain reales** (flujos netos hacia/desde exchanges, movimiento de wallets grandes) — mismo criterio que ya usa la industria (CryptoQuant y similares).
- **Entrenar por primera vez** el modelo XGBoost de Nexus-15/Nexus-5 (hoy inexistente — placeholder que devuelve 0.5 fijo) usando los datos históricos ya cacheados (`agent/data/klines.db`) + el resultado de trades reales acumulados, con validación out-of-sample estricta (no reentrenar y probar sobre los mismos datos).
- **BREAKING**: ninguno de estos ítems reemplaza las 14 estrategias existentes — se agregan como capacidades nuevas, evaluables independientemente vía el motor de backtesting (`agent/backtest_engine.py`, `agent/fvg_backtest.py`) antes de tocar producción.

## Capabilities

### New Capabilities
- `orderbook-imbalance-signal`: captura y cómputo de desequilibrio de compra/venta del order book en tiempo real (Binance), expuesto como señal/feature nueva para el agente y para el motor de backtesting.
- `funding-rate-signal`: lectura de funding rate actual + histórico por símbolo, uso como filtro de entrada y/o señal de predicción del próximo funding.
- `liquidation-dynamics-signal`: lectura de concentración de apalancamiento/liquidaciones recientes por símbolo (liquidation heatmap), usado como filtro de contexto para evitar entrar contra una cascada en curso.
- `onchain-whale-tracking`: reemplazo del keyword-matching actual por datos on-chain reales (flujos exchange in/out, movimiento de wallets grandes) para el widget de "ballenas" y como señal de contexto.
- `nexus-ml-model-training`: pipeline de entrenamiento real (primera vez) del modelo XGBoost de Nexus-15/Nexus-5 — dataset de features/etiquetas desde klines históricos + resultados de trades, entrenamiento, validación out-of-sample, y despliegue del `.json` del modelo real reemplazando el placeholder.

### Modified Capabilities
(ninguna — no hay specs previos en `openspec/specs/`, este es el primer change proposal del repo)

## Impact

- **Nuevo código** en `agent/` (nuevos módulos de fetch para order book/funding/liquidaciones, similar en espíritu a `binance_fetcher.py`/`multi_source_fetcher.py` ya existentes) y en `python-service/` (nuevo análisis, similar a los módulos `fvg/`, `nexus15/` ya existentes).
- **Backend .NET**: posible extensión del dashboard (`angular/src/app/dashboard`) para mostrar order flow/funding/liquidaciones reales, y reemplazo del cálculo de `whaleScore` actual (`dashboard.component.ts`, keyword-matching) por datos reales.
- **Nexus15/Nexus5** (`python-service/nexus15/`, `python-service/nexus5/`): entrenamiento y despliegue del modelo XGBoost real (`models/nexus15/xgb_nexus15_v1.json`, hoy inexistente).
- **Motor de backtesting** (`agent/backtest_engine.py`, `agent/fvg_backtest.py`): cada capacidad nueva debe poder validarse ahí ANTES de crear un StrategyProfile en producción — mismo proceso que ya se usó para descubrir que Caso 1/2 y FVG no tienen margen real.
- Ninguna de estas fuentes de datos existe hoy en el sistema — todo lo que corre actualmente (las 14 estrategias) deriva 100% de OHLCV (velas). Este change no toca esas 14 estrategias.
