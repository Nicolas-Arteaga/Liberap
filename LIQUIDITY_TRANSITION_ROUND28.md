# ROUND 28 — LIQUIDITY TRANSITION: ÚLTIMO ATAQUE AL HILO 22:00/ILIQUIDEZ

## Veredicto: **FAILED — se cierra definitivamente el hilo 22:00-UTC/iliquidez**

Seis rondas independientes (R19, R20, R21, R26, R27, R28) atacaron esta
familia desde ángulos distintos (hora fija, compresión previa, capitulación
+ ejecución, diagnóstico estructural, estado de iliquidez, y ahora
transición de iliquidez). Ninguna produjo una estrategia económica
sobreviviente. Se cierra sin rescates.

---

## Hipótesis exacta

Transición de liquidez: qué ocurre inmediatamente DESPUÉS de que un
símbolo sale de un régimen de iliquidez sostenida (no el estado estático,
lección explícita de R27). Predeclaradas 3 variantes, económicamente
distintas, antes de mirar resultados:

- **D — Salida simple**: `vol_pct` causal ≤10% durante ≥4 barras seguidas
  (≥1h sostenido), luego una barra donde `vol_pct` vuelve a subir por
  encima de 10%.
- **E — Salida + movimiento extremo**: igual que D, pero la barra de
  salida tiene además `|ret1_pct|` extremo (≥95% o ≤5%).
- **F — Salida + recuperación fuerte**: igual que D, pero el volumen no
  solo sale del decil bajo — salta directo a un decil alto (`vol_pct`≥90%
  en la misma barra), una aceleración brusca, no una vuelta gradual.

Dirección SIEMPRE decidida en TRAIN (long/short), nunca asumida, para
cada una de las 6 horizontes predeclarados (15m/1h/4h/8h/24h/48h).

## Datos utilizados

Universo ancho (357 símbolos), `klines_clean` 15m, `vol_pct`/`ret1_pct`
causales (`build_feats`, ROLL=2880≈30 días). TRAIN≤2026-01-08,
VAL≤2026-04-29, OOS>2026-04-29 (mismo corte de todas las rondas
anteriores).

## Resultados TRAIN/VAL/OOS

**D (salida simple) — 29,501 eventos: sin señal en NINGÚN horizonte.**
Ninguna dirección alcanza CI que excluya 0 en TRAIN, de 15m a 48h. El
evento más común de los tres, y el más limpiamente nulo.

**E (salida + movimiento extremo) — 1,140 eventos:** única señal
"positiva" fue a 15m (fade del movimiento de salida, TRAIN net=−8.31bp,
gross=15.69bp, ci_excl0=True) — pero **VAL no significativo, OOS no
significativo, y el placebo temporal SÍ es significativo** (gross=4.81bp,
ci_excl0=True) — exactamente el patrón de contaminación por drift que ya
mató hipótesis en R24: la señal de 15m no sobrevive el control temporal
más básico. A 4h/24h/48h aparecen magnitudes grandes en TRAIN pero ninguna
alcanza CI-excl-0 con signo consistente elegible.

**F (salida + recuperación fuerte) — solo 268 eventos, insuficiente
desde el inicio:** a 24h y 48h el filtro TRAIN "aprueba" con CI que
excluye 0, pero con **n=44 en TRAIN y un intervalo de confianza
absurdamente ancho** (24h: [2.59bp, 448.53bp] — un rango de casi 450
puntos básicos, la firma clásica de significancia espuria por muestra
minúscula). **OOS es plano o negativo y NUNCA significativo** (24h OOS:
gross=0.05bp, n=205, ci=[-52.81, 58.58]; 48h OOS: gross=−29.43bp,
negativo). El placebo temporal a 24h incluso supera a la señal real
(43.01bp vs gross real 0.05bp en OOS). No hay ninguna base para tomar
esto en serio — es ruido de muestra chica, no una estrategia.

## Controles

No se llegó a necesitar el paquete completo de controles (BTC/majors/
volatilidad/momentum) porque **ninguna de las 3 formulaciones sobrevivió
siquiera TRAIN→VAL→OOS→placebo**, el primer filtro. Aplicar controles
adicionales a una señal que ya murió en el filtro básico habría sido
gastar cómputo sin valor — coherente con la disciplina de "discovery vs
validación" establecida desde R23.

## Estrategia económica

**Ninguna.** No se construyó sim económica con `portfolio_engine.py`
porque ninguna de las 3 transiciones produjo una señal que mereciera
pasar a esa etapa — hacerlo habría sido simular una estrategia sin
mecanismo, exactamente lo que el proyecto decidió dejar de hacer desde
R22.5/R23.

## PnL mensual con 450 USDT

$0 — no aplica, no se construyó ninguna estrategia.

---

## Veredicto final: FAILED

Ninguna de las 3 formulaciones cumple ni el primer criterio del Paso 7
del brief (evidencia causal en TRAIN que sobreviva a VAL/OOS/placebo). D
no tiene señal. E tiene señal contaminada por drift (mismo patrón de R24).
F tiene significancia espuria de muestra chica que colapsa por completo
en OOS.

### Cierre definitivo del hilo 22:00-UTC / iliquidez

Seis intentos independientes (R19 hora fija, R20 ejecución realista sobre
esa hora, R21 capitulación+ejecución, R26 diagnóstico estructural, R27
estado de iliquidez, R28 transición de iliquidez) — ninguno produjo una
estrategia con PnL neto positivo sostenible. **No se abre un R29 sobre
otra variante de liquidez.** El propio proyecto ya extrajo el valor
disponible de esta familia: un mapa claro de dónde NO hay alpha
explotable en microestructura horaria/de liquidez con este dataset.

---

## Próxima familia — completamente distinta (R29)

Por prioridad del propio brief, la más prometedora y menos explorada:

**Secuencias OI + precio + volumen, DISTINTAS de capitulación (ya cerrada
en R18-R23).** No se ha probado formalmente ninguna secuencia donde el OI
sea el disparador en vez del precio — por ejemplo: expansión/contracción
anormal de Open Interest (no de precio) seguida de reacción de precio, o
una secuencia de 3 pasos (cambio de OI → confirmación de volumen →
resultado de precio) en vez de la secuencia único-evento que usó
capitulación. Cobertura de datos: `oi_metrics` cubre 63 símbolos (18% del
universo ancho, ya documentado en R23) — suficiente para un intento serio,
aunque con universo más chico que las 357 de OHLCV puro. Alternativa si
esto no rinde: comportamiento relativo entre altcoins con un framing
explícitamente NO beta-hedge (ya cerrado en R13) — por ejemplo,
divergencia de OI entre pares correlacionados del mismo sector, en vez de
divergencia de precio/beta.
