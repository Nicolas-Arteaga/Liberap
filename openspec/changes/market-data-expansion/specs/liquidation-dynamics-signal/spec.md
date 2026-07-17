## ADDED Requirements

### Requirement: Captura de liquidaciones recientes por símbolo
El sistema SHALL capturar el stream de liquidaciones forzadas (forceOrder) de Binance Futures por símbolo, y mantener una ventana reciente (ej. últimas 4-24 horas configurable) de volumen liquidado por lado (long/short).

#### Scenario: Racha de liquidaciones de un lado
- **WHEN** el volumen liquidado de posiciones LONG en la ventana reciente supera un umbral respecto al promedio del símbolo
- **THEN** el sistema marca ese símbolo con una bandera de "cascada de liquidaciones en curso" con timestamp y magnitud

### Requirement: Filtro anti-cascada para nuevas entradas
El sistema SHALL permitir que un StrategyProfile evite abrir una posición en la MISMA dirección que una cascada de liquidaciones activa reciente (ej. no abrir SHORT nuevo si acaban de liquidarse masivamente longs, ya que el movimiento fuerte puede estar agotándose, no empezando).

#### Scenario: Candidato coincide con una cascada ya en curso
- **WHEN** un candidato de cualquier estrategia se dispara en la misma dirección que una cascada de liquidaciones detectada en los últimos N minutos
- **THEN** el candidato se marca para revisión/veto configurable, auditable con el mismo mecanismo que otros vetos existentes

### Requirement: Historial reconstruible para backtesting
El sistema SHALL persistir el historial de liquidaciones de forma que el motor de backtesting pueda reconstruir, para cualquier punto histórico, el estado de "cascada activa o no" sin usar datos posteriores a ese punto.

#### Scenario: Backtest de un perfil con filtro anti-cascada
- **WHEN** se corre un backtest de un perfil que usa este filtro
- **THEN** el resultado refleja exactamente qué candidatos habrían sido vetados en su momento, no con información que solo se conoció después
