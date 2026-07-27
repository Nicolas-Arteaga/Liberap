## ADDED Requirements

### Requirement: Backtest de StrategyType=AdnCompression
El motor de backtest SHALL soportar perfiles con `StrategyType=AdnCompression`,
reusando `AdnCompressionAnalyzer` real (`python-service/adn_compression/analyzer.py`)
y `verge_agent.py::_build_adn_compression_candidate` sin reimplementar la
lógica de detección del patrón.

#### Scenario: Perfil AdnCompression aparece en el selector
- **WHEN** el usuario abre la pantalla de backtesting
- **THEN** los perfiles con `StrategyType=AdnCompression` aparecen en el
  selector de estrategias, igual que MaGeometry y FVG

#### Scenario: Corrida de AdnCompression usa el analizador real
- **WHEN** se ejecuta un backtest sobre un perfil AdnCompression
- **THEN** cada candidato se evalúa llamando a
  `AdnCompressionAnalyzer._analyze_symbol` (monkeypatcheado a datos
  históricos) seguido de `_build_adn_compression_candidate`, y el
  resultado (SL/TP/qty) pasa por `risk_manager.py::_calculate_position_nexus_style`
  igual que las demás estrategias

#### Scenario: Solo la fase PULLBACK_TO_MA7 genera candidato
- **WHEN** el analizador devuelve un item con `phase` distinto de
  `PULLBACK_TO_MA7` (ej. `COILED`, `EXTENDED`, `EXHAUSTED`)
- **THEN** el motor NO abre un trade para ese símbolo en ese instante,
  igual que hace `_run_adn_compression_scan` en producción
