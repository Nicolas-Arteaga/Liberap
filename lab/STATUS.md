# Estado visible — Laboratorio de Diagnóstico

Registro append-only. Horarios: America/Argentina/Buenos_Aires.

- 2026-09-26 17:02 ART — M1 abierto: auditoría e informe MA3 con seis hallazgos. Comando activo: preparación y verificación de los datos de `v3-cli-ma3-baseline-20260926/result.json`.
- 2026-09-26 17:11 ART — M1 abierto: la primera ejecución desacoplada no dejó proceso ni `exitcode`; no se usa. Comando activo: incorporación de `progress.json`, bootstrap diario e independiente de verificación en `lab_m1_ma3_audit.py`.
- 2026-09-26 17:14 ART — M1 en curso: `docker compose exec -T backtest python /app/backtest/lab_m1_ma3_audit.py`; `progress.json` confirma 4.021/9.400 señales, 125/425 símbolos. Sin resultado todavía.
- 2026-09-26 17:20 ART — M1 cerrado: `docker compose exec -T backtest python /app/backtest/lab_m1_ma3_audit.py`; 9.400/9.400, exit code 0. Verificación independiente de win rate, equilibrio y retorno medio: tres coincidencias exactas.
