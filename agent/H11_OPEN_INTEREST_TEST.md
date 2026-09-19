# H11 — Open Interest Information Test · METODOLOGÍA PRE-DECLARADA (congelada 2026-09-03)

**No es una estrategia.** Es un gate científico que responde UNA pregunta:

> ¿El Open Interest contiene información sobre retornos futuros que sea **incremental**
> respecto de precio / momentum / funding, **estable OOS**, de **amplitud suficiente
> para sobrevivir costos**, y **diversificada**?

Salida: **PASS** (→ recién ahí se diseña una estrategia) · **FAILED** (→ se cierra OI
como fuente de alpha) · **UNTESTABLE** (→ se dice exactamente qué falta y se espera).

Estos parámetros quedan **congelados**. No se ajustan después de mirar el OOS. No hay
grid-search. El script es `scratchpad/h11_oi.py`.

---

## 0 · Gate de disponibilidad de datos (se evalúa PRIMERO)

El collector (`open_interest_collector.py`) hace backfill de ~30 días + acumula hacia
adelante. H11 **no se corre** hasta cumplir TODO:

| Requisito | Umbral |
|---|---|
| Historia total de OI (min→max timestamp de la tabla) | **≥ 70 días** |
| Símbolos con cobertura de OI ≥ 90 % sobre la ventana | **≥ 20** |
| Barras de 15 m con OI presente, en promedio sobre esos símbolos | **≥ 90 %** |

Si no se cumple → **H11 = UNTESTABLE (todavía)**. El reporte dice cuántos días /
símbolos faltan. No se fuerza el test con datos flacos.

Cuando se cumple: las fechas exactas de los 3 splits se calculan de `min/max` del
timestamp de la tabla, se **escriben en el reporte ANTES de ejecutar**, y no se
vuelven a tocar.

---

## 1 · Datos y alineación temporal

| Serie | Fuente | Resolución | Notas |
|---|---|---|---|
| Open Interest | tabla `open_interest` (klines.db), Binance Futures, `period=5m` | 5 m → **se agrega a 15 m** (se toma la lectura de OI de cierre de cada bucket de 15 m) | `open_interest` (base) + `open_interest_value` (USDT) |
| Precio / volumen (perp) | `klines_clean` 15 m (`binance_vision_clean.db`) | 15 m | close + volume |
| Funding | tabla `funding_rates` (klines.db) | ~8 h | causal: último vigente ≤ t |

- **Resolución del test: 15 m.** El loop del agente es de 5 min y el tick de salida
  es 1 s → 15 m es ejecutable. Un variante a 5 m se puede agregar DESPUÉS si 15 m
  muestra algo (no antes — evita multiplicar variantes).
- **Anti-lookahead:** todo z-score / Δ / media usa sólo barras cerradas ≤ t. La
  lectura de OI en t es la del bucket que **ya cerró** en t (el collector nunca
  guarda el bucket en formación — ver `OPEN_INTEREST_COLLECTOR.md`). Se lee vía
  `get_open_interest_history(before_ms = t)` y para el bucket que se estaba formando
  en t se resta un período: `before_ms = t − 300_000` en la agregación.
- **Join:** inner join perp∩OI∩funding por `(symbol, open_time)` de 15 m. Barra sin
  OI → esa barra se descarta para ese símbolo (sin relleno).

---

## 2 · Parámetros congelados

```
Z_LOOKBACK_BARS   = 96                 # 1 día de 15m — media/desvío causal (= H8/H9/H10)
DELTA_LOOKBACKS   = [1, 4, 16]         # 15m / 1h / 4h — para ΔOI, %ΔOI, aceleración
Z_BUCKETS         = [(0,1),(1,2),(2,3),(3,∞)]   # sobre |z|, FIJOS (no percentil-tuned)
FWD_HORIZONS_BARS = [4, 16, 48]        # 1h / 4h / 12h forward
LIQ_FLOOR_USD_15M = 1_000_000          # perp: dólar-volumen mediano trailing-7d por barra 15m
OI_COVERAGE_MIN   = 0.90               # símbolo elegible sólo si su serie de OI cubre ≥90% de la ventana
FEE_PER_SIDE      = 0.0004
SLIP_LEVELS       = [0.0, 0.0002, 0.0005]
PLACEBO_SHIFT_BARS = 25                # OI desplazado +6h15 fijo → el efecto debe desaparecer
```

Splits (proporciones fijas, fechas calculadas al correr):
`discovery = primer 50%` · `validation = siguiente 25%` · `final_oos = último 25% (INTOCABLE)`.

---

## 3 · Señales de OI a evaluar (la lista del usuario)

Cada una causal, z-scoreada con `Z_LOOKBACK_BARS` donde aplique:

| # | Señal | Definición |
|---|---|---|
| 1 | `oi_level_z` | z-score del nivel de OI (notional) contra su propia distribución trailing |
| 2 | `d_oi` | ΔOI absoluto (base) sobre cada `DELTA_LOOKBACK` |
| 3 | `pct_d_oi` | %ΔOI sobre cada `DELTA_LOOKBACK` |
| 4 | `d_oi_norm_vol` | ΔOI (notional) / dólar-volumen del perp en la misma ventana |
| 5 | `oi_accel` | 2ª diferencia: ΔOI(t,k) − ΔOI(t−k,k) (aceleración/desaceleración) |
| 6 | `price_x_doi` | 4 cuadrantes: sign(Δprecio) × sign(ΔOI) → {nuevos longs / nuevos shorts / liquidación de longs / cobertura de shorts}; outcome por cuadrante |
| 7 | `price_oi_divergence` | precio sube con OI bajando (o viceversa), z-scoreado |
| 8 | `doi_x_funding` | ΔOI condicionado por signo/magnitud del funding |

**Outcome:** retorno forward del perp `r_fwd(t..t+k) = ln(perp_close(t+k)/perp_close(t))`.
Para señales direccionales (6, 7): `outcome = dirección_predicha × r_fwd`.
Para señales de magnitud (1–5): bucket por |z| y se mide media/mediana de `r_fwd` y si
es **monótona** entre buckets.

---

## 4 · Controles obligatorios

| | Control | Qué mide |
|---|---|---|
| A | OHLCV | retorno/rango trailing del perp, z-scoreado, mismos buckets → `r_fwd` |
| B | Momentum | z-score del retorno trailing del perp → `r_fwd` |
| C | Funding | funding rate causal → `r_fwd` |
| D | A + B + C | control multivariado |
| **E** | **OI + D → test INCREMENTAL** | **partial correlation** de cada señal de OI con `r_fwd`, residualizando AMBOS contra `[retorno trailing perp, rango/vol perp, funding]` por OLS. Se reporta por (señal, horizonte, split). **Este es el gate.** |
| Placebo | OI desplazado +25 barras | se recomputan todas las señales; el efecto **debe desaparecer** |

La pregunta NO es "¿OI tiene alguna correlación?" — es **si aporta información que
NO está ya en precio/momentum/funding**. Si al residualizar contra funding la señal
colapsa (como le pasó al basis en H10) → FAILED.

---

## 5 · Criterio de PASS — los 8 tienen que cumplirse

| # | Criterio | Umbral pre-declarado |
|---|---|---|
| 1 | **Efecto causal** | \|partial corr\| (control E) ≥ **0.03**, mismo signo en los 3 splits |
| 2 | **Incremental** | sobrevive residualizar contra precio + momentum + funding (no colapsa) |
| 3 | **Estabilidad temporal** | mismo signo y magnitud comparable en discovery, validation Y final OOS |
| 4 | **Amplitud** | la interpretación tradeable (portfolio direccional por decil/cuadrante) da **≥ ~15–20 bp/rebalanceo bruto** al horizonte relevante → plausiblemente > el piso de costo de 8–16 bp. **Un efecto de 1–3 bp = FAILED** aunque sea significativo. |
| 5 | **Amplitud de muestra** | efecto en **≥ 20 símbolos** con mediana positiva; **≥ 100 eventos** por bucket por split |
| 6 | **Sobrevive costos** | neto positivo tras fees + slippage 2 bp y 5 bp al turnover realista |
| 7 | **Sin concentración extrema** | top-5 símbolos aportan **< 60 %** del efecto sumado (H8 falló esto con 100–286 %) |
| 8 | **Mecanismo económico** | historia plausible por señal sobreviviente (ej. "OI↑ + precio↑ = longs apalancados nuevos → saturado → revierte"; "ΔOI en ruptura = convicción → continuación") |

**Gate de ejecutabilidad:** si el efecto se resuelve entero en el horizonte 1
(h4 ≈ h16 ≈ h48) → se marca potencialmente **no monetizable a 15 m** (= H9.2 / H10),
lo que arrastra el criterio 4 a FAILED salvo que la magnitud a h1 ya sea grande.

---

## 6 · Veredicto

- **PASS** — los 8 se cumplen → se pasa a diseñar una estrategia de OI (paso
  separado, con su propia validación independiente). No antes.
- **FAILED** — estadísticamente real pero (cualquiera de): no incremental / no
  estable / amplitud 1–3 bp / concentrado / muere con costos → **se cierra OI como
  fuente de alpha**. No se rescata con filtros.
- **UNTESTABLE** — no se cumplió el gate del §0 → se dice exactamente cuántos días /
  símbolos / cobertura faltan, y se espera.

No hay una cuarta opción de "probemos otra variante".

---

## 7 · Qué NO hace este test

- No crea una estrategia de producción.
- No modifica el motor de trading, SL/TP, sizing, router ni ningún modelo.
- No optimiza parámetros buscando el mejor resultado.
- No agrega variantes nuevas después de ver resultados.
