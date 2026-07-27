## ADDED Requirements

### Requirement: Chequeo de cobertura de datos históricos
El sistema SHALL exponer un endpoint que, dado un rango de fechas y una
lista de símbolos (o el watchlist completo), devuelva qué símbolos/días
faltan en `klines_5m` y `klines_clean`, sin descargar nada todavía.

#### Scenario: Cobertura completa
- **WHEN** se pide el estado de cobertura para un rango donde todos los
  símbolos ya tienen datos
- **THEN** el endpoint devuelve una lista vacía de huecos

#### Scenario: Faltan días recientes
- **WHEN** pasaron varios días desde la última descarga y se pide cobertura
  hasta la fecha actual
- **THEN** el endpoint identifica los días faltantes por símbolo (mes en
  curso vía archivo diario, meses ya cerrados vía archivo mensual)

### Requirement: Sincronización incremental desde la UI
El sistema SHALL permitir disparar la descarga de SOLO los datos faltantes
detectados por el chequeo de cobertura, con progreso visible, sin requerir
correr un script manual.

#### Scenario: Botón "Actualizar datos"
- **WHEN** el usuario presiona "Actualizar datos" en la pantalla de
  backtesting
- **THEN** el sistema descarga en paralelo (ThreadPoolExecutor, ~48-64
  workers, igual que los scripts ya probados) solo los símbolos/días
  faltantes, y la UI muestra una barra de progreso hasta completar

#### Scenario: Nada que actualizar
- **WHEN** la cobertura ya está completa para el rango pedido
- **THEN** el sistema no dispara ninguna descarga y lo informa
  explícitamente (no una barra de progreso vacía sin explicación)
