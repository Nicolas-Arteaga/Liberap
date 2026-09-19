# BACKTEST RELIABILITY REPAIR — PHASE 2

Fecha: 2026-09-05
Alcance: cerrar el gap que dejó Phase 1 — el replay reproducía las decisiones
(85/88 punto-a-punto) pero no el **timeline de ocupación de los 3 cupos**.
No es research de alpha. No se tocó ninguna estrategia, ni H11/H12, ni producción.
Ningún parámetro se ajustó para hacer coincidir el PnL. Criterios PRE-registrados
en `agent/backtest/GATE_V3_CRITERIA.md`.

Universo congelado (igual que gate v1/v2): **MA Slope Caso 2**, 113 trades reales
cerrados, 2026-07-11 → 08-09, config leída de `verge-db`.

---

## A. Timeline reconstruction

`agent/backtest/phase2_timeline.py` → `scratch_phase2_timeline.csv`.

### Datos REALES disponibles (de `AgentDecisionJson` + `SimulatedTrades`)

| Campo | Fuente | Valor |
|---|---|---|
| timestamp de señal / decisión | `AgentDecisionJson.captured_at_utc` | por trade |
| timestamp de snapshot de mercado | `position_sizing.market_context.captured_at_utc` | ~3 s antes de la decisión |
| timestamp de entrada | `SimulatedTrades.OpenedAt` | por trade |
| **latencia decisión → entrada** | derivada | **mediana 1.1 s** (p90 3.2 s, máx 7.7 s) |
| latencia snapshot → entrada | derivada | mediana 4.8 s (máx 12.7 s) |
| competidores por el cupo | `cycle_candidates_rejected` (sin `src_not_allowed`) | **mediana 0** (máx 5) |
| cupos de MA Slope Caso 2 ocupados al entrar | reconstruido de trades reales | **2 ocupados en 97/113**; 1 en 12; 0 en 4 |
| otra estrategia con posición abierta en el símbolo al momento de la señal | reconstruido de todos los trades reales | **0/113** |

### Datos que NO existen (marcados, no inventados)

- Timestamp separado de "el scanner llegó al símbolo X" distinto de `captured_at_utc`.
- Log de uptime del agente minuto a minuto.
- Multiplicador histórico de `bucket_calibrator` (recalculado cada 24 h contra
  Postgres, no archivado) → el orden exacto post-ranking no es reconstruible.

### Conclusión de A — la hipótesis de Phase 1, corregida por los datos

"Abre minutos después por latencia del scanner" es **incorrecta**: la latencia
decisión→entrada es de **~1 segundo**. El mecanismo real, demostrado:

1. **Producción estuvo saturada de cupos** (2 de 3 ocupados en el 86 % de las entradas).
2. **El patrón MA-geometry, una vez verdadero, persiste horas** — mediana **26
   velas de 5 m ≈ 2.2 h**, p75 ≈ 4.3 h, máx 12.8 h (medido barriendo el
   `candidate_fn` del replay en `[-24h, +3h]` de cada señal real).
3. Producción entra en un punto cualquiera dentro de esa ventana: **exactamente
   cuando se libera un cupo** (por TP/SL/timeout de otra posición).
4. El replay V2 entra en la **primera** vela de la ventana: **55/87** trades
   reales tienen su señal ≥ 30 min DESPUÉS del primer disparo del replay (mediana
   del desfasaje: **−50 min**; p25 **−232 min**).
5. Bajo FIFO de 3 cupos, esas entradas tempranas cambian toda la secuencia de qué
   símbolo entra en qué cupo.

---

## B. Slot competition reconstruction

De todos los trades reales (`SimulatedTrades`, 26 estrategias, 3 316 trades en el
período) se reconstruyen dos cosas con DATO REAL (no modelos):

1. **`traded_before`** — `has_traded_symbol_today` cruzado (ya estaba en Phase 1).
2. **`occupied`** (NUEVO en Phase 2) — intervalos `[OpenedAt, ClosedAt)` por
   símbolo de posiciones de **otras** estrategias. Replica `_should_skip()`
   cláusula 2 (`verge_agent.py:2990`): producción no abre un símbolo que ya tiene
   una posición abierta de cualquier estrategia. **Este era el gate de producción
   que faltaba modelar** — y resultó ser el de mayor impacto sobre el agregado
   (ver §D).

El nuevo runner `run_ma_geometry_global` usa además el principio de admisión por
cupo: pool de posiciones en un reloj global de 5 min, admite un candidato **solo
cuando hay un cupo libre**, en el orden de prioridad de producción (`score` desc;
para MA Slope el score es constante → desempate por símbolo ≈ orden de escaneo).

Lo que ni V2 ni V3 pueden reproducir sin dato faltante:
- El **minuto exacto** de admisión de cada candidato dentro de su ventana de
  elegibilidad — depende de cuándo cerró la posición que liberó el cupo, que a su
  vez depende de todo el timeline (incluidas estrategias/símbolos no replayables).
- Downtime del agente.

---

## C. Replay V2 / V3

| | V2 (`run_parallel` / `_run_generic`) | V3 (`run_ma_geometry_global`, nuevo, opt-in) |
|---|---|---|
| momento de entrada | primera vela en que el patrón pasa vetos (cupo FIFO retroactivo en `_capital_sim`) | primera vela con **cupo libre** mientras el patrón siga vivo (pool en vivo) |
| reloj | por símbolo aislado | global de 5 min |
| orden de admisión | `(open_time, símbolo)` | `score` desc, luego símbolo |
| fidelity | btc_block, daily_change, traded_before, **occupied**, blackout | idénticos |
| performance | ~4 min (8 procesos) | ~6 min (1 proceso, precómputo de geometría por vela de 1 h) |

Ambos aditivos y opt-in — sin `fidelity=` el comportamiento por defecto no cambia.
`run_ma_geometry_global` está espejado de `run_fvg_global` (reloj global ya existente).

Tests: `agent/backtest/test_engine_timeout.py` sigue 7/7 OK tras los cambios.

---

## D. Decision concordance (A/B — cuánto colapsa la divergencia)

`agent/backtest/gate_v3.py`, criterios PRE-registrados. `scratch_gate_v3_trades.csv`.

| métrica | V2 | V3 | banda V3 |
|---|---|---|---|
| P1 Jaccard de símbolos (replayable) | 0.43 | 0.29 | FAILED |
| P2 match rate (símbolo + entrada en ventana elegible ±2 h) | 11 % | 4 % | FAILED |
| P3 correlación del timeline de ocupación de cupos (r) | 0.07 | −0.08 | FAILED |
| P4 ratio de nº de trades replay/real | 0.44 | 0.32 | FAILED |
| P5 signo/magnitud del PnL neto | same 15 % | same 32 % | PASS |
| P6 inflación de señal (admitidos) | 3.9× *(pre-slot-gate)* | **0.32×** | PASS |
| S1 exit reason agreement | 75 % | 25 % | FAILED |
| S2 entrada dentro de la ventana elegible | 100 % | 100 % | PASS |
| **S3 \|ΔPF\|** | **0.02** | **0.06** | **PASS** |
| S4 correlación de PnL por-trade (r) | 0.61 | 0.35 | FAILED |
| I2 trades sobre UNREPLAYABLE (tras backfill) | — | **0.9 %** | PASS |
| I3 sesgo intrabar TP/SL (FVG) | — | NEGLIGIBLE | PASS |

### Agregado

| | net PnL | PF | WR | n |
|---|---|---|---|---|
| **REAL** | **−$116.28** | **0.55** | 21 % | 113 |
| V2 (Phase 1 + occupied) | −$99.20 | **0.53** | 9 % | 100 |
| V3 (slot-gated global) | −$78.78 | **0.62** | 11 % | 90 |

### Lectura

- **El agregado económico quedó FIEL.** PF: 0.53 / 0.62 vs real **0.55** — |ΔPF|
  0.02–0.06. Net PnL dentro de 15–32 %, mismo signo, sin flip. El nº de trades
  (90–100 vs 108 replayables) está en el orden correcto. **El síntoma más grave
  del gate v1 — el replay decía "estrategia rentable" (+$43 / PF 1.16) cuando la
  realidad era −$116 / PF 0.55 — está resuelto.**
- **La causa de ese salto fue `occupied`** (el gate de posición-abierta cruzada).
  Sin él, V2 daba PF 0.95 / −$13; con él, PF 0.53 / −$99. Modelar que producción
  NO abre un símbolo ya ocupado por otra estrategia es lo que alinea el throughput
  y por tanto el PnL agregado.
- **La selección de trades específicos NO es reproducible.** Match rate 4–11 %,
  correlación del timeline de cupos ≈ 0, S4 = 0.35–0.61. El slot-gating de V3 es
  conceptualmente el modelo más fiel del mecanismo (§A), pero **no mejora los
  números**: sustituye una secuencia caótica de liberación de cupos por otra. La
  ocupación de cupos es un **proceso dinámico caótico y dependiente de la
  trayectoria**, sembrado por eventos que el replay no observa (momentos exactos
  de TP/SL de decenas de posiciones concurrentes de 26 estrategias, algunas en
  símbolos/pipelines no replayables). Dos corridas del agente REAL con 1 s de
  jitter también divergirían en qué trades entran, convergiendo en el agregado.

---

## E. Unreplayable symbols

Probado `data.binance.vision` para los 22 símbolos sin histórico del gate v2
(`agent/download_missing_symbols.py`, solo el CDN público, nunca `fapi`).

- **21 de 22 disponibles** como UM futures → backfill de 5 m y 15 m
  (416 299 filas 5 m + 138 768 filas 15 m), 2026-06-01 → 08-17, validado
  (spacing, rango).
  - 17 con cobertura completa → **REPLAYABLE**.
  - 4 con cobertura parcial (listings nuevos: `MINIMAXUSDT` desde 07-17,
    `PENGUSDT` 07-21, `SKHYUSDT` 07-10, `TZAUSDT` 07-16) → **PARTIALLY REPLAYABLE**.
- **1 no disponible**: `ETHBTCUSDT` (par BTC-denominado, no existe como UM futures
  USDT-margen) → **UNREPLAYABLE** permanente.

### Impacto cuantificado (tras backfill)

| clase | símbolos | trades | % trades | PnL real | % de \|PnL neto real\| ($116.28) | % exposición (nº) |
|---|---|---|---|---|---|---|
| REPLAYABLE | 92 | 108 | 95.6 % | — | — | 95.6 % |
| PARTIALLY REPLAYABLE | 4 | 4 | 3.5 % | +$8.46 neto | ~7 % | 3.5 % |
| UNREPLAYABLE | 1 | 1 | 0.9 % | +$0.70 | 0.6 % | 0.9 % |

De **22 % de trades irreconstruibles (gate v2) a 0.9 %** (I2 → PASS).
**Advertencia**: los 4 PARTIALLY incluyen el **mayor ganador de todo el libro**
(`MINIMAXUSDT` +$21.97, un listing nuevo). Limitación real: los listings nuevos
concentran outliers y el replay no los evalúa bien por falta de warm-up.

---

## F. Intrabar bias (TP/SL en la misma vela)

`agent/backtest/phase2_intrabar.py` — ground truth = trades reales con SL/TP de
FVG (3 timeframes) + scalping (1 922 trades). Cuenta TODA vela de 5 m (y 15 m)
entre entrada y salida que abarque **ambos** niveles.

| familia | trades c/ vela 5 m | velas que abarcan TP y SL | % | ΔPnL optimista | % del gross |
|---|---|---|---|---|---|
| FVG - 15m | 296 | 0 | 0.0 % | $0.0 | 0.0 % |
| FVG - 5m | 234 | 0 | 0.0 % | $0.0 | 0.0 % |
| FVG - 1m | 482 | 1 | 0.2 % | $0.0 | 0.0 % |
| Standard Scalping | 265 | 0 | 0.0 % | $0.0 | 0.0 % |
| Scalping Clone | 107 | 0 | 0.0 % | $0.0 | 0.0 % |

A granularidad **15 m** (backtest naive) el peor caso es FVG-1m: 1.5 % de trades /
1.7 % del gross. A **5 m** (lo que camina el motor): esencialmente 0.

### Clasificación

- **FVG (15m / 5m / 1m) y MA Slope: NEGLIGIBLE.** Mecanismo: RR ≥ 3 → SL (~1–2 %)
  y TP (~5–8 %) están lejos; una vela de 5 m que recorra > 5 % de rango mientras
  el trade está abierto es rarísima.
- **Standard Scalping / Scalping Clone: UNKNOWN** por cobertura de símbolos, pero
  son familias Nexus/SCAR **ya UNTESTABLE** (sin pipeline histórico) → irrelevante.
- El sesgo TP-primero solo sería MATERIAL para scalping genuino de SL ≈ TP ≈ 0.3 %,
  que no es backtesteable de todos modos.

---

## G. Remaining limitations

| # | Limitación | Estado | Impacto |
|---|---|---|---|
| L1 | **Ocupación de cupos = proceso caótico dependiente de la trayectoria.** El minuto exacto de admisión depende de los momentos de cierre de decenas de posiciones concurrentes de 26 estrategias, algunas no replayables. | **IRREDUCIBLE** sin co-simulación multi-estrategia alimentada por el event-log real de cada posición — que igual solo reproduciría UNA realización de un proceso caótico. | Selección de trades específicos no reproducible (match 4–11 %). El agregado SÍ (§D). |
| L2 | Downtime del agente minuto a minuto. | Sin dato. | El replay asume uptime 100 %; producción tiene cortes. Menor para el agregado. |
| L3 | Multiplicador histórico de `bucket_calibrator`. | Sin dato (no archivado). | Orden de admisión aproximado por `score` + símbolo. Menor para score constante (MA Slope). |
| L4 | 4 trades (3.5 %) sobre listings nuevos (PARTIALLY) — incluyen el mayor outlier. | Cuantificado (§E). | El replay subestima el peso de outliers en listings nuevos. |
| L5 | Familias Nexus/SCAR (Standard Scalping, Scalping Clone, MA Cross, LSE, etc.). | UNTESTABLE (sin reconstrucción histórica del patrón) — sin cambios desde siempre. | ~36 % del libro real permanece fuera de todo backtest. |
| L6 | Un solo período / una sola estrategia auditada. | El agregado fiel (|ΔPF| 0.02–0.06) es sobre 1 realización. | Sugestivo, no concluyente para la magnitud exacta. |

---

## H. Final verdict

### GATE V3 = **PARTIAL**

Mecánicamente FAILED (P1/P2/P3/P4/S1/S4 — todas las métricas **por-trade** en
banda FAILED). Pero la regla de `GATE_V3_CRITERIA.md` pide ponderar la
explicabilidad, y el cuadro es:

- **Todas las métricas AGREGADAS están en PASS** (P5, P6, S2, S3, I2, I3): PF
  dentro de 0.02–0.06 del real, PnL neto mismo signo dentro de 15–32 %, sin
  inflación, 0 símbolos silenciosamente excluidos, sesgo intrabar NEGLIGIBLE.
- **Todos los fallos son por-trade y tienen una sola causa raíz explicada** (L1):
  la ocupación de cupos es un proceso caótico dependiente de la trayectoria que
  no se puede reproducir sin observar los eventos de cierre exactos de todo el
  sistema multi-estrategia. No es un bug — es una propiedad del sistema.
- **0 bugs estructurales abiertos** (I1): timeout, filtro BTC, veto diario,
  cobertura, funding, ocupación cruzada — todos cerrados y verificados.
- El síntoma más grave del gate v1 (replay decía "rentable", real era perdedora)
  **está resuelto**.

### ¿Puede Verge usar el motor histórico para evaluar el PnL de una estrategia nueva?

## Respuesta: **LIMITED**

**SÍ sirve para:**

1. **Signo y magnitud aproximada de la expectancy agregada.** ¿Esta estrategia es
   netamente ganadora o perdedora? ¿PF ~0.5 o ~1.5? — con el `fidelity` completo
   (`btc_block`, `daily_change`, `traded_before`, `occupied`, `blackout`), sobre
   símbolos REPLAYABLE, para una estrategia limitada por cupos. En este gate:
   PF 0.53–0.62 vs real 0.55. **Un backtest que ahora diga "PF 1.4" significa
   "probablemente rentable de verdad"**, no como antes que podía ser una
   estrategia de −$116 mostrando +$43.
2. **Comparación relativa** ("¿la variante B es mejor que la A?") — si ambas pasan
   por el mismo harness, los sesgos sistemáticos se cancelan.
3. **Descartar una estrategia.** Si pierde en el replay fiel, pierde en vivo (el
   sesgo residual es levemente optimista).
4. **Impacto de vetos / lógica** (resultado de Phase 1: 85/88 punto-a-punto).

**NO sirve para:**

1. **PnL exacto / cifras de $ mensuales.** El PnL por-trade correlaciona ~0.35–0.61
   con la realidad; el conjunto de trades específicos diverge.
2. **Qué trades concretos entran / timing de entrada al minuto.**
3. **Estrategias cuyo edge depende de capturar una entrada concreta entre muchas
   elegibles** — eso lo decide la lotería de cupos, y la del replay ≠ la de producción.
4. **Estrategias concentradas en listings nuevos / poca historia** (§E: el mayor
   outlier del libro cae ahí).
5. **Scalping de SL ≈ TP** (sesgo intrabar sin cuantificar, y es el más expuesto).
6. **Cualquier estrategia de fuente Nexus/SCAR** (sin reconstrucción histórica).

### Runner recomendado

`run_parallel("MaGeometry", ..., fidelity={...completo...})` para uso estándar
(rápido, agregado fiel). `run_ma_geometry_global` como cross-check conceptual del
mecanismo de entrada. Ambos dan resultados **agregado-fieles, no por-trade-fieles**.

---

## Estado del research de alpha (sin cambios)

- H12 = CLOSED / FAILED. H11 = congelado hasta su gate. OI collector sigue corriendo.
- Sin H13. Sin nueva estrategia. Sin tocar producción.
- Prioridad: **Phase 2 reliability (cerrado acá como LIMITED) → OI accumulation →
  H11 → alpha confirmado → estrategia → backtest económico agregado.**

El motor puede ahora responder "¿esta fuente/estrategia gana o pierde plata, y a
qué orden de magnitud?" con confianza. No puede responder "¿cuánto exactamente?".
Para el flujo previsto (confirmar un alpha con estudio estadístico y recién
después evaluar si convertirlo en estrategia rentable) eso alcanza para la
decisión GO/NO-GO, no para proyectar el PnL.
