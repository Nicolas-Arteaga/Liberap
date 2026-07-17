## ADDED Requirements

### Requirement: Captura de order book en tiempo real
El sistema SHALL capturar profundidad del order book (bids/asks, al menos 20 niveles) por símbolo desde Binance Futures, vía WebSocket, para los símbolos del watchlist activo — no solo para el símbolo seleccionado en el dashboard.

#### Scenario: Símbolo del watchlist sin datos de order book
- **WHEN** un símbolo del watchlist no tiene stream de order book activo
- **THEN** el sistema lo suscribe automáticamente en el próximo ciclo, sin requerir reinicio manual

### Requirement: Cómputo de desequilibrio de order book (OFI)
El sistema SHALL calcular un score de desequilibrio de flujo de órdenes (Order Flow Imbalance) por símbolo, normalizado en un rango conocido (ej. -1.0 a +1.0), actualizado en tiempo real a partir del order book capturado.

#### Scenario: Desequilibrio fuerte hacia compra
- **WHEN** el volumen acumulado en los primeros N niveles de bids supera significativamente al de asks (umbral configurable)
- **THEN** el score de OFI para ese símbolo refleja un valor positivo proporcional al desequilibrio

#### Scenario: Datos insuficientes para calcular OFI
- **WHEN** el order book de un símbolo tiene menos niveles de los requeridos para el cálculo
- **THEN** el sistema devuelve OFI=None (no un score arbitrario) y lo audita, sin bloquear el resto del ciclo

### Requirement: Exposición del OFI al motor de backtesting
El sistema SHALL exponer una fuente histórica de OFI reconstruible para backtesting — no solo el valor en vivo — de forma que `agent/backtest_engine.py` pueda evaluar candidatos que usen esta señal contra historia real, con la misma disciplina de no-lookahead ya usada para MaGeometry/FVG.

#### Scenario: Backtest de una estrategia que usa OFI
- **WHEN** se corre un backtest de un perfil que condiciona la entrada a un umbral de OFI
- **THEN** el motor usa solo OFI reconstruido con datos hasta el índice de vela evaluado, nunca datos futuros
