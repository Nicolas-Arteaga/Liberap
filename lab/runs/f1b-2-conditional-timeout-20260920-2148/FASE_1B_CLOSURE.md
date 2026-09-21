# FASE 1B — FAIL

## Gate fijado antes de correr

Sobre las entradas reales con cobertura de velas: motivo de salida coincidente >=80% y al menos 80% de retornos de precio dentro de +/-0,25 puntos porcentuales. El retorno se calcula solamente desde entrada, salida y lado inferido por SL; no usa `pnl` ni `result_csv` de `scratch_caso3_gt.json`.

## Resultado

| Modelo | Motivo | Retorno dentro de +/-0,25 pp | Veredicto |
|---|---:|---:|---|
| Baseline nivel + timeout incondicional 48h | 32/38 (84,2%) | 21/38 (55,3%) | FAIL |
| Fill cierre de vela + timeout incondicional 48h | 32/38 (84,2%) | 25/38 (65,8%) | FAIL |
| Fill próxima apertura + timeout incondicional 48h | 32/38 (84,2%) | 25/38 (65,8%) | FAIL |
| Timeout condicional negativo 48h, tope 720h, fill cierre | 29/38 (76,3%) | 23/38 (60,5%) | FAIL |

El mejor fill mejora cuatro retornos, pero ninguno alcanza 31/38 (80%). El timeout causal corrige JUPUSDT: TP real/replay, +2 minutos de diferencia, retorno real +10,311 pp frente a +9,903 pp de replay. Sin embargo, convierte otros cierres históricos TIMEOUT en TP/SL o NODATA y empeora el conjunto.

## Explicación medida

El código actual del agente en `agent/verge_agent.py:6519-6558` implementa `zombie_timeout`: a las velas configuradas sólo cierra si PnL < 0; si es positivo lo deja correr, con tope duro de 720h (`agent/config.py:119`). MA3 versionado usa 192 velas de 15m (=48h) en `agent/backtest/verify_ma_slope_caso3_full_period.py:28`.

En el fixture hay 22/45 cierres después de 48h: 20 TIMEOUT y 2 TP. JUPUSDT es el ejemplo que confirma la lógica condicional (208,644h, TP, +10,311 pp). Pero sin el precio exacto de cada ciclo ni el perfil efectivo guardado por posición, no se puede determinar por qué los otros 20 timeout históricos se cerraron como timeout cuando la vela local retrospectiva puede verse positiva.

Los cinco desajustes ZAMA/EGLD/FIL/HUSDT/GOOGL tienen diferencias de precio/tiempo cercanas a tick o ciclo; se registran como candidatos de redondeo, no como causas separadas.

## Evidencia y reproducción

- `lab/runs/f1b-exit-fidelity-20260920-2123/result.json`: baseline.
- `lab/runs/f1b-1-fill-model-20260920-2145/{level,close,next_open,worst,best}.json`: matriz de fill; `progress.json` contiene ID, inicio, fin y exit code.
- `lab/runs/f1b-2-conditional-timeout-20260920-2148/result.json` y `progress.json`: timeout condicional.
- Comando de matriz: `docker compose exec -T backtest python /app/backtest/fase1b_exit_fidelity.py --scratch /app/backtest/scratch_caso3_gt.json --output /app/backtest/lab_artifacts/<id>.json --fill <modelo>`.
- Comando timeout: agregar `--fill close --conditional-timeout --hard-timeout-hours 720`.

## Qué falta para pasar

Un ledger histórico de escaneo/ciclo o logs del agente que preserven: perfil y parámetros efectivos por posición, precio observado en cada ciclo y la razón/estado de timeout. No se implementa ese ledger en este cierre; quedó explícitamente diferido y requiere una rama separada/aprobación para paper.
