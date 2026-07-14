# Verge — guía rápida de orientación

Trading bot autónomo (cripto futuros, simulado por ahora). Cuatro piezas:

- **`agent/`** — agente Python (`verge_agent.py`) que corre en loop (`LOOP_INTERVAL_SECONDS=300`), escanea el watchlist (~400 símbolos), genera candidatos por estrategia, los valida (`setup_validator.py`) y los ejecuta contra el backend C# vía HTTP. `risk_manager.py` calcula SL/TP/tamaño de posición.
- **`python-service/`** — servicio FastAPI de análisis (Nexus15, FVG, ADN Compression, LSE, SCAR, Arrow Peak, etc.) que el agente consulta para scores/zonas. Cachea klines compartidas (`shared_kline_cache.py`) para no golpear a Binance de más.
- **`src/`** — backend .NET (ABP Framework). Persiste trades simulados, expone la API que consume Angular, corre `SimulationMarkPriceWorker.cs` (tick de mark price cada 1s, gestiona TP/SL de las posiciones simuladas).
- **`angular/`** — dashboard/frontend.

Para el diagrama completo y detalle de servicios ver **`DOCUMENTACION_COMPLETA.md`** (puede estar algo desactualizado en las estrategias más nuevas — confiar más en el código y en el progress log para eso).

## Antes de asumir que no hay contexto previo

Leer **`.claude/PROGRESS_LOG.md`** (últimas ~50-80 líneas si es largo) — es un changelog fechado, sesión a sesión, de qué se arregló/construyó y por qué. Esto YA lo pide el `~/.claude/CLAUDE.md` global del usuario, pero se refuerza acá porque en este proyecto es crítico: hay mucho estado no obvio desde el código solo (ej. qué servicios necesitan reinicio manual, qué bugs de datos históricos quedaron parcialmente arreglados).

## Cosas que no son obvias leyendo el código

- **Nada tiene hot-reload.** Agente Python, python-service y backend .NET necesitan reinicio manual para tomar cambios. El contenedor `market-data` (`verge-python-ai`) en particular NO tiene volumen montado — un `docker restart` simple no alcanza, hay que rebuildear la imagen.
- **Patrón de "inyección directa"**: estrategias con SL/TP estructural propio (MA Slope, Arrow Peak, Total Sweep, Golden U-Turn, ADN Compression, FVG) se inyectan directo a la lista de candidatos del agente (bypaseando el matching genérico de `AllowedSources` por perfil) y están marcadas con un flag `*_mode` (`ma_slope_mode`, `fvg_mode`, etc.) que:
  - `agent/risk_manager.py` usa para saber que el SL/TP viene armado y no debe recalcularlo con RR×SL genérico.
  - `agent/setup_validator.py::_is_direct_injection_candidate()` usa para eximir del veto `range_too_small` (rango estimado, no aplica a estas) y `disabled_signal_for_tier` (pensado para señales Nexus tipo "confianza 60-80%").
  - **Si se agrega una estrategia nueva de este tipo, hay que agregar su flag en AMBOS lugares** — olvidar el segundo (`setup_validator.py`) vetea el 100% de sus candidatos silenciosamente (pasó con FVG el 2026-07-13, ver progress log).
- **El monitoreo de posiciones abiertas corre a la misma velocidad que el loop principal (5 min)**, no en tiempo real — aunque el backend C# sí tickea mark price cada 1s. Esto significa que lógica de protección de ganancia (Cosecha Inteligente, trailing) puede reaccionar tarde a picos reales que sí quedaron grabados en la base. Ver progress log 2026-07-12 (caso BEATUSDT) — arquitectura pendiente de decisión, no arreglada.
- Horarios: todo lo que se muestre en UI debe fijar explícitamente `America/Argentina/Buenos_Aires` (no confiar en timezone del browser/SO).
