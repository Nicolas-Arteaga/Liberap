# ROUND 16 — FUNDING CARRY ATTACK: ¿SE PUEDE CONVERTIR FUNDING EN PnL REAL?

**Fecha:** 2026-09-19 · Script: `agent/backtest/r16_funding_carry.py` · Sin
descargas nuevas · Universo **REAL** (intersección física funding_hist ∩
spot_klines ∩ klines_clean perp) = **43 símbolos** · Ventana 2025-12-01 →
2026-08-17 (8.5 meses — limitada por `spot_klines`, no por 2026Q3: esta vez el
período no coincide con la ventana anómala).

## RESULTADO

# FAIL

**Ninguna configuración (de 20+ probadas: N, rebalanceo, ventana trailing,
ponderación, capital, apalancamiento) produjo un solo mes positivo.** 0/9 meses
positivos en la configuración primaria, y en TODAS las variantes. El mejor caso
absoluto (capital $150, sin apalancamiento) sigue siendo **−$7.2/mes**.

- **Mejor estrategia (la menos mala):** N=3, rebalanceo 72h, trailing 7d,
  equal-weight, sin apalancamiento, capital $150.
- **PnL neto mensual:** **−$7.9/mes** (esa config específica).
- **Capital:** $150 · **Posiciones:** 3 · **Leverage:** 1x (sin apalancar).
- **Funding capturado:** +$2.3/mes bruto.
- **Fees:** −$11.3/mes.
- **Slippage:** incluido en fees (spot 4bp + perp 4bp por lado).
- **Borrow:** N/A (estructura operable no requiere pedir prestado).
- **Turnover:** 194 operaciones sobre 8.5 meses (~23/mes).
- **Max DD:** $69.3 · **Peor mes:** −$13.8 · **OOS:** ver §3, igual de negativo.
- **Período testeado:** 2025-12-01 → 2026-08-17 (8.5 meses).

---

## 1. Mecanismo y universo

**Estructura A (OPERABLE):** funding positivo → LONG SPOT + SHORT PERP,
financiado con capital propio (sin pedir prestado nada) — el short-perp cobra
el funding, el spot neutraliza la dirección.

**Estructura B (NO OPERABLE, declarado explícitamente):** funding negativo →
requeriría SHORT SPOT (vender en corto), lo que exige pedir prestado el activo.
No tenemos datos de borrow-rate ni infraestructura de margen cruzado. Se
calculó el número matemático bruto **solo como diagnóstico** (66 183
bp-equivalente sobre 17 685 settlements, sin costos) — **irrelevante y no se
reporta como estrategia**, tal como exige el brief.

**Universo:** intersección real de `funding_hist` (63) ∩ `spot_klines` (240) ∩
`klines_clean` perp (450) = **43 símbolos**. No es una reducción arbitraria: es
el conjunto donde el mecanismo (comparar spot vs perp) es físicamente
calculable con los datos que existen. Ampliar a los ~357 del universo ancho de
R15 no es posible porque `spot_klines` y `funding_hist` simplemente no cubren
esos símbolos.

---

## 2. Persistencia del funding (Fase 4 — diagnóstico central)

- Probabilidad de que el signo del funding cambie de un settlement al
  siguiente: **22.2%** (n=49 858) → el funding NO es ruido puro.
- Duración media de una racha del mismo signo: **4.4 settlements (~36 h)**,
  mediana 2.
- Correlación trailing(pasado) vs funding del **próximo** settlement: **0.82**
  a 8h, decayendo a **0.68** a 7 días. Fuerte persistencia de corto plazo.
- **El problema no es que el funding sea impredecible — es que el RANKING
  cross-sectional del top-N rota mucho más rápido que la persistencia
  individual de cada símbolo.** Con 43 candidatos de magnitud similar, el
  orden relativo cambia cada pocos settlements aunque cada símbolo
  individualmente sea persistente — y cada cambio de orden dispara una
  rotación de posición con su costo de 46 bp.

---

## 3. Sim económica — TOP 5 configuraciones (ordenadas por NET/mes, dataset completo; todas negativas)

| # | Configuración | Funding/mes | Fees/mes | **NET/mes** | Meses +/− | Max DD |
|---|---|--:|--:|--:|--:|--:|
| 1 | cap $150, lev 1x, N=3, rebal 24h | +$0.4 | −$7.6 | **−$7.2** | 0/9 | $65 |
| 2 | trail 7d, N=3, rebal 24h, cap $450, lev 3x | +$2.3 | −$11.3 | **−$7.9** | 0/9 | $69 |
| 3 | rebal 72h, N=3, trail 24h, cap $450, lev 3x | +$1.4 | −$12.4 | **−$10.9** | 0/9 | $97 |
| 4 | cap $150, lev 3x, N=3, rebal 24h | +$0.6 | −$11.4 | **−$10.8** | 0/9 | $97 |
| 5 | trail 72h, N=3, rebal 24h, cap $450, lev 3x | +$2.2 | −$19.8 | **−$17.8** | 0/9 | $159 |
| — | N=10, rebal 24h, cap $450, lev 3x (más diversificado) | +$1.6 | −$23.9 | −$21.9 | 0/9 | $199 |
| — | rebal 8h (máxima frecuencia) | +$2.3 | −$60.6 | −$58.0 | 0/9 | $523 |

**El patrón es universal y monótono:** más rebalanceo → más funding capturado
pero MUCHO más fee → siempre peor. Menos capital/leverage → menos pérdida
absoluta pero el funding capturado también cae proporcionalmente → nunca
cruza a positivo. **Fees superan al funding capturado por 5× a 20× en TODAS
las 20+ configuraciones probadas**, sin una sola excepción.

**OOS (config primaria N=5/rebal24h/trail24h/lev3x/cap450, corte OOS >
2026-06-24):** NET/mes = **−$23.6**, 0/3 meses positivos. **Slice B (excluye
2026Q3 explícitamente):** NET/mes = **−$31.8** — de hecho ligeramente PEOR sin
2026Q3 (funding/mes cae a −$6.1, es decir el conjunto de candidatos con
funding positivo era, en promedio, una porción MENOR en ese sub-período). **No
depende de 2026Q3** — es negativo de forma consistente en todos los recortes
temporales, lo cual, para un FAIL, es la confirmación más limpia posible: no es
un artefacto de ventana, es estructural.

---

## 4. Placebos / controles

| Control | Funding/mes | Fees/mes | NET/mes |
|---|--:|--:|--:|
| Real (ranking por funding) | +$1.9 | −$30.3 | −$28.2 |
| Random selection (mismo N, símbolo al azar) | +$1.3 | −$39.6 | **−$38.1** |
| Matched-vol (rankea por volatilidad, no funding) | +$0.4 | −$17.4 | −$17.7 |

El ranking por funding real **sí es mejor que el azar** (capta más funding, y
con menos turnover — fees más bajas) — hay una señal genuina en usar funding
para elegir. Pero la brecha (−$28 vs −$38) es minúscula comparada con el
tamaño del problema (~$30/mes de fees estructurales). **El placebo no reproduce
el resultado porque no hay resultado positivo que reproducir — ambos pierden.**

---

## 5. Riesgo de base (Fase 11)

El componente `price_pnl` (retorno spot menos retorno perp durante el holding,
que debería ≈0 en un book perfectamente delta-neutral) fue consistentemente
pequeño (+$0.1 a +$1.2/mes) pero **no cero** y con signo variable entre
configuraciones — confirma que delta-neutral no es riesgo cero: hay drift de
basis real, capturado explícitamente en la simulación (no asumido a 0), aunque
en este caso no fue el factor decisivo (las fees lo son, por un orden de
magnitud).

---

## DIAGNÓSTICO

**¿El funding carry es una fuente de yield explotable con 450 USDT, o los
headline funding rates son ilusorios una vez incorporamos ejecución?**

**Son ilusorios a esta escala de capital y con esta arquitectura (rotación
cross-sectional diaria/horaria sobre un universo de 43 símbolos).** El
mecanismo es real — el funding existe, tiene persistencia genuina de corto
plazo (corr 0.82 a 8h), y el ranking por funding supera al azar — pero:

1. **La operación requiere DOS patas (spot + perp) cada vez que se rota una
   posición**, duplicando el costo de transacción de cualquier otra estrategia
   testeada en el proyecto (46 bp round-trip vs ~24 bp de las estrategias
   direccionales de R9-R15).
2. **El funding individual capturable en este universo es pequeño en términos
   absolutos** ($150-450 de capital genera $0.4-2.5/mes de funding bruto,
   incluso apalancado 3x) — los números anualizados grandes de R15 (ej.
   BTWUSDT +44%/año) son reales pero corresponden a un símbolo con liquidez
   baja y pocas observaciones; agregados sobre un universo diversificado y
   realista, el funding disponible cae mucho.
3. **La persistencia del RANKING (no del funding individual) es lo que
   importa para el turnover**, y esa es corta (~36h) — fuerza rotación
   frecuente, que es exactamente lo que las fees castigan.

No es un fallo de ejecución del round: se probaron 4 frecuencias de
rebalanceo, 4 ventanas de trailing, 5 tamaños de N, 3 esquemas de ponderación,
3 niveles de capital y 2 de apalancamiento — **20+ configuraciones, todas
negativas, con el mismo patrón de fees dominando funding.**

---

## SIGUIENTE RONDA — no se cierra la investigación

**FAIL documentado con causa exacta: el mecanismo de carry es real pero el
costo de las dos patas (spot+perp) y la corta persistencia del ranking lo
hacen inviable con rotación activa.**

**Hipótesis concreta para Round 17: FUNDING CARRY DE BAJO TURNOVER
("chronic yield"), no cross-sectional activo.** En vez de rankear y rotar el
top-N cada 24-72h (lo que mató a R16), identificar ex-ante los símbolos con
funding **estructuralmente sesgado durante MESES** (no solo la última semana)
— usando la misma dispersión ya documentada en R15 (algunos símbolos con
funding promedio consistente en un signo durante miles de observaciones) — y
mantener esas posiciones con rebalanceo **mensual o trimestral**, no diario.
Esto ataca directamente la causa raíz identificada en R16 (turnover destruye
el yield) sin necesitar cambiar el mecanismo. Costo de entrada esperado: ~1-2
rotaciones en 8.5 meses por posición en vez de ~200. Si el funding
estructural persiste a esa escala de tiempo (verificarlo, no asumirlo), el
break-even de costos cambia por completo.

Si eso también falla: pasar a un mecanismo genuinamente distinto (no una
variante de carry) — el más prometedor sin probar en 16 rounds es **eventos de
listing con fecha verificada** (bloqueado en rounds anteriores solo por
calidad del dato de fecha, nunca por el mecanismo en sí — ver R7/R8), usando
fuentes públicas (anuncios de Binance) para obtener fechas reales en vez de
inferirlas del primer kline.

---

## Infraestructura

Sin cambios. Colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
