# Reporte de Arquitectura y Handover: Proyecto Verge

Este documento tiene como objetivo poner en contexto a un nuevo desarrollador o agente de IA sobre el estado actual, la arquitectura técnica y las reglas críticas del ecosistema **Verge**.

## 1. Visión General
Verge es una plataforma de trading algorítmico distribuida que combina el poder de **Freqtrade** para la ejecución de órdenes, un **Backend en .NET 10 (ABP Framework)** para la orquestación y gestión, y un **Motor de IA en Python** para el análisis técnico predictivo.

---

## 2. Stack Tecnológico y Conectividad

El sistema corre de forma híbrida (procesos locales + contenedores Docker).

| Componente | Tecnología | Ubicación / Puerto | Función |
| :--- | :--- | :--- | :--- |
| **Backend API** | .NET 10 (ABP Framework) | `localhost:44396` | Orquestador central, Auth, CRUD de bots y Proxies. |
| **Frontend UI** | Angular | `localhost:4200` | Dashboard de control y visualización de señales. |
| **Trading Engine** | Freqtrade (Docker) | `127.0.0.1:8080` | Ejecución de trades reales/paper. |
| **AI Service** | FastAPI / Python (Docker) | `localhost:8000` | Análisis de RSI, MACD, Regímenes y predicciones. |
| **Base de Datos** | PostgreSQL 16 | **Puerto: 5433** | Persistencia de tenencia y configuración de bots. |
| **Message Broker** | Redis | Puerto estándar (6379) | Pub/Sub para señales en tiempo real (SuperScore). |

> [!IMPORTANT]
> **Puerto PostgreSQL:** El sistema está configurado para usar el puerto **5433**. No intentes cambiarlo a 5432 sin verificar la instancia de Docker, ya que 5433 es el puerto estable actual.

---

## 3. Arquitectura Funcional: "La Maquina de Datos"

Verge no es un monolito; es un pipeline de datos circular:

### A. El Pipeline del Scanner (Señales)
1. **MarketScannerService** (.NET) consulta cada X segundos los precios de Binance (limitado por un semáforo de 5 hilos para evitar 429).
2. Envía los datos al **Python AI Service** (`/analyze-technicals`).
3. El resultado se publica en **Redis** bajo la key `verge:superscore`.
4. El **BotDataPublisherService** escucha Redis y:
   - Envía los datos vía **SignalR** al Frontend (toasts y tablas dinámicas).
   - Actualiza un `HSET` en Redis para que el `BotAppService` muestre el ranking en el Dashboard.

### B. Integración con Freqtrade (Ejecución)
- No usamos la base de datos de Freqtrade directamente.
- Nos comunicamos con su **REST API** (`FreqtradeAppService`).
- **Control Virtual:** El sistema simula que un usuario "Borra" o "Pausa" una moneda manipulando dinámicamente el archivo `freqtrade/user_data/config.json` (whitelist/blacklist) y disparando un `/reload_config`.

### C. Persistencia y Sincronización (`BotSyncJob`)
Dado que hay dos fuentes de verdad (el `config.json` de Freqtrade y la tabla `TradingBots` en Postgres), el **BotSyncJob** corre cada 2 minutos para asegurar que:
- Si un bot está en Freqtrade pero no en DB -> Se importa.
- Si un bot está en DB marcado como activo pero no en Freqtrade -> Se inyecta en el JSON.

---

## 4. Reglas Críticas para Desarrolladores (NO ROMPER)

### ⚠️ Regla #1: El "Exchange" puede ser un String
En `FreqtradeAppService.GetStatusAsync()`, Freqtrade a veces devuelve el campo `exchange` como un string plano en lugar de un objeto. 
- **Error habitual:** `InvalidOperationException` al intentar leerlo como objeto.
- **Solución:** Verificar siempre el `ValueKind` antes de procesar el JSON.

### ⚠️ Regla #2: No bypassear el Backend
El Frontend **nunca** llama a Freqtrade o al Python Service directamente. Siempre pasa por un `AppService` en .NET para auditoría, seguridad y contratos de datos.

### ⚠️ Regla #3: Semáforo de Binance
En `MarketDataManager`, existe un `SemaphoreSlim(5, 5)` estático. 
- **Por qué:** Evita que múltiples instancias del scanner bloqueen la IP por exceso de peticiones a Binance. No lo aumentes agresivamente.

### ⚠️ Regla #4: Ciclo de Vida del Python Service
El servicio de IA corre en un contenedor Docker llamado `verge-python-ai`. 
- Si modificas el código en `python-service/`, debes hacer `docker build` y reiniciar el contenedor. No basta con editar el archivo local.

---

## 5. Lore y Contexto Reciente (2024-04)

- **Estabilización de DB:** Pasamos por un periodo de inestabilidad donde el backend no conectaba a Postgres. Se resolvió fijando el puerto **5433**.
- **Migraciones:** La tabla `TradingBots` es crítica y debe estar sincronizada. Si agregas columnas a la entidad, asegúrate de que el `BotSyncJob` las maneje o ignore según corresponda.
- **Multi-Bot:** El sistema soporta múltiples monedas ("bots virtuales") corriendo bajo una única instancia de Freqtrade mediante el manejo dinámico de la lista blanca.

---

## 6. Siguientes Pasos Recomendados
- **Refuerzo de Estrategias:** Actualmente el sistema usa señales de IA, pero se busca integrar lógicas de Groq/Gemini para filtrado de sentimiento.
- **Escalabilidad del Scanner:** Si se planea analizar más de 50 monedas, el pipeline de Redis deberá optimizarse para evitar latencia en SignalR.

---
*Este informe fue generado por Antigravity para asegurar la continuidad técnica del proyecto Verge.*
