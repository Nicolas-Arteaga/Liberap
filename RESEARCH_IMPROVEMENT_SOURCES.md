# Fuentes para ampliar el catálogo de mejoras

**Fecha:** 2026-10-04. Investigación documental: no se ejecutó backtest ni se
modificaron motor, `StrategyProfiles`, agente, ledger o datos operativos.

## Regla de admisión

Una técnica entra al catálogo sólo si tiene una fuente identificable con datos,
reglas o evaluación cuantitativa; puede expresarse como regla fija, causal y
auditable; y sus insumos están disponibles en OHLCV/velas existentes. Una
fuente no prueba que funcione aquí: cada ID seguirá TRAIN/VALIDATION, cuatro
escenarios y una sola corrida OOS.

## 1. SALIDA: retener avance favorable

**Trailing ATR, admitido.** [Viaggi, *Volatility Scaled Trailing Stops*
(SSRN, 2026)](https://papers.ssrn.com/sol3/Delivery.cfm/6432558.pdf?abstractid=6432558&mirid=1)
estudia trailing ATR con entradas aleatorizadas para aislar la salida, en
DAX/Nasdaq/oro e intradía/swing; estima piso de ruido 0.38 ATR (IC bootstrap
95% [0.12,0.53]). Es experimento/backtest de salida, no evidencia cripto. Se
agrega `exit_atr_trail_0_5_after_1r`, regla discreta por encima de ese piso.

**Salida estructural EMA, admitida con cautela.** [Bhatti,
*Regime-Filtered Intraday Trading Framework for Gold* (SSRN,
2026)](https://papers.ssrn.com/sol3/Delivery.cfm/6650958.pdf?abstractid=6650958&type=2)
especifica EMA50 sólo a cierre como trailing y reporta 247 trades 15m,
expectancy +0.414R y PF 1.76. Es un activo/año; se agrega
`exit_ema50_close_trail` como hipótesis, no como resultado trasladable.

**Salida parcial, no incorporada.** Aunque es una técnica conocida, el contrato
actual sólo tiene un cierre; simularla sin cantidad residual/comisiones/SL
remanente sería inventar datos.

## 2. Regímenes

[Arda, *Bollinger Bands under Varying Market Regimes* (SSRN,
2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5775962) backtestea
BTC/USDT 2017–2022 y reporta dependencia de breakout/mean-reversion respecto a
bear, acumulación, bull y distribución. [Prakash et al., *Structural clustering
of volatility regimes* (arXiv:2004.09963)](https://arxiv.org/abs/2004.09963)
usa change points/clustering y valida evitación de riesgo dinámica en acciones,
índices, ETF y FX. Ninguno demuestra ADX=25 o tercil medio: son constantes
locales preregistradas. Se agregan `entry_adx14_ge_25` y
`entry_realized_vol_20_mid`.

Correlación intermercado no se incorpora: faltan series sincronizadas,
congeladas y garantizadas para cada candidato.

## 3. Position sizing dinámico

[White y Haghani (SSRN,
2020)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3618417) discute
volatility targeting y presenta backtests largos. En contra de adopción fácil,
[Liu, Tang y Zhou (JPM/SSRN,
2019)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3289019) identifica
sesgo look-ahead y, corregido, drawdowns 68–93%. El [CFA Institute,
*Investment Model Validation*](https://rpc.cfainstitute.org/sites/default/files/-/media/documents/article/rf-brief/investment-model-validation.pdf)
exige probar protocolos de tamaño y advierte concentración.

**No se añade variante.** El contrato no contiene capital, tamaño, equity curve
ni fill model. Kelly, confianza o vol-target serían ficción sin extenderlo.

## 4. Filtros multi-indicador

[Paramashiva (SSRN, 2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6467818)
backtestea BTC con RSI14 30/70 y MA, coste 0.1%, OOS julio–enero y 21 ventanas
walk-forward; reporta RSI +1.60% y MA -3.61% durante BTC -17.21%. No prueba la
confluencia, pero sustenta componentes reproducibles. Se añade
`entry_rsi14_oversold_ma50_long` y se etiqueta evidencia indirecta.

[Goswami (SSRN, 2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6683818)
reporta confirmación MTF ETH/USDT: 1,969 a 9 trades, DD 99.17% a 1.46%, pero PF
0.722 y p=0.687; su muestra es insuficiente. **MTF queda descartada**.

## 5. Riesgo de cartera

El [CFA Institute, *Portfolio Risk and Return*](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/portfolio-risk-return-part-1)
documenta que pesos, covarianzas y correlaciones determinan riesgo de cartera.
Su [lectura de market risk](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/measuring-managing-market-risk)
define incremental VaR y enumera límites de posición/escenario/stop verificables
por backtest.

**No hay familia ejecutable.** Faltan snapshot histórico de posiciones
simultáneas, fills y retornos sincronizados; un límite por candidato no mide
exposición agregada real.

## 6. Cripto intradía/scalping

[Mercik y Bedowska-Sojka (SSRN,
2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6401099) analiza
datos 15m Binance/Coinbase BTC/ETH: volatilidad explica spreads y periodicidades
mejoran pronóstico OOS. Requiere spread/depth por venue, ausentes.

[Perera (SSRN, 2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6932998)
reporta 5 años/525,600 velas 5m SOL/USDT con costes Binance: SL 0.15% consume
93% del riesgo; SL 1–2% informa Sharpe>2/PF>2.5. Es una estrategia/mercado,
independiente y debe replicarse. Se agrega únicamente
`cost_hourly_range_ge_2x_roundtrip`, compatible con OHLCV. Rango es proxy, no
spread; no se fuerzan tape-speed, order book ni volume profile.

## Resultado

| Área | IDs añadidos | Evidencia |
| --- | --- | --- |
| SALIDA | `exit_atr_trail_0_5_after_1r`, `exit_ema50_close_trail` | backtests externos, no validados local/cripto |
| ENTRADA | `entry_adx14_ge_25`, `entry_realized_vol_20_mid`, `entry_rsi14_oversold_ma50_long` | régimen cripto + evidencia parcial de indicadores |
| COSTOS | `cost_hourly_range_ge_2x_roundtrip` | coste cripto real; proxy de rango |
| sizing/cartera/microestructura | ninguna ejecutable | faltan datos/contrato |
