# Preregistro — fidelidad prospectiva ledger real vs replay

**Estado:** preparado el 2026-09-30; no ejecutado. Este documento se congela antes de que el ledger acumule observaciones y no autoriza cambios de estrategia ni producción.

## Pregunta

Para cada posición que el ledger registre como aceptada y cerrada, ¿el replay congelado predijo el mismo motivo de cierre y un retorno suficientemente próximo? La comparación evalúa fidelidad descriptiva del replay; no evalúa rentabilidad ni selecciona variantes.

## Fuentes y unidad de análisis

- Ledger append-only: eventos `execution_accepted` y `position_close_decision` de `agent/data/scan_ledger.jsonl` (o sus rotaciones), esquema `agent/scan_ledger.py`.
- Replay: JSONL normalizado producido con el código/configuración congelados al inicio de la ventana. Cada fila debe contener `trade_id` o (`symbol`, `side`, `opened_at_utc`), además de `close_reason` y `return_pct`.
- Unidad primaria: posición cerrada con una aceptación y un cierre ledger emparejables. `trade_id` es la clave primaria. Si no existe en el replay, el fallback queda limitado a símbolo+lateral+apertura dentro de ±5 minutos y se informa como emparejamiento débil.
- Se excluyen y cuentan por separado los cierres sin `return_pct`, sin `rule`, sin `trade_id`/campos de fallback, duplicados ambiguos y posiciones aún abiertas. Nunca se imputan.

## Tamaño mínimo antes de emitir un veredicto

Se requiere **300 señales detectadas**, **200 posiciones aceptadas y cerradas emparejadas** y **30 días calendario distintos**, con al menos **20 días efectivos** al bootstrap por bloques de día. La cobertura de señales permite auditar selección; los 200 cierres dan, aun en el peor caso p=0,5, un semiancho normal aproximado de 6,9 pp para una proporción, y 30 días evita presentar una racha de mercado como independencia de 200 operaciones. Por debajo de cualquiera de esos mínimos, el script sólo emite `INSUFICIENTE`, nunca PASS/FAIL.

Los intervalos de proporciones y de error medio se calculan por bootstrap de días (10.000 remuestreos, semilla 20260930). El informe siempre muestra N de posiciones y N efectivo de días.

## Criterios congelados

### Motivo de salida

Se normalizan sin inferencia: TP/take-profit a `TP`; SL/stop-loss a `SL`; timeout/zombie/max-duration a `TIMEOUT`; cualquier otro valor conserva su mayúscula literal. Un par **coincide** sólo si ambos motivos normalizados son idénticos. El componente de motivo es `COINCIDE` si la tasa puntual es >=80% **y** el límite inferior del IC bootstrap 95% es >=70%; es `NO_COINCIDE` en otro caso con N suficiente.

### Retorno fino

El error firmado es `retorno_replay_pct - retorno_ledger_pct`, en puntos porcentuales. Un par **coincide** si `abs(error) <= 0,25 pp`, exactamente la tolerancia fijada antes de la Fase 1B (`MISION_LOG.md`, 2026-09-20). El componente de retorno es `COINCIDE` si la tasa puntual es >=80%, su límite inferior bootstrap 95% es >=70%, y el IC bootstrap 95% del error medio contiene 0 y queda completo dentro de [-0,25, +0,25] pp. Si no, es `NO_COINCIDE`; con N insuficiente es `INSUFICIENTE`.

### Fidelidad general

`COINCIDE` sólo si motivo y retorno son `COINCIDE`, la tasa de emparejamiento fuerte (`trade_id`) es >=95%, y no hay más de 2% de cierres ledger sin campos imprescindibles. Cualquier otro resultado con N suficiente es `NO_COINCIDE`. Esta etiqueta no afirma que el replay represente PnL futuro.

## Salidas esperadas

`agent/backtest/ledger_replay_fidelity.py` genera `result.json` e `informe.md`, conserva la lista de exclusiones y no escribe ni modifica el ledger. No se debe correr hasta que se cumpla el mínimo prospectivo; se permite `--help` y un chequeo sintáctico antes.

## Límites conocidos

El ledger nuevo no reconstruye datos anteriores al despliegue. El resultado sólo cubre estrategias/perfiles y reglas efectivos registrados por el ledger; cambios de configuración dentro de una ventana deben segmentarse por `profile_id` y `parameter_hash` antes de interpretar una tasa agregada.
