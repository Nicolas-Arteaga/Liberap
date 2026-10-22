# ROADMAP Alpha Microestructura — cierre de segunda pasada

Fecha: 2026-10-17.  Fuente de protocolo: `PHASE2_EVENT_STUDIES_V2.md`, SHA256
`B7351DD1D12EDDC1BDA973172F158CE785E258096C35BB0C770B259B7DAD392E`.

## Estado de infraestructura

| tarea | evidencia | estado |
|---|---|---|
| T1.2 OI histórico | 17.439.004 filas, 200 símbolos, QA sin duplicados/off-grid | HECHO |
| T1.4 funding | 313.354 settlements, 200 símbolos; signo validado contra ejemplo oficial, no Income History | HECHO, validación no empírica |
| T1.5 panel causal | OI/taker con un bucket 5m de lag y funding sólo post-settlement; 3 tests anti-lookahead | HECHO |
| T1.3 cost_v2 | colector de spread cada 5m activo pero sin 15 días de madurez | PENDIENTE |
| Vision | `metrics`, `aggTrades`, `bookDepth` se escanean; `bookTicker` no cubre 2025–26 | no usar bookTicker |
| liquidaciones / H14 | último evento a 2026-10-17: ~59,98h de antigüedad; 50 símbolos | CAPTURA INTERRUMPIDA |

El colector de spread es `VergeResearchQuoteSpreadsV1`; no fue desactivado.

## Fase 2 — resultados de la réplica OI

Artefacto no versionado: `research/reports/phase2_oi_event_study_v2.json`.
Panel: 163 símbolos, 2025-06-01 a 2026-08-17. Los retornos son bp crudos;
las bandas económicas son 10/26/36 bp RT y **no** son `cost_v2`.

| hipótesis | número principal | mecanismo | económico |
|---|---:|---|---|
| H13 A p↓/OI↑, 4h | -7,81 bp raw | PARK: placebo y control no sostienen una conclusión incremental | negativo como long en las 3 bandas |
| H13 B p↓/OI↓, 4h | -4,60 bp raw | PARK | no hay edge suficiente |
| H13 C p↑/OI↑, 4h | -6,18 bp raw | PARK | no hay edge suficiente |
| H13 D p↑/OI↓, 4h | -31,57 bp raw (= +31,57 bp short) | PARK, no PASS: la réplica muestra efecto pero aún falta control matcheado por split y BH final | +21,57 / +5,57 / -4,43 bp; `PENDING_COST_V2` (cambia de signo) |
| H15 | coeficiente taker `t=-1,08/-0,29/-1,21` a 4/8/12h | no evidencia incremental de taker; aún no se etiqueta FAILED formal sin la tabla completa de controles/BH | PENDIENTE cost_v2 |
| H16 | coeficiente funding `t=+0,15/-0,18/+0,17` a 8/16/24h | no evidencia incremental de funding; aún no se etiqueta FAILED formal sin controles/BH | PENDIENTE cost_v2 |
| H17 | 0 eventos con el cruce literal p20→p60 entre barras consecutivas | `INSUFFICIENT_SAMPLE`, no FAILED | no aplicable |

La corrida heredada produjo placebo, control OI-plano y residual BTC completos
para H13, pero no el control matcheado por split y la corrección BH requerida
para dar un PASS/FAILED formal a toda la familia. H15/H16 tampoco materializan
todavía todos los controles preregistrados. Por rigor, estos son resultados
numéricos reproducibles pero **no un cierre económico definitivo**.

## Fase 3a y Fase 4

- `research_loop.py` ahora persiste `catalog_completeness` (`COMPLETE` o
  `PARTIAL`), `missing_executors` y las familias ejecutables que no se
  alcanzaron antes del tope. Test: `test_research_loop_catalog.py`.
- Siguen faltando ejecutores documentados; ningún descarte puede presentarse
  como catálogo exhaustivo mientras existan.
- `h14_forward_harness.py` deja el gate/calendario listo y se rehúsa a correr
  H14 sin prueba independiente de >=90% uptime. No se ejecutó H14.

## Qué necesita Nico

1. Restaurar manualmente el launcher habitual de `verge_agent.py` y confirmar
   un heartbeat/evento nuevo de liquidaciones. No se reinició desde research.
2. Mantener `VergeResearchQuoteSpreadsV1` hasta >=15 días de cobertura.
3. Antes de decidir economía real, completar controles/BH de Fase 2 y madurar
   `cost_v2`. El resultado H13-D no autoriza operar: su signo neto cambia con
   las bandas de costo.

## Familia de ratios long/short (LS_RATIO_EVENT_FAMILY_V1) — 2026-10-21

Corrida única con `agent/backtest/ls_ratio_event_study.py` (commit 11c7548,
congelado antes de ejecutar). Reporte: `research/reports/ls_ratio_event_study_v1.json`.
163 símbolos, 2025-12 → 2026-08-17. Decisiones de implementación no cubiertas
por el prerregistro están en `implementation_notes` del reporte.

**Veredicto de mecanismo: 0/18 celdas PASS.** Solo una celda pasa BH
(`global_ls_acct` cola alta 1h: efecto incremental -4,5 bp, con placebo de
-2,3 bp en +48h, es decir mayormente drift). Las celdas con CI95 que excluye 0
sin BH (`global_ls_acct` lo 8h, `toptrader_ls_pos` lo 4h) tienen mitades de
distinto tamaño y no sobreviven a la corrección de 18 tests. 3 celdas
`taker_ls_vol` cola baja: ~420 eventos, 39 símbolos, top-5 = 52,7 % (viola el
límite 50 %), CI de ±100 bp.

**Veredicto económico:** bruto en la dirección implícita ≤ ~12 bp en las celdas
con muestra sólida; neto negativo en las tres bandas (10/26/36 bp) salvo
`PENDIENTE_cost_v2` en 2 celdas (neto >0 solo con 10 bp, mecanismo FAILED). La
única celda con neto positivo en todas las bandas (`taker_ls_vol|lo|8h`, +27 a
+53 bp) es ruido: n=421, CI incremental [-167,+55], mitades de signo opuesto.
No autoriza nada.

**Cierre parcial:** búsqueda direccional en este universo detenida para los
ratios long/short; pendiente solo H14 (liquidaciones) por calendario. Con el
agente apagado desde 2026-10-15, el test formal (≥60 días continuos) no puede
ser antes de ~60 días después de que se reinicie la captura.
