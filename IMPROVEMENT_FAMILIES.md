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

## Anexo B1 — `execution_recipe` declarativo

Este anexo habilita la representación de las familias PAYOFF, SALIDA, SL y
TIMEOUT sin convertir el manifiesto de Research en código ejecutable. Es parte
del contrato de Fase B y no es una autorización para implementar el motor aún.

### Forma exacta en la revisión hija

Una revisión que modifica la ejecución agrega una única clave
`execution_recipe` al nivel superior de su `candidate.json`:

```json
{
  "execution_recipe": {
    "recipe_version": "1.0",
    "area": "SL",
    "variant_id": "sl_atr_1_5",
    "parent_revision": 4,
    "catalog_sha256": "sha256-canonico-del-catalogo-aprobado"
  }
}
```

Los cinco campos son obligatorios y no admite campos adicionales:

| Campo | Tipo | Regla |
| --- | --- | --- |
| `recipe_version` | texto | Debe ser exactamente `1.0`. |
| `area` | texto | Uno de `PAYOFF`, `SALIDA`, `SL`, `TIMEOUT`. Debe coincidir con la categoría de la variante. |
| `variant_id` | texto | Un ID de las tablas de estas cuatro categorías y de ninguna otra. |
| `parent_revision` | entero positivo | Debe señalar la revisión inmutable de la cual deriva ésta. |
| `catalog_sha256` | texto hex SHA-256 | Huella del catálogo canónico con el que se seleccionó el ID. Impide redefinir silenciosamente una receta. |

El hash del catálogo se calcula como el SHA-256 de la sección de tabla que
contiene el `variant_id`, codificada UTF-8 y normalizada con LF, sin espacios
terminales. La implementación futura guardará además esa sección exacta en el
artefacto de la revisión. Si el hash no coincide, la Máquina responde
`INVALID` y no simula nada.

### Lista permitida y resolución cerrada

La Máquina resuelve el par `area` + `variant_id` exclusivamente contra estas
listas cerradas:

```text
PAYOFF:  payoff_tp_short_50, payoff_break_even_1r, payoff_trailing_2r
SALIDA:  exit_giveback_10, exit_giveback_25, exit_giveback_50,
          exit_opposite_ma_profile, exit_opposite_ma_or_close_below_ma7,
          exit_opposite_ma_or_giveback_25,
          exit_close_below_ma7_or_giveback_25, exit_all_three_confirmation,
          exit_atr_trail_0_5_after_1r, exit_ema50_close_trail
SL:      sl_atr_1_0, sl_atr_1_5, sl_atr_2_0
TIMEOUT: timeout_12h, timeout_24h, timeout_36h, timeout_24h_if_losing
```

Cada ID toma sus números, velas, condiciones y orden intravela de la tabla de
este documento. El JSON no puede aportar multiplicadores, períodos, umbrales,
operadores, nombres de indicadores, rutas, SQL, Python, URLs, expresiones o
plantillas. No existe una forma `custom`, `params`, `script` ni `code`.

### Semántica de una revisión con receta

1. `entries.jsonl` conserva exactamente las entradas de la revisión padre: el
   hash, conteo, `open_ms`, símbolo, lado, `entry`, SL y TP originales no se
   mutan. El cambio de ejecución se aplica sólo durante la simulación.
2. La receta se evalúa después de la entrada y sólo con velas causalmente
   disponibles. SL y TP base conservan prioridad; después se evalúa la receta,
   salvo las reglas PAYOFF cuyo orden específico ya está fijado en su tabla.
3. El resultado de cada trade debe incluir `exit_reason` con el ID de la
   receta cuando ésta cierre/modifique el trade. Si la receta no actúa, se
   mantiene el motivo base. Así `diagnosis.json.audit_result` puede evidenciar
   cuántas veces tuvo efecto.
4. La respuesta de la Máquina replica `execution_recipe` y agrega
   `execution_recipe_effect: {"eligible_n": N, "triggered_n": N,
   "missing_input_n": N}`. Son conteos de evidencia, no un criterio de éxito.
5. Una receta ausente significa ejecución base. Una receta presente no se
   combina con otra, incluso si su área vuelve a ser `main_area` en el nuevo
   diagnóstico.

### Relación con ENTRADA y COSTOS

`entry_*` y `cost_*` no usan `execution_recipe`: generan una nueva
`entries.jsonl` filtrada o reflejada, con nuevo hash. Deben dejar
`execution_recipe` ausente. La Máquina rechaza como `INVALID` una revisión que
mezcle población transformada y receta de ejecución en el mismo salto desde la
revisión padre; eso preserva atribución causal de una variante por vuelta.

### Rechazos obligatorios

La Máquina debe responder `INVALID`, sin severidad interpretable, si ocurre
cualquiera de estos casos:

- clave extra o faltante en `execution_recipe`;
- `area` no coincide con el ID o con la categoría atacada declarada;
- ID no listado, hash de catálogo distinto o versión diferente de `1.0`;
- hash/entradas diferentes a la revisión padre para una receta de ejecución;
- receta aplicada a una entrada sin los insumos causales requeridos sin que el
  resultado reporte el faltante;
- más de una receta, más de una transformación o un intento de adjuntar
  parámetros libres a la misma revisión.

Este anexo sigue sujeto a las seis integridades M1b y a las invariantes de
`LOOP_PROTOCOL.md`. No incorpora criterio de mejora, límite de intentos, OOS,
promoción, UI ni ninguna capacidad de despliegue.

## Anexo C — extensiones investigadas (2026-10-04, catálogo cerrado v1.1)

Esta ampliación no cambia los resultados anteriores ni autoriza ejecución. Cada
regla fue añadida antes de observar resultados de una estrategia concreta. Las
fuentes, calidad de evidencia y límites de datos están en
`RESEARCH_IMPROVEMENT_SOURCES.md`.

### ENTRADA — régimen y confluencia causal

| ID | Regla exacta | Insumos causales | Fuente/evidencia |
| --- | --- | --- | --- |
| `entry_adx14_ge_25` | Conservar sólo si ADX(14) de la última vela 1 h cerrada es >= 25; ADX usa Wilder sobre 14 velas cerradas. | OHLCV 1 h, 28 velas previas | Arda (SSRN 2025): las estrategias de bandas dependen de régimen/direccionalidad; no prueba este corte concreto. |
| `entry_realized_vol_20_mid` | Conservar sólo si la desviación estándar muestral de 20 retornos log 1 h previos está entre percentiles causales 33 y 67 de la historia del símbolo. | cierres 1 h, >=20 observaciones | Prakash et al. (arXiv:2004.09963) valida evitación de riesgo dinámica por regímenes; tercil medio es preregistro discreto local. |
| `entry_rsi14_oversold_ma50_long` | LONG: RSI(14) 1 h <=30 y cierre 1 h > MA50; SHORT: RSI(14)>=70 y cierre<MA50. RSI Wilder, sólo velas cerradas. | cierres 1 h, >=50 velas, side | Paramashiva (SSRN 2026) backtestea RSI 14/30/70 y MA con costes/walk-forward; no demuestra la confluencia. |

Son filtros: no alteran side, SL, TP, tamaño ni salida. Sin historia causal,
la entrada se excluye y se reporta `missing_history_n`; no hay imputación.

### SALIDA — trailing por volatilidad y estructura

| ID | Regla exacta | Insumos causales | Fuente/evidencia |
| --- | --- | --- | --- |
| `exit_atr_trail_0_5_after_1r` | Tras alcanzar +1R, LONG cierra en la primera vela 5m cerrada con cierre <= máximo favorable cerrado menos 0.5*ATR14_1h; SHORT espejo. SL/TP tienen prioridad. | trayectoria 5m, ATR14_1h | Viaggi (SSRN 2026) estudia trailing ATR con entradas aleatorizadas y estima piso de ruido 0.38 ATR; 0.5 es la variante discreta más próxima por encima. |
| `exit_ema50_close_trail` | Tras +1R, LONG cierra en el primer cierre 1h <= EMA50; SHORT en el primer cierre >= EMA50. SL/TP 5m tienen prioridad. | cierres 1h, trayectoria 5m | Bhatti (SSRN 2026) usa EMA50 a cierre como trailing en backtest intradía; evidencia XAU/USD, no cripto. |

No se agrega `partial_exit`: el contrato registra un solo cierre y no modela
cantidad remanente, doble comisión ni SL residual. Tampoco hay múltiplos ATR
libres: sólo estos IDs.

### COSTOS — oportunidad intradía

| ID | Regla exacta | Insumos causales | Fuente/evidencia |
| --- | --- | --- | --- |
| `cost_hourly_range_ge_2x_roundtrip` | Conservar sólo si `(high-low)/close*100` de última vela 1h cerrada >= `2.0 * cost_pct`. | OHLCV 1h, cost_pct | Perera (SSRN 2026) evidencia que costes pueden consumir 93% de un stop pequeño en SOL/USDT; 2.0 es constante preregistrada, no optimizada. |

El rango no estima spread: es un proxy de oportunidad, no coste real ni
liquidez ejecutable.
