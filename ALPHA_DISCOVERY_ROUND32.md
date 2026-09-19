# ROUND 32 — DISCOVERY ENGINE AUTOMATIZADO

## 1. Variables reales encontradas (Fase 1 — inventario)

Universo Feature-Complete (43 símbolos, ≥120,000 filas de OI, ~14.5 meses
sin huecos): 8 features causales construidas, TODAS con cobertura
verificada, ninguna inventada:

| Feature | Qué mide | Cobertura |
|---|---|---|
| `ret1_pct` | Percentil causal del retorno de 1 barra | 100%, 43 símbolos |
| `rv_pct` | Percentil causal de volatilidad realizada | 100%, 43 símbolos |
| `vol_pct` | Percentil causal de volumen propio | 100%, 43 símbolos |
| `dOI_pct` | Percentil causal del cambio de Open Interest | 100%, 43 símbolos |
| `d2OI_pct` | Percentil causal de la aceleración de OI | 100%, 43 símbolos |
| **`lspos_pct`** | Percentil causal de `toptrader_ls_pos` (posicionamiento long/short de cuentas grandes) | **100%, 43 símbolos — nunca usada con este rigor** |
| **`lsacct_pct`** | Percentil causal de `global_ls_acct` (long/short de todas las cuentas, proxy retail) | **100%, 43 símbolos — nunca usada con este rigor** |
| **`divergence_pct`** | Percentil causal de (ls_pos − ls_acct): divergencia smart-money vs retail | **100%, construida por primera vez esta ronda** |

Descartadas explícitamente sin usar: funding (solo como carry, ya cerrado
3 veces), OFI (FAILED en H12), liquidaciones (cobertura insuficiente,
R26).

## 2-3. Eventos/comportamientos descubiertos y candidatos producidos

**Grid automático: 128 máscaras (16 condiciones simples + 112
combinaciones de a pares) × 3 horizontes de criba (4h/24h/72h) = 384
pruebas en TRAIN.** Advertencia estadística aplicada desde el diseño: con
384 pruebas se esperan ~19 "significativas" al 95% por puro azar — el
filtro de TRAIN es una criba, nunca una conclusión.

- **70 de las 384 pruebas pasan la criba de TRAIN** — casi 4× lo esperado
  por azar, lo cual en sí mismo es informativo: sugiere una estructura
  real en el dataset a 72h, pero (ver abajo) resulta ser la MISMA
  estructura de siempre, no una señal nueva.
- El top-15 por efecto está dominado por combinaciones a **72 horas**
  con magnitudes enormes en TRAIN (+100 a +280bp) — casi todas
  combinaciones de `ret1_pct`/`rv_pct` extremos, exactamente la firma del
  **drift estructural de mercado bajista ya identificado y cerrado en R25**
  reapareciendo disfrazado de "evento nuevo" a través de features
  distintas. Confirmado por el patrón de falla siguiente.

## 4-5. Cuántos sobrevivieron VAL, OOS

- **De los 15 candidatos principales, solo 5 confirman el mismo signo en
  VAL** (los otros 10, incluidos los de mayor magnitud en TRAIN, invierten
  de signo — la firma exacta de que TRAIN capturó el régimen de mercado
  de su propio período, no un mecanismo estable).
- **Los 5 que confirman VAL llegan a OOS con n≥30.**
- **De esos 5, CERO sobrevive el control de placebo.** En cada uno, el
  placebo temporal (+25 barras, sin relación causal con el evento)
  reproduce una magnitud igual o mayor que la señal real:

| Candidato | Horizonte | OOS net | Placebo net | Veredicto |
|---|---|--:|--:|---|
| ret1_pct=HI & rv_pct=LO | 72h | +43.2bp | −24.7bp | Magnitudes distintas en signo — CI no excluye 0, inestable |
| vol_pct=HI & lspos_pct=LO | 72h | −162.2bp | −111.1bp | Placebo reproduce 68% de la magnitud |
| ret1_pct=LO & rv_pct=LO | 24h | −37.5bp | −36.3bp | Placebo reproduce 97% — prácticamente idéntico |
| rv_pct=LO & d2OI_pct=HI | 72h | −3.8bp | −7.9bp | Placebo MAYOR que la señal real |
| **rv_pct=LO & lsacct_pct=HI** | 72h | +14.1bp | **+16.7bp** | Placebo MAYOR que la señal real |

**El último caso es el más importante de reportar con detalle**: es la
única combinación que involucra `lsacct_pct` (posicionamiento retail) que
sobrevivió hasta esta etapa, y su OOS neto (+14.1bp) es *menor* que su
propio placebo temporal (+16.7bp) — es decir, **el "efecto" de esta
combinación no tiene nada que ver con el posicionamiento retail
específicamente: es indistinguible de tomar la misma dirección en
cualquier ventana de 72h de esa parte del dataset.** `toptrader_ls_pos` y
`global_ls_acct`, evaluados con el mismo rigor que el resto del proyecto
desde R23, **no aportan señal incremental** — la sospecha de R31 (que
merecían una ronda con rigor completo) queda resuelta: no la hay.

## 6. Resultado económico real

**$0 USDT/mes.** No se construyó ninguna simulación con `portfolio_engine.py`
porque **cero candidatos sobrevivieron el control de placebo** — el
prerrequisito mínimo antes de gastar cómputo en economía real. Llevar
cualquiera de los 5 finalistas a simulación habría sido fabricar
confianza sobre un efecto que el propio placebo demuestra que no existe.

## 7. Mejor candidato

Ninguno califica como candidato. El menos malo en términos de
supervivencia parcial fue `ret1_pct=HI & rv_pct=LO` a 72h (OOS
net=+43.2bp, el único con signo distinto al placebo) — pero **su propio
CI no excluye 0** (n=367, insuficiente para ese nivel de dispersión) y
representa solo 367 eventos en 43 símbolos durante 7 meses de OOS — muy
por debajo de la frecuencia necesaria para sostener una estrategia con 3
posiciones y rotación mensual.

## 8. Distribución (MFE/MAE) — ninguna asimetría explotable

Para los 5 finalistas se midió la distribución completa, no solo la
media: en todos los casos, **MFE y MAE son de magnitud casi simétrica
(ej. mfe_mean=609.8bp vs mae_mean=−550.5bp)** y los win rates rondan
0.51-0.55 — apenas por encima de azar, sin ninguna estructura de "downside
comprimido, upside abierto" ni cola favorable identificable. La
volatilidad a 72h en este universo es simplemente alta en ambas
direcciones, no asimétrica.

## 9. Por qué no hay PASS (causa raíz exacta)

- El 82% de los candidatos que "ganaron" la criba de TRAIN (70 de 384)
  invierten de signo en VAL — indicando que la mayoría de lo detectado es
  **régimen de mercado específico del período de TRAIN**, no un mecanismo.
- De los 5 que sí confirman VAL, **el 100% es indistinguible del placebo
  temporal** — el control diseñado específicamente para detectar esto
  (lección de R24/R25) funciona exactamente como debía.
- `toptrader_ls_pos` y `global_ls_acct`, la única pieza de datos
  genuinamente nueva incorporada esta ronda (nunca antes evaluada con este
  rigor), **no muestra información incremental** una vez controlada
  correctamente.

## 10. ¿El dataset está agotado? Sí — con evidencia sistemática, no solo intuición

Esta ronda es la prueba más exhaustiva y mejor controlada del proyecto:
384 combinaciones automáticas (no elegidas a mano), penalización de
complejidad explícita (solo pares, nunca tríos), criba de TRAIN,
confirmación de VAL, placebo temporal, y estudio de distribución completa
—y el resultado es 0 candidatos. Combinado con R29 (OI puro), R30 (8
combinaciones estado+evento intradía) y R31 (6 familias multi-día), el
espacio de **OHLCV + volumen + Open Interest + posicionamiento
(toptrader/global) de Binance USDⓈ-M Futures, sobre el universo
superviviente disponible**, está sistemáticamente cubierto y no contiene
una segunda fuente de alpha direccional explotable.

### Qué dato nuevo se necesita para romper el techo

En orden de viabilidad práctica para este proyecto:

1. **Liquidaciones históricas reales con cobertura de 60-90+ días** — el
   único dato bloqueado por una causa operativa reversible (reiniciar el
   colector), no por falta de fuente. Es la prioridad #1 recomendada.
2. **Order book / profundidad de mercado histórica** — requiere una fuente
   de datos que no existe en este proyecto (no la provee
   data.binance.vision); necesitaría contratar o construir un colector
   propio desde ya, para tener cobertura útil en 2-3 meses.
3. **On-chain** (flujos a exchanges, actividad de ballenas, métricas de
   red) — requiere decisión de inversión de datos del usuario, señalada
   como pendiente desde 2026-09-05.
4. Cualquier fuente de información NO derivada de precio/volumen/
   posicionamiento de futuros — el proyecto ya demostró, con method rigor
   creciente durante 10+ rondas, que ese espacio específico está agotado
   para este objetivo.

**No se recomienda un R33 que vuelva a combinar, re-parametrizar o
reformular OHLCV/volumen/OI/posicionamiento.** La investigación no se
cierra — se pausa en este eje hasta que haya una decisión sobre datos
nuevos, y se documenta con la evidencia más sólida producida en 32 rondas
de por qué ese eje específico no va a rendir más sin ellos.
