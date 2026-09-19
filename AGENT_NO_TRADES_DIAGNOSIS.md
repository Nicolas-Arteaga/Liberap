# DIAGNÓSTICO — el agente no abre posiciones (2 días)

**Fecha:** 2026-09-09
**Fuente:** `agent/logs/agent.log` (187 MB, instancia PID 25848 arrancada
2026-09-06 21:00:42 -03).
**No se modificó nada.** Esto es diagnóstico.

---

## VEREDICTO

**El agente NO está roto por el código de research infra.** El bloqueo es de
**configuración**: las 3 estrategias activas son perfiles **RECONSTRUIDOS** (tras
el Docker factory-reset del 2026-09-06) con `MinConfluenceScore = 60`, y **60 es
menor que el gate duro de 65 que `setup_validator.py` aplica a los símbolos
Tier 3**. Cada candidato que generan cae en Tier 3 y se vetea.

- **Trades ejecutados desde el restart (2026-09-06 21:00): 0.**
- **Vetos `low_confluence_for_tier3` desde el restart: 187.710.**
- Último trade real: 2026-09-05 21:47 (instancia anterior, DB pre-reset).

---

## 1. Causa raíz (cuantificada)

### 1.1 El gate

`agent/setup_validator.py:1360-1367`:
```python
# Regla B: Subir MIN_CONFLUENCE_SCORE a 65.0 exclusivamente para Tier 3
tier3_min_conf = profile.get("tier3MinConfluenceScore",
                             config.TIER3_MIN_CONFLUENCE_SCORE)   # = 65.0
if tier == "T3" and confluence_score < tier3_min_conf:
    return False, "low_confluence_for_tier3"
```
**No tiene exención para inyección directa** (a diferencia de la Regla A
`disabled_signal_for_tier`, que sí exime `ma_slope_mode`).

### 1.2 El score de los candidatos

`agent/verge_agent.py::_evaluate_ma_geometry_profile`:
`confluence_score = float(profile.get("minConfluenceScore", 80.0))`

Las 20 StrategyProfiles reconstruidas tienen **`MinConfluenceScore = 60`**
(verificado en la DB; descripción literal de cada una: *"RECONSTRUIDO
2026-09-05 tras perdida de datos - config APROXIMADA, revisar/re-tunear"*).

→ Todo candidato de MaGeometry / MA-pattern sale con **score 60**.

### 1.3 El choque

| Estrategia activa | Candidatos/ciclo | Score | Tier | Resultado |
|---|---|---|---|---|
| **MA Slope Caso 3** (`ma_pattern:d988cdc6-…`) | 93–96 | **60.0** | T3 (casi siempre) | **100% veto `low_confluence_for_tier3`** (489 vetos solo para OPENAIUSDT, 442 para OPENUSDT, …) |
| **FVG - 15m** (`[FVG-INJECT]`) | varios | **60.0** | T3 mayormente | veto `low_confluence_for_tier3` en T3 |
| **ARROW-PEAK** | ~1 cada varias horas (patrón raro) | **85.0** | — | pasa el gate de score; simplemente casi nunca dispara (necesita "3d de sangrado tras +22% pump") |

**Antes del reset funcionaba** porque el perfil real de MA Slope Caso 3
tenía `minConfluenceScore ≥ 65` (o usaba el default 80 del código). La
reconstrucción desde `agent/data/trades.csv` no pudo recuperar ese valor y lo
puso en 60 para las 20.

### 1.4 ¿Esto lo causó el trabajo de research infra (Round 3/4)?

**No.** El score 60 viene de `agent/reconstruct_db.py` (recuperación de DB del
2026-09-06, tras el factory-reset accidental de Docker). Los cambios de Round 3
(`kline_cache.py` aditivo) y Round 4 (colectores) no tocan `setup_validator`,
`_evaluate_ma_geometry_profile`, ni el score de los candidatos. El veto empezó
con el restart del agente del 2026-09-06 21:00, ~1 día antes de Round 3.

---

## 2. Problema secundario (degrada datos, NO es el bloqueo)

`[MSF] All exchanges failed for klines <X>` — ~10.500 ocurrencias en 2 días,
incluida BTCUSDT (última 2026-09-09 00:21:03).

Desglose:
- **44** son fallo real de DNS (`getaddrinfo failed` para okx.com/bybit.com).
  **DNS funciona bien ahora** desde el host (verificado: `nslookup` + `curl`
  a Binance/Bybit → HTTP 200, lookup 20–34 ms). Blips intermitentes.
- Un **cascade único** de circuit breakers cerca del restart:
  `[CB:binance/bybit/okx/bitget/pyth] CLOSED → OPEN ❌ (3 failures)` seguido de
  `OPEN → HALF_OPEN (probing…)`. Cuando los 4 breakers están abiertos,
  `_do_fetch_klines` ni se llama → "All exchanges failed" sin línea de error.
- El resto: símbolos basura del watchlist (`牛来USDT`, `我踏马来了USDT`),
  perps Tier-3 ilíquidos que OKX/Bybit no listan, y `[Nexus-15/5] Timeout`
  del `python-service`.

**Aunque los datos fueran perfectos, el Problema 1 vetearía todo igual.** Este
punto explica por qué el scan está ruidoso, no por qué hay 0 trades.

Los colectores de research (arrancados 2026-09-09 00:37 UTC) **no** son la
causa — los fallos de fetch son de 2026-09-06 en adelante y siguen igual con o
sin ellos. Suman algo de carga a Binance/Bybit desde la misma IP, pero el
circuit breaker compartido lo gestiona.

---

## 3. FIX (requiere tu decisión — NO lo apliqué)

El round dice "NO modificar StrategyProfiles / producción / motor live". El fix
mínimo es un valor de config en 3 filas de `StrategyProfiles`. **No lo toco sin
tu OK.**

### Opción A — desbloqueo inmediato (1 línea, reversible)

```sql
UPDATE "StrategyProfiles"
SET "MinConfluenceScore" = 70
WHERE "IsActive" = true
  AND "Name" IN ('MA Slope Caso 3', 'FVG - 15m', 'ARROW-PEAK');
```
70 ≥ 65 → los candidatos T3 dejan de vetearse por score. Reversible a 60.
(El código default histórico era 80; 70–80 es un rango sano.)

### Opción B — re-tunear los 3 perfiles a mano

Están marcados "APROXIMADA, revisar/re-tunear" a propósito. Vía el dashboard,
poner `MinConfluenceScore` y el resto de parámetros a valores deliberados. Es
lo correcto a mediano plazo; la Opción A es el parche.

### Opción C — bajar `config.TIER3_MIN_CONFLUENCE_SCORE`

**No recomendado.** Es el motor, afecta a TODAS las estrategias, no solo las 3.

### Además (Problema 2, menor)

- Reiniciar el agente para limpiar los circuit breakers (o dejarlos
  auto-recuperar vía HALF_OPEN).
- Limpiar del watchlist los símbolos basura (`牛来USDT`, etc.) que
  disparan timeouts y fallos de fetch cada ciclo.

---

## 4. Verificación tras aplicar el fix

1. `agent.log`: aparecen `✅ CANDIDATE` de MA Slope Caso 3 / FVG-15m que
   **pasan** en vez de `[VETO] low_confluence_for_tier3`.
2. `HEALTH CHECK ... | Pasaron: N` con N > 0.
3. `✅ Trade executed for profile MA Slope Caso 3 / FVG - 15m on <SYM>`.
4. El dashboard muestra la posición abierta.

Si tras subir el score siguen sin abrir, el próximo sospechoso es un veto
distinto (`range_too_small` — 116 casos; `rsi_extreme` — 89) o el gate de
slots, pero esos son de segundo orden frente a los 187.710 de
`low_confluence_for_tier3`.
