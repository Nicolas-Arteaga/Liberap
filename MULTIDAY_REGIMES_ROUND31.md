# ROUND 31 — CAMBIO DE HORIZONTE: PERSISTENCIA MULTI-DÍA

## ¿ENCONTRAMOS UNA ESTRATEGIA? **No.**

Las 6 familias multi-día probadas (momentum, reversión, acumulación de OI,
distribución de OI, OI+momentum alineado, OI+momentum en desacuerdo) —
**todas fallan en el mismo punto exacto: la ventana (W) que gana en TRAIN
nunca se confirma en VAL.** No es un fallo de magnitud ni de costos — es
que el ranking cross-sectional multi-día, con los datos disponibles, no
tiene ninguna persistencia fuera de muestra.

---

## Contexto que explica gran parte del resultado

BTC buy-and-hold es profundamente negativo en los TRES segmentos
(train≈−201bp/mes, val≈−488bp/mes, oos≈−462bp/mes equivalente, sin
costos) — **reconfirma el hallazgo de R25**: todo el dataset vive en un
mercado bajista de principio a fin. Esto no invalida per se una estrategia
de ranking relativo (que no apuesta a la dirección del mercado, solo a
diferencias entre símbolos) — pero sí ayuda a explicar por qué cualquier
señal de "momentum" es inestable: en un mercado que cae de forma
sostenida, el ranking de "quién sube más" cambia de composición
constantemente y no hay ganadores persistentes que perseguir.

## Ranking de familias (todas mueren en VAL, ninguna llega a comparación con baselines/OOS)

| Familia | W elegido por TRAIN | TRAIN net/mes | VAL net (bp) | Resultado |
|---|--:|--:|--:|---|
| A — Momentum (long top) | 14d | **+$302** | **−658.1bp** | DESCARTADO |
| E — OI+momentum alineado | 14d | +$93 | −466.7bp | DESCARTADO |
| F — OI+momentum desacuerdo | 7d | −$39 | −374.6bp | DESCARTADO |
| C — OI acumulación | 7d | −$24 | −331.9bp | DESCARTADO |
| D — OI distribución | 3d | −$59 | −221.2bp | DESCARTADO |
| B — Reversión (long bottom) | 3d | −$91 | −216.4bp | DESCARTADO |

**La familia A (momentum) es la más reveladora del problema**: en TRAIN,
la ventana de 14 días parece ganadora de forma aparentemente clara
(+$302/mes, muy por encima de las otras 3 ventanas que van de −$132 a
−$336/mes) — pero en VAL esa misma regla exacta pierde **−658bp**, la
peor caída de las 6 familias. Esto es la firma más limpia de overfitting
a ruido que ha aparecido en 31 rondas: **la ventana "ganadora" no tiene
ninguna relación causal real, es la que por azar tuvo mejor resultado en
el período de TRAIN específico.** Ninguna familia muestra una ventana
consistentemente buena a través de TRAIN — cada una "gana" con un W
distinto y sin ningún patrón (14d, 3d, 7d, 3d, 14d, 7d), reforzando que se
trata de ruido, no de una estructura real de persistencia.

## Baselines (para contexto, no se llegó a necesitarlos como comparación formal)

- Buy-and-hold BTC: fuertemente negativo en los 3 segmentos (mercado
  bajista de la muestra completa, ver R25).
- Canasta aleatoria de 3 símbolos (hold 7d): gross_mean=+44.2bp (TRAIN) /
  +27.4bp (OOS) — **positiva y del mismo orden de magnitud que cualquiera
  de las 6 familias "inteligentes" en su mejor caso de TRAIN**, reforzando
  que ninguna de las reglas de ranking probadas aporta selección real por
  encima de elegir al azar.

## Fase 7 — persistencia, no un pico

Exactamente lo que pedía esta fase quedó demostrado por el propio fracaso
en VAL: ninguna familia muestra una propiedad persistente. La supuesta
ganadora de TRAIN (momentum W=14d) es el ejemplo de manual de "funciona
del día X al día Y" que este mismo brief pide explícitamente rechazar.

## Fase 8 — economía real

No aplica — ninguna familia llegó a VAL confirmado, así que no hay
candidato para calcular trades/mes, drawdown, sensibilidad a fees x2, etc.
Hacerlo sobre una regla que ya se descartó en VAL sería fabricar
confianza donde no la hay.

---

## Veredicto: FAILED en las 6 familias, con causa raíz clara

**El ranking cross-sectional multi-día (momentum, reversión, y sus
variantes con OI) no tiene persistencia fuera de muestra con los datos
disponibles en este proyecto.** No es un problema de costos (nunca
llegamos a esa etapa) ni de concentración — es que el mecanismo mismo
(perseguir o desvanecer una tendencia de 3-30 días) no sobrevive el
control más básico: que la misma regla siga funcionando en el período
siguiente inmediato.

---

## ¿Qué información nueva necesitamos para seguir?

Tal como pide el propio brief para este escenario, no se abre un R32 con
"otra combinación de momentum". Después de 31 rondas exprimiendo
sistemáticamente OHLCV + volumen + OI (intradía en R1-R30, multi-día en
R31), el diagnóstico honesto es:

**El dataset actual (OHLCV + volumen + Open Interest de Binance USDⓈ-M
Futures, universo superviviente de 357/43 símbolos, 14.5 meses de un
mercado mayormente bajista) parece agotado para encontrar una segunda
fuente de alpha direccional — tanto intradía como multi-día.**

Prioridad de datos genuinamente nuevos, en el orden que indica el propio
brief:

1. **Liquidaciones históricas reales** — el intento de R26 quedó bloqueado
   por cobertura (48.5 horas, colector caído). Esto sigue siendo lo más
   accionable si el usuario reinicia el colector y lo deja correr 60-90
   días.
2. **Order book / microestructura histórica** — nunca disponible en este
   proyecto; requeriría una fuente de datos completamente nueva (no existe
   en data.binance.vision a nivel de profundidad de libro).
3. **On-chain** — nunca explorado; requiere decisión de inversión de datos
   del usuario, ya señalada como pendiente desde el Post-Mortem de
   2026-09-05.
4. **Otros datos de posicionamiento** (ej. long/short ratio de cuentas
   grandes vs retail, ya parcialmente en `oi_metrics` vía
   `toptrader_ls_pos`/`global_ls_acct` pero nunca explotado como fuente
   propia — H13/R12 lo tocaron tangencialmente y cerraron FAILED, pero no
   con el rigor de placebo/VAL-confirma que se usa desde R23).
5. Cualquier otra fuente estructural fuera de precio/volumen/OI.

**No se recomienda un R32 que repita, combine o reformule
precio/volumen/OI de nuevo.** El siguiente experimento con expectativa de
valor real requiere una decisión del usuario: reiniciar el colector de
liquidaciones y esperar cobertura, o invertir en una fuente de datos
nueva. Mientras tanto, una alternativa de bajo costo y no explorada con
el rigor actual: revisar `toptrader_ls_pos`/`global_ls_acct` (ya presentes
en `oi_metrics`, sin costo adicional) con el mismo protocolo TRAIN→VAL→
OOS→placebo que se usa desde R23, en vez de repetir el análisis superficial
de R12.
