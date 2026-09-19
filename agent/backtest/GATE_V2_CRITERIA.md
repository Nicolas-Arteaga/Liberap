# GATE V2 — criterios PRE-REGISTRADOS (antes de mirar el resultado)

Fecha de pre-registro: 2026-09-05, ANTES de correr `gate_v2.py`.
Repair del gate de confiabilidad — PHASE 1. Mismo universo congelado que el gate v1
(MA Slope Caso 2, 113 trades reales, 2026-07-11 → 08-09), misma config leída de
`verge-db`, mismo dataset histórico. Ningún parámetro se toca para hacer coincidir.

## Filosofía (fijada por el usuario)

La validación correcta es **¿el replay reproduce las DECISIONES de producción?**,
no **¿produce el mismo PnL?**. Si las decisiones coinciden pero quedan diferencias
inevitables por datos/fills, se cuantifican. Si las decisiones NO coinciden, hay
que encontrar la causa raíz.

## Métricas y bandas

### Primarias — concordancia de decisiones

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| P1 | REAL→REPLAY match rate (solo símbolos REPLAYABLE): trade real con contraparte replay mismo símbolo, señal ±3 h, misma dirección | ≥ 70 % | 45–70 % | < 45 % |
| P2 | REPLAY→REAL false-positive rate: trades aceptados por el replay que no matchean ningún trade real | ≤ 35 % | 35–60 % | > 60 % |
| P3 | Inflación de señal: señales crudas del replay ÷ trades reales (universo replayable) | ≤ 2.0× | 2.0–4.0× | > 4.0× |
| P4 | Acuerdo de signo del PnL neto (replay universo completo vs real) | mismo signo y \|Δ\| ≤ 40 % de \|real\| | mismo signo, \|Δ\| ≤ 100 % | signo opuesto |
| P5 | Profit factor agregado: replay dentro de … del real | ±0.15 | ±0.40 | peor |

### Secundarias — concordancia económica en los pares matcheados

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| S1 | Exit reason agreement (pares matcheados) | ≥ 75 % | 55–75 % | < 55 % |
| S2 | Correlación de PnL (Pearson r, pares matcheados) | ≥ 0.80 | 0.55–0.80 | < 0.55 |
| S3 | Δ precio de entrada (mediana \|Δ%\|) | ≤ 0.30 % | 0.30–0.80 % | > 0.80 % |
| S4 | Δ timing de entrada (mediana \|Δ\|) | ≤ 45 min | 45–180 min | > 180 min |
| S5 | Δ timing de salida (mediana \|Δ\|, pares con mismo motivo) | ≤ 2 h | 2–12 h | > 12 h |
| S6 | Acuerdo de dirección (long/short) | = 100 % | ≥ 98 % | < 98 % |

### De infraestructura

| # | Métrica | PASS | PARTIAL | FAILED |
|---|---|---|---|---|
| I1 | Bugs conocidos abiertos (timeout / btc-filter off / daily-change API en vivo / funding silencioso) | 0 | ≤ 1, documentado y acotado | ≥ 2 |
| I2 | Cobertura: % de trades reales sobre símbolos UNREPLAYABLE | ≤ 10 % | 10–30 % | > 30 % |
| I3 | Reproducibilidad del filtro BTC vs `btc_context.regime` real (113 trades) | ≥ 90 % acuerdo y 0 errores peligrosos | ≥ 80 % y 0 peligrosos | cualquier error peligroso |

## Regla de veredicto global (pre-registrada)

- **PASS**: TODA métrica en banda PASS **y** toda divergencia restante con causa raíz
  escrita **y** 0 bugs conocidos abiertos.
- **FAILED**: cualquier métrica en banda FAILED, **o** sign flip del PnL neto,
  **o** ≥ 2 bugs conocidos abiertos.
- **PARTIAL**: cualquier otro caso.

Si el resultado es **PARTIAL**, el reporte debe indicar explícitamente qué tipos de
investigación soporta el replay reparado y cuáles NO — no alcanza con "casi".

## Qué NO cuenta como PASS

- Que el código compile / los tests unitarios pasen. Eso es condición necesaria, no suficiente.
- Que el PnL del replay se parezca al real si las DECISIONES no coinciden (P1/P2/P3).
- Ajustar cualquier parámetro después de ver el número.
