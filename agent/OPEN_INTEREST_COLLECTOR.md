# Open Interest Collector — TRACK A (research post-H9, 2026-09-02)

**Esto es data collection, no estrategia.** Nada de producción lee la tabla
`open_interest` todavía. El objetivo: acumular una serie histórica limpia de OI
**desde ahora**, para poder testear más adelante (hipótesis aún sin definir) si el
Open Interest contiene información incremental sobre el retorno futuro.

Por qué ahora: Binance sólo expone los **últimos ~30 días** de OI histórico. Lo
que no capturemos hoy se pierde. Cada semana que corra el collector = una semana
más de historia utilizable para un futuro test OOS.

---

## Archivos

| Archivo | Rol |
|---|---|
| `agent/open_interest_collector.py` | el collector (loop REST + backfill) |
| `agent/kline_cache.py` | tabla `open_interest` + métodos `*_open_interest` (aditivos, dormidos) |
| `docker-compose.yml` → servicio `oi-collector` | ejecución persistente containerizada |

**No se tocó** `verge_agent.py`, ni estrategias, ni SL/TP/sizing, ni router, ni
ningún modelo. `kline_cache.py` sólo recibió una tabla `CREATE TABLE IF NOT
EXISTS` y métodos nuevos que nadie llama todavía.

---

## Fuente

```
GET https://fapi.binance.com/futures/data/openInterestHist
    ?symbol=<S>&period=5m&limit=<N>[&startTime=<ms>&endTime=<ms>]
```

Respuesta (sin auth):
```json
[{"symbol":"BTCUSDT","sumOpenInterest":"143210.5","sumOpenInterestValue":"1.29e10","timestamp":1788000000000}, ...]
```

| Campo fuente | Columna | Significado |
|---|---|---|
| `sumOpenInterest` | `open_interest` | OI en **unidades base** (coin / contratos) |
| `sumOpenInterestValue` | `open_interest_value` | OI en **notional USDT** |
| `timestamp` | `timestamp` | **ms UTC**, alineado al bucket de 5 m |

**Retención de la fuente: sólo ~30 días.** De ahí la urgencia de correrlo continuo.

Fallback disponible (no usado por defecto): `GET /fapi/v1/openInterest?symbol=<S>`
→ snapshot actual, weight 1.

**Otros exchanges:** no implementados en v1 (decisión deliberada — cobertura +
calidad + persistencia de UNA fuente primero). El esquema ya tiene columna
`exchange`; sumar bybit = un `fetch_bybit_oi_history()` + llamarlo con
`exchange="bybit"` (`GET /v5/market/open-interest`, `category=linear`,
`intervalTime=5min`).

---

## Frecuencia y rate limits

| | Valor | Nota |
|---|---|---|
| `PERIOD` | `5m` | granularidad de la fuente |
| Backfill inicial | hasta 30 d, `limit=500`/req, ~15 req/símbolo | idempotente (upsert) — re-correr sólo rellena huecos |
| Régimen permanente | cada `POLL_INTERVAL_S=300` s, `limit=12` (1 h)/símbolo | tapa huecos cortos + toma el bucket nuevo |
| `SLEEP_BETWEEN_CALLS_S` | `0.35` | ~30 símbolos en ~11 s/ciclo |
| Universo | `config.WATCHLIST_TIER1` (~30) | ampliar = 1 línea; empezar chico |

Los endpoints `/futures/data/*` de Binance se limitan **por IP** (~1000 req/5 min
por doc), no por el `X-MBX-USED-WEIGHT` de `/fapi/*`. El uso real acá es
~360 req/5 min en el peor caso (backfill), y ~30 req/5 min en régimen — muy por
debajo. Además comparte el **circuit breaker de Binance** (`circuit_breaker.py`):
ante un 418/429 no golpea la API y reintenta el próximo ciclo (mismo mecanismo
que evitó el baneo de sesiones anteriores).

---

## Almacenamiento

Tabla `open_interest` en `agent/data/klines.db` (misma DB que `funding_rates`,
`orderbook_ofi`, `liquidations`):

```sql
CREATE TABLE open_interest (
    exchange            TEXT NOT NULL DEFAULT 'binance',
    symbol              TEXT NOT NULL,
    timestamp           INTEGER NOT NULL,   -- ms UTC, inicio del bucket de 5m
    period              TEXT NOT NULL DEFAULT '5m',
    open_interest       REAL NOT NULL,      -- unidades base
    open_interest_value REAL,               -- notional USDT
    updated_at          INTEGER NOT NULL,   -- wall-clock de escritura (SOLO auditoría de lag)
    PRIMARY KEY (exchange, symbol, period, timestamp)
);
```

**Sólo se guarda el dato crudo** (base + notional). Los derivados que pediste —
OI absoluto, ΔOI, %ΔOI, OI/volumen — se calculan **al leer**, de forma causal, y
**nunca se persisten**. Razón: un bug en el cálculo de un derivado no debe
contaminar la serie histórica ni introducir lookahead retroactivo. La serie cruda
es la fuente de verdad; los derivados son una vista.

Retención local: `prune_old_open_interest(keep_days=400)` (una vez/día). Alto a
propósito — el objetivo es acumular. 5 m × 100 símbolos × 400 d ≈ 11,5 M filas.

---

## Detección de datos faltantes / calidad

`cache.open_interest_gaps(symbol)` →
```json
{"rows": 8640, "expected": 8641, "missing": 1, "coverage_pct": 99.99, "first": ..., "last": ...}
```
Calcula, entre el primer y último timestamp del símbolo, cuántos buckets de 5 m
deberían existir vs cuántos hay. El loop loguea **la peor cobertura** cada ciclo:

```
📊 OI ciclo 42: 30 actualizados, 0 saltados (breaker), 0 fallidos | peor cobertura: FOOUSDT 96.1% (5210 filas)
```

Cobertura < 95 % sostenida en un símbolo = investigar (delisted, o la fuente no
lo tiene). No hay backfill de huecos > 30 días: la fuente no los tiene.

---

## Normalización

- `open_interest` en unidades base y `open_interest_value` en USDT, **tal cual
  Binance**. No se re-escala nada.
- Para comparar entre símbolos: usar `open_interest_value` (USDT) o normalizar por
  el volumen/marketcap del símbolo **en el consumidor**, no acá.
- Un registro con `sumOpenInterestValue` ausente/`""` se guarda con
  `open_interest_value = NULL` (algunos símbolos exóticos), el base siempre está.

---

## Lookahead y timestamps — cómo se garantiza que el collector no los rompe

1. **El collector sólo escribe buckets ya cerrados que la API ya publicó.** No
   inventa timestamps: usa el `timestamp` de Binance. `_parse()` verifica
   `ts % 300000 == 0` (alineación) y descarta + loguea si no (posible cambio de
   esquema de la fuente).
2. **Nunca escribe un bucket con `timestamp > now - PERIOD_MS`** — el bucket
   actual todavía se está formando en la fuente; se toma recién cuando cerró.
3. **La lectura causal es responsabilidad del consumidor.** Para "OI conocido en
   el instante `t`":
   ```python
   cache.get_open_interest_history(sym, before_ms=t - 300_000)   # excluye el bucket que aún se formaba en t
   ```
   `before_ms` filtra `timestamp <= before_ms`. Restar un período extra evita usar
   el bucket que en `t` todavía no había cerrado.
4. **`updated_at`** (wall-clock de escritura) se guarda **sólo** para auditar el
   lag de captura (¿cuánto tardó el collector en ver un bucket?). **Nunca** se usa
   como eje temporal en ningún cálculo.
5. **UPSERT idempotente** por `(exchange, symbol, period, timestamp)`: re-correr
   el backfill no duplica ni re-fecha nada.

---

## Cómo ejecutarlo — TAREA PROGRAMADA (para el run de semanas)

El colector tiene que sobrevivir reinicios de PC (2-3 por semana) sin intervención
manual. Solución: una tarea de Windows que arranca al iniciar sesión y se
auto-reinicia si el proceso muere.

```powershell
# registrar (una vez, PowerShell normal, sin admin):
powershell -ExecutionPolicy Bypass -File agent\register_oi_collector_task.ps1
# arrancar ya, sin esperar al próximo login:
Start-ScheduledTask -TaskName VergeOICollector
# quitar:
Unregister-ScheduledTask -TaskName VergeOICollector -Confirm:$false
```

Archivos: `oi_collector_run.bat` (lanzador, con rotación de log a 20 MB) +
`register_oi_collector_task.ps1` (registro de la tarea: trigger AtLogOn +30s,
restart cada 5 min ×999, una sola instancia, sin límite de tiempo).

**Reinicios de PC:** la tarea lo re-arranca sola al loguearte. Cada arranque
re-corre el backfill de 30 días (idempotente por PK) → **cualquier hueco de menos
de 30 días se rellena solo**. O sea: 2-3 reinicios por semana no cuestan historia,
siempre que el colector vuelva a arrancar en menos de 30 días.

### Arranque manual (solo para pruebas / no persiste al reinicio)
```bash
cd agent && python -u open_interest_collector.py > logs/oi_collector.log 2>&1 &
```

**Por qué NO en Docker (en Windows):** SQLite en modo WAL sobre un bind mount de
Docker Desktop tira `sqlite3.OperationalError: disk I/O error` (el WAL necesita
shared-memory mmap que no funciona sobre la capa 9p/virtiofs). Misma razón por la
que `market-ws` y `backtest` usan volúmenes NOMBRADOS y DBs separadas. Un volumen
nombrado acá obligaría a un paso de sync para que el research vea los datos — anula
el propósito. Desde el host, `klines.db` es el mismo archivo nativo que ya usan
`funding_rates.py`, el agente y el backtest — coordinado por WAL. El servicio
`oi-collector` de `docker-compose.yml` quedó documentado pero desactivado.

### Verificar que está acumulando
```python
from kline_cache import get_cache
c = get_cache()
print(c.count_open_interest("BTCUSDT"))          # crece ~288/día
print(c.open_interest_gaps("BTCUSDT"))           # coverage_pct debería quedar ~100
print(c.get_latest_open_interest("BTCUSDT"))     # timestamp < ~10 min de antigüedad
```

---

## Checkpoint sugerido

Revisar en **~4–6 semanas**: si hay ≥ 30 días de historia limpia (coverage ≥ 98 %
en la mayoría de TIER1) sumados a los ~30 días de backfill inicial → ~2 meses de
serie, suficiente para un primer test de existencia de señal con split
discovery/validation/OOS. Recién ahí se define la hipótesis OI (no antes).
