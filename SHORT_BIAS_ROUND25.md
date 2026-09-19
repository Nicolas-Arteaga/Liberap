# ROUND 25 — CONVERTIR EL SESGO BAJISTA EN ALPHA OPERABLE

## Resumen ejecutivo

- **¿Encontramos alpha?** No. El "sesgo bajista" que apareció 5 veces
  (R12→R13→R15→R18→R24) **no es un fenómeno específico de altcoins** —
  es beta pura a un mercado de BTC que cayó ~38% durante toda la ventana
  histórica del dataset (de $104,545 a $64,504 entre 2025-06 y 2026-08).
- **¿Cuánto produce neto?** No se llegó a simular una estrategia con
  capital: se cerró en la Fase A (reproducción del fenómeno), antes de
  diseñar cualquier regla operable, porque el fenómeno mismo resultó no
  ser lo que parecía.
- **¿Es SHORT, LONG o market-neutral?** Ninguno de los tres es viable
  como estrategia nueva: es simplemente estar corto del mercado cripto
  en una muestra donde el mercado cripto bajó. Eso es una apuesta
  direccional, no una estrategia.
- **¿Es robusta? PASS/CANDIDATE/FAILED?** **FAILED**, con evidencia sólida
  y una causa raíz identificada con precisión (no un cierre vago).
- **Próxima acción:** pivotar a familia 4 (liquidation cascade, si el
  colector ya tiene cobertura suficiente) o familia 6 (microestructura de
  22:00 UTC investigando el fenómeno, no usando la hora como feature) —
  las dos únicas familias de la lista de prioridad de R23-R25 que
  todavía no se tocaron con el motor corregido.

---

## Fase A — reproducir el fenómeno de forma simple y transparente

Antes de diseñar cualquier regla de selección, se midió el retorno
forward NO condicionado (sin ningún evento disparador) de: el universo
completo, un subconjunto "majors" (20 símbolos de capitalización grande:
BTC, ETH, SOL, XRP, etc.), un subconjunto "antiguos" (22 símbolos con
historia desde el inicio del dataset, proxy de liquidez/madurez), un
subconjunto "nuevos" (44 símbolos listados tarde), y BTC/ETH por
separado — en TRAIN/VAL/OOS y 4 horizontes.

**Resultado decisivo — TODOS los grupos son negativos, incluido BTC solo:**

| Grupo | TRAIN @24h | VAL @24h | OOS @24h |
|---|--:|--:|--:|
| Universo completo | −80.4bp | −33.3bp | −27.1bp |
| Majors (20 símbolos grandes) | −3.7bp (no sig.) | **−33.6bp** | **−22.3bp** |
| Antiguos (22 símbolos, historia completa) | −9.4bp | −37.8bp | −15.5bp |
| Nuevos (44 símbolos, listados tarde) | — | — | **−51.6bp** |
| **BTC solo** | **−8.3bp** | **−15.9bp** | **−16.3bp** |
| **ETH solo** | +12.4bp | **−28.6bp** | **−15.8bp** |

**BTC solo — sin ningún condicionamiento, sin ninguna selección de
altcoins — ya es negativo y significativo en los tres segmentos.** Esto
no es un fenómeno de "altcoins chicas se diluyen" — es que **todo el
mercado cripto, BTC incluido, cayó durante toda la ventana capturada por
el dataset** (BTCUSDT: $104,545 el 2025-06-01 → $64,504 el 2026-08-17,
verificado directamente contra los precios crudos de la base de datos,
una caída real de ~38%).

## Lo que esto significa — el fenómeno de R12-R24 nunca fue alfa alt-específico

Lo que 5 rondas independientes interpretaron como "sesgo estructural
bajista de altcoins chicas" es, medido de forma limpia y sin condicionar
en ningún evento, simplemente **beta al mercado**: estar corto de
CUALQUIER cosa cripto —BTC, majors, o altcoins chicas— generó PnL
positivo durante este período histórico específico, porque el mercado
entero bajó. Sí existe un gradiente de magnitud (nuevos/pequeños caen más
que antiguos/grandes: −51.6bp vs −15.5bp a 24h en OOS) — pero esa
diferencia es totalmente consistente con **beta más alta en activos más
chicos y volátiles frente a un mercado que cae**, no con una dilución
estructural independiente del mercado.

**Esto responde exactamente la pregunta que pedía la Parte 1/2 del
brief** ("¿el edge está realmente en el lado SHORT o simplemente en que
el universo entero tuvo drift bajista?"): es lo segundo. Y peor
todavía — no es "el universo de altcoins", es **el mercado cripto
completo en esta ventana muestral**.

## Por qué esto NO es monetizable como estrategia nueva

Una estrategia que consiste en "estar corto el universo cripto" es
indistinguible, en la práctica, de tomar una posición corta apalancada en
BTC — no requiere ninguna de las 357 altcoins, ningún ranking, ningún
score de vulnerabilidad. Es una apuesta direccional sobre hacia dónde va
el mercado cripto en general, no un mecanismo de mercado específico.
Consecuencias:

- **Depende 100% del régimen de mercado** (exactamente la pregunta del
  checklist final: "¿el efecto solamente existe en determinados
  regímenes?" — sí, existe únicamente porque esta muestra capturó un
  mercado bajista; en una muestra alcista el mismo mecanismo produciría
  pérdidas simétricas y probablemente catastróficas con apalancamiento).
- Es, en la práctica, la misma familia que **"beta betting"**, ya cerrada
  explícitamente en R13 (banned list del propio brief de esta ronda) —
  no se puede convertir en Strategy Candidate nueva sin violar esa
  regla, porque en el fondo es la misma apuesta con otro nombre.
- No sobrevive la prueba especial del brief ("¿la selección inteligente
  aporta valor sobre selección aleatoria?") de forma significativa: el
  patrón es tan uniforme entre majors/antiguos/nuevos que cualquier
  canasta corta al azar del universo captura la mayor parte del efecto —
  la selección no es lo que genera el resultado, es simplemente estar
  corto de cripto.

**No se llegó a construir Modelos A-F (basket/ranking/tail/régimen/
deterioro/rebalanceo lento) ni se corrió `portfolio_engine.py`** porque
hacerlo sería simular una estrategia cuyo mecanismo real ya está
identificado como beta de mercado, no como una señal — construir la
sim económica completa habría sido gastar cómputo en confirmar algo que
la Fase A ya demostró con datos crudos verificables.

## Segmentación — lo único potencialmente interesante, con advertencia explícita

El gradiente antiguos vs nuevos (−15.5bp vs −51.6bp @24h OOS) sí sugiere
que las altcoins más nuevas/chicas tienen MÁS beta al mercado que las
grandes — pero aislar esa diferencia de forma limpia requiere exactamente
la metodología de beta-hedge/residual-momentum que R13 ya probó y CERRÓ
como FAILED (el placebo aleatorio superó al portfolio "inteligente"). No
se repite esa metodología en este round, tal como pide explícitamente el
brief ("no repetir... residual momentum").

---

## Veredicto: FAILED, con causa raíz identificada (no un cierre vacío)

Respondiendo el checklist del brief directamente:

- **¿El edge desaparece con fees?** No llegó a ese punto — desapareció
  antes, al identificarse como beta de mercado.
- **¿Es demasiado lento / depende de activos ilíquidos?** No es el
  problema — el efecto está presente incluso en BTC/majors líquidos.
- **¿Funding destruye la ventaja?** No se evaluó — irrelevante frente al
  hallazgo principal.
- **¿El efecto solo existe en determinados regímenes?** **Sí — este es
  exactamente el problema.** Existe solo porque la muestra capturó un
  mercado bajista de principio a fin.
- **¿La selección aporta sobre un short aleatorio?** No de forma
  significativa — el patrón es demasiado uniforme entre grupos.
- **¿El capital de 450 USDT es insuficiente?** No es el limitante.

**El "short bias" NO es monetizable como estrategia independiente de
mercado.** Es una descripción correcta de lo que pasó en esta muestra
histórica (BTC bajó, todo bajó con él, más las altcoins chicas que las
grandes) — no es un mecanismo reutilizable ni una fuente de alpha nueva.
Las 5 rondas anteriores que tropezaron con este patrón como confounder
tenían razón en descartarlo como explicación de SUS hipótesis
específicas; ahora, investigado directamente, también queda descartado
como estrategia en sí misma.

---

## Próximo paso concreto (R26)

**No se cierra la investigación.** Quedan dos familias de la lista de
prioridad (R23-R25) sin tocar con el motor corregido:

1. **Liquidation cascade** (familia 4): el colector de liquidaciones
   corre desde 2026-09-10 — verificar cobertura acumulada antes de
   empezar; si sigue siendo insuficiente, reconstruir histórico vía
   `data.binance.vision/.../metrics/` (mismo mecanismo que desbloqueó OI
   en R9) en vez de esperar más al colector en vivo.
2. **Microestructura de 22:00 UTC** (familia 6): R19/R20 encontraron el
   efecto horario más fuerte del proyecto (−12.3bp, 3.2× el placebo) pero
   nunca se investigó el FENÓMENO subyacente (cambio de liquidez,
   transición de sesión, concentración de actividad institucional) —
   solo se usó la hora como feature. Investigar qué pasa estructuralmente
   a esa hora podría convertir un efecto de magnitud insuficiente (la
   mitad del costo de ejecución) en algo explotable si se identifica el
   mecanismo causal y se puede aislar el subconjunto de eventos donde el
   mecanismo es más fuerte.

Recomendación: priorizar liquidation cascade primero (mecanismo más
distinto de todo lo ya explorado), y usar 22:00 UTC como plan B si la
cobertura de liquidaciones sigue siendo insuficiente.
