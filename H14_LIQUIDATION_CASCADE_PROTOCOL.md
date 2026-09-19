# H14 — LIQUIDATION CASCADE: FROZEN PROTOCOL + DATA PLAN

**Fecha:** 2026-09-06
**Estado:** protocolo **CONGELADO**. **NO se corre backtest todavía** — la
historia disponible es ~7 días y además se está auto-borrando (ver § 3). Este
documento fija las definiciones **antes** de ver resultados y define qué hay
que hacer para poder testear.

---

## 0. Pregunta

Alrededor de una cascada de liquidaciones (flujo **forzado y observable**),
¿qué pasa con el precio? Dos mecanismos rivales, **no se asume cuál**:

- **CONTINUATION** — la cascada empuja el precio a un nivel que detona más
  stops/liquidaciones en la misma dirección ⇒ el retorno forward **continúa**
  la dirección de la cascada.
- **EXHAUSTION / REVERSAL** — la cascada barre el libro, el precio
  sobre-extiende, y hay rebote mecánico cuando entran los market makers ⇒ el
  retorno forward **revierte** contra la dirección de la cascada.

**Predicción a priori (no optimizada):** el signo depende de si el **OI cae**
en la ventana de la cascada (deleveraging real, se agotó el combustible ⇒
REVERSAL) o **no cae** (todavía hay posición forzable ⇒ CONTINUATION); y del
tamaño de la cascada relativo a la liquidez normal del símbolo.

---

## 1. Definiciones de evento — CONGELADAS

Trabajo sobre barras de **5 min** (resolución nativa del feed de liquidaciones
y suficiente para timing de cascada). Por símbolo, sobre su propia historia
(todo causal, rolling hacia atrás).

| Concepto | Definición congelada |
|---|---|
| **liq_notional(bar)** | `Σ (qty · price)` de todas las liquidaciones del símbolo en la barra de 5 min |
| **liq_long(bar) / liq_short(bar)** | idem, separando `side="Sell"` (se liquidó un LONG) / `side="Buy"` (se liquidó un SHORT) |
| **liq_intensity(bar)** | `liq_notional(bar) / median_5m_dollar_volume_7d(símbolo)` — cascada normalizada por la liquidez típica |
| **LIQUIDATION SPIKE** | una barra con `liq_intensity ≥ p95` de la distribución 14 d del símbolo **Y** `liq_notional ≥ $50 000` (piso absoluto para descartar microcaps con volumen nominal ridículo) |
| **LIQUIDATION CASCADE** | ≥ 2 SPIKEs en una ventana de 15 min (3 barras), **o** un solo SPIKE con `liq_intensity ≥ p99`. El **timestamp del evento** = fin de la última barra-spike de la ventana |
| **DIRECTIONAL LIQUIDATION EVENT** | cascada con `liq_imbalance = (liq_long − liq_short)/(liq_long + liq_short)` con `\|·\| ≥ 0.6` (≥ 80 % de un lado). Dirección = el lado liquidado: LONG-flush (bajista) / SHORT-flush (alcista) |
| **ABNORMAL LIQUIDATION INTENSITY** | `liq_intensity ≥ p99.5` 14 d **o** `liq_notional ≥ $1 M` en 5 min |
| **COOLDOWN** | tras un evento en un símbolo, se suprimen nuevos eventos de ese símbolo por 60 min (12 barras) |

**Umbrales congelados:** p95 / p99 / p99.5 de intensidad, piso $50 k, imbalance
0.6, ventana 15 min, cooldown 60 min. **No se re-ajustan sobre PnL.** Si el
piloto formal muestra que un umbral no genera muestra suficiente, se documenta
como "muestra insuficiente para ese bucket" — NO se baja el umbral para forzar
eventos.

---

## 2. Features a registrar por evento — CONGELADAS

Al timestamp del evento, y en la ventana [evento − 1 h, evento + horizonte]:

1. `liq_long_notional`, `liq_short_notional`, `liq_total_notional`
2. `liq_imbalance` (definido arriba)
3. `liq_intensity` (pico y suma en la ventana de la cascada)
4. `n_spike_bars` (nº de barras-spike en la cascada)
5. `price_return` en la ventana de la cascada (la extensión que causó)
6. `ret_prior_1h` (retorno de la hora previa al evento)
7. **`dOI`** en la ventana de la cascada y en la hora previa (de
   `open_interest`; **ojo: OI es de Binance, liquidaciones de Bybit** — venues
   distintos, se documenta como limitación)
8. `volume_z` (volumen de la ventana vs mediana 7 d)
9. `taker_imbalance` si hay `taker_flow` para ese símbolo/fecha
10. `realized_vol_1h` previa
11. `btc_regime` (ret BTC 1 h y 24 h, bucket)
12. `symbol`, `symbol_age_days` (desde la primera vela)
13. `spread_estimate` (de `orderbook_ofi` o del rango de la vela) — para el
    costo realista

**Horizontes forward (congelados):** 15, 30, 60 min. (Cascadas son eventos
rápidos; no se agregan horizontes largos.)

---

## 3. Estado de los datos — POR QUÉ NO SE PUEDE TESTEAR AÚN

### 3.1 Qué hay

| Ítem | Valor |
|---|---|
| Tabla | `klines.db → liquidations` |
| Filas | 9 786 |
| Símbolos | 106 |
| Span | **2026-08-31 → 2026-09-07 = 7.0 días** |
| Fuente | **Bybit** WS `allLiquidation.<symbol>` (`agent/liquidation_tracker.py`). **Binance NO tiene feed** (`!forceOrder@arr` muerto en este entorno, `/fapi/v1/allForceOrders` dado de baja globalmente). |
| Notional mediano por liq | **$124** (p99 = $9 166, max = $305 k) — el feed captura liquidaciones **chicas de microcaps**, no las grandes de majors |
| Duplicados exactos | 0 (bien) |
| Gap inter-evento máx | 1 784 min (~30 h) ⇒ **el colector estuvo caído** |
| Eventos/día | 3 931 (31-ago) → 1 567 → 1 425 → 193 → 2 097 → 548 → **15 → 10** (6-7 sep) ⇒ **colección intermitente** |

### 3.2 Los tres problemas

1. **AUTO-BORRADO.** `kline_cache.py:844 prune_old_liquidations(keep_hours=24*7)`
   corre cada hora y **borra todo lo que tiene más de 7 días**. Por eso la
   tabla nunca crece. **Mientras esto siga activo, H14 es imposible** — la
   historia se destruye sola.
2. **UNIVERSO CHICO.** El tracker solo se suscribe a `config.WATCHLIST_TIER1`
   (~30 símbolos volátiles). No hay BTC/ETH/SOL ni top-100. Las cascadas que
   importan económicamente (las de nombres líquidos) no se están capturando.
3. **INTERMITENCIA.** Los conteos por día y el gap de 30 h muestran que el
   tracker se cae y no siempre se levanta. Historia de bugs de reconexión en
   el propio archivo (`2026-07-17`: la conexión se caía cada ~60 s).

### 3.3 Backfill histórico — NO ES POSIBLE

- Bybit `allLiquidation`: **solo tiempo real**, sin REST histórico.
- Binance: feed muerto.
- `data.binance.vision`: **no publica liquidaciones**.
- Coinglass / Coinalyze: tienen historia pero **de pago** (decisión de
  inversión del usuario, fuera de alcance).

⇒ **H14 solo se puede testear con datos recolectados HACIA ADELANTE.**

---

## 4. Plan de recolección (research infra — NO toca producción)

Cambios acotados, todos en el lado de research (`agent/liquidation_tracker.py`
+ `kline_cache.py`), ninguno en `verge_agent.py` ni en el motor live:

1. **Detener el auto-borrado para research.** Opción A: subir `keep_hours` a
   `24*400` (400 días). Opción B (preferida): que el tracker escriba también a
   una tabla `liquidations_research` **sin prune**, y dejar `liquidations`
   como está (la usa `get_liquidation_cascade` del agente con ventana corta).
2. **Ampliar el universo suscripto** de `WATCHLIST_TIER1` (~30) a: **BTC, ETH,
   SOL + top-100 perps de Bybit por volumen 24 h**, refrescado diario. Bybit
   permite muchos topics (batching de a 10, ya implementado).
3. **Endurecer la reconexión / supervisión** — heartbeat, y un check externo
   (tarea programada) que reinicie el tracker si no escribió en > 10 min.
4. **Registrar metadatos de calidad** por hora: nº de eventos, nº de símbolos
   activos, gap máximo, reconexiones. Guardar en una tabla `liq_collector_health`.
5. **Objetivo:** **60–90 días** de recolección continua y supervisada, con
   ≥ 90 % de uptime y ≥ 100 símbolos (incluidos los 3 majors).

**Métricas a auditar cuando haya datos** (antes de correr el test):
cobertura (uptime %), gaps (nº y duración), símbolos (cuántos con ≥ 90 %
uptime), timestamps (monotonía, timezone), latencia (T del evento vs
`updated_at`), duplicados, calidad (¿el feed trae todas las liq o solo un
umbral? — verificar contra un día de referencia de Coinglass si el usuario
decide pagar una muestra puntual).

---

## 5. Diseño del test formal H14 — CONGELADO (ejecutar con ≥ 60 d)

- **Universo:** símbolos con ≥ 90 % de uptime de colección sobre el período,
  con `median_5m_dollar_volume_7d ≥ $200 k` (filtro de liquidez).
- **Splits:** 50 % TRAIN (params ya congelados) / 25 % VALIDATION / 25 %
  FINAL-OOS. VALIDATION y FINAL-OOS se miran una vez.
- **Buckets pre-definidos (sin grid):**
  - por dirección: LONG-flush vs SHORT-flush
  - por OI: cascada con `dOI < 0` (deleveraging) vs `dOI ≥ 0`
  - por intensidad: SPIKE / CASCADE / ABNORMAL
- **Para cada bucket × horizonte {15, 30, 60 min}:**
  - retorno forward crudo (bp) + IC bootstrap (sobre eventos y sobre símbolos)
  - **matched non-event control**: barras del mismo símbolo con misma
    `realized_vol_1h` (±25 %) y mismo `ret_prior_1h` (±25 %), sin cascada,
    a ≥ 2 h de cualquier evento ⇒ efecto **incremental**
  - **placebo temporal**: evento + 2 h (ventana sin cascada) ⇒ si reproduce el
    efecto, es régimen/vol, no la cascada
  - efecto tras costos: fee RT 8 bp + slippage/lado {0, 2, 5, 10} bp + medio
    spread real (§ 4.5). Las cascadas ocurren en el peor momento de spread ⇒
    el escenario base del gate es **10 bp/lado**, no 2.
- **Multiple testing:** BH sobre todos los bucket × horizonte; reportar q-values.

### Regla de veredicto formal (pre-declarada)

| Veredicto | Condición |
|---|---|
| **CONTINUE** (a Fase 4) | un bucket direccional muestra, en ≥ 2 de los 3 horizontes, efecto **incremental** (vs matched) con IC 90 % que **excluye 0**, **mismo signo** en VALIDATION y FINAL-OOS, mismo signo en ≥ 60 % de símbolos, el **placebo no lo reproduce**, y el efecto **incremental tras 10 bp/lado + spread real** es ≥ 20 bp. Además el mecanismo (CONTINUATION vs REVERSAL) tiene que ser el mismo en los dos splits. |
| **PARK** | signo consistente y limpio de placebo pero magnitud tras costos < 20 bp, o IC incremental marginal. Re-check con más datos. |
| **FAILED** | el efecto lo reproduce el placebo, o desaparece contra el matched control (era solo "el mercado se movía"), o el signo se da vuelta entre splits, o CONTINUATION y REVERSAL se alternan según el split. **Se cierra. Sin H14.x de rescate.** |

---

## 6. Disciplina (aplica ya, durante la recolección)

Prohibido:
- optimizar umbrales sobre PnL o sobre el resultado del piloto;
- cambiar las definiciones del § 1 después de ver datos;
- agregar features o filtros para "mejorar" un bucket;
- elegir solo los símbolos/períodos/eventos que funcionan;
- convertir el event-study en estrategia antes del gate del § 5;
- usar el resultado forward para redefinir qué cuenta como cascada.

Si H14 falla el gate ⇒ **FAILED**, se cierra.

---

## 7. Resumen accionable

| Ítem | Estado / acción |
|---|---|
| Protocolo H14 | **CONGELADO** (§ 1, § 2, § 5) |
| Datos históricos | 7 d, **se están auto-borrando**, universo de ~30 microcaps. **Inservibles.** |
| Backfill histórico | **imposible** (sin fuente gratuita) |
| Acción requerida (research infra) | (1) parar el prune / tabla `liquidations_research`; (2) ampliar universo a majors + top-100 Bybit; (3) supervisión de uptime; (4) 60–90 d de colección continua |
| Test formal | recién con ≥ 60 d y ≥ 90 % uptime. Protocolo ya fijado. |
| Producción / DB / motor live | **no se tocan** |
