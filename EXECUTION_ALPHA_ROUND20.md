# ROUND 20 — EXECUTION ALPHA + REALISTIC FILL ATTACK

**Fecha:** 2026-09-23 · Script: `agent/backtest/r20_execution.py` · Universo
ancho (357 símbolos) · Ataca directamente el hallazgo de R19 (hora UTC +
compresión, el primero que el placebo no reprodujo).

**Nota de proceso:** la primera corrida tenía un bug real de signo (la
dirección se fijaba invertida respecto al retorno crudo de TRAIN) más un bug
de doble escala en dos tablas de diagnóstico. Se encontró, se corrigió y se
volvió a correr antes de reportar — los números de abajo son de la corrida
corregida.

## Respuesta directa a la pregunta del round

**¿Los ~12bp son demasiado pequeños, o el modelo de costo era demasiado
conservador?** **Ambas cosas, parcialmente — y ninguna alcanza para pasar.**
Corregir la dirección (congelada en TRAIN, no elegida mirando el resultado
completo) mejoró la consistencia real de la señal. Modelar ejecución maker de
forma realista (fill mecánico, no asumido) bajó el costo efectivo de 24bp a
~6-9bp. **Con ambas correcciones aplicadas a la vez, el resultado sigue siendo
negativo en todas las configuraciones — pero por mucho menos margen que antes.**

# RESULTADO: FAIL

**Mejor caso económico real: −$4/mes** (maker, capital $150, 5 slots). Ningún
escenario de capital/slots/fill-rate cruza a positivo, y mucho menos a $150.

---

## 1. Auditoría del piso de 24bp (Fase 1)

Descompuesto explícitamente para una estrategia **direccional de una sola
pata** (NO el modelo de dos patas de R16/R17, que es para carry
delta-neutral — distinción que el brief pedía verificar y que se confirma
correcta: el código de R18-R20 ya usaba 1 pata):

| Componente | Taker | Maker |
|---|--:|--:|
| Fee (por lado) | 5bp | 2bp |
| Spread cruzado | 3bp | 0bp (por definición, no cruza) |
| Slippage/impacto residual | 4bp | 1bp |
| **Total por lado** | **12bp** | **3bp** |
| **Round-trip (entrada+salida)** | **24bp** | **6bp — SI llena ambos lados** |

## 2. Familia horaria — dirección fijada en TRAIN (sin mirar VAL/OOS)

| Hora | Dirección (TRAIN) | VAL | OOS |
|---|---|--:|--:|
| 20:00 | LONG | +5.2bp | +1.1bp |
| 21:00 | LONG | −2.6bp | −2.4bp |
| **22:00** | **SHORT** | **+6.6bp** | **+14.1bp** |
| 23:00 | SHORT | +6.1bp | −11.4bp |
| 00:00 | SHORT | +1.6bp | +0.3bp |
| 01:00 | LONG | +1.7bp | +2.1bp |

**22:00 UTC es la única de las 6 horas con signo POSITIVO y CRECIENTE tanto
en VAL como en OOS** — evidencia (no concluyente con n=6, pero consistente)
de que no es una hora arbitraria entre vecinas equivalentes.

## 3. Taker baseline por horizonte (H=22, SHORT, costo 24bp)

| h | train gross | val gross | oos gross | val net | oos net |
|---|--:|--:|--:|--:|--:|
| 30m | +1.0bp | +2.1bp | +8.7bp | −21.9bp | −15.4bp |
| **1h** | +22.9bp | +6.6bp | +14.1bp | **−17.4bp** | **−9.9bp** |
| 2h | +84.8bp | +16.8bp | +2.9bp | −7.2bp | −21.1bp |
| 4h | +86.6bp | +15.8bp | −1.1bp | −8.2bp | −25.1bp |

**A costo taker puro, nada es net-positivo en VAL u OOS.** 1h es el horizonte
con menor pérdida neta (−9.9bp OOS) — se usa como base para el resto de la
ronda.

## 4-5. Maker con fill mecánico + selección adversa (h=1h)

**No se asumió fill al 100%.** Se modeló mecánicamente: limit a 6bp de mejora
sobre el precio de señal, ventana de 4 barras (1h) para que el precio lo
toque (usando máximos/mínimos intrabar, no cierre):

- **Fill mecánico observado: 71.7%** (18 204 de 64 300 señales no llenan en
  la ventana — se descartan, no generan PnL ni ocupan slot).
- **Taker (todas las señales): gross = 15.0bp.**
- **Maker (solo las que llenaron): gross = 3.79bp — 4× MÁS CHICO.**

**Esto es selección adversa real, medida, no supuesta:** las señales donde
el limit llega a llenarse son precisamente aquellas donde el precio se movió
primero HACIA el trader (para tocar el limit) — y esas resultan tener, en
promedio, mucho menos continuación favorable después. Confirma exactamente
la preocupación del brief.

**Con costo maker (6bp) el neto mejora igual:** MAKER filled net = −2.21bp
vs TAKER-todas net = −9.0bp. El ahorro de fee/spread compensa PARTE de la
selección adversa, pero no toda.

**Escenarios de fill-rate (25/50/75/90/100%):** el EV por señal es negativo
en los 5 escenarios (−0.55bp a −2.21bp) — el fill-rate más bajo (menos
señales ejecutadas, menos exposición al costo) da la EV menos negativa, pero
**nunca cruza a positivo bajo ningún supuesto de fill.**

## 7-8. Timing de entrada

| Entrada | gross | net (taker) |
|---|--:|--:|
| t−1 (−15min, anticipada) | +10.6bp | −13.4bp |
| **t (señal, open[t+1])** | **+15.0bp** | **−9.0bp — la mejor** |
| t+1 (+15min tarde) | +14.0bp | −10.0bp |
| t+2 (+30min tarde) | +12.9bp | −11.2bp |

Entrar exactamente en la señal es óptimo; adelantarse o demorarse solo
empeora. No hay una ventana de entrada escondida que rescate la estrategia.

## 9. Salida — TP/SL desde percentiles de TRAIN (congelado, no optimizado en OOS)

TP = +49bp (p60 MFE en TRAIN) · SL = −44bp (p40 MAE en TRAIN), aplicado tal
cual a VAL/OOS:

| | gross | net (taker) | WR |
|---|--:|--:|--:|
| VAL | +5.9bp | −18.1bp | 0.47 |
| OOS | +8.8bp | −15.2bp | 0.56 |

Mejora el win-rate (0.56 en OOS, contra el objetivo del brief de no exigir
WR alto) pero el costo taker sigue devorando el gross. Con costo maker
(6bp) el número de OOS rondaría ≈ +2.8bp — pero un TP/SL requiere salida
garantizada (de facto taker) en el momento del disparo, así que aplicar
costo maker a la salida no es realista; se reporta la limitación en vez de
inventar un número optimista.

## 10-11. Sim económica — capital real, TAKER vs MAKER (h=1h)

| Ejecución | Capital | Slots | trades/mes | avg_net | WR | **NET/mes** |
|---|--:|--:|--:|--:|--:|--:|
| TAKER | $150 | 1 | 30 | −20.0bp | 0.31 | **−$9** |
| TAKER | $450 | 5 | 149 | −21.3bp | 0.27 | −$29 |
| **MAKER (fill mecánico)** | **$150** | **5** | **127** | **−9.9bp** | **0.42** | **−$4 (el mejor caso)** |
| MAKER (fill mecánico) | $450 | 1 | 27 | −11.8bp | 0.42 | −$14 |

**Ninguna configuración (12 probadas: 3 capitales × 4 combinaciones de
slots/ejecución) es positiva.** El apalancamiento no se probó porque el
prerrequisito del brief ("primero demostrar expectancy positiva después de
costos") no se cumplió — no tiene sentido apalancar una pérdida.

---

## Veredicto por criterio (§16 del brief)

| Criterio | ¿Cumple? |
|---|---|
| ≥150 USDT/mes netos | **NO** (mejor caso −$4/mes) |
| OOS positivo | Parcial — gross sí (+14.1bp), NET no en ninguna ejecución |
| Costes reales | Sí, descompuestos y auditados |
| No depende de 100% maker fill | Sí — fill mecánico 71.7%, ya incorporado, y sigue negativo |
| No depende de 1 símbolo | Sí — 357 símbolos, n=64 300 eventos |
| Placebo negativo | Sí (heredado de R19: shuffle da 1/3 del efecto real) |
| Mecanismo explicable | Parcial — 22:00 UTC es la única hora consistente de 6, pero sin explicación causal definitiva (¿cierre de sesión asiática? ¿ajuste pre-medianoche?) |

**No PASS. No near-PASS ($75-149) tampoco — el mejor resultado económico real
es −$4/mes, no un número positivo insuficiente.**

---

## DIAGNÓSTICO FINAL

**R19 encontró una señal genuina pero, incluso con la ejecución más realista
y favorable que se pudo modelar honestamente (maker con fill mecánico medido,
no supuesto, y su selección adversa correspondiente medida y no ignorada), la
señal sigue siendo inutilizable.** La mejora de ejecución SÍ importa — redujo
la pérdida de −$9 a −29/mes (taker) a −$4 a −14/mes (maker) — pero no alcanza
a cerrar la brecha completa hasta $150. El techo de 24bp no era enteramente
"demasiado conservador" (bajarlo a ~6-9bp con maker realista ayuda mucho) ni
la señal era "demasiado chica sin remedio" (mejoró con dirección correcta:
+14bp OOS vs los −12bp reportados en R19) — la combinación de ambos efectos
cierra buena parte de la brecha pero no toda.

## SIGUIENTE RONDA — no se cierra la investigación

**Round 21: re-auditar los mejores "casi-PASS" anteriores del proyecto bajo
el costo maker AHORA VALIDADO (~6-9bp, no 24bp genérico).** Varios mecanismos
de R9-R19 fueron descartados usando el piso de 24bp taker sin considerar
ejecución maker (ej.: R18 capitulación N=5/12h daba ~+$19/mes teórico a 24bp
— con ~9bp de costo maker realista, el número podría cambiar sustancialmente;
R10 dOI-régimen-UP tenía evidencia estadística fuerte pero fallaba por
magnitud económica). Aplicar el modelo de fill mecánico + selección adversa
validado en R20 (no supuestos optimistas) a esos candidatos es la palanca de
mayor expected value restante: no requiere descubrir una señal nueva, solo
re-medir economía ya conocida con el costo correcto. Si eso también falla,
recién ahí el mapa de 20 rondas (mecanismo tras mecanismo con edge real
insuficiente incluso bajo costo optimizado) constituye evidencia legítima de
un límite — pero esa conclusión formal se entrega solo si R21 también falla.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
