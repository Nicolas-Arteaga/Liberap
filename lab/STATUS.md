# Estado visible — Laboratorio de Diagnóstico

Registro append-only. Horarios: America/Argentina/Buenos_Aires.

- 2026-09-26 17:02 ART — M1 abierto: auditoría e informe MA3 con seis hallazgos. Comando activo: preparación y verificación de los datos de `v3-cli-ma3-baseline-20260926/result.json`.
- 2026-09-26 17:11 ART — M1 abierto: la primera ejecución desacoplada no dejó proceso ni `exitcode`; no se usa. Comando activo: incorporación de `progress.json`, bootstrap diario e independiente de verificación en `lab_m1_ma3_audit.py`.
- 2026-09-26 17:14 ART — M1 en curso: `docker compose exec -T backtest python /app/backtest/lab_m1_ma3_audit.py`; `progress.json` confirma 4.021/9.400 señales, 125/425 símbolos. Sin resultado todavía.
- 2026-09-26 17:20 ART — M1 cerrado: `docker compose exec -T backtest python /app/backtest/lab_m1_ma3_audit.py`; 9.400/9.400, exit code 0. Verificación independiente de win rate, equilibrio y retorno medio: tres coincidencias exactas.
- 2026-09-26 17:23 ART — M1b abierto: reproducir defecto de alineación antes de recalcular. Comando activo: inspección del stream MA3 y `engine.py:636`; no se reutilizará el informe M1 hasta que los chequeos de integridad pasen.
- 2026-09-26 17:37 ART — M1b: defecto CONFIRMADO (300/300 `b` al inicio de hora y 300/300 entradas iguales al cierre de offset 11). Comando activo: prueba de integridad con población desalineada y corrección del adaptador a `open_ms=b+1h`.
- 2026-09-26 17:44 ART — M1b: informe MA3 corregido terminó 9.400/9.400 y todos los chequeos PASS. Comando activo: recalcular baseline de cuatro escenarios con `lab_diagnose.py` para comparar v1 desalineado contra v2 alineado.
- 2026-09-26 17:51 ART — M1b en curso: selftest de 18.000 comparaciones terminó y la matriz alineada `ma3-20260926T204835Z` está activa; `lab_artifacts/m1b-ma3-aligned-20260926/progress.json` es la fuente de avance. Sin comparación v1→v2 publicada todavía.
- 2026-09-26 18:01 ART — M1b: matriz alineada cerró exit 0 (9.400/9.400). Baseline OOS v2 ya existe; comando activo: extracción reproducible de comparación v1→v2 de motivos, MFE/giveback y conclusiones antes de redactar/cerrar.
