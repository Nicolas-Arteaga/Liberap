# INTEGRITY TEST RESULTS

Generado: 2026-09-08T01:46:42.149959+00:00
DB temporal: `C:\Users\Nicolas\AppData\Local\Temp\verge_itest_g6_l4t9r\klines.db` (descartable)

**15/15 PASS**

| test | resultado | detalle |
|---|---|---|
| OI upsert idempotente (1 fila) | PASS | n=1 |
| OI upsert actualiza valor | PASS | oi=111.0 |
| OI out-of-order queda ordenado al leer | PASS | ts=[1788826001998, 1788829001998] |
| OI gap detectable (missing>0) | PASS | gaps={'rows': 3, 'expected': 18, 'missing': 15, 'coverage_pct': 16.67, 'first': 1788826001998, 'last': 1788831101998} |
| OI sin duplicados tras re-insert x3 | PASS | dup_groups=0 |
| OI sobrevive reopen (restart) | PASS | 3 -> 3 |
| LIQ research insert nuevo devuelve True | PASS |  |
| LIQ research duplicado devuelve False | PASS |  |
| LIQ research dedup (1 fila) | PASS | n=1 |
| LIQ research: eventos distintos se guardan | PASS | n=3 |
| LIQ research out-of-order ordenado al leer | PASS | ts=[1788820001998, 1788830501998, 1788830501998, 1788830501998] |
| PRUNE borra del live cache la fila vieja | PASS | live 2 -> 1 |
| PRUNE NO toca liquidations_research | PASS | research 4 -> 4 |
| PRUNE keep_hours=0 vacia live pero research intacto | PASS | research=4 |
| LIQ research sobrevive reopen (restart) | PASS | 4 -> 4 |
