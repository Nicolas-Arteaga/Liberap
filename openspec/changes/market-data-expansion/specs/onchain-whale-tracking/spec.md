## ADDED Requirements

### Requirement: Reemplazo del score de ballenas basado en texto
El sistema SHALL reemplazar el cálculo actual de `whaleScore` en `dashboard.component.ts` (keyword-matching sobre mensajes de texto, con un valor default de 65 si matchea una palabra clave) por una fuente de datos on-chain real.

#### Scenario: Alerta con palabra clave pero sin actividad on-chain real
- **WHEN** un mensaje de alerta contiene la palabra "ballena" pero no hay movimiento real de wallets grandes detectado en la fuente on-chain
- **THEN** el score de ballenas NO se activa solo por la palabra clave — depende del dato real

### Requirement: Flujos netos exchange in/out por símbolo
El sistema SHALL consultar flujos netos de entrada/salida de exchanges para los activos relevantes del watchlist (al menos los de mayor capitalización/liquidez, dado el costo de APIs on-chain), con la misma disciplina de caché que el resto del sistema para no exceder límites de la fuente de datos.

#### Scenario: Fuente on-chain no disponible o rate-limited
- **WHEN** la API on-chain configurada no responde o excede su límite
- **THEN** el sistema degrada con gracia (mismo patrón que `Nexus15ModelLoader`: valor neutro/None auditable, nunca un dato inventado) y lo deja registrado en el log, no en silencio total

### Requirement: Visibilidad de que el dato es real
El sistema SHALL indicar en el dashboard, de forma visible, si el score de ballenas mostrado proviene de datos on-chain reales o de un fallback/placeholder — para no repetir el problema encontrado (una UI que parece real pero no lo es, sin que nadie lo note).

#### Scenario: Fallback activo mostrado en la UI
- **WHEN** el sistema está usando el fallback por falta de datos on-chain
- **THEN** el widget de ballenas lo indica explícitamente (ej. badge "sin datos on-chain"), en vez de mostrar un número sin contexto
