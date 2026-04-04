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
