# H12 — TAKER ORDER FLOW / CVD · PROTOCOLO CONGELADO (preregistration, 2026-09-04)

**No es una estrategia.** Es un test de si el flujo agresor comprador/vendedor es una
**alpha source**: información **incremental, causal y económicamente monetizable** sobre
el retorno futuro, *después* de controlar por precio / momentum / volatilidad / funding.

Salida: **PASS** · **FAILED** · **UNTESTABLE**. Nada más. Si FAILED, se cierra la línea
order-flow con estos datos y se espera a H11/OI. **No hay H12.1/H12.2 para rescatarla.**

Estos parámetros quedan **congelados**. No se tocan tras mirar resultados. Sin
grid-search, sin optimización, sin variantes post-hoc, sin filtros descubiertos
después, sin selección de símbolos después.

---

## 1 · DATA

### Fuente
Sólo `data.binance.vision` (CDN de archivos públicos — **NO `fapi.binance.com`**).
Los klines de futures USDⓈ-M ya bajados tienen 12 columnas; el downloader
(`download_binance_vision_daily_all_v2.py`) sólo guardó las 6 primeras. Se recuperan:

| # | Columna | Uso |
|---|---|---|
| 5 | `volume` | total base (ya lo tenemos en `klines_clean` — se re-verifica) |
| 7 | `quote_volume` | total USDT |
| 8 | `count` | nº de trades en la barra |
| 9 | `taker_buy_volume` | volumen **agresor comprador** (base) |
| 10 | `taker_buy_quote_volume` | agresor comprador (USDT) |

`taker_sell_volume = volume − taker_buy_volume` (definición; verificado exacto en el QA).

### Destino
Tabla **nueva** `taker_flow` en `binance_vision_clean.db` (aditiva, no toca `klines_clean`):
```sql
CREATE TABLE taker_flow (
  symbol       TEXT NOT NULL,
  interval     TEXT NOT NULL,       -- '15m'
  open_time    INTEGER NOT NULL,    -- ms UTC (idéntico a klines_clean)
  volume            REAL,
  quote_volume      REAL,
  trade_count       INTEGER,
  taker_buy_volume  REAL,
  taker_buy_quote   REAL,
  PRIMARY KEY (symbol, interval, open_time)
);
```

### Backfill
- Mismos símbolos que el panel principal (`klines_clean`, 429 perp), misma ventana
  (2025-12-01 → 2026-08-17), misma resolución (15 m).
- Monthly + daily del CDN, `INSERT OR IGNORE` (idempotente).
- Documentar cobertura real por símbolo tras el backfill (símbolos con &lt; 95 % de la
  ventana quedan fuera del test — ver §6).

### Data QA (hecho — muestra: 4 símbolos × 3 días = 1.152 barras 15 m)
| Chequeo | Resultado |
|---|---|
| `open_time` coincide con `klines_clean` (mismo valor exacto) | **1.152 / 1.152 (100 %)** |
| `volume` coincide con `klines_clean` (≤ 1 bp) | **1.152 / 1.152** |
| `taker_buy + taker_sell == volume` (exacto) | **1.152 / 1.152** |
| duplicados de `open_time` | **0** |
| lookahead (última barra del día cierra 23:59:59.999, sin spillover) | **OK** |
| `count` presente y &gt; 0 | **OK** (rango 5.951–95.504 trades/barra en BTC) |
| timezone | ambos UTC ms — sin diferencia |
| `taker_buy_frac` varía (no está clavado en 0,5) | **OK** (0,26–0,70 en un día normal) |

---

## 2 · HIPÓTESIS CONGELADAS

**Hipótesis:** el imbalance entre volumen agresor comprador y vendedor contiene
información incremental sobre el retorno futuro que **no** está en
retorno / momentum / volatilidad / funding.

Cinco familias de variables (A–E). **Congeladas. No se agregan más.**

| ID | Nombre | Fórmula (causal, sólo barras cerradas ≤ t) |
|---|---|---|
| **H12-A** | Taker Imbalance | `TI(t) = (taker_buy - taker_sell) / volume` por barra de 15 m |
| **H12-B** | CVD | `CVD_w(t) = Σ (taker_buy - taker_sell)` sobre la ventana causal `w`; también su versión normalizada `CVD_w / Σ volume_w` |
| **H12-C** | Flow acceleration | `ΔTI_w(t) = TI_agg(t, w) − TI_agg(t−w, w)` (y lo mismo para CVD normalizado) |
| **H12-D** | Price/Flow divergence | signo de `retorno_w(t)` vs signo de `TI_agg(t, w)`; magnitud = `z(retorno_w) − z(TI_agg_w)` |
| **H12-E** | Extreme flow | eventos donde `|z(TI_agg_w)| ≥ 2` y `≥ 3` (umbrales **ex-ante**, z-score causal con lookback = §3) |

Donde `TI_agg(t, w)` = imbalance agregado sobre la ventana `w` = `CVD_w / Σ volume_w`.

---

## 3 · WINDOWS (congeladas)

- Ventanas de agregación / lookback: **1 h, 4 h, 12 h, 24 h** (= 4, 16, 48, 96 barras de 15 m).
- Horizontes forward: **1 h, 4 h, 12 h** (= 4, 16, 48 barras).
- z-score causal: lookback **96 barras** (1 día), media/desvío sobre barras ≤ t.
- Buckets `|z|` para las señales de magnitud: **`[0,1) [1,2) [2,3) [3,∞)`** (fijos, no percentil-tuned).

No se prueban otras ventanas/horizontes/buckets después de ver resultados.

---

## 4 · CONTROLES

Cada señal se compara contra:

| | Control |
|---|---|
| A | forward return bruto (baseline) |
| B | trailing price return (momentum del perp, z-score) |
| C | trailing volatility / range (rango de las últimas 16 barras / precio) |
| D | funding (causal, `funding_rates` — último vigente ≤ t) |
| E | **B + C + D combinados** → **test incremental** |

**Test incremental (el que decide):** partial correlation de la señal de taker-flow con
el retorno forward del perp, **residualizando ambos** contra `[trailing return, trailing
range, funding]` por OLS. Se reporta por (señal, ventana, horizonte, split).

La pregunta: **¿el taker-flow explica algo del futuro que precio + volatilidad +
funding no explican?** Si la partial corr colapsa al controlar (como el basis en H10
colapsó contra funding) → FAILED.

Nota de cobertura: funding sólo existe desde 2026-07-07. Para discovery/validation el
control D se corre con `funding = 0` donde no hay dato (documentado); el veredicto se
apoya sobre todo en el OOS, donde el funding sí está.

---

## 5 · TEMPORAL SPLITS (congelados, el OOS se mira UNA vez)

| Split | Rango |
|---|---|
| DISCOVERY | 2025-12-01 → 2026-03-31 |
| VALIDATION | 2026-04-01 → 2026-05-31 |
| **FINAL OOS** | 2026-06-01 → 2026-08-17 (máximo disponible) — **intocable** |

No se modifican las fechas después de observar resultados.

---

## 6 · CROSS-SECTION

Universo: los perp de `klines_clean`. Se **excluye** un símbolo si:
- historia &lt; 95 % de la ventana en `taker_flow`, o
- dólar-volumen mediano trailing-7d &lt; **$1.000.000 / 15 m** (mismo piso que H9/H10/H11), o
- datos taker incompletos / inconsistentes en el QA por símbolo.

Se documenta exactamente cuántos símbolos quedan.

Reportar siempre: nº de símbolos · eventos por símbolo · **concentración del efecto
(share de los top-5 símbolos)** · mediana cross-sectional del efecto · % de símbolos
con efecto del mismo signo. **BTC/ETH o el top-5 no pueden dominar el resultado.**

---

## 7 · PLACEBO

Obligatorio: **desplazar la serie de taker-flow +25 barras** (≈ 6 h 15) y recomputar
TODAS las señales A–E. Si el placebo reproduce el efecto real de forma comparable →
se está midiendo régimen / beta común, **no** order-flow causal → FAILED.

Control adicional contra correlación espuria por autocorrelación: los retornos forward
se solapan entre observaciones consecutivas → los intervalos de confianza / significancia
se calculan con bloques no solapados (o se reporta el efecto sobre observaciones
espaciadas ≥ el horizonte forward).

---

## 8 · COSTOS

Slippage: **0 bp · 2 bp · 5 bp** (+ fees 0,04 %/lado). Separar:
1. **amplitud estadística** (partial corr, spread de deciles);
2. **amplitud económicamente capturable** (retorno direccional neto de costos al turnover real).

**Gate económico:** el movimiento potencial por rebalanceo tiene que ser **≥ 15–20 bp
bruto** al horizonte relevante. Un efecto de 1–3 bp **NO cuenta como alpha útil** aunque
sea estadísticamente significativo → FAILED.

---

## 9 · CRITERIO DE PASS — los 10 tienen que cumplirse

| # | Criterio |
|---|---|
| 1 | Efecto **causal** (sin lookahead — garantizado por construcción) |
| 2 | **Mismo signo** en Discovery, Validation y Final OOS |
| 3 | Partial correlation / señal incremental **suficientemente fuerte** (`|partial corr| ≥ 0.03`, mismo signo 3 splits) |
| 4 | Efecto **≥ 15–20 bp** (gate económico §8) |
| 5 | **≥ 20 símbolos** con efecto del mismo signo; **≥ 100 eventos** por bucket por split |
| 6 | Sobrevive **2 y 5 bp** de costos |
| 7 | **No depende del top-5** (share top-5 &lt; 60 % del efecto sumado) |
| 8 | El **placebo no reproduce** el efecto |
| 9 | **Mecanismo económico coherente** (por qué el flujo agresor debería predecir eso) |
| 10 | **No requiere combinar múltiples filtros arbitrarios** — una familia A–E con una ventana/horizonte tiene que funcionar por sí sola |

Un buen Sharpe/PnL de **una sola variante** NO es un PASS.

---

## 10 · REGLA ANTI-OVERFITTING (fundamental)

**Prohibido:** grid-search · optimización de parámetros · combinaciones exhaustivas ·
"probar una variante → mirar → inventar otra" · filtros de régimen post-hoc · seleccionar
símbolos tras ver resultados · cambiar ventanas porque "esa parece funcionar" · rescatar
una señal FAILED con un filtro nuevo.

Las 5 familias A–E y sus ventanas/horizontes están congeladas. Si **todas** fallan,
**H12 termina**. No hay H12.1/H12.2/H12.3.

---

## 11 · VEREDICTO

| | Significado |
|---|---|
| **PASS** | descubrimos una fuente de alpha potencialmente real → recién ahí se diseña una estrategia alrededor del mecanismo que demostró incrementalidad |
| **FAILED** | el efecto no es suficientemente robusto/económico → se cierra definitivamente la línea taker/order-flow **con estos datos** y se espera a H11/OI |
| **UNTESTABLE** | la calidad/cobertura temporal no permite concluir → se dice exactamente qué falta |

---

## 12 · LO QUE H12 NO HACE

No implementa ninguna estrategia. No modifica producción. No se conecta al agente. No
toca el motor de trading, SL/TP, sizing, router ni ningún modelo. Es sólo el estudio de
alpha source.

---

## 13 · ORDEN DE EJECUCIÓN

1. **[HECHO]** Este documento (protocolo congelado) + Data QA sample (§1). ✅ QA pasó.
2. **[PENDIENTE — requiere aprobación del usuario]** Backfill completo de `taker_flow`
   (429 símbolos, 260 días, sólo CDN).
3. Auditoría de cobertura post-backfill + universo final (§6).
4. Ejecutar el test congelado (`agent/backtest/h12_taker_flow.py` — a escribir, mismo
   patrón que `h9`/`h10`/`h11`).
5. H12 RESEARCH REPORT con el veredicto único.

**La prioridad es preservar la validez del experimento, no avanzar rápido.**
