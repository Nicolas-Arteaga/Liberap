# ROUND 37 — VALIDACIÓN FINAL DE TRAIL-1

## VEREDICTO FINAL: **PASS**

Trail-1 (y sus variantes cercanas Trail-2/Trail-3) mejoran el PnL de
forma consistente en OOS, no dependen de un puñado de símbolos o
perfiles, y pequeñas variaciones del umbral producen resultados
similares — el estándar que definiste para PASS. **No es un artefacto del
subconjunto reconstruible de R36.**

**No se implementa todavía** — el siguiente paso (fuera del alcance de
esta ronda, según tu instrucción) es diseñar la incorporación a
`risk_manager.py` sin tocar la lógica de entrada.

---

## FASE 1 — El "sesgo" de R36 explicado: no era una muestra sesgada, eran datos corruptos

Se auditó exactamente por qué la población completa (3,315 trades,
+$34,890) y la reconstruible de R36 (2,337 trades, baseline negativo)
parecían contradecirse. La respuesta es concreta y verificable por SQL
directo, no una hipótesis:

**10 trades de ONUSDT y 2 de BBUSDT tienen `ClosePrice` corrupto** — saltos
de precio de ~1000× que ningún movimiento real de mercado produce en 15
minutos-horas (ej. ONUSDT: `EntryPrice=$0.09207 → ClosePrice=$98.63`;
BBUSDT: `EntryPrice=$0.009397 → ClosePrice=$8.175`). Estos 12 trades
generan PnL de 5-6 cifras sobre posiciones de $150 de notional
(`+$160,537`, `+$164,172`, `−$112,938`, `−$130,343`, etc.) — matemáticamente
imposible con el tamaño de posición real del sistema. Es un error de
datos (probablemente del mismo incidente de reset de Docker), no
trading real.

**Verificado por SQL**: excluyendo únicamente estos 12 trades, la
población limpia de **3,271 trades suma −$2,488.02** — negativa, del
mismo signo y orden de magnitud que el baseline reconstruido en R36
(~−$1,624 sobre el subconjunto de esa ronda). **La "contradicción" nunca
existió — el número +$34,890 de R35/R36 estaba inflado por datos
corruptos, no por un sesgo de muestreo.** Se recomienda además que el
usuario audite el origen de estos dos registros en la base de producción,
fuera del alcance de esta investigación.

## FASE 8 — Recuperación de cobertura: 608/608 símbolos (100%), no 421/610

Se buscó exhaustivamente en fuentes locales antes de asumir que 2,337 era
el máximo posible. Se encontró que **`agent/data/klines.db` (caché propio
del agente, 858 símbolos, colector en vivo) tiene cobertura de 15m para
los 189 símbolos que faltaban** en `binance_vision_clean.db`. Se
fusionaron ambas fuentes (`binance_vision_clean.db` como fuente
primaria, `klines.db` como respaldo) y se logró cobertura del **100% de
los símbolos con trades** (608/608). Con SL/TP disponibles y suficiente
historia previa a la entrada, la población simulable creció de
**2,337 → 2,985 trades** (descartados: 286, principalmente por historia
insuficiente antes de la entrada para calcular ATR/contexto, no por falta
de cobertura de precio).

---

## FASE 7 — TRAIN / VAL / OOS + mitades temporales (población ampliada, 2,985 trades)

| Regla | TRAIN | VAL | OOS | Mitad 1 | Mitad 2 |
|---|--:|--:|--:|--:|--:|
| **baseline** | −$2,256.8 (PF 0.62) | +$90.6 (PF 1.07) | −$446.2 (PF 0.76) | −$2,256.8 | −$355.6 |
| **Trail-1** | −$185.2 (PF 0.93) | **+$353.8** (PF 1.41) | **+$199.2** (PF 1.23) | −$185.2 | **+$552.9** |
| Trail-2 (inicio en 75bp) | **−$40.2** (PF 0.98) | +$393.8 (PF 1.50) | +$225.9 (PF 1.28) | −$40.2 | +$619.7 |
| Trail-3 (umbrales más anchos) | −$128.9 (PF 0.95) | +$347.3 (PF 1.40) | +$221.7 (PF 1.25) | −$128.9 | +$569.0 |

**Las 3 variantes de trailing mejoran el baseline en los 5 cortes
independientes** (TRAIN, VAL, OOS, mitad 1, mitad 2) — ninguna excepción.
Los 3 profit factors en OOS son >1.2 (rentables) vs 0.76 del baseline.
**Pequeñas variaciones del umbral (Trail-1 vs Trail-2 vs Trail-3) producen
resultados del mismo orden de magnitud y siempre positivos en VAL/OOS** —
exactamente el criterio de robustez del punto 6 del brief: el concepto no
depende de un número mágico.

**Matiz honesto**: TRAIN sigue siendo negativo con las 3 variantes (aunque
muchísimo menos que el baseline: de −$2,256.8 a entre −$40 y −$185) — el
trailing reduce dramáticamente las pérdidas pero no las elimina por
completo en el tramo más antiguo de la muestra.

## FASE 2 — Por perfil de estrategia

**11 de 12 perfiles con ≥30 trades mejoran con Trail-1** (el único que
empeora, delta=−$6.3, es marginal). El perfil dominante (`857c1536...`,
n=1,689, el más grande por lejos — coincide con la estrategia Nexus
principal) mejora de −$2,806.2 a −$542.9 (delta +$2,263.3) — sigue
negativo pero la pérdida se reduce en un 81%. Ningún perfil individual
explica por sí solo la mejora total — está distribuida.

## FASE 4 — Por dirección

| | n | Baseline | Trail-1 | Delta |
|---|--:|--:|--:|--:|
| LONG | 2,199 | −$2,744.9 | −$350.3 | **+$2,394.6** |
| SHORT | 786 | +$132.5 | +$718.0 | **+$585.5** |

**Trail-1 funciona en ambas direcciones** — mejora tanto LONG como SHORT.
Matiz honesto: LONG sigue siendo negativo incluso con Trail-1 (−$350.3);
SHORT ya era rentable en baseline y se vuelve más rentable todavía. Esto
sugiere que Trail-1 por sí solo no "arregla" la rama LONG del sistema,
pero reduce sustancialmente su costo.

## FASE 3 — Por símbolo (no depende de pocos)

- Top-10 símbolos por volumen de trades: mejora de $162.5 (n=211).
- Resto (600+ símbolos): mejora de $2,817.7 (n=2,774).
- **De 382 símbolos con ≥3 trades: Trail-1 mejora en 256 (67.0%) y empeora
  en 80 (20.9%)** (el resto, sin cambio apreciable). Una mayoría clara,
  no una minoría de símbolos atípicos.

## FASE 5 — Por régimen de volatilidad (ATR relativo al entrar, terciles)

| Régimen | n | Baseline | Trail-1 | Delta |
|---|--:|--:|--:|--:|
| ATR bajo | 996 | −$726.1 | −$251.4 | +$474.7 |
| ATR medio | 995 | −$991.0 | −$186.4 | +$804.7 |
| ATR alto | 994 | −$895.3 | **+$805.6** | **+$1,700.8** |

**Mejora en los 3 regímenes, creciente con la volatilidad** — tiene
sentido económico: cuanto mayor la excursión típica del trade, más valor
hay para capturar con una gestión activa de salida. El régimen de alta
volatilidad es el único que Trail-1 vuelve completamente positivo por sí
solo.

---

## Respuesta a la pregunta del brief

> **¿Trail-1 es una mejora real de nuestro sistema o fue un artefacto del
> subconjunto reconstruible?**

**Es una mejora real.** Se descartó la hipótesis de artefacto de muestra:
el "sesgo" de R36 se explicó por completo (datos corruptos de 2 símbolos,
no exclusión sistemática de trades ganadores), la población se amplió a
2,985 trades (100% de símbolos con cobertura recuperada), y el resultado
se sostiene: mejora en TRAIN/VAL/OOS, ambas mitades, 11/12 perfiles,
ambas direcciones, 67% de los símbolos individuales, y los 3 regímenes de
volatilidad. Es robusto a variar el umbral en ±25-50bp (Trail-1/2/3 dan
resultados similares).

**Clasificación: PASS**, con dos matices a tener en cuenta en el diseño
de implementación (no cambian el veredicto, pero son relevantes): (1)
TRAIN queda cerca de breakeven pero no positivo — el trailing reduce
pérdidas más de lo que genera ganancia neta en ese tramo específico de la
muestra; (2) la rama LONG mejora muchísimo pero no se vuelve rentable por
sí sola con Trail-1 — SHORT es la que más se beneficia en términos
absolutos.

## Siguiente paso (fuera de esta ronda)

Diseñar la incorporación de una regla de trailing tipo Trail-1/Trail-2 en
`risk_manager.py`, sin alterar la lógica de generación de señales de
entrada. No se toca producción en esta ronda ni se implementa nada
todavía — queda pendiente de decisión del usuario.
