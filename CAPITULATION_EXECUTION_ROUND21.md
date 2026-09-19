# ROUND 21 — EXECUTION EDGE + RESEARCH REVIVAL

**Fecha:** 2026-09-24 · Script: `agent/backtest/r21_capitulation_exec.py` ·
Universo ancho (357 símbolos) · Re-audita capitulación (R18) con el costo
maker validado en R20 + selección de eventos por score pre-señal + selección
de slot por score en vez de FIFO.

## RESULTADO — el hallazgo más fuerte del proyecto, con una advertencia real

# PARK (no PASS)

**Mejor configuración: TAKER, capital $450, 5 posiciones, selección por
score (no FIFO) → NET/mes = $150.00, exactamente el objetivo, sobre 1054
operaciones (VAL+OOS, 8 meses).** Sobrevive fee×2, slippage×3, remover el
mejor trade, y bate por 10× a un placebo honesto (mismo mecanismo sin score).
**Pero la mitad del período OOS+VAL fue negativa** (−$16/mes en la primera
mitad, +$316/mes en la segunda) — la razón exacta por la que 20 rounds
anteriores mataron cada "casi-PASS" anterior. No se lo declara PASS sin
resolver esa pregunta.

---

## 1. Auditoría de R20 (Fase 1) — confirmada

Se reprodujo la lógica de R20 (fill mecánico, no asumido) sobre el evento de
capitulación de R18 (drop percentil≤3% + volumen percentil≥90%, SHORT =
apostar continuación). TAKER baseline @24h reconfirma R18b exactamente:
VAL gross=−0.12bp, OOS gross=+89.39bp — sin cambios respecto a lo ya
reportado.

## 2-5. Maker con fill mecánico + selección adversa como feature

**Fill mecánico observado: 83.6%** (vs 71.7% del evento horario de R20 — la
capitulación es más volátil, retrocede más fácil hacia el limit).
**MAKER (llenadas): gross=37.9bp, net=+31.9bp — POSITIVO**, aunque menor que
el gross de TAKER-todas (87.5bp) — hay selección adversa, pero mucho menos
severa que en el hallazgo horario de R20 (donde el filled-edge caía a 1/4;
acá cae a ~0.43×, y el costo maker (6bp) es tan bajo que igual queda neto
positivo).

**Selección adversa como feature — el hallazgo clave de esta fase:** los
features disponibles ANTES de colocar la orden predicen el edge post-fill
con una separación enorme y monotónica:

| Feature | Tercil bajo | Tercil alto |
|---|--:|--:|
| Volatilidad realizada (`rv`) | +2.3bp | **+107.4bp** |
| Percentil de vol. realizada (`rvp`) | −4.7bp | **+79.9bp** |
| Distancia al mínimo de 20 barras | +6.6bp | **+86.1bp** |
| Magnitud de la caída (`drop_mag`) | +13.5bp | **+82.9bp** |

**No todas las capitulaciones son iguales — las más extremas (mayor
volatilidad, caída más profunda relativa al rango reciente) tienen 30-40× más
edge que las moderadas.** Esto es información genuinamente nueva y accionable,
no un re-descubrimiento.

## 6. Selección de slot por SCORE en vez de FIFO — el segundo hallazgo clave

Cuando compiten varios candidatos por un slot libre en el mismo instante
(frecuente: la capitulación ocurre en oleadas), priorizar por
`drop_mag × volp_extra` (causal, conocido al momento de la señal) en vez de
tomar el primero cronológico:

| Config | avg_net (bp/trade) | NET/mes |
|---|--:|--:|
| TAKER FIFO | +11.5bp | $15 |
| **TAKER score-select** | **+115.9bp** | **$150** |

**10× de mejora.** Esto responde directamente la pregunta del brief: el
problema de R18b no era solo la concurrencia — era que el FIFO capturaba
oportunidades al azar entre las disponibles, cuando había información
disponible (el mismo score que predice el edge post-fill) para elegir las
mejores.

## Auditoría del candidato ($150/mes, TAKER, score-select, cap$450, slots=5)

| Test | Resultado |
|---|---|
| Base | **$150/mes**, n=1054 |
| Remove-best-trade | $120/mes (top trade = 20% del total, no catastrófico) |
| Remove-top5-trades | $71/mes (top-5 de 1054 = 47% — concentración moderada, no fatal) |
| Fee ×1.5 / ×2.0 | $135 / $119/mes — robusto |
| Slippage ×2 / ×3 | $140 / $129/mes — muy robusto |
| **Placebo (mismo TAKER/cap/slots, SIN score = FIFO)** | **$15/mes — el score aporta genuinamente, no es ruido de ranking** |

**Pero — desglose mensual (VAL+OOS, 8 meses):**

| Mes | NET |
|---|--:|
| 2026-01 | +$54 |
| 2026-02 | +$53 |
| **2026-03** | **−$75** |
| **2026-04** | **−$101** |
| 2026-05 | +$342 |
| 2026-06 | +$337 |
| 2026-07 | +$315 |
| 2026-08 | +$174 |

**1ra mitad de VAL+OOS: −$16/mes (n=509). 2da mitad: +$316/mes (n=545).**

**Esto NO es el mismo patrón que mató a R18** (una sola ventana de 6 semanas
anómala) — acá son **4 meses calendario consecutivos** (mayo-agosto), cada
uno individualmente fuerte, dentro del período OOS genuino (parámetros y
dirección congelados antes de tocar esos datos). Es una evidencia
sustancialmente más fuerte que cualquier "casi-PASS" anterior del proyecto.
**Pero** los 4 meses inmediatamente anteriores (enero-abril, incluidos en
VAL) muestran un régimen distinto (mixto/negativo), y no hay forma de saber
—sin más datos hacia adelante— si mayo-agosto es el régimen "real" que se
sostiene, o una racha dentro de un régimen más amplio y variable.

## 11. dOI-régimen-UP (R10/R11) — NO re-abierto, con motivo documentado

R11 (historia extendida a 14.5 meses) encontró que el efecto UP-régimen tuvo
**signo opuesto** entre la primera mitad (−12bp) y la segunda mitad (+54bp)
de la muestra — no-estacionariedad de régimen, no un problema de costo de
ejecución. Ningún modelo de fill/maker puede arreglar una señal cuyo signo se
invierte con el tiempo. Se mantiene cerrado; re-correrlo bajo el costo de R20
no puede cambiar esa conclusión, así que no se gastó cómputo en repetirlo.

---

## Veredicto por criterio (§15 del brief)

| Criterio | ¿Cumple? |
|---|---|
| ≥150 USDT/mes netos | Sí, exactamente $150 en el blend VAL+OOS |
| OOS positivo | Sí, y con 4 meses consecutivos individualmente positivos |
| Costes reales | Sí, taker completo (24bp), sin asumir maker |
| Robustez a fees/slippage | Sí, con margen |
| No depende de 1 símbolo | Sí — 357 símbolos, eventos distribuidos |
| No depende de 1 trade | Parcial — top-5/1054 = 47% del total, moderado no trivial |
| Placebo inferior | Sí, claramente (10×) |
| **Estabilidad temporal** | **NO — primera mitad de VAL+OOS negativa** |

**Por esta última fila, no se declara PASS.** Es el candidato con mejor
evidencia del proyecto, pero declarar victoria ignorando que la mitad del
período de validación fue negativa repetiría exactamente el error que este
proyecto ha evitado con disciplina en las 20 rounds anteriores.

# PARK

---

## SIGUIENTE RONDA — no se cierra la investigación

**Round 22, dos acciones concretas, no más variantes:**

1. **Entender económicamente por qué marzo-abril fue distinto de mayo-agosto**
   — comparar régimen de BTC, volatilidad agregada del universo, y actividad
   de listings nuevos en cada bloque. Si hay una variable de régimen
   identificable (ej. volatilidad agregada del mercado por encima de un
   umbral) que separe limpiamente los meses positivos de los negativos,
   **condicionar la estrategia a ese régimen** convierte esto de "funciona
   la mitad del tiempo por razones desconocidas" a "funciona cuando la
   condición X se cumple" — que sí sería una estrategia operable con una
   regla de encendido/apagado explícita.
2. Si no aparece una variable de régimen limpia: **PARK se mantiene como
   está** — es candidato real para combinar con una segunda estrategia
   independiente (tal como pide el brief para el caso PARK), pero no se
   despliega solo. Empezar la búsqueda de esa segunda estrategia
   independiente en paralelo, usando exactamente el mismo método que
   funcionó acá (score de selección pre-señal + selección de slot por score,
   no FIFO) sobre un mecanismo económicamente distinto (no capitulación).

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
