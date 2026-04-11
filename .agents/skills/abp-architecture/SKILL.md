---
name: ABP Architecture Rules
description: Reglas estrictas para seguir la arquitectura DDD y ABP Framework en el proyecto Verge.
---

# Reglas de Arquitectura ABP Framework y DDD

Al trabajar en el proyecto Verge, es **OBLIGATORIO** respetar la arquitectura ABP y Domain-Driven Design (DDD). Nunca rompas este flujo arquitectónico.

## 1. Nunca bypassear el Backend
**El frontend (Angular) NUNCA debe comunicarse directamente con APIs externas de terceros** o contenedores internos aislados (como el de Freqtrade, Binance, etc.).

## 2. Flujo de Trabajo Obligatorio
Si necesitas integrar una nueva API o servicio:
1. **Modelos (C#):** Crea los DTOs y Requests/Responses en la capa `Application.Contracts` (o equivalente) del backend en .NET.
2. **Interfaz de Servicio (C#):** Define un `I[Nombre]AppService` en `Application.Contracts`.
3. **Implementación (C#):** Implementa el servicio `[Nombre]AppService` en la capa `Application`. Desde allí invocas al servicio externo (ej. Freqtrade API usando HttpClientFactory).
4. **Proxy (Angular):** Una vez que compila y corre el backend, asegúrate de correr el generador de proxy del lado de Angular.
   - Comando habitual: `abp generate-proxy -t ng`
5. **Uso en Frontend (TypeScript):** Consumir el servicio proxy generado (`[Nombre]Service`) e invocar los métodos desde allí, tipados estáticamente.

## 3. Interfaces en TypeScript
Nunca escribas interfaces a mano en el Frontend (`src/app/services/*.models.ts`) si su única función es mapear servicios del backend. Deja que `abp generate-proxy` se encargue de esto para garantizar que la API de .NET y Angular estén siempre sincronizadas y mantengan el contrato.

## ⚠️ REGLA CRÍTICA: Python AI Service (puerto 8000)

**NUNCA modifiques la infraestructura del python-service sin leer esto primero.**

El servicio Python de IA (`python-service/main.py`) **SIEMPRE corre como contenedor Docker**, NO como proceso local.
- El contenedor se llama: `verge-python-ai`
- Puerto: `0.0.0.0:8000->8000/tcp`
- Este contenedor puede llevar días corriendo y respondiendo 200 OK aunque no se vea actividad en consola local.

### Verificación rápida (antes de asumir que está roto):
```bash
docker logs verge-python-ai --tail 50
docker ps --filter "publish=8000"
```

### Reglas de oro:
1. **NUNCA pares ni elimines el contenedor `verge-python-ai` sin confirmación explícita del usuario.**
2. **Si el usuario ejecuta `python main.py` localmente, el proceso levanta pero Docker ya tiene el puerto 8000 tomado.** Los requests siguen llegando al contenedor — eso es correcto y esperado.
3. **Si necesitas actualizar el código del servicio**, debes hacer `docker build` y `docker restart verge-python-ai`, NO simplemente editar el archivo local y asumir que se actualiza solo.
4. **El `.NET backend** (`MarketScannerService`) llama al contenedor Docker via `http://localhost:8000` (o una URL configurada en `appsettings.json`). Ese target nunca debe cambiar sin actualizar también la config del backend.
5. **Si hay múltiples procesos en el puerto 8000** (verificar con `netstat -ano | findstr ":8000"`), es NORMAL que Docker (`com.docker.backend`, `wslrelay`) aparezca — es la plomería interna de Windows/WSL. Solo preocuparse si el contenedor `verge-python-ai` NO aparece en `docker ps`.
