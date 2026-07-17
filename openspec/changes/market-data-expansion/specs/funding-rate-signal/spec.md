## ADDED Requirements

### Requirement: Lectura de funding rate actual e histórico
El sistema SHALL leer el funding rate vigente y su historial reciente (al menos los últimos 30 períodos) por símbolo, desde Binance Futures u otro exchange configurado, cacheado igual que las klines (`kline_cache.py`) para no golpear la API de más.

#### Scenario: Símbolo sin historial de funding cacheado
- **WHEN** se solicita funding histórico de un símbolo nunca antes consultado
- **THEN** el sistema hace un backfill inicial y lo persiste, igual que el flujo existente de klines vía REST on-demand

### Requirement: Filtro de entrada por funding extremo
El sistema SHALL permitir que un StrategyProfile configure un umbral de funding rate (ej. no entrar LONG si el funding está extremadamente positivo, señal de sobre-apalancamiento en largos) como condición adicional, sin reemplazar la lógica de entrada existente.

#### Scenario: Funding extremo bloquea una entrada que de otro modo sería válida
- **WHEN** un candidato LONG cumple todas las condiciones de su perfil pero el funding rate del símbolo supera el umbral configurado
- **THEN** el candidato se descarta con un motivo de rechazo auditable (mismo patrón que los vetos existentes en `setup_validator.py`)

### Requirement: Predicción de próximo funding vía desequilibrio de order book
El sistema SHALL estimar la dirección probable del próximo funding rate usando la señal de `orderbook-imbalance-signal`, expuesta como feature adicional, no como una estrategia aislada.

#### Scenario: Feature disponible para nuevos perfiles
- **WHEN** se evalúa un candidato de cualquier StrategyType que declare uso de esta feature
- **THEN** el valor de predicción de funding está disponible en el mismo `geo`/contexto que ya reciben las funciones de evaluación existentes
