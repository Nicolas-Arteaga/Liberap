# ROUND 27 — LIQUIDITY REGIME → ALPHA

## Resumen ejecutivo

- **¿Encontramos alpha?** No.
- **¿Cuánto produce neto?** $0 — ninguna hipótesis pasó siquiera el
  filtro TRAIN, así que no se construyó ninguna simulación económica.
- **¿Qué mecanismo?** Ninguno sobrevivió — ni "estado de iliquidez solo",
  ni "iliquidez + movimiento extremo", ni el propio filtro de hora 22:00
  UTC re-testeado con esta formulación.
- **¿Cuántos trades? ¿Es robusta?** N/A — no llegó a esa etapa.
- **¿PASS / CANDIDATE / FAILED?** **FAILED, limpio** — a diferencia de
  R24 (donde el placebo reproducía el efecto), acá directamente **no hay
  ninguna dirección con CI que excluya 0 en TRAIN**, en ningún horizonte
  (15m/1h/4h/8h/24h), para ninguna de las 4 formulaciones probadas.
- **Siguiente acción:** R28 debe probar la TRANSICIÓN de liquidez
  (iliquidez → vuelta de liquidez), tal como el propio brief anticipa
  como plan B — es una construcción genuinamente distinta de lo ya
  probado en R19-R21-R26-R27 y todavía no se testeó.

---

## PASO 1 — Régimen de liquidez causal construido

Se usó `vol_pct` (percentil causal de volumen propio de cada símbolo,
ya presente en `build_feats`, ROLL=2880 barras ≈ 30 días) — decil más
bajo (≤10%) como "estado ilíquido". Cobertura: **15.1% de las 4.9M
barras válidas** cayeron en ese decil (ligeramente por encima del 10%
esperado, por concentración de rachas de iliquidez consecutivas —
esperable, no un error).

## PASO 3 — Estado solo (sin evento de movimiento)

| Horizonte | TRAIN cont | TRAIN rev | Elegido |
|---|--:|--:|---|
| 15m | +0.53bp | −0.53bp | **ninguno** |
| 1h | −1.08bp | +1.08bp | **ninguno** |
| 4h | +0.13bp | −0.13bp | **ninguno** |
| 8h | +0.83bp | −0.83bp | **ninguno** |
| 24h | +13.99bp | −13.99bp | **ninguno** |

Ninguna dirección alcanza CI que excluya 0 en TRAIN, en ningún
horizonte. Estar en un estado de baja liquidez, por sí solo, **no tiene
ninguna dirección predecible** — ni siquiera una candidata débil.

## PASO 4/5 — Estado + evento (iliquidez + movimiento extremo en la misma barra)

| Horizonte | TRAIN cont | TRAIN rev | Elegido |
|---|--:|--:|---|
| 15m | +0.04bp | −0.04bp | ninguno |
| 1h | −3.07bp | +3.07bp | ninguno |
| 4h | −14.31bp | +14.31bp | ninguno |
| 8h | −30.4bp | +30.4bp | ninguno |
| 24h | −87.15bp | +87.15bp | ninguno |

Las magnitudes crecen con el horizonte (hasta ±87bp a 24h) pero **ninguna
alcanza significancia estadística en TRAIN** — la dispersión entre
símbolos es demasiado grande para que la muestra de 16,363 eventos
distinga la dirección. Interesante nota metodológica: esto es distinto
del patrón de R24 (donde SÍ había significancia en TRAIN pero el placebo
la reproducía) — acá el problema es más básico, no hay ni siquiera señal
aparente que llegue a probarse en VAL/OOS.

## Control — mismo evento SIN condición de iliquidez

Igual de débil: solo alcanza significancia en OOS a 4h/24h (gross
7.7bp/12.46bp) pero no supera el costo (net negativo en ambos), y ni
siquiera es significativo en TRAIN. Confirma que el movimiento extremo
por sí solo tampoco es una señal utilizable con esta formulación.

## Modelo A (hora==22) vs Modelo B (iliquidez causal) — ninguno funciona con esta formulación

| Modelo | Eventos | TRAIN 4h | TRAIN 24h |
|---|--:|---|---|
| A: hora==22 UTC + movimiento extremo | 12,412 | sin señal | sin señal |
| B: iliquidez causal + movimiento extremo | 16,363 | sin señal | sin señal |

**Ninguno de los dos gana** — ninguno alcanza significancia en TRAIN. Esto
es informativo: el efecto de R19-R21 (−12.3bp @22:00×compresión) usaba una
condición distinta (compresión de volatilidad ANTES de la hora, no un
movimiento extremo DENTRO de la hora, y tampoco iliquidez). Los dos
mecanismos —"iliquidez + movimiento extremo" y "hora fija + movimiento
extremo"— son formulaciones genuinamente nuevas de esta ronda, y ninguna
reproduce ni supera el hallazgo original de R19.

## Controles adicionales

BTC solo: 0 eventos (BTC prácticamente nunca cae en el decil más bajo de
volumen relativo de su propia historia — coherente, es el activo más
líquido del universo). Excluyendo la hora 22 UTC del set "iliquidez +
evento": sigue sin significancia en ningún segmento.

---

## Veredicto — FAILED, causa raíz precisa

Respondiendo el checklist del brief:

- **¿Es solamente volumen?** No aplica — el volumen (iliquidez) por sí
  solo no tiene dirección.
- **¿Es solamente hora?** No — la hora tampoco tiene dirección con esta
  formulación.
- **¿No tiene dirección?** **Sí, exactamente esto.** Ninguna de las 4
  construcciones (estado solo, estado+evento, hora+evento, control
  volumen-only) logra que TRAIN decida un signo con confianza estadística
  — la varianza entre símbolos/eventos es demasiado grande para el tamaño
  de muestra en cualquier horizonte probado.
- **¿El efecto es demasiado pequeño?** No es cuestión de tamaño — ni
  siquiera hay consistencia de signo suficiente para medir un tamaño.
- **¿Fees/slippage destruyen la ventaja?** No llegó a esa etapa — se cerró
  antes, en el filtro de TRAIN, tal como exige el protocolo (no se generan
  falsos positivos forzando una dirección sin evidencia).

**"Illiquidez causal por símbolo", tal como se definió y combinó en esta
ronda (estado solo, estado+movimiento extremo), no es alpha.** Se cierra
esta formulación específica.

---

## Próximo paso (R28) — la transición, no el estado

El propio brief anticipa correctamente el plan B: **no volver al filtro
`hour==22` ni al estado de iliquidez estático — probar la TRANSICIÓN**:
`iliquidez → retorno de liquidez` como el evento disparador (el momento en
que `vol_pct` cruza HACIA ARRIBA desde el decil bajo, no el momento en que
está abajo). La intuición económica es distinta y no probada todavía:
mientras el libro está fino no hay suficiente participación para que un
movimiento se consolide; cuando la liquidez vuelve, el movimiento que
ocurrió en el vacío puede confirmarse o corregirse — eso es una pregunta
de reacción a un evento de TRANSICIÓN, no de un estado estático, y es
mecánicamente diferente de las 4 construcciones ya cerradas en esta ronda.

Si la transición también falla sin señal en TRAIN (mismo patrón limpio de
esta ronda), recién ahí se cierra definitivamente todo el hilo
22:00-UTC/iliquidez (5 intentos: R19, R20, R21, R26, R27, y R28 sería el
sexto) y se pasa a una familia completamente distinta — de las priorizadas
originalmente en R23 y sin tocar todavía: microestructura de secuencias
OI+precio+volumen con una secuencia distinta a capitulación, o
comportamiento relativo entre altcoins con un framing distinto al
beta-hedge ya cerrado.
