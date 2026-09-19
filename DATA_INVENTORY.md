# VERGE — DATA INVENTORY (FASE 1)

**Fecha:** 2026-09-06. Inventario exhaustivo de datos crudos disponibles.
Todo verificado por query directa a las bases (no de memoria).
**Nada se modificó.**

---

## 0. Fuentes físicas

| Archivo | Tamaño | Contenido |
|---|---|---|
| `agent/data/binance_vision_clean.db` | 5.6 GB | OHLCV/spot/taker/multi-exchange descargados de `data.binance.vision` (CDN estático, **sin lookahead**, limpio) |
| `agent/data/klines.db` | 2.3 GB | Cache del agente + colectores en vivo (OI, liquidaciones, OFI, whale, funding). **Riesgo de lookahead vía `updated_at`** — usar solo `open_time`/`timestamp` del evento |
| `agent/data/trades.csv` | — | Log de trades del agente (FORENSIC, PnL aproximado) |
| DB Postgres `Verge` | — | NON-CANONICAL (ver `RESEARCH_RESET_PLAN.md §2`) |
| `python-service/scar_data.db` | 52 KB | snapshots SCAR (residual, no histórico) |

---

## 1. Inventario por dataset

### binance_vision_clean.db (CANONICAL, limpio, estático)

| Tabla | Filas | Resolución | Símbolos | Período | Cobertura / gaps | Lookahead | Coste proc. |
|---|---|---|---|---|---|---|---|
| `klines_5m` | 28.3 M | 5 m | 450 | **2025-12-01 → 2026-08-17** (~8.5 m) | alta; gaps por deslistings/listings nuevos | **Ninguno** (CDN diario cerrado) | bajo (indexado) |
| `klines_clean` | 5.8 M | 15 m | 450 | idem | idem | Ninguno | bajo |
| `btc_klines_1m` | 112 k | 1 m | **1 (BTCUSDT)** | 2026-05-01 → 2026-07-13 (~78 d) | continua | Ninguno | bajo |
| `spot_klines` | 5.8 M | 15 m | 240 | 2025-12-01 → 2026-08-17 | media (solo majors tienen spot) | Ninguno (ojo: archivos SPOT en **microsegundos**) | bajo |
| `taker_flow` | 9.3 M | 15 m | 429 | 2025-12-01 → 2026-08-17 | 100% vs `klines_clean` | Ninguno | medio |
| `klines_multi_exchange` | 4.2 M | 15 m | 270 | 2025-12-01 → **2026-07-25** (corta antes) | bitget 95 sym / bybit 96 / okx 79 (okx desde 2026-05-24) | Ninguno | medio |
| `backtest_runs` | 3 | — | — | — | LEGACY | — | — |

### klines.db (cache + colectores en vivo — lookahead risk)

| Tabla | Filas | Resolución | Símbolos | Período | Cobertura / gaps | Lookahead | Coste proc. |
|---|---|---|---|---|---|---|---|
| `klines` | 12.5 M | 1m/5m/15m/1h/4h mezclados | 858 | **1h: 2024-05-22 → 2026-09-07 (~2.3 años)**; 15m: 2024-05-25→; 5m/1m: solo desde 2026-05-25; 4h: desde 2026-04-12 | irregular; `is_final` flag; huecos por reinicios del agente | **Sí** (`updated_at`); usar solo `open_time` de velas `is_final=1` | medio |
| `funding_rates` | 48.7 k (limpio) | 8 h | 496 | **2026-07-07 → 2026-09-07 (~2 meses)** | ~1 fila cada 8h; 1 fila basura (`funding_time=1`) | bajo (funding se publica al cierre del período) | bajo |
| `open_interest` | 447 k | 5 m | 188 | **2026-08-04 → 2026-09-07 (33.3 d)** | **45/188 sym ≥90%**, mediana de cobertura **0.02** (la mayoría entró tarde / esporádica). BTCUSDT y majors ~100% | bajo (`/futures/data/openInterestHist`, period cerrado) | bajo |
| `liquidations` | 9.8 k | tick (evento) | 106 | **2026-08-31 → 2026-09-07 (7 d)** | continua desde el arranque; **muy poca historia** | bajo (evento con timestamp propio) | bajo |
| `orderbook_ofi` | 2.2 M | ~1 snapshot / 8 min / sym | 499 | **2026-08-08 → 2026-09-07 (30 d)** | ~75 k filas/día; regular | **medio** (snapshot de libro en vivo; el `ofi` ya está agregado) | medio |
| `whale_events` | 10.8 k | evento | 31 (mayormente BTC) | **2026-09-04 → 2026-09-07 (3 d)** | trivial | bajo | bajo |
| `live_prices` | 413 | snapshot único | 413 | — | NO es serie temporal | — | — |

---

## 2. Clasificación por las 13 categorías pedidas

| # | Categoría | Fuente disponible | Profundidad | Calidad | ¿Explotada en H1–H12? |
|---|---|---|---|---|---|
| 1 | **Precio** | `klines_5m/clean` (8.5 m, 450) + `klines` 1h (2.3 a) | alta | alta (BV) / media (cache) | **SÍ, agotada** (grid, ML, H1, subset) |
| 2 | **Volumen** | mismo que precio + `taker_flow.volume` | alta | alta | SÍ (parte de OHLCV) |
| 3 | **Volatilidad** | derivable de precio (realized vol, ATR, Parkinson) | alta | alta | SÍ implícitamente (grid) — **NO como transición de régimen event-driven** |
| 4 | **Funding** | `funding_rates` (2 m, 496) | **baja (2 m)** | media | SÍ como filtro (AUC 0.539 → PF 0.98 OOS) — **NO como interacción con OI** |
| 5 | **Open Interest** | `open_interest` (33 d, 45 sym ≥90%) | **insuficiente (gate 70 d)** | alta donde hay | **NO — H11 UNTESTABLE, gateado por datos** |
| 6 | **Taker buy/sell** | `taker_flow` (8.5 m, 429) | alta | alta (100% integridad) | **SÍ, H12 FAILED** — como señal continua. NO como componente de evento de flujo forzado |
| 7 | **CVD** | derivable de `taker_flow` (cumsum de imbalance) | alta | alta | SÍ, H12 FAILED |
| 8 | **Cross-sectional** | derivable de cualquier tabla con `symbol` | alta | alta | SÍ, H8 FAILED (= momentum) |
| 9 | **Multi-exchange** | `klines_multi_exchange` (bitget/bybit/okx, 8 m, corta jul-25) + `klines` (bybit en `live_prices`) | media | media | SÍ, H9 FAILED (1–5 bp < costo) |
| 10 | **Liquidaciones** | `liquidations` (7 d, 106) | **trivial** | ok | **NO — sin datos suficientes** |
| 11 | **Basis / premium** | `spot_klines` vs perp `klines_clean` (8.5 m, 240) | alta | alta | SÍ, H10 FAILED (= funding re-medido) |
| 12 | **Derivados (opciones/greeks)** | **NINGUNO** | — | — | NO — no hay datos |
| 13 | **Otras** | `orderbook_ofi` (30 d, 499); `whale_events` (3 d, 31) | baja / trivial | media / baja | OFI SÍ (filtro, AUC 0.46 FAILED); on-chain NO |

---

## 3. Fuentes con información potencialmente incremental NO explotada correctamente

Ordenadas por (ortogonalidad real × prior de edge × prontitud de datos):

| Rank | Fuente / ángulo | Por qué podría ser incremental | Estado de datos | Riesgo principal |
|---|---|---|---|---|
| **1** | **Open Interest como magnitud de posicionamiento** (ΔOI, OI/vol, OI vs precio) | Único plano que mide **cuánta posición hay abierta**, no el precio. Ni H8–H12 ni OHLCV lo tocan. Es la variable de estado de los mecanismos de flujo forzado. | 33 d / 45 sym ≥90%. **Gate 70 d ≈ mediados oct.** Piloto de existencia posible ya. | historia corta ⇒ pocos regímenes; sesgo de supervivencia de símbolos |
| **2** | **Eventos de liquidación en cascada** (clusters de `liquidations`) | Evento de flujo forzado **observable directamente**, no inferido. Nunca testeado (no había datos). Respuesta post-cascada (continuación vs vacío de liquidez) es no lineal. | **7 d.** Requiere ~60–90 d ⇒ decisión de colección. | feed parcial (¿todas las liq o solo grandes?); latencia del WS |
| **3** | **Interacción OI × taker-flow × precio en extremos** (evento conjunto) | Cada uno falló **solo**. El mecanismo "shorts agresivos entrando durante una caída con OI subiendo" es un **estado conjunto** que ningún test tocó. | Gateado por OI (#1). | multiple testing; definición del evento |
| **4** | **Funding extremo condicionado a OI en máximo local** (carry unwind) | Funding solo = marginal. Funding extremo **cuando la posición está crowdeada** (OI alto) = el desarme. Interacción no testeada. | funding 2 m + OI 33 d ⇒ **muy poca overlap**. | ventana de solapamiento minúscula |
| **5** | **Transición de régimen de volatilidad (compresión → expansión) como evento** | OHLCV está agotado como señal continua, pero la **transición** low→high vol nunca se modeló como evento con dispersión cross-sectional. | OHLCV completo ⇒ testeable ya. | prior BAJO (OHLCV); riesgo de redescubrir vol-targeting |
| **6** | **Catch-up tras shock de BTC** (beta dislocation a 15m–1h) | Lead-lag falló a sub-segundo (resolución). A 15m–1h **condicionado a un shock de BTC**, los alts que no siguieron: ¿snap-back o fuerza idiosincrática? No testeado a esta escala como evento. | OHLCV completo ⇒ testeable ya. | prior BAJO-MED; solapa con momentum |
| **7** | **OFI en el instante del evento de flujo forzado** (no como filtro continuo) | OFI falló **como filtro promedio**. En la ventana ±N min de un spike de OI / cascada de liq, el desbalance del libro podría tener signo. | OFI 30 d + eventos gateados. | snapshot cada ~8 min ⇒ resolución pobre para eventos rápidos |
| **8** | **Dinámica de OI en perps jóvenes** (post-listing) | Los perps nuevos tienen acumulación de OI y funding distintos; posible ineficiencia estructural de mercado inmaduro. | parcial (OI escaso justamente en listings nuevos). | muestra chica; sesgo de selección |

**Sin datos, no testeable en ningún horizonte cercano:** opciones/greeks (#12),
on-chain serio (#13 — 3 d), multi-venue OI (solo binance), order book full
depth (solo OFI agregado).

---

## 4. Veredicto de Fase 1

- **Región barata y ya arbitrada:** precio, volumen, volatilidad-como-señal,
  taker-flow, basis, cross-sectional lineal, multi-exchange convergencia,
  OFI-como-filtro, funding-como-edge. **No volver.**
- **Región con edge potencial + datos llegando:** **Open Interest y la familia
  de flujo forzado** (ranks 1–4, 7). Todo gateado por profundidad de historia.
- **Región con edge potencial + SIN datos:** liquidaciones profundas, opciones,
  on-chain, multi-venue OI. Requiere **decisión de inversión del usuario** en
  colección; no iniciar colectores nuevos por cuenta propia.
- **Cambio metodológico clave:** pasar de `corr(x_t, ret_{t+h})` continua a
  **event-study de flujo forzado** con placebo temporal + muestra matcheada
  sin-evento. Es lo único no hecho.

Las 8 hipótesis derivadas de este inventario están en
`ALPHA_HYPOTHESIS_LEDGER.md`.
