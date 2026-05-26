# VERGE TRADING SYSTEM - DOCUMENTACIÓN COMPLETA

## ÍNDICE
1. [Arquitectura General](#arquitectura-general)
2. [Backend - ABP Framework](#backend---abp-framework)
3. [Agente Python](#agente-python)
4. [Interacción entre Backend y Agente](#interacción-entre-backend-y-agente)
5. [Componentes del Sistema](#componentes-del-sistema)
6. [Flujo de Trading](#flujo-de-trading)
7. [Configuración y Parámetros](#configuración-y-parámetros)

---

## ARQUITECTURA GENERAL

El sistema VERGE Trading es una plataforma de trading autónoma que combina:
- **Backend C#**: Basado en ABP Framework para gestión de datos, usuarios y persistencia
- **Agente Python**: Motor de inteligencia artificial para análisis de mercado y ejecución de trades
- **Frontend Angular**: Interfaz de usuario para monitoreo y control
- **Redis**: Puente de comunicación en tiempo real entre backend y agente
- **SignalR**: Comunicación bidireccional en tiempo real entre backend y frontend

### Diagrama de Arquitectura

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   Frontend      │         │   Backend C#    │         │   Agente Python │
│   Angular       │◄────────►│   ABP Framework │◄────────►│   VergeAgent     │
│                 │ SignalR │                 │ HTTP/REST │                 │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                      │                              │
                                      ▼                              ▼
                              ┌───────────────┐              ┌───────────────┐
                              │  PostgreSQL   │              │   Binance API  │
                              │   Database    │              │   Market Data │
                              └───────────────┘              └───────────────┘
                                      │                              │
                                      ▼                              ▼
                              ┌───────────────┐              ┌───────────────┐
                              │     Redis     │◄─────────────│  KlineCache    │
                              │   Pub/Sub     │              │   SQLite       │
                              └───────────────┘              └───────────────┘
```

---

## BACKEND - ABP FRAMEWORK

### Estructura del Proyecto Backend

El backend sigue la arquitectura de capas de ABP Framework:

```
src/
├── Verge.Domain/              # Entidades de dominio y lógica de negocio
├── Verge.Domain.Shared/       # Constantes y enums compartidos
├── Verge.Application.Contracts/ # DTOs e interfaces de servicios
├── Verge.Application/         # Implementación de servicios de aplicación
├── Verge.HttpApi/             # Controladores API (expuestos por convención)
├── Verge.HttpApi.Host/        # Punto de entrada de la aplicación
└── Verge.EntityFrameworkCore/ # Acceso a datos (Entity Framework Core)
```

### Servicios Principales

#### 1. SimulatedTradeAppService

**Ubicación**: `src/Verge.Application/Trading/SimulatedTradeAppService.cs`

**Propósito**: Gestiona el ciclo de vida completo de los trades simulados.

**Métodos principales**:

- **OpenTradeAsync(OpenTradeInputDto input)**
  - Abre un nuevo trade simulado
  - Valida SL/TP contra precio de entrada en vivo
  - Implementa "Smart Position Management": si existe una posición abierta para el mismo símbolo y perfil, añade a la posición (precio promedio) en lugar de bloquear
  - Verifica límites de capital y riesgo
  - Guarda en base de datos y notifica vía SignalR

- **CloseTradeAsync(Guid tradeId)**
  - Cierra un trade existente
  - Calcula PnL basado en precio de cierre
  - Actualiza balance virtual del usuario
  - Registra MaxAdversePrice si no está seteado
  - Notifica cierre vía SignalR

- **GetActiveTradesAsync()**
  - Retorna todos los trades abiertos del usuario actual
  - Incluye información de estrategia, símbolo, side, TP/SL

- **GetTradeHistoryAsync()**
  - Retorna historial completo de trades cerrados
  - Incluye métricas de rendimiento

- **UpdateTpSlAsync(Guid tradeId, UpdateTpSlInputDto input)**
  - Actualiza Take Profit y Stop Loss de un trade abierto
  - Valida permisos del usuario
  - Notifica cambios vía SignalR

- **UpdateMaxAdversePriceAsync(Guid tradeId, UpdateMaxAdversePriceInputDto input)**
  - Registra el precio adverso máximo alcanzado durante el trade
  - Para LONG: precio más bajo visto
  - Para SHORT: precio más alto visto
  - Usado para análisis de riesgo y drawdown

- **GetVirtualBalanceAsync()**
  - Retorna el balance virtual actual del usuario
  - Se actualiza automáticamente al cerrar trades

- **GetPerformanceStatsAsync()**
  - Calcula estadísticas de rendimiento del usuario
  - Win rate, PnL total, drawdown máximo, etc.

- **GetRecentTradesAsync(int limit)**
  - Retorna los N trades más recientes
  - Usado para mostrar actividad reciente en el dashboard

#### 2. StrategyProfileAppService

**Ubicación**: `src/Verge.Application/Trading/StrategyProfileAppService.cs`

**Propósito**: Gestiona perfiles de estrategia de trading.

**Perfiles virtuales implementados**:

- **Standard Scalping**: Estrategia principal con SL 0.6x
  - SL_MULTIPLIER: 0.6 (~2.5% stop)
  - TP_MULTIPLIER: 3.5
  - Color: rgb(67, 182, 0)

- **Scalping Clone**: Estrategia clon con SL doble
  - SL_MULTIPLIER: 1.2 (~5.0% stop)
  - TP_MULTIPLIER: 3.5
  - CLONE_MAX_STOP_LOSS_PCT: 5.0 (techo absoluto)
  - Protecciones:
    - No puede abrir símbolo si Standard ya lo tiene abierto
    - Requiere confluencia 10 puntos más alta que Standard (70 vs 60)
    - Evita tokens extremadamente volátiles (rango máximo 10% vs 15%)

**Métodos principales**:

- **GetAsync()**: Retorna todos los perfiles activos del usuario
- **CreateAsync()**: Crea un nuevo perfil de estrategia
- **UpdateAsync()**: Actualiza un perfil existente
- **DeleteAsync()**: Elimina un perfil

#### 3. TradingAppService

**Ubicación**: `src/Verge.Application/Trading/TradingAppService.cs`

**Propósito**: Servicio principal de trading con lógica avanzada.

**Funcionalidades**:
- Gestión de múltiples exchanges (Binance, Bybit, OKX, Bitget)
- Análisis de mercado en tiempo real
- Ejecución de trades reales y simulados
- Gestión de riesgo y posición

#### 4. ValidationAppService

**Ubicación**: `src/Verge.Application/Trading/ValidationAppService.cs`

**Propósito**: Valida setups de trading antes de ejecución.

**Validaciones**:
- Confluencia mínima
- Rango estimado
- RSI
- Volumen
- Liquidez

### DTOs (Data Transfer Objects)

**Ubicación**: `src/Verge.Application.Contracts/Trading/DTOs/`

#### DTOs Principales

- **SimulatedTradeDto**: Representación completa de un trade
  ```csharp
  public class SimulatedTradeDto
  {
      public Guid Id { get; set; }
      public string Symbol { get; set; }
      public int Side { get; set; }  // 0=LONG, 1=SHORT
      public decimal EntryPrice { get; set; }
      public decimal? TpPrice { get; set; }
      public decimal? SlPrice { get; set; }
      public decimal? MaxAdversePrice { get; set; }
      public decimal Pnl { get; set; }
      public TradeStatus Status { get; set; }
      public DateTime OpenedAt { get; set; }
      public DateTime? ClosedAt { get; set; }
      public Guid? StrategyProfileId { get; set; }
      public string AgentDecisionJson { get; set; }
  }
  ```

- **OpenTradeInputDto**: Input para abrir un trade
  ```csharp
  public class OpenTradeInputDto
  {
      public string Symbol { get; set; }
      public int Side { get; set; }
      public decimal Amount { get; set; }  // Margin
      public int Leverage { get; set; }
      public decimal? TpPrice { get; set; }
      public decimal? SlPrice { get; set; }
      public Guid? TradingSignalId { get; set; }
      public string AgentDecisionJson { get; set; }
      public Guid? StrategyProfileId { get; set; }
  }
  ```

- **UpdateTpSlInputDto**: Input para actualizar TP/SL
  ```csharp
  public class UpdateTpSlInputDto
  {
      public decimal? TpPrice { get; set; }
      public decimal? SlPrice { get; set; }
  }
  ```

- **UpdateMaxAdversePriceInputDto**: Input para actualizar MaxAdversePrice
  ```csharp
  public class UpdateMaxAdversePriceInputDto
  {
      public decimal MaxAdversePrice { get; set; }
  }
  ```

### SignalR Hub

**Ubicación**: `src/Verge.Application/Trading/TradingHub.cs`

**Propósito**: Comunicación bidireccional en tiempo real entre backend y frontend.

**Eventos**:
- **ReceiveTradeUpdate**: Notifica actualización de trade (abierto, cerrado, TP/SL actualizado)
- **ReceiveSignal**: Notifica nueva señal de trading del agente
- **ReceiveAgentLog**: Notifica log del agente Python

---

## AGENTE PYTHON

### Estructura del Proyecto Agente

```
agent/
├── config.py                 # Configuración central del agente
├── verge_agent.py            # Loop principal del agente
├── auth_manager.py           # Gestión de autenticación con backend
├── position_manager.py       # Comunicación con backend para trades
├── state_manager.py          # Gestión de estado local (SQLite)
├── signal_engine.py          # Motor de generación de señales
├── risk_manager.py           # Gestión de riesgo y posición
├── binance_fetcher.py        # Obtención de datos de Binance
├── kline_cache.py            # Caché de velas (SQLite)
├── setup_validator.py        # Validación de setups (LSE, Nexus)
├── circuit_breaker.py        # Protección contra condiciones adversas
├── redis_signal_bridge.py    # Puente Redis para señales en tiempo real
├── report_engine.py          # Generación de reportes
├── trade_analytics.py        # Análisis de trades
├── auto_tuner.py             # Auto-ajuste de parámetros
└── market_ws_server.py       # Servidor WebSocket para datos de mercado
```

### Componentes Principales

#### 1. VergeAgent (verge_agent.py)

**Propósito**: Orquestador principal del sistema de trading.

**Responsabilidades**:
- Inicializar todos los componentes del sistema
- Ejecutar el loop principal de trading (cada 5 minutos)
- Coordinar la generación de señales
- Gestionar la apertura y cierre de posiciones
- Implementar lógica de Scalping Clone con protecciones

**Métodos clave**:

- **__init__()**: Inicializa todos los componentes
  ```python
  def __init__(self):
      self.auth = AuthManager()
      self.fetcher = BinanceFetcher()
      self.state = StateManager()
      self.signals = SignalEngine(self.fetcher)
      self.risk = RiskManager(self.fetcher)
      self.positions = PositionManager(self.auth)
      self.report = ReportEngine()
  ```

- **run()**: Loop principal del agente
  - Sincroniza perfiles de estrategia
  - Escanea mercado en busca de oportunidades
  - Genera señales de trading
  - Ejecuta trades según señales
  - Monitorea posiciones abiertas
  - Actualiza MaxAdversePrice en tiempo real

- **_open_clone_trade()**: Abre trade clon con protecciones
  - Verifica límite de slots del Clone
  - Bloquea si Standard ya tiene el símbolo abierto
  - Valida SL contra techo CLONE_MAX_STOP_LOSS_PCT (5.0%)
  - Requiere confluencia más alta que Standard
  - Evita tokens extremadamente volátiles
  - Calcula SL con multiplicador 2x (1.2x vs 0.6x)

#### 2. PositionManager (position_manager.py)

**Propósito**: Interfaz de comunicación con el backend ABP para gestión de trades.

**Métodos principales**:

- **open_trade(position_data)**: Abre un trade en el backend
  - Envía POST a `/api/app/simulated-trade/open-trade`
  - Payload: OpenTradeInputDto
  - Retorna trade ID si exitoso

- **close_trade(trade_id)**: Cierra un trade en el backend
  - Envía POST a `/api/app/simulated-trade/close-trade/{tradeId}`
  - Retorna true si exitoso

- **update_tp_sl(trade_id, tp_sl_data)**: Actualiza TP/SL
  - Envía PUT a `/api/app/simulated-trade/tp-sl/{tradeId}`
  - Payload: UpdateTpSlInputDto

- **update_max_adverse_price(trade_id, max_adverse_price)**: Actualiza MAE
  - Envía PUT a `/api/app/simulated-trade/{tradeId}/update-max-adverse-price`
  - Payload: UpdateMaxAdversePriceInputDto
  - Registra el precio adverso máximo alcanzado

- **get_active_trades()**: Obtiene trades abiertos del backend
  - Envía GET a `/api/app/simulated-trade/active-trades`
  - Retorna lista de SimulatedTradeDto

- **get_virtual_balance()**: Obtiene balance virtual
  - Envía GET a `/api/app/simulated-trade/virtual-balance`
  - Retorna balance actual

- **broadcast_signal(signal_data)**: Envía señal al backend
  - Envía POST a `/api/app/agent/broadcast-signal`
  - Se transmite vía SignalR al frontend

- **broadcast_signals(signals)**: Envía lote de señales
  - Envía POST a `/api/app/agent/broadcast-signals`
  - Optimización para evitar spam de requests

- **get_strategy_profiles()**: Obtiene perfiles de estrategia
  - Envía GET a `/api/app/strategy-profile`
  - Retorna perfiles activos del usuario

#### 3. AuthManager (auth_manager.py)

**Propósito**: Gestiona autenticación OAuth2 con el backend ABP.

**Funcionalidades**:
- Obtiene token JWT usando credenciales de cliente
- Renueva token automáticamente cuando expira
- Proporciona headers de autenticación para requests HTTP

#### 4. StateManager (state_manager.py)

**Propósito**: Gestión de estado local persistente usando SQLite.

**Funcionalidades**:
- Almacena posiciones abiertas localmente
- Cache de métricas de trading
- Estadísticas diarias
- Historial de trades

**Métodos principales**:
- `get_open_positions()`: Retorna posiciones abiertas
- `add_position(position)`: Agrega nueva posición
- `remove_position(trade_id)`: Elimina posición cerrada
- `update_position_tpsl(trade_id, tp, sl)`: Actualiza TP/SL
- `get_daily_stats()`: Retorna estadísticas del día

#### 5. SignalEngine (signal_engine.py)

**Propósito**: Motor de generación de señales de trading.

**Funcionalidades**:
- Analiza datos de mercado
- Calcula indicadores técnicos
- Genera señales de entrada/salida
- Calcula confluencia de múltiples factores

#### 6. RiskManager (risk_manager.py)

**Propósito**: Gestión de riesgo y tamaño de posición.

**Funcionalidades**:
- Calcula tamaño de posición basado en riesgo
- Valida límites de exposición
- Gestiona stop loss dinámico
- Calcula take profit

#### 7. BinanceFetcher (binance_fetcher.py)

**Propósito**: Obtención de datos de mercado de Binance.

**Funcionalidades**:
- Obtiene velas (klines) de múltiples timeframes
- Obtiene precio actual
- Obtiene volumen y liquidez
- Gestiona rate limiting de Binance

#### 8. KlineCache (kline_cache.py)

**Propósito**: Caché de velas en SQLite para reducir llamadas REST.

**Funcionalidades**:
- Almacena velas localmente
- Actualiza caché periódicamente
- Sirve datos desde caché cuando está fresca
- Reduce dependencia de API de Binance

#### 9. SetupValidator (setup_validator.py)

**Propósito**: Validación de setups de trading (LSE y Nexus).

**Funcionalidades**:
- **LSE (Liquidity Sweep Engine)**: Detecta barridos de liquidez
  - Identifica equal lows
  - Detecta rupturas de estructura
  - Calcula score de calidad del setup
  
- **Nexus-15**: Sistema de puntuación de confluencia
  - Analiza 15 factores diferentes
  - Calcula score de confluencia (0-100)
  - Valida umbrales mínimos

**Métodos principales**:
- `validate_pre_trade(candidate, current_price, profile)`: Valida setup antes de entrada
- `validate_lse_setup(candidate, current_price, profile)`: Valida setup LSE
- `calculate_nexus_score(candidate)`: Calcula score Nexus

#### 10. CircuitBreaker (circuit_breaker.py)

**Propósito**: Protección contra condiciones adversas del mercado.

**Funcionalidades**:
- Detecta condiciones de mercado extremas
- Pausa trading cuando se activan breakers
- Reanuda cuando condiciones mejoran

**Breakers implementados**:
- Volatilidad extrema
- Spread anormal
- Liquidez insuficiente
- Condiciones técnicas adversas

#### 11. RedisSignalBridge (redis_signal_bridge.py)

**Propósito**: Puente de comunicación en tiempo real con backend vía Redis.

**Funcionalidades**:
- Escucha canal `verge:superscore` de Redis
- Recibe señales del backend C# en tiempo real
- Inyecta símbolos como candidatos cuando score >= umbral
- Permite operar tokens fuera de watchlist hardcodeada

**Flujo**:
1. Backend C# detecta score alto en un símbolo (ej: TRUTHUSDT al 75%)
2. Publica en canal `verge:superscore`
3. Agente Python recibe mensaje en tiempo real
4. Inyecta símbolo como candidato para análisis
5. Si pasa validaciones, ejecuta trade

#### 12. ReportEngine (report_engine.py)

**Propósito**: Generación de reportes de rendimiento.

**Funcionalidades**:
- Calcula estadísticas de trading
- Genera reportes diarios/semanales/mensuales
- Exporta datos a CSV/JSON
- Visualiza métricas clave

#### 13. TradeAnalytics (trade_analytics.py)

**Propósito**: Análisis avanzado de trades.

**Funcionalidades**:
- Análisis de win rate por timeframe
- Análisis de PnL por símbolo
- Análisis de drawdown
- Identificación de patrones

#### 14. AutoTuner (auto_tuner.py)

**Propósito**: Auto-ajuste de parámetros basado en rendimiento histórico.

**Funcionalidades**:
- Analiza historial de trades
- Identifica parámetros subóptimos
- Genera recomendaciones de ajuste
- Aplica overrides si hay suficientes datos

**Parámetros ajustables**:
- MIN_RR_DEFAULT
- MIN_RR_NEXUS
- MIN_RR_AGGRESSIVE_LSE
- MIN_TP_DISTANCE_ATR_MULT
- MIN_STOP_ATR_MULT
- MAX_ENTRY_SLIPPAGE_PCT
- AGENT_MAX_RANK_FOR_NEXUS_FALLBACK

#### 15. MarketWSServer (market_ws_server.py)

**Propósito**: Servidor WebSocket para datos de mercado.

**Funcionalidades**:
- Expone datos de mercado vía WebSocket
- Endpoint `/health` para health checks
- Endpoint `/logs` para logs del agente
- Corre en puerto 8001

---

## INTERACCIÓN ENTRE BACKEND Y AGENTE

### Protocolo de Comunicación

#### 1. Autenticación

**Flujo**:
1. Agente inicia con credenciales (AGENT_USERNAME, AGENT_PASSWORD)
2. AuthManager solicita token JWT a `/connect/token`
3. Backend valida credenciales y retorna token
4. Agente usa token en headers de todas las requests subsiguientes

**Headers de autenticación**:
```
Authorization: Bearer {jwt_token}
```

#### 2. Apertura de Trade

**Flujo**:
1. Agente detecta oportunidad de trading
2. Valida setup con SetupValidator
3. Calcula TP/SL con RiskManager
4. Envía POST a `/api/app/simulated-trade/open-trade`
5. Backend valida y crea trade en base de datos
6. Backend notifica vía SignalR al frontend
7. Backend retorna trade ID al agente
8. Agente guarda trade ID en StateManager

**Request**:
```json
POST /api/app/simulated-trade/open-trade
{
  "symbol": "BTCUSDT",
  "side": 0,
  "amount": 150.0,
  "leverage": 1,
  "tpPrice": 45000.0,
  "slPrice": 44000.0,
  "strategyProfileId": "00000000-0000-0000-0000-000000000000",
  "agentDecisionJson": "{\"nexus_score\": 85.5, \"confluence\": 78.0}"
}
```

**Response**:
```json
{
  "id": "3a216f15-2753-1044-8754-13a9f377340e",
  "symbol": "BTCUSDT",
  "side": 0,
  "entryPrice": 44250.0,
  "tpPrice": 45000.0,
  "slPrice": 44000.0,
  "status": 0,
  "openedAt": "2026-05-25T00:00:00Z"
}
```

#### 3. Cierre de Trade

**Flujo**:
1. Agente detecta condición de cierre (TP, SL, o señal)
2. Envía POST a `/api/app/simulated-trade/close-trade/{tradeId}`
3. Backend calcula PnL basado en precio actual
4. Backend actualiza balance virtual del usuario
5. Backend calcula MaxAdversePrice si no está seteado
6. Backend notifica vía SignalR al frontend
7. Backend retorna confirmación al agente

**Request**:
```json
POST /api/app/simulated-trade/close-trade/3a216f15-2753-1044-8754-13a9f377340e
```

**Response**:
```json
{
  "id": "3a216f15-2753-1044-8754-13a9f377340e",
  "pnl": 6.42,
  "closedAt": "2026-05-25T00:38:00Z",
  "maxAdversePrice": 0.8682
}
```

#### 4. Actualización de MaxAdversePrice

**Flujo**:
1. Agente monitorea precio en tiempo real para cada posición abierta
2. Para LONG: actualiza si precio actual < max_adverse_price
3. Para SHORT: actualiza si precio actual > max_adverse_price
4. Envía PUT a `/api/app/simulated-trade/{tradeId}/update-max-adverse-price`
5. Backend actualiza campo MaxAdversePrice en base de datos
6. Backend loggea actualización

**Request**:
```json
PUT /api/app/simulated-trade/3a216f15-2753-1044-8754-13a9f377340e/update-max-adverse-price
{
  "maxAdversePrice": 0.8682
}
```

**Response**:
```
Status: 200 OK
```

#### 5. Actualización de TP/SL

**Flujo**:
1. Agente decide ajustar TP/SL (trailing stop, etc.)
2. Envía PUT a `/api/app/simulated-trade/tp-sl/{tradeId}`
3. Backend valida permisos del usuario
4. Backend actualiza TP/SL en base de datos
5. Backend notifica vía SignalR al frontend

**Request**:
```json
PUT /api/app/simulated-trade/tp-sl/3a216f15-2753-1044-8754-13a9f377340e
{
  "tpPrice": 45500.0,
  "slPrice": 44100.0
}
```

**Response**:
```
Status: 200 OK
```

#### 6. Broadcast de Señales

**Flujo**:
1. Agente genera señal para un símbolo
2. Envía POST a `/api/app/agent/broadcast-signal`
3. Backend recibe señal
4. Backend transmite vía SignalR a todos los clientes conectados
5. Frontend actualiza dashboard en tiempo real

**Request**:
```json
POST /api/app/agent/broadcast-signal
{
  "symbol": "BTCUSDT",
  "score": 85.5,
  "confluence": 78.0,
  "direction": 0,
  "timestamp": "2026-05-25T00:00:00Z"
}
```

**Response**:
```
Status: 200 OK
```

#### 7. Sincronización de Perfiles de Estrategia

**Flujo**:
1. Agente inicia o cada 5 minutos
2. Envía GET a `/api/app/strategy-profile`
3. Backend retorna perfiles activos del usuario
4. Agente actualiza lista de perfiles activos
5. Agente usa perfiles para ejecutar trades con diferentes parámetros

**Request**:
```json
GET /api/app/strategy-profile
```

**Response**:
```json
[
  {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Standard Scalping",
    "slMultiplier": 0.6,
    "tpMultiplier": 3.5,
    "maxOpenPositions": 3,
    "isActive": true,
    "color": "rgb(67, 182, 0)"
  },
  {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "Scalping Clone",
    "slMultiplier": 1.2,
    "tpMultiplier": 3.5,
    "maxOpenPositions": 3,
    "isActive": true,
    "color": "rgb(255, 100, 100)"
  }
]
```

### SignalR - Comunicación en Tiempo Real

**Hub**: TradingHub

**Métodos del servidor**:
- `SendAgentLog(log)`: Envía log del agente a clientes conectados
- `SendTradeUpdate(trade)`: Envía actualización de trade
- `SendSignal(signal)`: Envía señal de trading

**Eventos del cliente**:
- `ReceiveAgentLog(log)`: Recibe log del agente
- `ReceiveTradeUpdate(trade)`: Recibe actualización de trade
- `ReceiveSignal(signal)`: Recibe señal de trading

**Flujo de SignalR**:
1. Frontend se conecta a `/hubs/trading`
2. Backend acepta conexión
3. Cuando ocurre un evento (trade abierto/cerrado, señal), backend llama método del hub
4. Hub transmite evento a todos los clientes conectados
5. Frontend recibe evento y actualiza UI

---

## COMPONENTES DEL SISTEMA

### 1. Sistema de Tiers (Watchlist Jerárquica)

**Propósito**: Optimizar escaneo de mercado priorizando símbolos importantes.

**Estructura**:
- **Tier 1 (30 símbolos)**: Alta prioridad
  - Posiciones abiertas (siempre incluidas)
  - Símbolos más volátiles del mercado
  - Monitoreados por TODOS los exchanges (redundancia HA)
  
- **Tier 2 (70 símbolos)**: Prioridad media
  - Distribuidos entre exchanges (balance de carga)
  - Escaneados con menor frecuencia
  
- **Tier 3 (300 símbolos)**: Baja prioridad
  - Resto del universo de símbolos
  - Rotación por ciclo (10 símbolos por ciclo)
  - Escaneados con menor frecuencia

**Beneficios**:
- Reducción de llamadas API a Binance
- Mejor rendimiento del agente
- Monitoreo continuo de posiciones abiertas
- Detección rápida de movimientos en símbolos volátiles

### 2. Sistema de Perfiles de Estrategia

**Propósito**: Permitir múltiples estrategias con parámetros diferentes.

**Perfiles Implementados**:

#### Standard Scalping
- **SL_MULTIPLIER**: 0.6 (~2.5% stop)
- **TP_MULTIPLIER**: 3.5
- **MAX_OPEN_POSITIONS**: 3
- **MIN_CONFLUENCE_SCORE**: 60.0
- **Color**: rgb(67, 182, 0)

#### Scalping Clone
- **SL_MULTIPLIER**: 1.2 (~5.0% stop) - Doble que Standard
- **TP_MULTIPLIER**: 3.5
- **MAX_OPEN_POSITIONS**: 3
- **MIN_CONFLUENCE_SCORE**: 70.0 - 10 puntos más alto que Standard
- **CLONE_MAX_STOP_LOSS_PCT**: 5.0 - Techo absoluto
- **Protecciones**:
  - No puede abrir símbolo si Standard ya lo tiene abierto
  - Evita tokens con rango > 10% (vs 15% Standard)
- **Color**: rgb(255, 100, 100)

**Lógica de Coexistencia**:
- Standard y Clone tienen límites de slots separados
- Pueden coexistir en símbolos diferentes
- Clone NO puede abrir símbolo si Standard ya lo tiene abierto
- Previene doble exposición en la misma bomba

### 3. Sistema de Validación (SetupValidator)

**Componentes**:

#### LSE (Liquidity Sweep Engine)
- Detecta barridos de liquidez en 1h
- Identifica equal lows
- Calcula score de calidad (0-100)
- Modos: conservative | aggressive
- Entry modes: conservative | aggressive

**Validaciones LSE**:
- LSE_MIN_SCORE: 65 (mínimo para considerar)
- LSE_BLOCK_REASONING_SUBSTRING: "R:R bajo"
- LSE_FOLLOW_THROUGH: Confirmación de dirección
- LSE_SYMBOL_COOLDOWN: Cooldown por símbolo tras trade LSE

#### Nexus-15
- Sistema de puntuación de confluencia
- Analiza 15 factores diferentes
- Calcula score de confluencia (0-100)
- Valida umbrales mínimos

**Factores Nexus**:
- Tendencia (MA99, EMA)
- Momentum (RSI, MACD)
- Volumen
- Liquidez
- Volatilidad
- Estructura de mercado
- Niveles de soporte/resistencia
- Y más...

**Validaciones Nexus**:
- MIN_NEXUS_CONFIDENCE: 76.0
- MIN_CONFLUENCE_SCORE: 60.0
- HIGH_VOLATILITY_MIN_CONFLUENCE: 90.0 (cuando rango > 7%)

### 4. Sistema de Gestión de Riesgo

**Componentes**:

#### RiskManager
- Calcula tamaño de posición basado en riesgo
- Valida límites de exposición
- Gestiona stop loss dinámico
- Calcula take profit

**Parámetros de Riesgo**:
- VIRTUAL_CAPITAL_BASE: 10000.0
- RISK_PER_TRADE_PCT: 0.015 (1.5% por trade)
- EQUITY_RISK_PCT_FOR_STOP: 0.01 (1% del equity en riesgo por stop)
- MAX_MARGIN_PER_TRADE_USD: 150
- MAX_NOTIONAL_PER_TRADE_USD: 50000
- MAX_STOP_LOSS_PCT: 9.0 (techo absoluto)
- CLONE_MAX_STOP_LOSS_PCT: 5.0 (techo absoluto para Clone)

#### CircuitBreaker
- Detecta condiciones de mercado extremas
- Pausa trading cuando se activan breakers
- Reanuda cuando condiciones mejoran

**Breakers Implementados**:
- Volatilidad extrema
- Spread anormal
- Liquidez insuficiente
- Condiciones técnicas adversas

### 5. Sistema de Caché (KlineCache)

**Propósito**: Reducir llamadas API a Binance almacenando velas localmente.

**Funcionalidades**:
- Almacena velas en SQLite
- Actualiza caché periódicamente
- Sirve datos desde caché cuando está fresca
- Reduce dependencia de API de Binance

**Beneficios**:
- Reducción de rate limiting
- Mejor rendimiento del agente
- Menor latencia en análisis
- Resiliencia ante caídas de API

### 6. Sistema de Auto-Tuning

**Propósito**: Auto-ajuste de parámetros basado en rendimiento histórico.

**Funcionalidades**:
- Analiza historial de trades
- Identifica parámetros subóptimos
- Genera recomendaciones de ajuste
- Aplica overrides si hay suficientes datos (>= 30 trades)

**Parámetros Ajustables**:
- MIN_RR_DEFAULT
- MIN_RR_NEXUS
- MIN_RR_AGGRESSIVE_LSE
- MIN_TP_DISTANCE_ATR_MULT
- MIN_STOP_ATR_MULT
- MAX_ENTRY_SLIPPAGE_PCT
- AGENT_MAX_RANK_FOR_NEXUS_FALLBACK

---

## FLUJO DE TRADING

### 1. Inicialización del Sistema

```
1. Backend ABP se inicia
   - Carga configuración
   - Conecta a PostgreSQL
   - Inicia SignalR Hub
   - Expone endpoints HTTP

2. Agente Python se inicia
   - Carga config.py
   - Inicializa AuthManager
   - Obtiene token JWT
   - Inicializa todos los componentes
   - Conecta a Redis (SignalBridge)
   - Inicia servidor WebSocket (puerto 8001)

3. Frontend Angular se inicia
   - Conecta a backend
   - Conecta a SignalR Hub
   - Carga datos iniciales
```

### 2. Loop Principal del Agente (cada 5 minutos)

```
1. Sincronizar perfiles de estrategia
   - GET /api/app/strategy-profile
   - Actualizar lista de perfiles activos

2. Escanear mercado (Tier 1 → Tier 2 → Tier 3)
   - Obtener datos de Binance (o caché)
   - Calcular indicadores técnicos
   - Generar señales para cada símbolo

3. Procesar candidatos Redis (SignalBridge)
   - Escuchar canal verge:superscore
   - Inyectar símbolos con score >= umbral

4. Rankear candidatos
   - Ordenar por score de confluencia
   - Aplicar filtros de riesgo

5. Validar setups
   - validate_pre_trade() para cada candidato
   - Validar LSE (si aplica)
   - Validar Nexus-15
   - Validar umbrales mínimos

6. Ejecutar trades
   - Para cada perfil activo:
     - Verificar límite de slots
     - Para Standard: abrir si pasa validaciones
     - Para Clone: abrir si pasa validaciones + protecciones adicionales
       - Verificar que Standard no tiene el símbolo abierto
       - Verificar SL <= CLONE_MAX_STOP_LOSS_PCT
       - Verificar confluencia >= 70
       - Verificar rango <= 10%

7. Monitorear posiciones abiertas
   - Obtener precio actual
   - Actualizar MaxAdversePrice
   - Verificar TP/SL
   - Cerrar si se alcanza TP/SL

8. Broadcast de señales
   - Enviar señales al backend
   - Backend transmite vía SignalR al frontend

9. Generar reportes
   - Actualizar estadísticas
   - Guardar métricas
```

### 3. Flujo de Apertura de Trade

```
1. Agente detecta oportunidad
   - Símbolo: BTCUSDT
   - Score Nexus: 85.5
   - Confluencia: 78.0
   - Dirección: LONG

2. Validar setup
   - validate_pre_trade(candidate, price, profile)
   - Validar LSE (si aplica)
   - Validar umbrales mínimos
   - Validar riesgo

3. Calcular TP/SL
   - SL = entry_price * (1 - range_pct * SL_MULTIPLIER)
   - TP = entry_price * (1 + range_pct * TP_MULTIPLIER)
   - Validar SL <= MAX_STOP_LOSS_PCT

4. Para Clone: Validar protecciones adicionales
   - Verificar Standard no tiene BTCUSDT abierto
   - Verificar SL <= CLONE_MAX_STOP_LOSS_PCT (5.0%)
   - Verificar confluencia >= 70
   - Verificar rango <= 10%

5. Abrir trade
   - POST /api/app/simulated-trade/open-trade
   - Payload: OpenTradeInputDto
   - Incluir strategyProfileId

6. Backend procesa
   - Valida SL/TP contra precio en vivo
   - Verifica límites de capital
   - Crea trade en base de datos
   - Notifica vía SignalR

7. Agente guarda trade ID
   - Guarda en StateManager
   - Inicia monitoreo de MaxAdversePrice
```

### 4. Flujo de Cierre de Trade

```
1. Agente monitorea posición
   - Obtiene precio actual cada tick
   - Actualiza MaxAdversePrice
   - Verifica TP/SL

2. Condición de cierre detectada
   - TP alcanzado
   - SL alcanzado
   - Señal de salida

3. Actualizar MaxAdversePrice final
   - PUT /api/app/simulated-trade/{tradeId}/update-max-adverse-price
   - Payload: UpdateMaxAdversePriceInputDto

4. Cerrar trade
   - POST /api/app/simulated-trade/close-trade/{tradeId}
   - Backend calcula PnL
   - Backend actualiza balance virtual
   - Backend notifica vía SignalR

5. Agente actualiza estado local
   - Elimina de StateManager
   - Actualiza estadísticas
   - Guarda métricas
```

### 5. Flujo de Actualización de MaxAdversePrice

```
1. Agente monitorea precio en tiempo real
   - Para LONG: precio más bajo visto
   - Para SHORT: precio más alto visto

2. Inicialización
   - Al abrir trade: max_adverse_price = entry_price
   - Log: "[MAE] {symbol} LONG init max_adverse_price from entry={price}"

3. Actualización durante trade
   - Si precio actual < max_adverse_price (LONG):
     - max_adverse_price = precio_actual
     - PUT /api/app/simulated-trade/{tradeId}/update-max-adverse-price
     - Log: "[MAE] {symbol} LONG updated max_adverse_price: {price}"
   - Si precio actual > max_adverse_price (SHORT):
     - max_adverse_price = precio_actual
     - PUT /api/app/simulated-trade/{tradeId}/update-max-adverse-price
     - Log: "[MAE] {symbol} SHORT updated max_adverse_price: {price}"

4. Al cerrar trade
   - Backend calcula MaxAdversePrice si no está seteado
   - Aproxima MAE basado en entry y close prices
   - Log: "MaxAdversePrice calculated for {Symbol}: {Price}"
```

---

## CONFIGURACIÓN Y PARÁMETROS

### Configuración del Agente (config.py)

#### Endpoints y URLs
```python
PYTHON_SERVICE_URL = "http://localhost:8005"
ABP_BACKEND_URL = "https://localhost:44396"
REDIS_URL = "redis://localhost:6379/0"
```

#### Credenciales ABP
```python
AGENT_USERNAME = "agent@verge.internal"
AGENT_PASSWORD = "1q2w3E*"
CLIENT_ID = "Verge_App"
CLIENT_SECRET = ""
```

#### Gestión de Riesgo
```python
VIRTUAL_CAPITAL_BASE = 10000.0
RISK_PER_TRADE_PCT = 0.015
EQUITY_RISK_PCT_FOR_STOP = 0.01
MIN_RR_DEFAULT = 2.5
MIN_RR_NEXUS = 2.5
MIN_RR_AGGRESSIVE_LSE = 1.2
MAX_MARGIN_PER_TRADE_USD = 150
MAX_NOTIONAL_PER_TRADE_USD = 50000
```

#### Límites de Trading
```python
MAX_OPEN_POSITIONS = 3
MIN_ENTRY_NEXUS = 76.0
MIN_UPGRADE_NEXUS = 80.0
MAX_TRADES_PER_DAY = 100
MAX_POSITION_DURATION_HOURS = 48
DEFAULT_LEVERAGE = 1
```

#### Umbrales de Inteligencia
```python
MIN_NEXUS_CONFIDENCE = 76.0
MIN_SCAR_SCORE = 4
MIN_CONFLUENCE_SCORE = 60.0
LSE_WARNING_OVERRIDE_SCORE = 85.0
MIN_ESTIMATED_RANGE_PCT = 0.8
```

#### Calibración de Volatilidad
```python
MAX_ESTIMATED_RANGE_PCT = 15.0
MAX_STOP_LOSS_PCT = 9.0
CLONE_MAX_STOP_LOSS_PCT = 5.0
MAX_RSI_LONG_LIMIT = 75.0
TIER3_MIN_CONFLUENCE_SCORE = 65.0
```

#### Regla Sniper de Alta Volatilidad
```python
HIGH_VOLATILITY_RANGE_THRESHOLD = 7.0
HIGH_VOLATILITY_MIN_CONFLUENCE = 90.0
```

#### Take Profit / Stop Loss
```python
TP_MULTIPLIER = 3.5
SL_MULTIPLIER = 0.6
TP_MULT_TREND_FOLLOWING_MAX = 3.2
TP_MULT_MEAN_REVERSION_MAX = 2.0
```

#### Configuración LSE
```python
LSE_ENABLED = true
LSE_MIN_SCORE = 65
LSE_DETECTION_MODE = "conservative"
LSE_DUAL_SCAN = true
LSE_ENTRY_MODE = "aggressive"
LSE_HTTP_TIMEOUT_SEC = 360
LSE_MAX_SYMBOLS_PER_CYCLE = 450
LSE_BATCH_TOP_K = 10
LSE_MAX_INJECTED_CANDIDATES = 10
LSE_REQUIRE_SCAN_BEFORE_ENTRY = true
LSE_MIN_SYMBOLS_PROCESSED_GATE = 1
LSE_REQUIRE_ALL_QUEUED_PROCESSED = true
```

#### Configuración Redis Signal Bridge
```python
REDIS_URL = "redis://localhost:6379/0"
BRIDGE_MIN_SCORE = 45.0
```

#### Kill Switch
```python
AGENT_KILL_SWITCH_CONSECUTIVE_LOSSES = 4
AGENT_KILL_SWITCH_PAUSE_MINUTES = 120
```

#### Configuración de Tiers
```python
TIER2_MIN_VOLATILITY_PCT = 0.3
TIER3_ROTATE_PER_CYCLE = 10
_TIER1_SIZE = 30
_TIER2_SIZE = 70
_TOTAL_LIMIT = 400
```

### Configuración del Backend (appsettings.json)

#### Connection String
```json
{
  "ConnectionStrings": {
    "Default": "Server=localhost;Database=Verge;Trusted_Connection=True;"
  }
}
```

#### Configuración Redis
```json
{
  "Redis": {
    "ConnectionString": "localhost:6379"
  }
}
```

#### Configuración SignalR
```json
{
  "SignalR": {
    "EnableDetailedErrors": true,
    "HubTimeout": 30
  }
}
```

---

## RESUMEN DE ARQUITECTURA

### Backend (ABP Framework)
- **Framework**: ABP Framework (ASP.NET Core)
- **Base de Datos**: PostgreSQL
- **ORM**: Entity Framework Core
- **Comunicación en tiempo real**: SignalR
- **Pub/Sub**: Redis
- **Arquitectura**: DDD (Domain-Driven Design)
- **Patrón**: CQRS (Command Query Responsibility Segregation)

### Agente Python
- **Framework**: Python 3.x
- **Caché local**: SQLite
- **Comunicación HTTP**: requests
- **Comunicación en tiempo real**: Redis Pub/Sub
- **Análisis técnico**: pandas, numpy
- **Gestión de estado**: StateManager (SQLite)

### Frontend Angular
- **Framework**: Angular
- **Comunicación en tiempo real**: SignalR Client
- **UI Components**: shadcn/ui, Lucide Icons
- **Styling**: TailwindCSS

### Infraestructura
- **Contenedores**: Docker
- **Orquestación**: docker-compose
- **Base de Datos**: PostgreSQL
- **Cache**: Redis
- **Message Broker**: Redis Pub/Sub

---

## CONCLUSIÓN

El sistema VERGE Trading es una plataforma de trading autónoma sofisticada que combina:

1. **Backend robusto** basado en ABP Framework para gestión de datos y persistencia
2. **Agente inteligente** en Python para análisis de mercado y ejecución de trades
3. **Frontend moderno** en Angular para monitoreo y control
4. **Comunicación en tiempo real** vía SignalR y Redis
5. **Sistema de perfiles múltiples** para diferentes estrategias de trading
6. **Protecciones de riesgo** avanzadas para prevenir pérdidas catastróficas
7. **Sistema de caché** para reducir dependencia de APIs externas
8. **Auto-tuning** para optimizar parámetros basado en rendimiento histórico

La arquitectura modular permite fácil extensión y mantenimiento, mientras que la separación de responsabilidades asegura que cada componente se especialice en su función específica.
