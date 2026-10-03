# Protocolo de datos Research ↔ Máquina de Diagnóstico

**Versión:** `1.0-draft`  
**Estado:** Fase A. Contrato para revisión; no habilita ejecución, mejora, despliegue ni escritura en producción.

## Propósito y límite de seguridad

Research entrega una hipótesis ya materializada en señales reproducibles. La
Máquina la adapta al contrato genérico del Laboratorio y devuelve un diagnóstico
auditable. El protocolo no tiene ningún campo, endpoint ni efecto que cree o
active `StrategyProfiles`, modifique el agente o envíe órdenes.

Cada intercambio usa un directorio inmutable por revisión:

```text
research_loop/<candidate_id>/<revision>/
  candidate.json       # manifiesto declarativo
  entries.jsonl        # población congelada de entradas normalizadas
  diagnosis.json       # respuesta de la Máquina (sólo después de auditar)
  informe.md           # informe humano correspondiente
```

`candidate_id` es un UUID o slug estable en minúsculas; `revision` es un entero
positivo. Una revisión nunca se sobrescribe: una variante recibe la revisión
siguiente y conserva el manifiesto, hash y diagnóstico anteriores.

### Huellas inmutables

La huella de `candidate.json` usa su forma canónica: el mismo objeto JSON
reserializado en UTF-8, con claves ordenadas recursivamente,
`ensure_ascii=false`, separadores `,` y `:`, sin espacio ni salto de línea
final. La de `entries.jsonl` se calcula sobre los bytes exactos del archivo.
Ambas son SHA-256 hexadecimal en minúsculas. De este modo,
`input_fingerprint.candidate_sha256` de la respuesta detecta cualquier cambio
entre la entrega de Research y el diagnóstico de la Máquina.

## 1. Entrega de Research: `candidate.json`

Research no entrega código Python arbitrario. Entrega este manifiesto JSON y
una población congelada en `entries.jsonl`. La futura capa de integración sólo
podrá usar `candle_source.key` y `split_policy.kind` que estén registrados por
la Máquina; una ruta local libre o una instrucción ejecutable es inválida.

```json
{
  "protocol_version": "1.0-draft",
  "candidate_id": "research-uuid-o-slug",
  "revision": 1,
  "display_name": "Nombre humano de la hipótesis",
  "submitted_at_utc": "2026-10-03T00:00:00Z",
  "research_run": {
    "run_id": "identificador-inmutable-de-Research",
    "family": "familia_preregistrada",
    "hypothesis": "texto breve y falsable",
    "source_commit": "sha-del-codigo-que-materializo-la-senal"
  },
  "adapter_definition": {
    "name": "research_slug",
    "display_name": "Nombre humano de la hipótesis",
    "aliases": ["research_slug"],
    "population": "raw",
    "bar_ms": 900000,
    "cost_pct": 0.08,
    "require_coverage": false
  },
  "entry_definition": {
    "source": "research_run:identificador-inmutable-de-Research",
    "condition": "condición humana exacta que produjo la señal",
    "execution_time": "fin de la vela 15m cuyo cierre es entry",
    "side_convention": "0=long, 1=short"
  },
  "candle_source": {
    "key": "canonical_15m",
    "interval": "15m",
    "start_ms": 0,
    "end_ms": null
  },
  "split_policy": {
    "kind": "temporal_quantile_50_25_25"
  },
  "entries_artifact": {
    "path": "entries.jsonl",
    "sha256": "hexadecimal SHA-256 de 64 caracteres",
    "count": 0
  }
}
```

### Reglas de cada campo

- `adapter_definition` equivale uno a uno a `AdapterDefinition` del
  Laboratorio. `population` sólo puede ser `raw` o `real`; `bar_ms` y
  `cost_pct` son positivos; `name` es único y estable.
- `entry_definition` equivale uno a uno a `EntryDefinition`. Describe la
  señal pero no ejecuta una función. Para `raw`, `execution_time` debe decir
  que `open_ms` es el fin de la vela cuyo **cierre** coincide con `entry`; para
  `real`, debe declarar el instante real de apertura.
- `candle_source.key` es un identificador de fuente aprobada en modo sólo
  lectura. La Máquina resuelve la ruta de SQLite internamente. Research no
  aporta `db_path`, SQL ni URLs.
- `split_policy.kind` sólo admite inicialmente `fixed_time` (con
  `train_validation_ms` y `validation_oos_ms`) o
  `temporal_quantile_50_25_25`. La clasificación siempre usa `open_ms`.
- `entries_artifact.sha256` y `count` se verifican antes de diagnosticar. Un
  cambio de una señal requiere nueva revisión, nunca edición silenciosa.

## 2. Población congelada: `entries.jsonl`

Hay una línea JSON por entrada, ordenada ascendentemente por `open_ms`. El
esquema es exactamente el que exige `Adapter.entries()`:

```json
{"open_ms":1760000000000,"symbol":"BTCUSDT","entry":62500.0,"side":0,"sl":61500.0,"tp":64500.0}
```

Campos obligatorios y tipos:

| Campo | Tipo | Regla |
| --- | --- | --- |
| `open_ms` | entero UTC en milisegundos | Instante efectivo de entrada; no la detección previa. |
| `symbol` | texto | Símbolo disponible en `candle_source.key`. |
| `entry` | número positivo | Precio de entrada observable según `population`. |
| `side` | entero | `0` LONG; `1` SHORT. |
| `sl` | número positivo | Para LONG, menor que `entry`; para SHORT, mayor. |
| `tp` | número positivo | Para LONG, mayor que `entry`; para SHORT, menor. |

No se permiten campos que decidan una salida, PnL futuro, severidad ni estado
de despliegue. Campos adicionales sólo pueden ser metadatos no usados y deben
quedar dentro de `research_metadata` para no contaminar la simulación.

## 3. Adaptación obligatoria en la Máquina

La futura implementación construirá un adaptador de datos, no un adaptador por
estrategia escrito a mano. Debe implementar sin reinterpretar la hipótesis:

```text
definition        = candidate.adapter_definition
entry_definition  = candidate.entry_definition
build_entries()   = leer entries.jsonl, validar hash/esquema/orden
candles(symbol)   = resolver candle_source.key de sólo lectura
split_of(open_ms) = aplicar split_policy declarada
```

Antes de publicar un diagnóstico debe verificar:

1. versión de protocolo soportada;
2. hash, conteo, esquema y orden de `entries.jsonl`;
3. todas las reglas del contrato `Adapter`;
4. los seis chequeos de integridad M1b;
5. que el resultado identifica el commit y hash de la entrada recibida.

Si falla cualquiera, la respuesta tiene `status: "INVALID"`; no emite
severidad interpretable ni puede entrar a una fase de mejora.

## 4. Respuesta de la Máquina: `diagnosis.json`

La respuesta conserva el `result.json` auditado completo bajo `audit_result`
y agrega un resumen estable para Research. Así la UI puede usar el resumen sin
perder las métricas exactas ni la evidencia original.

```json
{
  "protocol_version": "1.0-draft",
  "candidate_id": "research-uuid-o-slug",
  "revision": 1,
  "status": "DIAGNOSED",
  "diagnosed_at_utc": "2026-10-03T00:00:00Z",
  "input_fingerprint": {
    "candidate_sha256": "sha256 de candidate.json canonico",
    "entries_sha256": "sha256 de entries.jsonl",
    "research_source_commit": "sha de Research"
  },
  "machine_fingerprint": {
    "machine_commit": "sha de la Máquina",
    "adapter_contract": "Adapter/EntryDefinition v1",
    "candle_source_key": "canonical_15m"
  },
  "integrity": {
    "valid": true,
    "checks": {
      "entry_price_observable": {"status":"PASS","pass_n":100,"n":100},
      "no_pre_entry_candle": {"status":"PASS","pass_n":100,"n":100},
      "no_exit_before_entry": {"status":"PASS","pass_n":100,"n":100},
      "split_at_entry": {"status":"PASS","pass_n":100,"n":100},
      "forward_1h_variance": {"status":"PASS","variance":0.1,"n":100},
      "sample_counts": {"status":"PASS","n":100,"n_days":20,"splits":{"TRAIN":50,"VALIDATION":25,"OOS":25}}
    }
  },
  "diagnosis": {
    "net_expectancy_pct": -0.15,
    "gross_edge_pct": -0.07,
    "main_area": "COSTOS",
    "severity": {"ENTRADA":1,"COSTOS":100,"PAYOFF":3,"SALIDA":38,"SL":21,"TIMEOUT":0},
    "evidence_by_area": {
      "ENTRADA": {"metric":"forward_return_24h_mean_pct","value":-0.07,"rule":"max(0,-media_24h*20)"},
      "COSTOS": {"metric":"gross_edge_pct","value":-0.07,"rule":"max(0,-edge_bruto*20)"},
      "PAYOFF": {"metric":"break_even_minus_win_rate_pp","value":2.7,"rule":"max(0,win_equilibrio-win_real)"},
      "SALIDA": {"metric":"reached_2pct_ended_loss_pct","value":38.3,"rule":"porcentaje que llegó +2% y terminó en pérdida"},
      "SL": {"metric":"sl_cf_reaches_tp_pct","value":21.4,"rule":"porcentaje contrafactual que habría llegado al TP"},
      "TIMEOUT": {"metric":"timeout_damage","value":0.0,"rule":"timeout_pct*max(0,-timeout_mean_return_pct)"}
    }
  },
  "artifacts": {
    "result_json": "ruta relativa a result.json",
    "report_markdown": "ruta relativa a informe.md",
    "audit_result": {}
  },
  "safety": {
    "research_status": "DIAGNOSED",
    "strategy_profile_write": false,
    "agent_execution": false
  }
}
```

`status` puede ser sólo `INVALID` o `DIAGNOSED` en Fase A. Estados de mejora
como `IN_REFINEMENT`, `DISCARDED` y `IMPROVED` pertenecen a fases posteriores;
no se crean todavía.

## 5. Interpretación para Research

- La categoría objetivo es `main_area`: máxima severidad; en empate se usa el
  orden fijo `ENTRADA`, `COSTOS`, `PAYOFF`, `SALIDA`, `SL`, `TIMEOUT`.
- `evidence_by_area` lleva siempre métrica, valor y regla de severidad. No se
  permite que Research deduzca una causa sólo desde el titular humano.
- `audit_result` conserva horizonte, bootstrap, motivos de salida, splits y
  regresión exactos. Es la evidencia primaria; el resumen es una interfaz.
- Un diagnóstico válido es evidencia descriptiva de replay. No es una orden de
  despliegue, ni una recomendación de modificar una estrategia real.

## 6. Invariantes no negociables

1. Research no puede enviar código, SQL, rutas libres ni credenciales.
2. La Máquina no puede cambiar entradas, costos, velas o splits sin crear una
   revisión nueva y un fingerprint distinto.
3. Un informe inválido bloquea la lectura de severidades y toda mejora futura.
4. OOS, promoción, intentos y UI de “Mejoradas” no están implementados ni
   autorizados por este protocolo; serán fases separadas tras aprobación.
5. Ningún artefacto del protocolo escribe `StrategyProfiles`, el ledger, el
   agente vivo o cualquier sistema de ejecución.
