# ROUND 26 — LIQUIDATION CASCADE → BLOQUEADA POR DATOS (Caso C), pivote a 22:00 UTC con hallazgo nuevo

## Resumen ejecutivo

- **¿Encontramos alpha?** No en liquidation cascade — la investigación
  nunca llegó a probar ninguna hipótesis de mecanismo porque **los datos
  no alcanzan** (auditados exhaustivamente en el Paso 1, no se inventó
  nada). Pivoté dentro de esta misma ronda a la microestructura de
  22:00 UTC, tal como autoriza el propio brief como plan B.
- **¿Cuánto produce neto?** $0 — no se construyó ninguna sim económica
  esta ronda.
- **¿Qué mecanismo?** Ninguno todavía — pero el diagnóstico de 22:00 UTC
  arroja un hallazgo nuevo y concreto (ver abajo) que cambia la hipótesis
  causal que se venía usando desde R19/R20.
- **¿Es robusta? PASS/CANDIDATE/FAILED?** Liquidation cascade = **Caso C
  (datos insuficientes, causa raíz exacta documentada)**. 22:00 UTC =
  progreso diagnóstico, no una estrategia todavía — justifica R27.
- **Próxima acción:** R27 debe testear el efecto de 22:00 UTC condicionado
  en RÉGIMEN DE LIQUIDEZ (no en la hora del reloj) — ver hallazgo abajo.

---

## PASO 1 — Auditoría de datos de liquidaciones (antes de investigar nada)

Se auditó directamente la tabla `liquidations_research` en
`agent/data/klines.db` (la que alimenta el colector
`agent/liquidation_tracker.py` vía Bybit, corriendo — supuestamente — desde
2026-09-10 según el progress log).

| Campo | Valor medido |
|---|---|
| Fuente/venue | **Bybit únicamente** — no Binance (el stream nativo de Binance para liquidaciones fue dado de baja por Binance globalmente, documentado en el propio código) |
| Filas totales | 14,732 |
| Símbolos con al menos 1 evento | 49 |
| Rango temporal real | **2026-09-09 00:31 UTC → 2026-09-11 01:04 UTC — 48.5 horas** |
| Gap desde entonces | El collector debía seguir corriendo (progress log del 2026-09-10 decía "vivo, fresco"), pero **no hay ni un solo evento nuevo en los 13 días siguientes** hasta hoy (2026-09-24) — se detuvo y no fue reiniciado |
| Duplicados exactos | 0 |
| Nulls en qty/price | 0 |
| Campos disponibles | venue, symbol, timestamp, side (Buy=liquidó SHORT / Sell=liquidó LONG), qty, price, ingested_at |
| Distribución de lado | Buy=12,575 (85%) / Sell=2,157 (15%) — fuertemente desbalanceado, consistente con un movimiento alcista puntual durante esas 48h, no con cobertura representativa |
| Concentración | BTCUSDT solo = 2,464 eventos (17% del total); el resto disperso entre 48 símbolos más |

### Veredicto Paso 1: DATOS INSUFICIENTES, explícito y cuantificado

- **48.5 horas de cobertura real** vs el gate de 60-90 días que este mismo
  proyecto exigió para Open Interest antes de investigarlo (R9-R11) — ni
  remotamente cerca.
- **Venue equivocado para lo que necesitamos**: los eventos son de Bybit,
  pero TODO el resto de la investigación (precio, volumen, OI, funding,
  ejecución) usa Binance USDⓈ-M Futures. Las liquidaciones de Bybit no
  necesariamente coinciden en timing/magnitud con cascadas en el libro de
  Binance — cruzar ambas fuentes introduciría ruido de atribución, no
  señal.
- **No hay forma de reconstruir histórico**: a diferencia de Open Interest
  (rescatado en R9 vía `data.binance.vision/.../metrics/`), Binance dio de
  baja su endpoint de liquidaciones históricas (`/fapi/v1/allForceOrders`)
  globalmente — no existe ningún archivo público de Binance Vision con
  liquidaciones históricas para hacer un backfill. La única fuente posible
  es captura en vivo hacia adelante.
- **El collector está caído** — no es un problema de "esperar más
  cobertura", es un problema operativo que primero hay que resolver
  (reiniciarlo) antes de que "esperar" tenga sentido.

**No se inventaron datos ni se relajó el criterio.** Liquidation cascade
queda **cerrada por Caso C** con causa raíz exacta: falta de cobertura
(operativa + estructural, no solo temporal) y mismatch de venue. Si el
usuario reinicia el colector contra Binance-compatible o acumula Bybit
por 60+ días limpios, se puede reabrir — no antes.

---

## PIVOTE — Microestructura de 22:00 UTC (familia 6, autorizada como plan B por el propio brief)

R19/R20 encontraron el efecto horario más fuerte del proyecto
(−12.3bp @22:00 UTC × compresión previa, 3.2× el placebo) pero nunca
investigaron POR QUÉ pasa ahí específicamente — solo usaron la hora como
feature. Se corrió un diagnóstico puramente descriptivo (solo TRAIN, sin
mirar VAL/OOS, sin construir ninguna señal todavía) caracterizando volumen,
rango intrabar, retorno absoluto y dispersión cross-sectional por cada
hora UTC del día.

### Hallazgo — 22:00 UTC NO es una hora de alta actividad. Es la SEGUNDA hora más tranquila del día completo.

| Métrica | 22:00 UTC | vecinas (21h/23h) | promedio del día | ratio 22:00/día |
|---|--:|--:|--:|--:|
| Volumen mediano | $178,929 | $185,649 | $235,093 | **0.76×** |
| Rango intrabar | 0.548% | 0.509% | 0.571% | 0.96× |
| Dispersión cross-sectional | 0.389% | 0.370% | 0.402% | 0.97× |

Las horas de MAYOR actividad del día están claramente en **14:00-16:00
UTC** (volumen hasta 2× el de 22:00, |ret1| mediano hasta 50% mayor,
~13% de barras "extremas" vs ~6.5% a las 22:00) — coincide con la apertura
del mercado accionario de EE.UU. (13:30 UTC) y su primera hora de
actividad, un patrón económicamente sensato y ya documentado
indirectamente en R7/R8/R18/R19.

**22:00-23:00 UTC es, en cambio, el tramo más tranquilo de todo el ciclo
de 24 horas** — justo después del cierre del mercado accionario de EE.UU.
(20:00-21:00 UTC) y antes de que la sesión asiática tome volumen. Esto
**contradice la hipótesis implícita que se venía arrastrando** (que 22:00
sería una "transición de sesión" con actividad elevada) — es lo opuesto:
es el valle de liquidez del día.

### Por qué esto es informativo, no un callejón sin salida

Esto es consistente con — y le da una explicación causal más precisa a —
el patrón de selección adversa que R20/R21 ya habían medido empíricamente
en esta ventana: **libro de órdenes fino → cualquier flujo residual mueve
el precio de forma desproporcionada → ese movimiento no está respaldado
por información nueva → tiende a revertir cuando la liquidez vuelve**. Es
el mecanismo clásico de "iliquidez temporal", no de "evento informado".

Esto cambia la variable a testear: **en vez de condicionar en el reloj
(hora==22), condicionar en el RÉGIMEN DE LIQUIDEZ** (volumen trailing por
debajo de un percentil bajo, causal, símbolo por símbolo) — el reloj es
solo un proxy imperfecto y compartido de ese régimen; el régimen real de
liquidez varía por símbolo y por día, y usar directamente la variable
causal en vez del proxy horario podría capturar el efecto con más
precisión y en más ventanas horarias de las que el filtro rígido "22:00"
permite.

---

## Próximo paso concreto (R27)

1. **No repetir liquidation cascade** hasta que el usuario decida
   reiniciar el colector (operativo) y/o se acumulen 60+ días limpios —
   documentado como bloqueo externo, no como fallo de la hipótesis.
2. **Testear la hipótesis de régimen de liquidez directamente**: reemplazar
   el filtro "hora==22:00 UTC" por una variable causal continua de
   liquidez trailing (volumen/rango relativo al propio historial de cada
   símbolo, no un promedio de mercado), descubrir el umbral en TRAIN,
   validar en VAL/OOS con el mismo rigor de placebo que el resto del
   proyecto (control temporal Y control de magnitud emparejada, lección
   de R23/R24). Si el efecto de "iliquidez temporal → reversión" es real y
   generaliza, esto sería un mecanismo genuinamente nuevo, no una
   repetición de R19-R21 (que usaban el reloj como filtro rígido, no la
   liquidez real).
3. Seguir sin cerrar la investigación — este es exactamente el caso B del
   brief: progreso diagnóstico real, no una estrategia todavía, pero con
   una pista concreta y accionable para la próxima ronda.
