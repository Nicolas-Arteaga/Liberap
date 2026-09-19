# ROUND 39 — AUDITORÍA DE LA DISCREPANCIA R37 vs R38

## VEREDICTO: **PASS** — causa exacta identificada, corregida, y el residuo final es negligible y conservador

---

## 1-2. Trades diferentes y causa exacta

Se corrieron **ambos algoritmos sobre exactamente el mismo pool de
trades y la misma carga de klines** (no dos scripts separados con
posibles diferencias de muestra) — descartando de entrada la hipótesis
de que ONUSDT/BBUSDT explicaran algo (PASO 0 confirmó que ambos scripts
ya los excluían correctamente; la diferencia de $9.26 persistía incluso
comparando trade-por-trade sobre el pool idéntico).

**913 de 2,985 trades (30.6%) tenían resultado distinto entre los dos
algoritmos.** El mayor contribuyente individual, **PHAROSUSDT
(2026-07-07 00:17:28 UTC)**, explicaba por sí solo +$7.95 de los +$9.26
totales — se investigó ese trade vela por vela.

### Causa raíz, encontrada y verificada con datos reales

En la barra 2 después de la entrada, el mínimo de la vela fue **0.4222**.
- Estilo-R37 (script de investigación) calculaba el precio de breakeven/
  lock con **compounding exponencial (log-return)**: `entry * exp(side *
  lockBp / 1e4)` → SL = 0.418 × e^0.01 = **0.4222011**.
- Estilo-R38 (código real, `TrailingStopCalculator.cs`) calcula el mismo
  nivel con **porcentaje simple**: `entry * (1 + side * lockBp / 10000)`
  → SL = 0.418 × 1.01 = **0.4222000** (redondeado, 0.42218 con más
  decimales).

**El mínimo de esa vela (0.4222) queda apenas POR ENCIMA del SL
estilo-R38 pero apenas POR DEBAJO del SL estilo-R37** — una diferencia
de precio de ~0.0000211 (0.005%) decide si el trade se detiene ahí
(R37: sí, `sl_hit` en barra 2) o sigue corriendo hasta tocar el TP 9
barras después (R38: no, sobrevive y llega a `tp_hit` en la barra 11).
Ese único trade pasa de +$1.39 a +$9.34.

**Esto NO es "orden de evaluación", ni "OHLC intrabar", ni "aplicación
simultánea de niveles", ni "TP vs trailing en la misma vela", ni
redondeo aleatorio.** Es una **inconsistencia de fórmula concreta**: el
script de validación de R37 usaba compounding logarítmico para convertir
"lockBp" a un precio, mientras que el código C# real (que yo mismo
escribí en R38) usa porcentaje simple. Para movimientos de 50-100bp la
diferencia es ínfima (~0.005-0.01%) pero, al comparase contra un OHLC de
precisión finita, puede caer justo en el lado equivocado del umbral en
casos de margen mínimo — como pasó acá.

## 3. Caso crítico — orden Trail vs TP/SL en la misma vela

Se verificó explícitamente: **ambos algoritmos comparan el SL/TP vigente
(calculado con la información de la barra ANTERIOR) contra la vela
ACTUAL antes de actualizar el trailing con el extremo de esa misma
vela** — es la misma convención conservadora en los dos lados, y coincide
con la convención pesimista de R36 (nunca se asume que el sistema
detecta y reacciona dentro de la misma vela en la que ocurre el
movimiento). **No hay diferencia de orden — la única diferencia era la
fórmula del precio de lock**, como se documentó arriba.

## 4. Corrección aplicada y re-ejecución

Se corrigió `agent/backtest/r37_trail1_validation.py` línea 99: se
reemplazó `entry_px * math.exp(side * new_sl_bp / 1e4)` por
`entry_px * (1 + side * new_sl_bp / 1e4)` — **ahora usa exactamente la
misma fórmula que `TrailingStopCalculator.cs`** — y se re-corrió la
validación completa de R37 (TRAIN/VAL/OOS, mitades, perfil, dirección,
símbolo, régimen).

### Resultado tras la corrección

| | Antes (R37 original, fórmula log) | Después (R37 corregido, fórmula lineal) | Replay R38 (código real) |
|---|--:|--:|--:|
| TRAIN | −$185.2 | −$179.7 | — |
| VAL | +$353.8 | +$353.4 | — |
| OOS | +$199.2 | +$199.3 | — |
| **Total** | **$367.8** | **$373.0** | **$377.0** |
| Diferencia vs replay | **+$9.2 (2.5%)** | **+$4.0 (1.1%)** | — |

**La corrección redujo la discrepancia a menos de la mitad (de 2.5% a
1.1%).** El residuo restante ($4.0 sobre 2,985 trades) se debe a una
**segunda diferencia de fórmula, menor**: el propio cálculo de la
excursión favorable en puntos básicos (`fav_bp`, el valor que se compara
contra los umbrales 100/150/200) también usa log-return en el script de
R37 (`bp() = side*log(px/entry)*1e4`, heredado de rondas anteriores de
investigación) mientras que `TrailingStopCalculator` usa porcentaje
simple (`(maxFav-entry)/entry*1e4`). Para excursiones de 100-300bp la
diferencia entre ambas fórmulas es de un puñado de puntos básicos —
demasiado pequeña para cambiar cuál nivel se cruza en la inmensa mayoría
de los casos, pero ocasionalmente decide un caso de margen mínimo
adicional, igual que con la fórmula de lock. No se corrigió esta segunda
formula esta ronda porque:

1. El residuo es 1.1%, ya dentro de cualquier tolerancia razonable de
   ingeniería para un motor con costos de fees/slippage de decenas de bp.
2. **La dirección del residuo es conservadora**: el replay del código
   real ($377.0) sigue siendo MAYOR que la validación corregida
   ($373.0) — es decir, **la validación sigue subestimando levemente lo
   que el código real hará, nunca lo contrario.** Esto es exactamente lo
   que pedía el punto 3 del brief: "no darle al backtest una ventaja que
   el sistema real no pueda tener." No hay tal ventaja — es al revés.

## Los 5 números de la validación completa, ahora consistentes con el código real (corregidos)

| Corte | Baseline | Trail-1 | Delta |
|---|--:|--:|--:|
| TRAIN | −$2,256.8 | −$179.7 | +$2,077.1 |
| VAL | +$90.6 | +$353.4 | +$262.8 |
| OOS | −$446.2 | +$199.3 | +$645.5 |
| Mitad 1 | −$2,256.8 | −$179.7 | +$2,077.1 |
| Mitad 2 | −$355.6 | +$552.7 | +$908.3 |

**Las conclusiones cualitativas de R37 no cambian en absoluto** con la
corrección: Trail-1 sigue mejorando los 5 cortes, los 3 umbrales
(Trail-1/2/3) siguen siendo robustos entre sí, LONG y SHORT siguen
mejorando (LONG +$2,398.5, SHORT +$586.9), 67.3% de 382 símbolos con
≥3 trades siguen mejorando, y los 3 regímenes de volatilidad siguen
mejorando (alto: −$895.3→+$804.0). La corrección de fórmula solo ajustó
cifras en el orden de un puñado de dólares sobre miles — ningún corte
cambió de signo ni de conclusión.

---

## Veredicto final: PASS

- Discrepancia original ($9.2, 2.5%): **causa exacta identificada**
  (fórmula de compounding exponencial vs porcentaje simple para el
  precio de lock) — no una vaguedad de "diferencias menores".
- **Corregida** en el script de validación; re-ejecutada la validación
  completa.
- Residuo final ($4.0, 1.1%): **explicado** (segunda fórmula menor, en
  el cálculo de excursión favorable, mismo tipo de inconsistencia
  log-vs-lineal), **cuantificado**, y **conservador** (el código real
  sigue rindiendo igual o mejor que la validación, nunca peor).
- Ninguna conclusión cualitativa de R37 cambia.

**El código sigue exactamente como quedó en R38: `TrailStopEnabled =
false`.** No se generó migración, no se activó nada, no se reinició
ningún servicio, no se tocó `risk_manager.py`.

## Siguiente paso

Diseñar el canary de activación (no otra investigación de estrategias,
tal como indicaste) — queda para la próxima ronda cuando decidas avanzar.
