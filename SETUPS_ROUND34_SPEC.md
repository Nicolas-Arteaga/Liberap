# ROUND 34 — 13 SETUPS DE PRICE ACTION / MEDIAS MÓVILES (1H)

Convención común a los 13: MA7/MA25/MA50/MA99 = SMA de cierre horario,
causales (solo datos hasta la barra `i`, cerrada). "Pendiente" de una MA
en `i` = `MA[i] - MA[i-3]` (3 horas). "Rápido" = magnitud de esa pendiente
en las últimas 2 barras por encima del percentil 80 causal de |pendiente|
de esa MA en las últimas 30 días (720 barras). "Pico" de MA7 = `MA7[i-2]`
es el máximo de `MA7[i-6..i+1]`. "Tocar" una MA = `low<=MA<=high` en esa
barra. ATR14 = SMA de True Range de 14 barras horarias, causal. Entrada
siempre en el open de la barra siguiente al evento. Stop = 1.5×ATR14 al
momento de la señal. TP = 2R (2× la distancia del stop). Salida por
tiempo si no toca ninguno en 72 horas (cierre a mercado). Válido durante
un máximo de 3 barras desde el evento (si no se confirma antes, se
invalida).

---

## SETUP 1 — MA7 gira antes del pullback a MA25 (semilla del usuario)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA25 con pendiente bajista en las últimas 10 barras (contexto de caída previa).
**ESTADO:** MA7 < MA25 y MA7 < MA99.
**EVENTO:** Pendiente de MA7 cruza de negativa a positiva (giro reciente, ≤3 barras).
**CONFIRMACIÓN:** En alguna de las últimas 3 barras, el precio tocó MA25 (high≥MA25) pero cerró por debajo (close<MA25) — mecha de rechazo, no cierre de recuperación.
**ENTRADA:** Open de la barra siguiente a la confirmación.
**NO ESPERAR:** El cruce MA7/MA25 — se entra antes, con el giro de pendiente.
**STOP:** 1.5×ATR14 debajo del mínimo de la mecha de rechazo.
**TP/EXIT:** 2R, o cierre por tiempo a 72h.
**INVALIDACIÓN:** Si pasan 3 barras sin la confirmación de mecha, se descarta el evento.
**NO TRADE:** Si MA7 ya cruzó por encima de MA25 antes de la confirmación (entrada tardía, no es este setup).
**HIPÓTESIS:** El giro de pendiente de la media rápida anticipa que la presión vendedora se agota antes de que el cruce (que reaccionan otros participantes) sea visible.

## SETUP 2 — MA7 toca MA99 desde arriba como soporte dinámico (semilla)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** Recuperación en curso (MA7 ya cruzó por encima de MA99 en las últimas 20 barras).
**ESTADO:** MA7 > MA99, pero MA7 < MA25 y MA7 < MA50.
**EVENTO:** MA7 retrocede (pendiente negativa ≥2 barras) y toca MA99 (low≤MA99≤high).
**CONFIRMACIÓN:** La barra del toque cierra con close>MA99 (rechazo, no ruptura).
**ENTRADA:** Open de la barra siguiente.
**NO ESPERAR:** Ningún crossover adicional — la reacción en el toque es la señal.
**STOP:** 1.5×ATR14 debajo del mínimo de la barra de toque.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el toque no ocurre dentro de 3 barras desde que empezó el retroceso de MA7.
**NO TRADE:** Si MA7 cierra por debajo de MA99 (ruptura real, no rechazo).
**HIPÓTESIS:** MA99 actúa como referencia de valor de mediano plazo; el primer retest desde arriba durante una recuperación atrae compradores que se perdieron el impulso inicial.

## SETUP 3 — Quiebre rápido de MA7 desde un pico (semilla)
**TIMEFRAME:** 1H · **DIRECCIÓN:** SHORT
**CONTEXTO:** Tendencia alcista alineada (MA99<MA50<MA25<MA7).
**ESTADO:** MA7 en pico local (máximo de las últimas 6 barras).
**EVENTO:** Pendiente de MA7 se vuelve fuertemente negativa en ≤2 barras desde el pico (magnitud en percentil causal ≥80 de |pendiente| de MA7).
**CONFIRMACIÓN:** El precio acompaña — vela bajista (close<open) en la barra del quiebre.
**ENTRADA:** Open de la barra siguiente, inmediato.
**NO ESPERAR:** El cruce MA7/MA25 — se entra antes.
**STOP:** 1.5×ATR14 encima del pico de MA7 (en precio, no en valor de MA).
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si pasan 2 barras desde el pico sin el quiebre rápido.
**NO TRADE:** Si el quiebre es gradual (pendiente negativa pero no en el percentil alto de velocidad).
**HIPÓTESIS:** La pérdida abrupta de momentum de la media rápida refleja agotamiento de compradores marginales antes de que las medias lentas (que reaccionan con lag) confirmen el cambio.

---

## SETUP 4 — Pullback simple con rechazo en MA25 (A)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** Tendencia alcista clara: MA7>MA25>MA50>MA99, las 4 con pendiente positiva.
**ESTADO:** Precio retrocede y toca MA25 (primera vez en ≥8 barras).
**EVENTO:** Vela con mecha inferior que toca MA25 (low≤MA25) y cierra por encima (close>MA25).
**CONFIRMACIÓN:** La vela siguiente hace nuevo máximo local de 2 barras (confirma que el rechazo no fue ruido).
**ENTRADA:** Open de la barra posterior a la confirmación.
**NO ESPERAR:** Un segundo toque — el primero limpio es la entrada.
**STOP:** 1.5×ATR14 debajo del mínimo de la mecha de rechazo.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el precio cierra por debajo de MA25 dentro de las 2 barras siguientes al toque.
**NO TRADE:** Si MA25 tiene pendiente plana o negativa (no es tendencia establecida).
**HIPÓTESIS:** En tendencia madura, el primer pullback a la media de referencia atrae compradores institucionales que "compran el retroceso"; toques posteriores tienen menos convicción (por eso no se espera un segundo toque).

## SETUP 5 — Pullback de dos piernas hacia MA50 (B)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA7>MA25>MA50>MA99, tendencia alcista.
**ESTADO:** Precio retrocede hacia MA50 en DOS piernas: baja, rebota parcialmente (sin recuperar MA25), vuelve a bajar y toca MA50.
**EVENTO:** La segunda pierna toca MA50 (low≤MA50) con un mínimo IGUAL O MÁS ALTO que el mínimo de la primera pierna (estructura de piso ascendente).
**CONFIRMACIÓN:** Cierre de esa barra por encima de MA50.
**ENTRADA:** Open de la barra siguiente.
**NO ESPERAR:** Que el precio recupere MA25 antes de entrar — se entra en la reacción de la segunda pierna.
**STOP:** 1.5×ATR14 debajo del mínimo de la segunda pierna.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el mínimo de la segunda pierna es MÁS BAJO que el de la primera (estructura rota, no es pullback de 2 piernas sano).
**NO TRADE:** Si entre las dos piernas pasan menos de 4 barras (probablemente la misma pierna, no dos distintas).
**HIPÓTESIS:** Un pullback de dos piernas con piso ascendente muestra que cada intento de vender pierde fuerza — patrón clásico de acumulación dentro de tendencia.

## SETUP 6 — Ruptura de MA25 seguida de retest fallido (C)
**TIMEFRAME:** 1H · **DIRECCIÓN:** SHORT
**CONTEXTO:** MA7 y MA25 convergiendo o MA7 recién cruzando debajo de MA25 en tendencia previamente alcista.
**ESTADO:** Precio cruza debajo de MA25 (close<MA25 tras varias barras close>MA25).
**EVENTO:** En las siguientes ≤4 barras, el precio intenta volver (high toca o supera levemente MA25) pero NO logra cerrar por encima.
**CONFIRMACIÓN:** El intento fallido cierra con vela bajista y el precio hace un mínimo más bajo que el de la ruptura original.
**ENTRADA:** Open de la barra siguiente al cierre del intento fallido.
**NO ESPERAR:** Un segundo intento de retest — el primer fallo ya es la señal.
**STOP:** 1.5×ATR14 encima del máximo del retest fallido.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el retest SÍ cierra por encima de MA25 (ruptura falsa, cancela el setup).
**NO TRADE:** Si la ruptura original ocurrió hace más de 4 barras sin retest (la oportunidad ya pasó).
**HIPÓTESIS:** El retest fallido de una media rota confirma que los compradores que la defendían ya no tienen fuerza — el nivel pasó de soporte a resistencia.

## SETUP 7 — Falsa ruptura de MA25 con recuperación inmediata (D)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA7>MA25>MA50, tendencia alcista intacta.
**ESTADO:** Precio cierra por debajo de MA25 por 1 sola barra (ruptura aparente).
**EVENTO:** La barra siguiente recupera y cierra por encima de MA25 de nuevo.
**CONFIRMACIÓN:** El rango de la barra de recuperación cubre más del 70% del rango de la barra de ruptura (recuperación fuerte, no tibia).
**ENTRADA:** Open de la barra posterior a la recuperación.
**NO ESPERAR:** Una segunda vela de confirmación — la recuperación fuerte ya es suficiente.
**STOP:** 1.5×ATR14 debajo del mínimo de la barra de ruptura.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si la ruptura dura más de 2 barras antes de recuperar (deja de ser "falsa ruptura", es ruptura real).
**NO TRADE:** Si MA25 tiene pendiente negativa al momento de la ruptura (contexto ya débil).
**HIPÓTESIS:** Una ruptura de un solo período que se revierte de inmediato suele ser liquidez barrida (stop-hunt) más que un cambio real de estructura — clásico patrón de trampa bajista dentro de tendencia.

## SETUP 8 — Compresión de MA7/25/50 seguida de expansión (E)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG o SHORT (según lado de la expansión)
**CONTEXTO:** Ninguno específico — se busca la compresión en sí.
**ESTADO:** MA7, MA25 y MA50 convergen: la distancia máxima entre las 3 (como % del precio) cae al percentil causal ≤15% de los últimos 30 días, sostenida ≥6 barras.
**EVENTO:** El precio rompe con una vela cuyo rango (high-low) supera el percentil causal ≥90% del rango de las últimas 30 días.
**CONFIRMACIÓN:** El cierre de esa vela queda en el 25% externo de su propio rango (cierre fuerte en la dirección de la ruptura, no vela de indecisión).
**ENTRADA:** Open de la barra siguiente, en la dirección de la ruptura.
**NO ESPERAR:** Un retest de las MAs comprimidas — se entra con la expansión misma.
**STOP:** 1.5×ATR14 en contra desde el extremo de la vela de expansión.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si la vela de expansión cierra en el centro de su rango (indecisión, no ruptura limpia).
**NO TRADE:** Si la compresión duró menos de 6 barras (puede ser ruido, no una compresión real).
**HIPÓTESIS:** La compresión de medias refleja equilibrio entre compradores/vendedores; la primera expansión fuerte con cierre direccional marca el desequilibrio inicial, antes de que el resto del mercado reaccione.

## SETUP 9 — Separación fuerte entre MAs + primer pullback ordenado (F)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA7>MA25>MA50>MA99 con separación entre MA7 y MA25 (como % del precio) en percentil causal ≥85% de los últimos 30 días (tendencia "estirada").
**ESTADO:** Tras la separación máxima, MA7 empieza a converger hacia MA25 (pendiente de la distancia MA7-MA25 se vuelve negativa).
**EVENTO:** El precio retrocede ordenadamente (sin vela con rango >2×ATR14) hasta tocar MA7 (no MA25 — la separación es tan grande que MA7 es el primer soporte relevante).
**CONFIRMACIÓN:** Cierre por encima de MA7 en la barra del toque.
**ENTRADA:** Open de la barra siguiente.
**NO ESPERAR:** Que el precio llegue hasta MA25 — con esta separación, MA7 ya es el nivel relevante.
**STOP:** 1.5×ATR14 debajo del mínimo del toque.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si alguna vela del retroceso tiene rango >2×ATR14 (retroceso desordenado/pánico, no pullback sano).
**NO TRADE:** Si la separación MA7-MA25 nunca alcanzó el percentil 85% (no es una tendencia lo suficientemente estirada para este setup).
**HIPÓTESIS:** Tendencias muy estiradas generan pullbacks más superficiales porque la demanda subyacente es más fuerte — el primer soporte relevante se acerca a la acción del precio, no a las medias lentas.

## SETUP 10 — Cruce de MA7 sin confirmación de precio = señal falsa a desvanecer (G)
**TIMEFRAME:** 1H · **DIRECCIÓN:** SHORT (fade del cruce falso)
**CONTEXTO:** MA7 estuvo por debajo de MA25 en tendencia bajista reciente.
**ESTADO:** MA7 cruza por encima de MA25 (crossover clásico alcista).
**EVENTO:** En las 2 barras posteriores al cruce, el precio NO hace un máximo nuevo respecto de las 5 barras previas al cruce (el cruce no viene acompañado de fuerza de precio real).
**CONFIRMACIÓN:** La segunda barra posterior al cruce cierra por debajo de su propio open (vela bajista, rechazando la continuación).
**ENTRADA:** Open de la barra siguiente, SHORT (se desvanece el cruce).
**NO ESPERAR:** Un cruce inverso de vuelta — se opera la falta de confirmación directamente.
**STOP:** 1.5×ATR14 encima del máximo alcanzado desde el cruce.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el precio SÍ hace nuevo máximo en esas 2 barras (el cruce se confirma, no se opera esto).
**NO TRADE:** Si el cruce ocurre con una vela cuyo rango es >2×ATR14 (cruce "real" con fuerza, distinto de un cruce técnico débil).
**HIPÓTESIS:** Un cruce de medias sin acompañamiento de precio suele ser producto del propio cálculo de la media (lag matemático) más que un cambio real de flujo — los operadores que entran por el cruce mecánico proveen liquidez a desvanecer.

## SETUP 11 — Precio cruza MA25 pero MA25/MA50 mantienen estructura → continuación (H)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA25>MA50>MA99 con las 3 en pendiente positiva sostenida (≥15 barras).
**ESTADO:** El precio (no las medias) cruza momentáneamente por debajo de MA25.
**EVENTO:** Durante el cruce, MA25 NUNCA pierde su pendiente positiva (la media no reacciona, solo el precio se desvía).
**CONFIRMACIÓN:** El precio recupera MA25 (close>MA25) dentro de 3 barras desde el cruce.
**ENTRADA:** Open de la barra siguiente a la recuperación.
**NO ESPERAR:** Que MA50 o MA99 confirmen nada — la señal es que NO reaccionaron.
**STOP:** 1.5×ATR14 debajo del mínimo alcanzado durante el cruce.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si MA25 pierde pendiente positiva en algún momento del cruce (deja de ser este setup, la estructura sí se está debilitando).
**NO TRADE:** Si el precio no recupera MA25 dentro de 3 barras (el cruce se vuelve una ruptura real).
**HIPÓTESIS:** Cuando el precio se desvía de una media pero la media (que integra información de más plazo) no reacciona, es más probable que sea ruido de corto plazo que un cambio de tendencia real.

## SETUP 12 — Cambio de pendiente de MA7 mientras MA50/MA99 mantienen dirección → entrada temprana (I)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** MA50 y MA99 con pendiente positiva sostenida (≥20 barras) — tendencia de fondo intacta.
**ESTADO:** MA7 había girado a pendiente negativa (retroceso de corto plazo) mientras MA50/MA99 seguían positivas.
**EVENTO:** MA7 vuelve a girar a pendiente positiva (segundo cambio de pendiente, confirmando que el retroceso de corto plazo terminó).
**CONFIRMACIÓN:** El precio está por encima de MA50 en el momento del giro (el retroceso no llegó a romper la estructura de fondo).
**ENTRADA:** Open de la barra siguiente al giro de MA7.
**NO ESPERAR:** Que MA7 vuelva a cruzar por encima de MA25 — se entra con el giro de pendiente.
**STOP:** 1.5×ATR14 debajo del mínimo desde que MA7 giró a negativa.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el precio cierra por debajo de MA50 en cualquier momento antes del giro (la estructura de fondo se rompió, ya no aplica).
**NO TRADE:** Si MA50/MA99 no llevan al menos 20 barras de pendiente positiva sostenida (tendencia de fondo no establecida).
**HIPÓTESIS:** Retrocesos de corto plazo dentro de una tendencia de fondo sólida son ruido a comprar; el segundo giro de la media rápida confirma que el ruido terminó sin dañar la estructura de plazo mayor.

## SETUP 13 — Rechazo en zona de convergencia MA25/MA50 (J)
**TIMEFRAME:** 1H · **DIRECCIÓN:** LONG
**CONTEXTO:** Tendencia alcista de fondo (MA99 con pendiente positiva).
**ESTADO:** MA25 y MA50 están muy cerca entre sí (distancia ≤ percentil causal 20% de los últimos 30 días) — forman una "zona" en vez de dos niveles distintos.
**EVENTO:** El precio retrocede hasta esa zona (low toca el rango [min(MA25,MA50), max(MA25,MA50)]).
**CONFIRMACIÓN:** Vela con cierre por encima de AMBAS medias tras el toque (rechazo limpio de la zona completa, no de una sola media).
**ENTRADA:** Open de la barra siguiente.
**NO ESPERAR:** Un rechazo de cada media por separado — la zona conjunta es la señal.
**STOP:** 1.5×ATR14 debajo del mínimo del toque.
**TP/EXIT:** 2R o 72h.
**INVALIDACIÓN:** Si el precio cierra por debajo de ambas medias (ruptura de la zona, no rechazo).
**NO TRADE:** Si MA25 y MA50 no están realmente cerca (percentil de distancia >20%) — sería solo un toque de una media individual, ya cubierto por el Setup 4.
**HIPÓTESIS:** Cuando dos medias de referencia convergen, la zona concentra más liquidez y atención que cualquiera por separado — el rechazo conjunto es una señal más fuerte que un toque individual.
