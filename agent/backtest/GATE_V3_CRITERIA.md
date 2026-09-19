# GATE V3 — criterios PRE-REGISTRADOS (Phase 2)

Pre-registro: 2026-09-05, ANTES de correr `gate_v3.py`. Mismo universo congelado
(MA Slope Caso 2, 113 trades reales, 2026-07-11 → 08-09), misma config de
`verge-db`. Ningún parámetro se toca para hacer coincidir.

## Qué demostró Phase 2 §A/B (`phase2_timeline.py`) — contexto de estos criterios

- Latencia decisión→entrada real: **mediana 1.1 s** (no minutos). El desfasaje
  **no** es latencia de ejecución.
- Producción estuvo **saturada de cupos**: en **97/113** entradas ya tenía 2 de 3
  cupos ocupados. Entra **cuando se libera un cupo**, no cuando aparece el patrón.
- El patrón MA-geometry, una vez verdadero, **persiste horas** (mediana 26 velas de
  5 m ≈ 2.2 h; p75 ≈ 4.3 h; máx 12.8 h).
- El replay v2 (`_run_generic`) abre en la **primera** vela del patrón; **55/87**
  trades reales tienen su señal ≥ 30 min DESPUÉS del primer disparo del replay.
- Ocupación cruzada (otra estrategia con posición en el símbolo) en la señal real:
  **0/113** → no es el mecanismo.

Conclusión: el mecanismo de divergencia es **el momento de admisión por cupo**
dentro de una ventana de elegibilidad larga. `run_ma_geometry_global` (nuevo,
opt-in) modela eso: el candidato queda elegible mientras el patrón viva y se abre
solo al liberarse un cupo, en el orden de prioridad de producción.

## Métricas y bandas (V3)

El objetivo NO es un PF parecido. Es: reproducir decisiones + timeline +
competencia por cupos + explicar divergencias + 0 bugs estructurales.

### Primarias

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| P1 | Solape de conjunto de símbolos (Jaccard, universo REPLAYABLE): \|R∩B\| / \|R∪B\| | ≥ 0.55 | 0.30–0.55 | < 0.30 |
| P2 | REAL→REPLAY match rate: trade real con contraparte mismo símbolo y **entrada dentro de la ventana de elegibilidad real del patrón ± 2 h** | ≥ 55 % | 35–55 % | < 35 % |
| P3 | Correlación del timeline de ocupación de cupos (nº de posiciones abiertas por hora, replay vs real; Pearson r) | ≥ 0.70 | 0.45–0.70 | < 0.45 |
| P4 | Ratio de nº de trades replay/real (universo REPLAYABLE) | 0.80–1.25 | 0.6–1.6 | fuera |
| P5 | PnL neto: signo + magnitud (replay vs real) | mismo signo y \|Δrel\| ≤ 60 % | mismo signo, ≤ 130 % | signo opuesto |
| P6 | Inflación de señal (trades **admitidos**, ya gateados por cupo) | ≤ 1.5× | 1.5–2.5× | > 2.5× |

### Secundarias

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| S1 | Exit reason agreement (pares matcheados) | ≥ 70 % | 50–70 % | < 50 % |
| S2 | Entrada del replay DENTRO de la ventana de elegibilidad real (pares matcheados) | ≥ 80 % | 60–80 % | < 60 % |
| S3 | Δ profit factor (replay vs real) | ≤ 0.20 | ≤ 0.45 | > 0.45 |
| S4 | Correlación de PnL por-trade (pares, Pearson r) | ≥ 0.70 | 0.45–0.70 | < 0.45 |

### Infraestructura

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| I1 | Bugs estructurales conocidos abiertos | 0 | ≤ 1, documentado y acotado | ≥ 2 |
| I2 | % de trades reales sobre símbolos UNREPLAYABLE **tras intentar el backfill** | ≤ 10 % | 10–25 % | > 25 % |
| I3 | Sesgo intrabar TP/SL clasificado para FVG + OrderBlock | NEGLIGIBLE, o MATERIAL con impacto cuantificado | UNKNOWN en ≤ 1 familia | UNKNOWN en ≥ 2 |

## Regla de veredicto global (pre-registrada)

- **PASS**: toda métrica en banda PASS **y** toda divergencia restante con causa
  raíz escrita **y** 0 bugs estructurales abiertos.
- **FAILED**: cualquier métrica en banda FAILED, **o** sign flip del PnL neto,
  **o** ≥ 2 bugs estructurales abiertos.
- **PARTIAL**: cualquier otro caso.

## Mapeo a la pregunta final

**¿Puede Verge usar el motor histórico para evaluar el PnL de una estrategia nueva?**

- **PASS → YES.**
- **PARTIAL → LIMITED** — el reporte debe listar exactamente para qué SÍ y para qué NO.
- **FAILED → NO.**

## Prohibido (fijado por el usuario)

parameter fitting · optimización · alterar producción · elegir otro período o
estrategia · ajustar SL/TP · modificar filtros/slots · eliminar estrategias
competidoras. Producción = ground truth; el replay se adapta a producción.
