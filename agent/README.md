# VERGE Autonomous Trading Agent

Agente de trading autónomo v2.0 para la plataforma VERGE. Se encarga de monitorear automáticamente los mercados cruzando datos de SCAR (Whale Extraction) y Nexus-15 (AI Price Action), abriendo posiciones simuladas en el backend de VERGE y llevándolas a Take Profit (TP) o Stop Loss (SL).

## 🚀 Requisitos

- Python 3.10+
- `pip install requests`

## ⚙️ Configuración Inicial

Antes de correr el agente, verificá las variables en `config.py`:

1. **Credenciales de ABP:**
   Asegurate que el usuario `agent@verge.internal` (con la password `1q2w3E*`) exista en la base de datos de ABP y pueda loguearse.
2. **Endpoints:**
   Si corrés el backend ABP o el Python service en puertos/URLs diferentes a los default, modificalos en `config.py` o pasálos como variables de entorno (`ABP_BACKEND_URL`, `PYTHON_SERVICE_URL`).
3. **Telegram (Opcional):**
   Si querés notificaciones, poné el `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en `config.py` (o como `.env`).

## 💻 Cómo Correrlo (Arquitectura Anti-Ban)

Para evitar que Binance bloquee la IP por exceso de peticiones (Rate Limit), el sistema utiliza una arquitectura de dos componentes: un servidor WebSocket local y el Agente Principal.

**Se necesitan 2 terminales abiertas simultáneamente:**

**Terminal 1 — Iniciar el Servidor WebSocket (Hacerlo primero)**
Este servidor abre una sola conexión a Binance y cachea el historial y los precios en vivo.
```bash
python market_ws_server.py
```
*⚠️ Esperá a ver el mensaje "[HTTP] Servidor listo en http://localhost:8001" antes de continuar.*

**Terminal 2 — Iniciar el Agente**
El agente iniciará su ciclo, validará su auth contra el backend ABP, y comenzará a evaluar el mercado usando los datos en tiempo real del servidor local.
```bash
python verge_agent.py
```

## 📊 Persistencia y Logs

Toda la data generada por el agente se guarda en la carpeta `data/`:

- `positions.json`: Estado en vivo de las posiciones abiertas para trackear TP/SL.
- `daily_stats.json`: Límites de seguridad diarios para evitar el sobre-operar (anti-churn).
- `trades.csv`: Base de datos de análisis post-mortem. Útil para cargar en un Excel y analizar qué combinación de señales funciona mejor (ej. filtrar por SCAR+Nexus vs Nexus solo).
