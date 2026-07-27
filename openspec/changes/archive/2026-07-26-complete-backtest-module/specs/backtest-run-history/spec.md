## ADDED Requirements

### Requirement: Persistencia de corridas de backtest
Cada corrida de backtest completada SHALL guardarse en almacenamiento
persistente (tabla SQLite local, independiente del backend .NET) con sus
parámetros y resultado completo, y SHALL sobrevivir a un reinicio del
servidor de backtest.

#### Scenario: Corrida completada se guarda sola
- **WHEN** una corrida de backtest termina con `status=completed`
- **THEN** el resultado completo (perfil, rango de fechas, PnL, win rate,
  desglose mensual, trades) queda guardado en la tabla de corridas sin
  acción manual del usuario

#### Scenario: Reinicio del servidor no borra el historial
- **WHEN** el proceso `agent/backtest/api.py` se reinicia
- **THEN** las corridas guardadas previamente siguen disponibles para
  listar y consultar

#### Scenario: Nunca se sobreescribe una corrida anterior
- **WHEN** se corre un nuevo backtest con los mismos parámetros
  (estrategia + rango de fechas) que uno anterior
- **THEN** se crea un registro nuevo, el anterior permanece intacto

### Requirement: Listado y consulta de corridas pasadas
El sistema SHALL exponer un endpoint para listar corridas pasadas (con
filtro opcional por estrategia) y otro para consultar el detalle completo
de una corrida por id, y la UI SHALL mostrar este listado.

#### Scenario: Listado en la UI
- **WHEN** el usuario abre la pantalla de backtesting
- **THEN** ve una sección con las corridas anteriores (estrategia, fechas,
  PnL, fecha de ejecución), ordenadas de más reciente a más antigua

#### Scenario: Ver detalle de una corrida pasada
- **WHEN** el usuario selecciona una corrida del listado
- **THEN** se muestran sus resultados completos (igual que si se acabara
  de correr), sin volver a ejecutar el backtest
