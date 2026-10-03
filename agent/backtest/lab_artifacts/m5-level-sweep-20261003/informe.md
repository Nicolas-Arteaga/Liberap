# Auditoría Level Sweep 15m SL3/RR3 — 12533 trades
## Chequeos de integridad
- entry_price_observable: PASS.
- no_pre_entry_candle: PASS.
- no_exit_before_entry: PASS.
- split_at_entry: PASS.
- forward_1h_variance: PASS.
- sample_counts: PASS.
## TITULAR
La estrategia PIERDE -0.15 % neto por trade. La causa de mayor severidad medida es COSTOS (100/100).
## Resultado simple
- Win rate 26.65 %; equilibrio 29.36 %; ganancia media 3.97 % y pérdida media 1.65 %.
## Hallazgos
### [ENTRADA] — severidad 1/100
QUÉ PASA: Retorno medio 1/4/12/24/48h con IC bootstrap por día: 1h=-0.01% [-0.05, 0.03], n=12533, días=413, 4h=-0.02% [-0.09, 0.05], n=12533, días=413, 12h=-0.10% [-0.25, 0.04], n=12533, días=413, 24h=-0.07% [-0.28, 0.13], n=12533, días=413, 48h=-0.18% [-0.44, 0.08], n=12533, días=413.
POR QUÉ IMPORTA: El intervalo incluye valores negativos y positivos: la señal no demuestra por sí sola que anticipe el movimiento.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [COSTOS] — severidad 100/100
QUÉ PASA: Bruto -0.07% y costo 0.08%.
POR QUÉ IMPORTA: La diferencia entre bruto y neto muestra cuánto margen pierde la estrategia antes de poder ejecutar un trade real.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [PAYOFF] — severidad 3/100
QUÉ PASA: Win rate 26.65% vs equilibrio 29.36%.
POR QUÉ IMPORTA: La comparación con el equilibrio muestra si el tamaño de ganadores compensa la frecuencia de pérdidas.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SALIDA] — severidad 38/100
QUÉ PASA: 5098 llegaron a +2%; 38.27% terminaron perdiendo.
POR QUÉ IMPORTA: Una ganancia flotante que vuelve a pérdida no paga el resultado final; aquí se cuantifica ese desperdicio.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SL] — severidad 21/100
QUÉ PASA: 9062 SL; 21.40% habría llegado a TP sin SL.
POR QUÉ IMPORTA: El contrafactual separa un stop protector de uno que corta ganadores que habrían alcanzado el objetivo.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [TIMEOUT] — severidad 0/100
QUÉ PASA: 790 timeout (6.30%), retorno 2.05%.
POR QUÉ IMPORTA: El retorno de las posiciones que expiran indica si el tiempo está cerrando riesgo útil o capital estancado.
EVIDENCIA: n=12533, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
## Motivos de salida
| Motivo | N | % | Retorno medio |
|---|---:|---:|---:|
| SL | 9062 | 72.31 | -1.66 |
| TP | 2681 | 21.39 | 4.30 |
| timeout_48 | 790 | 6.30 | 2.05 |
## Qué no se pudo evaluar
Fidelidad: no evaluada todavía contra ledger ni contra export de trades reales; este informe describe señales históricas brutas, no selección de producción.
## Qué haría alguien no técnico con esto
- No cambiaría la estrategia en producción a partir de este informe.
- Vigilaría las ganancias que superan +2 % porque muchas terminan en pérdida.
- Esperaría la validación contra el ledger antes de modificar la salida.