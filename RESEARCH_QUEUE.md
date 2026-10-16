# Cola persistente Research→Máquina (F2)

`agent/backtest/research_queue.py` es una cola SQLite local para candidatos
formalmente materializados. No genera hipótesis, no inicia `evolutionary_lab`,
no escribe `StrategyProfiles`, no interactúa con el agente ni el ledger.

## Admisión

Sólo admite `<root>/<candidate_id>/1` que pase `verify_revision`: requiere el
contrato Fase A (`candidate.json`, `entries.jsonl` y hashes válidos). La clave
primaria `candidate_id` hace el enqueue idempotente; no hay duplicados.

```powershell
python agent/backtest/research_queue.py --enqueue CANDIDATE_ID --root agent/backtest/research_loop --catalog IMPROVEMENT_FAMILIES.md --funding-db agent/data/funding_history.db
```

## Consumo

El consumidor hace claim atómico en SQLite/WAL y ejecuta `run_autonomous`.
Guarda `IMPROVED`, `DISCARDED`, `INVALID` o `FAILED` con el `history.json`
como resultado. Un candidato `RUNNING` no puede ser reclamado por otro worker.

```powershell
python agent/backtest/research_queue.py --workers 3
```

`--workers` es un máximo solicitado, no una promesa. El plan reserva 6 GiB
para Windows/agente y presupone 7 GiB por worker según el benchmark MA3. Al
momento de construir F2 había ~8,82 GiB disponibles, por lo que el límite
seguro calculado es **1 worker**. Dos o tres workers sólo se habilitan cuando
la memoria disponible real permite mantener esa reserva.

Consultar sin ejecutar:

```powershell
python agent/backtest/research_queue.py --status --workers 3
```

La cola está lista, pero el generador cuántico continúa explícitamente apagado.
