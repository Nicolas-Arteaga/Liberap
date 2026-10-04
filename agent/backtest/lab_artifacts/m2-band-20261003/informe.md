# Auditoría Band Touch 15m — 82 trades
## Chequeos de integridad
- entry_price_observable: PASS.
- no_pre_entry_candle: PASS.
- no_exit_before_entry: PASS.
- split_at_entry: PASS.
- forward_1h_variance: PASS.
- sample_counts: PASS.
## TITULAR
La estrategia PIERDE -0.63 % neto por trade. La causa de mayor severidad medida es COSTOS (100/100).
## Resultado simple
- Win rate 15.85 %; equilibrio 19.93 %; ganancia media 12.44 % y pérdida media 3.09 %.
## Hallazgos
### [ENTRADA] — severidad 0/100
QUÉ PASA: Retorno medio 1/4/12/24/48h con IC bootstrap por día: 1h=0.17% [-0.83, 1.29], n=82, días=11, 4h=0.42% [-1.41, 2.37], n=82, días=11, 12h=0.54% [-1.58, 3.30], n=82, días=11, 24h=0.15% [-2.97, 3.44], n=82, días=11, 48h=-2.25% [-5.81, 1.93], n=82, días=11.
POR QUÉ IMPORTA: El intervalo incluye valores negativos y positivos: la señal no demuestra por sí sola que anticipe el movimiento.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [COSTOS] — severidad 100/100
QUÉ PASA: Bruto -0.55% y costo 0.08%.
POR QUÉ IMPORTA: La diferencia entre bruto y neto muestra cuánto margen pierde la estrategia antes de poder ejecutar un trade real.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [PAYOFF] — severidad 4/100
QUÉ PASA: Win rate 15.85% vs equilibrio 19.93%.
POR QUÉ IMPORTA: La comparación con el equilibrio muestra si el tamaño de ganadores compensa la frecuencia de pérdidas.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SALIDA] — severidad 72/100
QUÉ PASA: 46 llegaron a +2%; 71.74% terminaron perdiendo.
POR QUÉ IMPORTA: Una ganancia flotante que vuelve a pérdida no paga el resultado final; aquí se cuantifica ese desperdicio.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [SL] — severidad 7/100
QUÉ PASA: 68 SL; 7.35% habría llegado a TP sin SL.
POR QUÉ IMPORTA: El contrafactual separa un stop protector de uno que corta ganadores que habrían alcanzado el objetivo.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
### [TIMEOUT] — severidad 0/100
QUÉ PASA: 5 timeout (6.10%), retorno 10.95%.
POR QUÉ IMPORTA: El retorno de las posiciones que expiran indica si el tiempo está cerrando riesgo útil o capital estancado.
EVIDENCIA: n=82, `result.json`.
CONFIANZA: BAJA; no son selecciones reales de producción.
Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.
## Motivos de salida
| Motivo | N | % | Retorno medio |
|---|---:|---:|---:|
| SL | 68 | 82.93 | -3.12 |
| TP | 9 | 10.98 | 11.74 |
| timeout_48 | 5 | 6.10 | 10.95 |
## Qué no se pudo evaluar
Fidelidad: detección 37/38, motivo 84%, retorno fino 66%; selección/timeouts de producción no reproducibles sin ledger.
## Qué haría alguien no técnico con esto
- No cambiaría la estrategia en producción a partir de este informe.
- Vigilaría las ganancias que superan +2 % porque muchas terminan en pérdida.
- Esperaría la validación contra el ledger antes de modificar la salida.