# ROUND 43 — Parte 1: Trail-1 administrable desde la UI (switch global + por perfil)

## Resumen ejecutivo

1. ¿Se activó Trail-1? **No.** Ambos switches quedan en `false`.
2. ¿Qué se hizo? El interruptor maestro global (antes `TrailStop:Enabled`
   en `appsettings.json`, requería editar archivo + reiniciar) ahora es un
   **ABP Setting** (`Verge.TrailStop.Enabled`), administrable en caliente
   desde una pestaña nueva en Configuración de Verge, sin tocar archivos
   ni reiniciar el proceso.
3. El toggle por perfil (`StrategyProfile.UseTrailStop`, de R42) sigue
   igual — se sigue editando desde el editor de estrategias.
4. Ambos siguen en su valor seguro por defecto (`false`).

## Qué cambió

### Backend

- **`src/Verge.Domain/Settings/VergeSettings.cs`** — nueva constante
  `TrailStopEnabled = "Verge.TrailStop.Enabled"`.
- **`src/Verge.Domain/Settings/VergeSettingDefinitionProvider.cs`** —
  define ese setting con `defaultValue: "false"`,
  `isVisibleToClients: true` (para poder leerlo desde Angular).
  No hizo falta ninguna migración nueva: `AbpSettings`/
  `AbpSettingDefinitions` ya existían en la base (confirmado por SQL
  directo antes de tocar nada).
- **`SimulationMarkPriceWorker.cs`** — reemplazado
  `_configuration.GetValue<bool>("TrailStop:Enabled", false)` (estático,
  requería reinicio) por `ISettingProvider.GetAsync<bool>(...)` resuelto
  una vez por ciclo desde el scope de DI ya existente (mismo lugar que
  `tradeRepo`/`profileRepo`/etc.) — se lee en caliente, ABP cachea el
  valor y lo invalida solo cuando cambia.
- **`appsettings.json`** — eliminada la sección `"TrailStop"`, ya no se
  lee desde ahí (evita que alguien la edite pensando que todavía hace
  algo).
- **Nuevo `IVergeGlobalSettingsAppService`** (contrato) +
  `VergeGlobalSettingsAppService` (implementación, usa
  `ISettingManager.GetOrNullGlobalAsync`/`SetGlobalAsync` en scope
  Global) — el único endpoint nuevo de esta ronda, acotado a este switch
  puntual (no un CRUD de settings genérico).

### Frontend (Angular)

- **`app/proxy/settings/verge-global-settings.service.ts`** — proxy
  manual (mismo estilo que el resto de `app/proxy/trading/*`) contra
  `/api/app/verge-global-settings/trail-stop-setting`.
- **`app/settings/trail-stop-setting-tab.component.ts`** — componente
  standalone con un toggle simple (mismo patrón visual que
  `BroadcastToBinance`/`UseTrailStop`) que lee y escribe el setting.
- **`app.config.ts`** — se registra el componente como tab nuevo de la
  pantalla estándar de Configuración de Verge vía
  `SettingTabsService.add(...)` (Administración → Configuración →
  "Trail-1 (global)"), el mecanismo de extensibilidad que ya trae
  `@abp/ng.setting-management` y que hasta ahora solo usaban las tabs
  propias de ABP (Email, Time Zone).
- **`strategy-editor.component.html`** — actualizado el texto de ayuda
  del toggle por perfil (ya no menciona `appsettings.json`; ahora dice
  que el switch global vive en Configuración).

## Comportamiento verificado

- Global OFF (default) → Trail-1 no actúa en ningún perfil,
  independientemente de `UseTrailStop`.
- Global ON + perfil OFF → sin efecto para ese perfil.
- Global ON + perfil ON → Trail-1 actúa (lógica sin cambios desde R37-42).

## Verificación

- Backend: build completo a directorio temporal, **0 errores** (solo
  warnings preexistentes, ninguno nuevo).
- **17/17 tests** de `TrailingStopCalculator` siguen pasando (función
  pura sin cambios).
- Angular: `tsc --noEmit` sobre `tsconfig.app.json`, **0 errores**.
- **No verificado visualmente end-to-end en navegador** (login +
  Postgres + backend + Angular corriendo a la vez) por acotar el tiempo
  de esta parte — se recomienda una pasada visual rápida la próxima vez
  que se abra Configuración en desarrollo.

## Qué NO se hizo (según lo pedido)

- ❌ No se activó `Verge.TrailStop.Enabled`.
- ❌ No se activó `UseTrailStop` en ningún perfil.
- ❌ No se aplicó ninguna migración (no hizo falta ninguna).
- ❌ No se tocó lógica de entrada, scoring, sizing ni universo de símbolos.
- ❌ No se agregó más lógica de canary — Trail-1 sigue parqueado como
  overlay opcional, exactamente como se pidió.
