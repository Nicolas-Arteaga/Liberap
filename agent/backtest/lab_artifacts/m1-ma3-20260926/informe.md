# Auditoría MA Slope Caso 3 — 9400 trades
## Chequeos de integridad
- entry_price_observable: PASS.
- no_pre_entry_candle: PASS.
- no_exit_before_entry: PASS.
- split_at_entry: PASS.
- forward_1h_variance: PASS.
- sample_counts: PASS.
## TITULAR
La estrategia GANA 0.05 % neto por trade, pero es frágil: el edge bruto (0.13 %) apenas supera el costo (0.08 %). El daño más alto medido es SALIDA (34/100).
## Resultado simple
- Win rate 34.15 %; equilibrio 33.02 %; ganancia media 3.20 % y pérdida media 1.58 %.
## Hallazgos
### [ENTRADA] — severidad 0/100
QUÉ PASA: Retorno medio 1/4/12/24/48h con IC bootstrap por día: 1h=0.03% [0.01, 0.05], n=9400, días=238, 4h=0.03% [-0.04, 0.09], n=9400, días=238, 12h=0.04% [-0.09, 0.20], n=9400, días=238, 24h=0.06% [-0.22, 0.34], n=9400, días=238, 48h=0.15% [-0.25, 0.56], n=9400, días=238.
POR QUÉ IMPORTA: El intervalo incluye valores negativos y positivos: la señal no demuestra por sí sola que anticipe el movimiento.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [COSTOS] — severidad 0/100
QUÉ PASA: Bruto 0.13% y costo 0.08%.
POR QUÉ IMPORTA: La diferencia entre bruto y neto muestra cuánto margen pierde la estrategia antes de poder ejecutar un trade real.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [PAYOFF] — severidad 0/100
QUÉ PASA: Win rate 34.15% vs equilibrio 33.02%.
POR QUÉ IMPORTA: La comparación con el equilibrio muestra si el tamaño de ganadores compensa la frecuencia de pérdidas.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SALIDA] — severidad 34/100
QUÉ PASA: 3813 llegaron a +2%; 33.91% terminaron perdiendo.
POR QUÉ IMPORTA: Una ganancia flotante que vuelve a pérdida no paga el resultado final; aquí se cuantifica ese desperdicio.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SL] — severidad 3/100
QUÉ PASA: 5289 SL; 2.89% habría llegado a TP sin SL.
POR QUÉ IMPORTA: El contrafactual separa un stop protector de uno que corta ganadores que habrían alcanzado el objetivo.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [TIMEOUT] — severidad 0/100
QUÉ PASA: 3845 timeout (40.90%), retorno 1.86%.
POR QUÉ IMPORTA: El retorno de las posiciones que expiran indica si el tiempo está cerrando riesgo útil o capital estancado.
EVIDENCIA: n=9400, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
## Motivos de salida
| Motivo | N | % | Retorno medio |
|---|---:|---:|---:|
| SL | 5289 | 56.27 | -1.76 |
| TP | 266 | 2.83 | 9.92 |
| timeout_48 | 3845 | 40.90 | 1.86 |
## Qué no se pudo evaluar
Fidelidad: detección 37/38, motivo 84%, retorno fino 66%; selección/timeouts de producción no reproducibles sin ledger.
## Qué haría alguien no técnico con esto
- No cambiaría la estrategia en producción a partir de este informe.
- Vigilaría las ganancias que superan +2 % porque muchas terminan en pérdida.
- Esperaría la validación contra el ledger antes de modificar la salida.