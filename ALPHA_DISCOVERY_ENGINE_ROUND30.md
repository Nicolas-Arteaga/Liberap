# ROUND 30 — ALPHA DISCOVERY ENGINE (combinaciones estado+evento)

## ¿ENCONTRAMOS UNA CANDIDATA ECONÓMICA? **No.**

Se construyó y corrió un motor de discovery combinatorio (no una hipótesis
aislada) sobre 8 combinaciones predeclaradas de estado+evento, cruzando
volatilidad/volumen/precio (357 símbolos) y volatilidad/volumen/OI (43
símbolos feature-complete). **Ninguna de las 8 combinaciones se acerca al
costo de ejecución (24bp RT), y las que sobreviven el filtro de
confirmación en VAL muestran ganancia bruta OOS de entre −44bp y +3bp —
lejos, en todos los casos, de ser una estrategia.**

---

## Fase 1 — Inventario de features (auditado, no repetido de rondas previas)

| Feature | Cobertura | Estado |
|---|---|---|
| Precio (ret1_pct causal) | 357 símbolos, 14.5 meses | Disponible, usado |
| Volumen (vol_pct causal) | 357 símbolos, 14.5 meses | Disponible, usado |
| Volatilidad realizada (rv_pct causal) | 357 símbolos, 14.5 meses | Disponible, usado |
| Open Interest (dOI_pct, d2OI_pct causal) | **43 símbolos** feature-complete (de 63 con algo de OI) | Disponible, usado |
| Funding | 63 símbolos, cada 8h | Disponible pero no incorporado esta ronda (cobertura más rala que OI sin ganancia clara sobre lo ya cerrado en R9-R17) |
| OFI | — | **FAILED en H12** (AUC 0.46) — no se reintroduce |
| Liquidaciones | 48.5 horas reales (R26) | Insuficiente, no se usa |

## Fase 2/3 — 8 combinaciones predeclaradas (2 y 3 features, nunca repetidas de rondas previas)

| # | Combinación | Universo | Interpretación económica |
|---|---|---|---|
| 1 | Volatilidad alta + volumen contrayéndose | 357 | Iliquidez ocurriendo DENTRO de un régimen ya volátil |
| 2 | Volatilidad alta + spike de volumen simultáneo | 357 | Confirmación de participación durante volatilidad (distinto del "doble shock" de R24, que exigía 2 barras consecutivas sin volumen) |
| 3 | Spike de volumen en régimen tranquilo | 357 | Actividad anómala aislada en un mercado calmo |
| 4 | Movimiento extremo que rompe un régimen tranquilo | 357 | Ruptura de calma (contexto, no solo el movimiento aislado) |
| 5 | Volatilidad alta + expansión de OI | 43 | Apalancamiento nuevo entrando durante un shock |
| 6 | Volatilidad baja + aceleración de OI | 43 | Posicionamiento silencioso antes de una expansión (líder, no seguidor) |
| 7 | Volumen contrayendo + expansión de OI | 43 | Acumulación silenciosa (sube el OI sin perseguir el precio) |
| 9 | Volatilidad alta + OI expandiendo + volumen extremo (3-way) | 43 | Confirmación triple — penalizado por complejidad, probado solo por completitud |

## Fase 4 — Resultados (TRAIN→VAL confirma signo→OOS)

Se aplicó la disciplina reforzada tras el caso E de R29: **VAL debe
confirmar el mismo signo que TRAIN antes de siquiera mirar OOS** — si no
confirma, se descarta sin generar el número de OOS.

| Combinación | Horizonte | OOS gross | OOS net (−24bp) | Placebo net | CI excl 0 |
|---|---|--:|--:|--:|---|
| 2-RVhigh&Vspike | 1h | +2.83bp | **−21.17bp** | −26.38bp | Sí |
| 1-RVhigh&Vcontract | 1h | +0.57bp | −23.43bp | −23.73bp | No |
| 4-Pext&RVlow | 1h | −2.21bp | −26.21bp | −23.50bp | Sí |
| 5-RVhigh&OIexp | 1h/24h | −6.16bp / −23.46bp | −30.16bp / −47.46bp | −22.33bp / −24.29bp | No |
| 9-3way | 1h/24h | −11.78bp / −43.59bp | −35.78bp / −67.59bp | −23.18bp / −39.97bp | No |
| 3-Vspike&RVlow | 8h | −13.57bp | −37.57bp | −31.54bp | Sí |
| 6-RVlow&OIaccel | — | insuficiente para pasar el filtro VAL en ningún horizonte | | | |
| 7-Vcontract&OIexp | — | insuficiente para pasar el filtro VAL en ningún horizonte | | | |

**Ninguna combinación se acerca al costo de 24bp**, y en la mayoría de
los casos donde el placebo temporal también es calculable, tiene una
magnitud SIMILAR o MAYOR que la señal real (ej. combo 4: real −2.21bp vs
placebo −23.5bp — comparables, sin discriminar nada; combo 9 a 24h: real
−43.59bp vs placebo −39.97bp — básicamente indistinguibles).

## Fase 5 — Distribución completa, no solo la media (el punto central de esta ronda)

Para cada combinación superviviente del filtro VAL se calculó la
distribución completa (no solo el promedio) — exactamente lo que pedía
esta ronda para detectar una asimetría explotable que la media
incondicional pudiera esconder:

| Combinación | Media | Mediana | P25 | P75 | Win rate | Skew |
|---|--:|--:|--:|--:|--:|--:|
| 1-RVhigh&Vcontract | +2.2bp | 0.0bp | −41.3 | +40.7 | 0.48 | 22.6 |
| 2-RVhigh&Vspike | +3.7bp | +6.4bp | −102.9 | +116.3 | 0.51 | 3.1 |
| 3-Vspike&RVlow | +4.9bp | −14.5bp | −126.8 | +96.5 | 0.46 | 6.6 |
| 4-Pext&RVlow | −0.3bp | 0.0bp | −29.0 | +17.8 | 0.33 | 16.7 |
| 5-RVhigh&OIexp | +1.8 / +2.6bp | 0.0 / +7.5bp | amplio (hasta ±354bp) | | 0.50-0.51 | ~0-0.9 |
| 9-3way | +4.0 / +0.1bp | +4.2 / +10.3bp | amplio (hasta ±417bp) | | 0.51 | ~0.1-0.3 |

**No hay ninguna asimetría explotable.** Los win rates están todos
pegados a 0.46-0.51 (esencialmente una moneda), las medianas rondan cero,
y la dispersión (P25/P75) es enorme en términos absolutos pero
SIMÉTRICA — no hay cola favorable que un TP/SL o salida parcial pudiera
capturar de forma sistemática. El skew alto en algunas filas (16-22) es
producto de un puñado de outliers extremos, no de una estructura
recurrente — coherente con activos cripto de cola pesada en general, no
con el mecanismo específico que se está probando.

## Fase 6 — Top candidatos (ninguno califica como CANDIDATE)

Los 8 resultados de la tabla de Fase 4 son, en efecto, el "top 5+"
pedido — no hay más de 8 combinaciones que llegaran siquiera a producir
un número de OOS. Ninguno alcanza el estándar mínimo de DISCOVERY→
CANDIDATE (gross OOS que se acerque al costo, con CI que excluya 0 Y
supere claramente al placebo). Clasificación final:

- **DISCOVERY**: las 8 combinaciones fueron exploradas con disciplina
  (TRAIN→VAL→OOS, placebo, distribución completa).
- **CANDIDATE**: 0.
- **VALIDATED / ECONOMIC PASS**: no aplica — no hubo candidato que
  llevar a `portfolio_engine.py`.

## Fase 7 — Backtest económico

**No se ejecutó.** Llevar cualquiera de estas 8 combinaciones a
`portfolio_engine.py` sería simular una estrategia sin mecanismo
identificable — el mismo error que el proyecto decidió dejar de cometer
desde R22.5/R23. Ninguna de las 8 superó siquiera el filtro de
DISCOVERY, así que no había nada que llevar a dinero.

## Fase 9 — Portfolio de señales combinadas

No aplica: se requieren al menos 2-3 señales individualmente razonables
(aunque débiles) para evaluar si complementan entre sí — acá ninguna de
las 8 llegó a ser "razonable" siquiera de forma aislada.

---

## Veredicto

**FAILED, en las 8 ramas, con evidencia de por qué el enfoque combinatorio
tampoco encontró nada esta vez:** no es que faltara explorar
interacciones — se probaron 8 combinaciones genuinamente nuevas de estado
+evento sobre los tres pilares de datos disponibles (precio, volumen,
volatilidad, OI) sin repetir nada de las 29 rondas anteriores, con
disciplina de confirmación en VAL antes de mirar OOS, y **ninguna muestra
ni una media económicamente relevante ni una asimetría de distribución
explotable.** Las combinaciones con OI (5, 6, 7, 9) tienen además el
límite adicional de la cobertura de 43 símbolos, que ya se documentó como
insuficiente para escalar a una estrategia grande aunque hubiera señal.

### Lo que esto sugiere sobre el estado real de la investigación

Después de 30 rondas cubriendo sistemáticamente: eventos extremos de
precio (solos y en secuencia), volumen, volatilidad, Open Interest (nivel,
cambio, aceleración), liquidez/iliquidez (estado y transición), y ahora
8 combinaciones cruzadas de todo lo anterior — **el espacio de
features causales disponibles en este dataset (OHLCV + volumen + OI de
Binance USDⓈ-M Futures, universo superviviente de 357/43 símbolos) parece
estar genuinamente agotado para el tipo de señal direccional de corto
plazo que se viene buscando.** Esto no significa que no exista alpha en
el mercado — significa que, con los datos y el universo actualmente
disponibles en este proyecto, la búsqueda direccional de eventos-en-OHLCV
+volumen+OI no la encuentra.

## Siguiente paso — honesto, no otra variante

Dos caminos reales quedan abiertos, ninguno es "otra combinación de las
mismas 4 features":

1. **Datos genuinamente nuevos**: funding como feature de INTERACCIÓN
   (no como carry, ya cerrado) combinado con OI/precio — nunca probado en
   combinación (solo aislado en H16, FAILED). Requiere unir funding_hist
   (63 símbolos) con las combinaciones de esta ronda — universo aún más
   chico, pero es la única pieza de datos disponible que no se cruzó
   todavía con nada.
2. **Cambio de horizonte de la pregunta**: todo lo probado en 30 rondas
   fue intradía a 48h. No se ha probado nada en el rango de días-semanas
   con rebalanceo de baja frecuencia usando estas mismas features
   agregadas (ej. régimen semanal de OI/volatilidad en vez de eventos de
   15 minutos) — un espacio de frecuencia genuinamente distinto, no
   otra variante del mismo.

Si ninguno de los dos produce evidencia en R31, la conclusión honesta a
comunicar sería que el dataset actual (OHLCV+volumen+OI de Binance
Futures, universo superviviente) no contiene una segunda fuente de alpha
direccional de corto plazo distinta de la que ya opera el usuario — y que
avanzar requeriría datos estructuralmente nuevos (order book, liquidaciones
con cobertura real, on-chain) en vez de más combinaciones de lo mismo.
