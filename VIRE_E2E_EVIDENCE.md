# VIRE — Evidencia E2E

Fecha de verificación: 2026-09-19.

## Garantías verificadas

- VIRE corre en `verge-backtest` y no tiene rutas de ejecución de órdenes ni
  dependencia de `StrategyProfiles`.
- El hedge ratio se ajusta únicamente en TRAIN; VAL y OOS usan ese fit fijo.
- Cada retorno incluye fee + slippage y el stress agrega una perturbación
  adversa adicional.
- La selección de relaciones cubre el universo antes de repetir símbolos y su
  ranking de descubrimiento usa retornos del segmento TRAIN solamente.
- Funding/OI se leen una vez por corrida para auditoría; liquidaciones se
  montan read-only desde la DB del colector. Ninguno de esos módulos puede
  promocionar un candidato hasta que tenga validación histórica independiente.

## Corridas reales

| Run ID | Universo | Relaciones | Estructurales | Paper-ready | Resultado |
|---|---:|---:|---:|---:|---|
| `dac4ebb4-407d-47b3-8be2-d920723696e3` | 400 | 400 | 0 | 0 | Selección coverage-first inicial; sin falsos positivos. |
| `bea4416a-0c8f-4716-a52d-fc39fd418cbf` | 400 | 400 | 3 | 0 | Pre-screen causal TRAIN; las tres fallaron VAL/OOS/stress. |
| `a593f559-2d26-4ce8-b21a-569600bf3283` | 400 | 400 | 3 | 0 | Repetición E2E tras incorporar fee + slippage. |
| `c21d0c2f-a08d-4a3b-b61d-7324d60f3423` | 62 | 2.027 eventos | — | 0 | Forced-flow proxy: TRAIN +$91,36; VAL +$4,54; OOS −$30,00; estrés −$75,63. Rechazado. |
| `2bd5b3df-c4c6-4c0a-a6e9-e49b477bd35c` | 10 | 6.645 eventos | — | 0 | Dislocación Bybit↔Bitget: TRAIN −$1.171,75; VAL −$587,68; OOS −$507,36; estrés −$794,64. Rechazado. |

La última corrida cubrió 79.800 combinaciones elegibles y representó los 400
símbolos. El detalle completo permanece inmutable en
`invariant_research_runs` y `invariant_research_candidates`.

## Límites de datos actuales

- OHLCV histórico: 450 símbolos disponibles; la corrida registra rango real.
- Funding y Open Interest: 63 símbolos con historial.
- Liquidaciones: 56.643 eventos / 50 símbolos. El backfill gratuito de precio
  Bybit cubre los 50 símbolos, pero hay 10,08 días de solapamiento real;
  el gate exige 30 días antes de permitir una hipótesis de eventos.
- Forced-flow proxy: usa meses de OI + taker flow + precio y está etiquetado
  explícitamente como proxy, no como liquidaciones. Su primera corrida E2E
  fue rechazada por OOS y estrés; no produjo candidato paper-ready.
- Cross-venue: se añadió un universo común gratuito de 10 contratos líquidos
  entre Bybit y Bitget. La simulación carga cuatro piernas de fee/slippage y
  rechazó la convergencia de spread; esa divergencia no cubre fricción real.

No existe evidencia para prometer un retorno mensual, ni se generó o promovió
ninguna estrategia live. Cualquier candidato futuro requiere validación de los
módulos de funding, OI y liquidaciones, además de paper trading.
