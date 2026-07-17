# #156 — Fin de OHLCV

Auditoría con backtesting real (agent/backtest_engine.py, agent/fvg_backtest.py) sobre ~2.5 meses de historia: de las 14 estrategias activas, **solo MA Slope Caso 3 tiene margen real** (profit factor 1.13-1.31). Caso 1, Caso 2 y FVG (1m/5m/15m) empatan o pierden en conjunto. Las 14 son variantes de lo mismo: reglas sobre posición/pendiente de medias derivadas de OHLCV (velas). Investigación de mercado 2026 confirma que ese tipo de edge ya está absorbido por el mercado — la ventaja real está en datos que Verge nunca miró.

De paso, encontramos que dos piezas "inteligentes" del sistema eran cascarones vacíos:
- El modelo XGBoost de Nexus-15/Nexus-5 **nunca fue entrenado** (el archivo `.json` no existe en ningún lado) — el 15% de "score de IA" siempre fue un 0.5 fijo.
- El widget de "ballenas" del dashboard es keyword-matching en texto, no datos on-chain reales.

## Qué se agrega (spec completa en `openspec/changes/market-data-expansion/`)

1. **Order book imbalance (OFI)** — desequilibrio de compra/venta en tiempo real, gratis vía Binance WebSocket. Primera prioridad: sin costo externo y con el respaldo académico más sólido (arXiv 2602.00776, 2506.05764).
2. **Funding rate como señal** — no solo como costo, como filtro/predictor.
3. **Dinámica de liquidaciones** — cascadas de apalancamiento como filtro anti-entrada-tardía.
4. **On-chain real** — reemplaza el keyword-matching de ballenas por flujos de exchange/wallets reales (proveedor a definir).
5. **Entrenamiento real del modelo XGBoost de Nexus-15/5** — primera vez, con validación out-of-sample estricta.

## Cómo se valida

Todo se agrega como **feature/filtro opcional** sobre estrategias ya existentes (empezando por Caso 3, la única con edge confirmado) — nunca se activa en producción sin pasar antes por un backtest A/B (con vs. sin la señal nueva) usando el mismo motor que ya reveló que Caso 1/2/FVG no sirven.

## Estado

Spec-driven vía OpenSpec — `openspec/changes/market-data-expansion/` (proposal, design, 5 specs de capacidad, 34 tareas en tasks.md). Empezamos por la sección 1 (order book imbalance).
