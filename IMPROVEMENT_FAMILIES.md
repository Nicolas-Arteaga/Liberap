# Familias preregistradas de mejora acotada

**Versión:** `1.0-draft`  
**Estado:** Fase B, catálogo para revisión. No implementa un motor, no evalúa
resultados, no promociona candidatos y no modifica producción.

## Propósito

Este documento fija el espacio de búsqueda que podrá usar el bucle
Research ↔ Máquina. No hay mutación libre, optimización continua ni selección
posterior a mirar resultados: cada identificador de variante es una regla
finita, determinista y auditable.

Un diagnóstico válido elige la categoría `main_area` de `diagnosis.json`. En
un turno futuro del motor se aplica **exactamente una** variante aún no usada
de la familia correspondiente. No se combinan filtros, cambios de tamaño,
SL, TP ni salidas en la misma revisión.

Este catálogo no afirma que alguna variante funcione. Variantes equivalentes
ya medidas sobre MA3 siguen siendo evidencia negativa: 43 hipótesis/variantes
auditadas y 0 PASS robustos, documentadas en `MISION_LOG.md` (2026-09-29/30).
La reutilización evita inventar reglas después de ver cada diagnóstico.

## Reglas comunes de aplicación

1. La entrada es el único punto de partida: se copia íntegramente la revisión
   padre y se genera `research_loop/<candidate_id>/<revision+1>/` nuevo. Nunca
   se edita la revisión anterior.
2. La nueva revisión declara `parent_revision`, `improvement_area`,
   `improvement_variant` y una descripción determinista de la transformación.
   La nueva población y el manifiesto reciben sus SHA-256 propios conforme a
   `LOOP_PROTOCOL.md`.
3. Si faltan velas, BTC, volumen, ATR u otro insumo causal indispensable, la
   variante queda `NOT_APPLICABLE_MISSING_INPUT`; no se la sustituye ni se
   relajan sus parámetros.
4. Si la regla deja la población vacía o viola las seis integridades, la
   revisión se diagnostica como `INVALID`. No se intenta una segunda regla en
   ese mismo turno.
5. Los valores numéricos de abajo son constantes de este preregistro. El motor
   no puede barrer, interpolar ni ajustar umbrales.
6. Ninguna variante crea, edita ni activa `StrategyProfiles`; todas son
   transformaciones de investigación offline.

## Convenciones causales

- Una vela de 1 h o 15 m sólo se puede usar una vez cerrada antes de
  `open_ms` (para filtrar la entrada) o de la decisión de salida.
- `ATR14_1h` es la media simple de los últimos 14 True Range de velas 1 h
  cerradas; no usa Wilder ni velas futuras.
- `BTC24h` es la variación causal de BTC al instante de la entrada. `bear` es
  menor a -2 %, `bull` mayor a +2 % y el resto es `flat`.
- `vol_tercil` se calcula sólo con historia previa de la serie correspondiente;
  `low` y `high` son los terciles inferior y superior.
- Si una estrategia no suministra `side=0/1`, no es candidata a estas familias
  hasta normalizarse al contrato de `LOOP_PROTOCOL.md`.

## Catálogo fijo por categoría

### ENTRADA — selección o dirección de señales

Estas reglas sólo conservan/eliminan o invierten una entrada ya materializada;
no cambian SL, TP, tamaño ni salida.

| ID | Regla exacta | Insumos | Origen auditado |
| --- | --- | --- | --- |
| `entry_hour_00_05_btc_bear` | Conservar sólo entradas con hora UTC 00:00–05:59 y `BTC24h < -2 %`. | reloj UTC, BTC24h | F4 filtros combinados |
| `entry_hour_18_23_btc_bull` | Conservar sólo entradas con hora UTC 18:00–23:59 y `BTC24h > +2 %`. | reloj UTC, BTC24h | F4 filtros combinados |
| `entry_hour_00_05_vol_low` | Conservar sólo entradas 00:00–05:59 UTC con `vol_tercil=low`. | reloj UTC, volatilidad causal | F4 filtros combinados |
| `entry_hour_18_23_vol_high` | Conservar sólo entradas 18:00–23:59 UTC con `vol_tercil=high`. | reloj UTC, volatilidad causal | F4 filtros combinados |
| `entry_btc_bear_vol_high` | Conservar sólo entradas con `BTC24h < -2 %` y `vol_tercil=high`. | BTC24h, volatilidad causal | F4 filtros combinados |
| `entry_btc_bull_vol_low` | Conservar sólo entradas con `BTC24h > +2 %` y `vol_tercil=low`. | BTC24h, volatilidad causal | F4 filtros combinados |
| `entry_invert_side` | Cambiar cada LONG a SHORT y cada SHORT a LONG; intercambiar geométricamente SL/TP a la misma distancia porcentual de `entry`. | side, entry, SL, TP | Fase A/B v2 |

`entry_invert_side` no reinterpreta una señal: es una imagen especular fija.
Los seis filtros son exactamente las seis intersecciones diagonales congeladas
para F4; no se agregan intersecciones alternativas.

### COSTOS — evitar entradas cuyo movimiento causal es demasiado pequeño

Las variantes sólo eliminan entradas. No reducen el costo declarado ni
reescriben comisiones/spread para hacer mejor un resultado.

| ID | Regla exacta | Insumos |
| --- | --- | --- |
| `cost_atr14_ge_1_5x_roundtrip` | Conservar sólo si `ATR14_1h / entry * 100 >= 1.5 * cost_pct`. | ATR14_1h causal, entry, cost_pct |
| `cost_atr14_ge_2_0x_roundtrip` | Conservar sólo si `ATR14_1h / entry * 100 >= 2.0 * cost_pct`. | ATR14_1h causal, entry, cost_pct |
| `cost_volume_ge_1_5x_mean20` | Conservar sólo si el volumen de la última vela cerrada es al menos 1.5 veces la media simple de las 20 velas cerradas previas. | volumen causal |

`cost_pct` es el costo ida+y+vuelta que ya usa `AdapterDefinition` (por
defecto, 0,08 %, es decir 0,04 % por lado). Estas reglas son filtros, no una
afirmación de que el costo real sea menor.

### PAYOFF — objetivo y captura de beneficio

| ID | Regla exacta | Insumos | Origen auditado |
| --- | --- | --- | --- |
| `payoff_tp_short_50` | Reemplazar TP por el punto situado al 50 % de la distancia entre `entry` y TP original; SL no cambia. | entry, TP, side | Fase 2 / 2b |
| `payoff_break_even_1r` | Después de alcanzar +1R, mover SL a `entry`; TP original se conserva. `R=abs(entry-SL)`. | trayectoria causal 5 m, entry, SL, TP, side | Fase 2 / 2b |
| `payoff_trailing_2r` | Después de alcanzar +2R, aplicar trailing stop fijo de 2R desde el máximo favorable (LONG) o mínimo favorable (SHORT); TP original se conserva. | trayectoria causal 5 m, entry, SL, TP, side | Fase 2 / 2b |

Si una vela contiene SL, TP y una regla de payoff, el orden es el ya auditado:
SL, TP y luego la regla de payoff. No se cambia por candidato.

### SALIDA — recuperación tras avance favorable o señal técnica opuesta

| ID | Regla exacta | Insumos | Origen auditado |
| --- | --- | --- | --- |
| `exit_giveback_10` | Cerrar cuando el retroceso desde MFE sea 10 % del MFE positivo alcanzado. | trayectoria causal 5 m | Fase 2 |
| `exit_giveback_25` | Cerrar cuando el retroceso desde MFE sea 25 % del MFE positivo alcanzado. | trayectoria causal 5 m | Fase 2 |
| `exit_giveback_50` | Cerrar cuando el retroceso desde MFE sea 50 % del MFE positivo alcanzado. | trayectoria causal 5 m | Fase 2 |
| `exit_opposite_ma_profile` | Cerrar al cierre de la siguiente vela 1 h con la señal opuesta ya auditada. Para LONG: `ma7 < ma25`, `ma7 < ma50`, `ma7 < ma99`, pendiente actual MA7 ≥ +0.2°, pendiente previa ≤ -0.2° y proximidad a mínimo de 10 velas dentro de 1 %. Para SHORT, imagen especular. SL/TP 5 m se evalúan antes. | MA 1 h cerradas, trayectoria 5 m | Fase B v2 |
| `exit_opposite_ma_or_close_below_ma7` | Para LONG, cerrar cuando ocurra primero la señal opuesta anterior o un cierre 1 h bajo MA7; para SHORT, el espejo sobre MA7. | MA 1 h cerradas, trayectoria 5 m | F4 multiseñal |
| `exit_opposite_ma_or_giveback_25` | Cerrar cuando ocurra primero la señal opuesta anterior o `exit_giveback_25`. | MA 1 h, trayectoria 5 m | F4 multiseñal |
| `exit_close_below_ma7_or_giveback_25` | Para LONG, cerrar cuando ocurra primero cierre 1 h bajo MA7 o giveback 25 %; para SHORT, el espejo. | MA 1 h, trayectoria 5 m | F4 multiseñal |
| `exit_all_three_confirmation` | Cerrar sólo cuando coincidan señal opuesta, cruce adverso MA7 y giveback 25 %; para SHORT se usa el espejo. | MA 1 h, trayectoria 5 m | F4 multiseñal |

Las cuatro últimas son las cuatro reglas multiseñal congeladas. No se permiten
combinaciones nuevas de sus componentes.

### SL — distancia de stop basada en volatilidad causal

| ID | Regla exacta | Insumos | Origen auditado |
| --- | --- | --- | --- |
| `sl_atr_1_0` | `SL_dist = min(SL_dist_original, 1.0 * ATR14_1h)`. TP no cambia. | ATR14_1h causal | Fase 2b |
| `sl_atr_1_5` | `SL_dist = min(SL_dist_original, 1.5 * ATR14_1h)`. TP no cambia. | ATR14_1h causal | Fase 2b |
| `sl_atr_2_0` | `SL_dist = min(SL_dist_original, 2.0 * ATR14_1h)`. TP no cambia. | ATR14_1h causal | Fase 2b |

`min` hace que el SL sea sólo igual o más estricto que el original. Una entrada
sin 15 velas 1 h anteriores conserva su SL y queda marcada en la evidencia;
no recibe ATR fabricado.

### TIMEOUT — duración máxima fija

| ID | Regla exacta | Insumos | Origen auditado |
| --- | --- | --- | --- |
| `timeout_12h` | Cerrar a las 12 h al cierre de la vela aplicable si no ocurrió antes SL/TP. | trayectoria causal | Fase 2b |
| `timeout_24h` | Cerrar a las 24 h al cierre de la vela aplicable si no ocurrió antes SL/TP. | trayectoria causal | Fase 2b |
| `timeout_36h` | Cerrar a las 36 h al cierre de la vela aplicable si no ocurrió antes SL/TP. | trayectoria causal | Fase 2b |
| `timeout_24h_if_losing` | A las 24 h cerrar sólo si el retorno a ese cierre es negativo; de otro modo conservar la salida original. | trayectoria causal | Fase 2b |

El orden intravela siempre es SL, TP y luego timeout.

## Orden fijo dentro de cada familia

El motor futuro recorre los IDs de la tabla en el orden publicado. No elige por
resultado, nombre, símbolo ni datos de OOS. Una variante ya aplicada a la rama
actual no puede repetirse. El límite de intentos, la comparación TRAIN/
VALIDATION y cualquier lectura de OOS pertenecen a Fase C y no están definidos
ni autorizados por este documento.

## Límite del contrato actual y próximo paso técnico

`LOOP_PROTOCOL.md` v1 normaliza entradas, no especificaciones de ejecución de
salida ni tamaño. Por ello, antes de implementar el motor habrá que proponer
un anexo declarativo y versionado para `execution_recipe` que represente las
familias PAYOFF, SALIDA, SL y TIMEOUT sin código arbitrario. Esta observación
no autoriza a modificar el protocolo ni el motor ahora: es el punto concreto a
revisar antes de escribir código de Fase B.

Los filtros de ENTRADA/COSTOS pueden materializarse como una población nueva.
Las familias que cambian ejecución deberán conservar la misma población de
entradas y declarar su receta en ese anexo. En todos los casos, la nueva
revisión vuelve a la Máquina para un diagnóstico completo y nunca a producción.
