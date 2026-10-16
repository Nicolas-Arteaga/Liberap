# ROADMAP — Búsqueda de alpha en OI / flujo forzado / microestructura

**Fecha:** 2026-10-12 · **Autor:** Claude (handoff a GPT + Nico; los créditos de Claude se agotan)
**Propósito:** que GPT pueda ejecutar este plan sin depender de Claude. Es un mapa con
tareas, entregables y criterios de PASS / KILL. No es una promesa de rentabilidad.

Leyenda de confianza usada en todo el documento:

- **[REPO]** leído por mí en este repo el 2026-10-12.
- **[EN VIVO]** verificado por mí contra Binance Vision (listing S3) el 2026-10-12.
- **[GPT]** reportado por GPT durante la sesión; yo NO lo verifiqué (vive en worktrees de Windows).
- **[PROPUESTA]** decisión o número mío, no un hecho. Discutible.

---

## 0. TL;DR

1. **Dejar de buscar edge en precio.** MA/RSI/Bollinger/FVG/Order Block están agotados. Esto ya
   lo decía el repo antes de esta sesión (`DATA_INVENTORY.md` §4: "Región barata y ya arbitrada…
   No volver"; `FINAL_DISCOVERY_ROUND47_48.md`: "Discovery TERMINADO") **[REPO]**. Esta sesión
   volvió a recorrer esa región y confirmó lo mismo con más rigor.
2. **La única región que el repo marca como abierta** es Open Interest + familia de flujo forzado
   (H13, H15, H16, H14, H19, H20) **[REPO]**. Estaba bloqueada por falta de historia de datos.
3. **Ese bloqueo probablemente ya no existe.** Binance Vision publica OI histórico a 5 min (más
   ratios long/short y taker) desde 2020, además de `aggTrades`, `bookTicker` (spread real) y
   `bookDepth` **[EN VIVO]**. Y el repo ya tiene `agent/download_oi_metrics.py` que baja
   exactamente eso **[REPO]**. No hace falta esperar 70 días.
4. **Primera apuesta concreta:** H13, cuadrante C (precio↓ + OI↑), horizonte 1–4 h. En el piloto
   del repo fue la única señal que pasó el placebo (+63 / +49 bp en las dos mitades) pero su efecto
   incremental tenía IC que incluye 0 con solo 33 días **[REPO: `H13_PILOT_REPORT.md`]**. Con ~8,5
   meses de OI se puede resolver en días, no en semanas.
5. **Prior honesto:** el ledger asigna prior MED a H13/H14 y LOW-MED o menos al resto **[REPO]**.
   Lo más probable sigue siendo "no hay edge operable". El valor de este plan es decidirlo rápido,
   barato y sin autoengaño — y encontrarlo con controles si existe.

---

## 1. Estado verificado

### 1.1 Qué dice el repo (verdad de base)

Familias declaradas agotadas o falladas **[REPO]**: precio, volumen, volatilidad como señal,
taker flow a 15 m (H12 FAILED), cross-sectional (H8), multi-exchange (H9), basis (H10), OFI como
filtro (AUC 0,46), funding como edge (AUC 0,539 → PF 0,98 OOS), gap de perps de acciones (M18
FAILED), C2 de R46/R47 (no sobrevive quitar los 3 mejores trades), D1/D2 de R48.

Abiertas, todas en **PARK por datos** **[REPO: `ALPHA_HYPOTHESIS_LEDGER.md` L872–1130]**:

| ID | Hipótesis | Prior | Dato que necesita |
|---|---|---|---|
| H13 | Divergencia OI/precio → desapalancamiento/crowding (4 cuadrantes) | MED | OI 5 m |
| H14 | Cascada de liquidaciones: continuación vs vacío de liquidez | MED | liquidaciones + OI |
| H15 | Evento conjunto OI↑ × taker-sell dominante × precio↓ → squeeze | MED-LOW | OI + taker_flow |
| H16 | Funding extremo × OI en máximo local → desarme de carry | LOW-MED | funding + OI |
| H19 | OFI en la ventana de un evento forzado | LOW | OFI + eventos |
| H20 | OI en perps jóvenes (post-listing) | LOW | OI + edad |
| H17 / H18 | Transición de vol / catch-up alts tras shock BTC | LOW / LOW-MED | OHLCV (listo) |

Cambio metodológico clave que el repo exige y nunca se hizo: pasar de `corr(x_t, ret_{t+h})`
continua a **event-study de flujo forzado con placebo temporal + muestra matcheada** **[REPO]**.

### 1.2 Qué se probó en esta sesión (reportado por GPT)

| Línea | Resultado reportado | Nota crítica |
|---|---|---|
| RSI14 Reversal | DISCARDED_CATALOG_PARTIAL; neto TV ≈ -0,10 % | catálogo de arreglos incompleto |
| MA Slope Caso 3 (formal, 189 d, 6.763 señales TV) | bruto +0,0205 %, neto -0,0595 %; mejor variante TV -0,0235 % | el +$153 del dashboard eran 2 trades (sin ellos: -$15,03) |
| FVG formal (792 trades TV) | bruto +0,0080 %, neto -0,0720 % | replay con Top-40, scan 15 m, sin vetos BTC/corr ⇒ **no es réplica fiel** |
| Order Block SHORT BTC/ETH | 27 trades todo el rango; 14 trades en 7 meses bajistas; bruto -$1,30 | **muestra diminuta**; no concluye nada fuerte |
| 560 genomas MA/RSI/Bollinger/… | 0 con neto > 0 en TV **y** OOS; ~20 "IMPROVED" solo relativos | "IMPROVED" ≠ rentable |
| Reversión por cascada de liquidaciones | 2.074 trades, bruto -0,0475 %, neto -0,1675 % (costo 0,12 %) | **NO es el protocolo H14 congelado** (ver §2) |

### 1.3 Infraestructura construida **[GPT]**

Vive en worktrees aislados de Windows (`Verge-orchestrator`, `Verge-funding-backfill`) y, según
los reportes, **sin commit**. Componentes: separación TRAIN/VALIDATION/OOS con OOS una sola vez,
catálogo cerrado de variantes (`IMPROVEMENT_FAMILIES.md`, ya en `origin/main`), funding histórico
(`funding_history.db`, ~564 k eventos, 425 símbolos, signo validado solo por ejemplo documental
oficial, **no** empírico), `AuditContext` + trayectorias compactas (candidato completo ~7,8 min),
cola SQLite `research_queue.py` con dedupe y claim atómico, Fábrica sin endpoint de despliegue
(`lab_control_server.py` eliminado), backfill de velas Bybit 5 m (`backfill_liquidation_ohlcv.py`).

### 1.4 Datos propios disponibles (reportado 2026-10-10) **[GPT]**

| Fuente | Estado |
|---|---|
| `orderbook_ofi` (snapshot agregado 20 niveles cada 30 s) | ~28 d, 470 símbolos, **retención intencional de 30 d: se borra solo** |
| `liquidations_research` (Bybit, append-only) | ~32 d, 50 símbolos, mediana de liquidación chica (microcaps) |
| `open_interest` (colector propio) | detenido desde ~11-sep |
| `historical_funding_events` en `klines.db` | 0 filas (el backfill real está en `funding_history.db` del worktree) |
| `scan_ledger.jsonl` | decisiones del agente; **no sirve** como microestructura |

### 1.5 Binance Vision (verificado por mí en vivo, 2026-10-12) **[EN VIVO]**

Listing S3 `data/futures/um/daily/<dataset>/BTCUSDT/`, primer archivo disponible:

| Dataset | Desde | Nota |
|---|---|---|
| `metrics` | 2020-09-01 | OI 5 m + long/short ratios + taker L/S vol (confirmado por el docstring de `download_oi_metrics.py`) |
| `aggTrades` | 2019-12-31 | todos los trades agregados |
| `trades` | 2019-09-08 | crudo |
| `bookDepth` | 2023-01-01 | profundidad por % de precio |
| `bookTicker` | 2023-05-16 → 2024 | mejor bid/ask. **CORRECCIÓN 2026-10-16:** para BTCUSDT hay archivos 2023 y 2024 pero NINGUNO en 2025 ni 2026 (último día exacto no verificado). **No cubre la ventana de investigación (2025-12 → hoy).** Sirve solo para calibrar spread por bucket de liquidez con un período anterior, nunca para medir el período actual. |
| `liquidationSnapshot` | — | **no hay archivos** para um (coincide con `H14_...PROTOCOL.md` §3.3) |

**Verificado después (2026-10-16):** `metrics` llega hasta 2026-10-15; `aggTrades`, `bookDepth` y
`metrics` tienen archivos en 2026 para BTCUSDT.

**No verificado:** cobertura de símbolos distintos de BTCUSDT, tamaños actuales por día. El host `data.binance.vision` (CDN) estaba bloqueado desde mi sandbox
(HTTP 403); solo respondió el listing S3. GPT debe verificarlo desde Windows (§7).

### 1.6 Arquitectura: cómo funciona el sistema construido **[GPT]**

Fuente: reportes de GPT. El código vive en worktrees de Windows y yo no lo leí; tratar esto como
mapa conceptual, no como auditoría del código. Los nombres "Research" y "Máquina" son apodos
informales de GPT, no módulos. Los archivos son los que se indican abajo.

| Pieza | Archivo (según GPT) | Qué hace |
|---|---|---|
| **Candidato** | `candidate.json` + `entries.jsonl` | Estrategia congelada como "revisión 1" inmutable: lista de entradas históricas (símbolo, lado, hora, precio, reglas de SL/TP) + hashes. |
| **Puerta de admisión** | `verify_revision()` | Sin pasar esto no entra a la cola ni al orquestador (Fase A). |
| **Máquina (auditor)** | `lab_audit.py` | Rehace las entradas sobre velas históricas con fees y funding. TRAIN/VALIDATION deciden; OOS se toca una sola vez y solo si TV pasa. Devuelve expectancy bruta y neta, win rate y una severidad 0–100 por categoría (COSTOS, SALIDA, SL, PAYOFF, ENTRADA, TIMEOUT). `main_area` = la que más sangra. Es el diagnóstico de dónde pierde plata. |
| **Orquestador ("Research")** | `research_loop.py` | Automatiza lo que antes decidía GPT a mano. Lee el diagnóstico y ataca las categorías por severidad descendente. Prueba variantes con `variant_id` fijo de un catálogo cerrado (`IMPROVEMENT_FAMILIES.md`): giveback 10/25/50, SL por ATR, TP corto, breakeven, trailing, timeout 12 h, filtros de costo y de entrada (ADX, volatilidad). Cada variante crea una revisión hija inmutable que se re-audita. |
| **Veredictos** | `history.json` | `IMPROVED` (mejora relativa que pasa TV y OOS), corte positivo (TV y OOS con neto > 0; **nunca ocurrió**), o `DISCARDED_CATALOG_PARTIAL` tras 10 intentos fallidos. Las variantes sin ejecutor o sin insumo se marcan `NOT_APPLICABLE_MISSING_INPUT` y no cuentan como intento. |
| **Capa de performance** | `audit_context.py`, `lab_core.py` | Caché LRU de velas y series derivadas (ATR, ADX, rango, vol) y trayectorias compactas por trade de las que se derivan las variantes. Bajó un candidato de ~50 min a ~7,8 min. |
| **Cola (F2)** | `research_queue.py` (SQLite) | Admite solo candidatos válidos, deduplica por `candidate_id`, claim atómico, consumidor que llama al orquestador. 1 worker por límite de memoria (~7 GiB c/u). Estados: PENDING/RUNNING/IMPROVED/DISCARDED/INVALID/FAILED. |
| **Fábrica (F1)** | `evolutionary_lab.py` (ex "Laboratorio Cuántico") | Solo generador: arma genomas de bloques (MA, RSI, Bollinger, ADX, level sweep, ma_pullback…) sobre TOP-40 con máx. una señal por símbolo/día, los materializa y los encola. `lab_control_server.py` (endpoint de despliegue) **eliminado**: no hay camino a producción. |
| **Funding** | `funding_history.py`, `funding_history.db` | Eventos de funding por settlement; cobertura incompleta invalida la auditoría, nunca imputa cero. |

Flujo completo:

```
Fábrica ─► verify_revision ─► Cola ─► Orquestador ◄──► Máquina (TV/OOS + costos + funding)
(genomas)   (puerta)         (SQLite) (elige variante)        │
                                                              ▼
                                    veredicto IMPROVED / DISCARDED ─► revisión humana
                                                                      (nada va solo a producción)
```

Debilidades conocidas y dónde las ataca este roadmap:

| Debilidad | Tarea |
|---|---|
| Costo del pipeline = solo fee de taker (0,08 % RT), sin spread ni slippage | T1.3 |
| Signo del funding validado solo con ejemplo documental, no con cuenta real | T1.4 (queda pendiente Income History real) |
| `IMPROVED` es mejora relativa contra la revisión anterior, no rentabilidad | Gates de Fase 3 |
| Tope de 10 intentos + orden por severidad: categorías enteras nunca se prueban (MA Slope nunca llegó a ENTRADA) | Fase 3 (política de intentos) |
| Sin corrección por comparaciones múltiples en 560 genomas × 10 intentos | Fase 2 y 3 |
| Cada revisión se compara contra la anterior, no acumula transformaciones | Fase 3 |
| Todo el código vive sin commit en Windows | T0.1 |

---

## 2. Correcciones a lo que dije antes en esta sesión

1. **"aggTrades no existe y hay que construir un colector"** — falso. Vision tiene aggTrades
   históricos. No hace falta colector live para empezar.
2. **"aggTrades / order flow es la pieza más prometedora"** — exagerado. H12 (taker flow a 15 m)
   FALLÓ como señal continua **[REPO]**. El valor de aggTrades es condicionado a eventos (H15) y
   para modelar costos, no como señal suelta.
3. **"La hipótesis de liquidaciones está muerta"** — no. Lo que corrió GPT fue una reversión
   incondicional con salida fija a 1 h. El protocolo H14 congelado usa barras de 5 min, spike
   `liq_intensity ≥ p95` + piso $50 k, imbalance ≥ 0,6, horizontes 15/30/60 min, **condicionado al
   signo de dOI**, con placebo y muestra matcheada **[REPO: `H14_LIQUIDATION_CASCADE_PROTOCOL.md`]**.
   La predicción a priori de H14 es que el signo **depende** de si el OI cae; una reversión
   incondicional promedia ambos regímenes y puede dar cero. H14 sigue sin testear en su forma
   congelada.
4. **"Seis hipótesis distintas, todas muertas"** — fueron seis variantes dentro de la familia que
   el repo ya había cerrado. Semanas de esta sesión se gastaron ahí. La causa de proceso: la
   compactación de contexto perdió el ledger. **Regla para toda sesión nueva:** leer primero
   `ALPHA_HYPOTHESIS_LEDGER.md`, `DATA_INVENTORY.md` y `FINAL_DISCOVERY_ROUND47_48.md`.
5. **Costos.** El `0,08 %` roundtrip del pipeline coincide con `TakerFeeRate = 0.0004` × 2 en
   `TradingSimulationService.cs` **[REPO]** — es **solo fee**, sin spread ni slippage. El doc de
   M18 estimó un RT realista de ~26 bp (banda 16–36) para perps menos líquidos **[REPO]**. Hoy el
   pipeline puede estar subestimando el costo real. Hay que medirlo (Fase 1, T1.3).

---

## 3. Tesis

El precio dice dónde está el mercado; el OI y el flujo forzado dicen cuánta posición apalancada
lo sostiene y quién está obligado a salir. Esa información no es derivable de OHLCV. Es el único
plano que el repo nunca testeó con event-study riguroso. Si existe edge retail-accesible, es más
probable ahí que en otro cruce de medias.

Cómo se vería un edge usable **[PROPUESTA]**: eventos de baja frecuencia y movimiento grande
(≥ 15–20 bp netos tras costos reales), no scalps de 3 bp.

### 3.1 Visión profesional **[PROPUESTA]**

1. **El sistema es un motor de falsación, no un inventor de estrategias.** Solo prueba retoques
   paramétricos de un catálogo chico. Si el edge bruto es cero o negativo (RSI14), ningún retoque
   lo arregla. Que diga "no" seguido es lo esperable; su valor es que no miente.
2. **La arquitectura está bien; el combustible no.** La Fábrica genera combinaciones de
   MA/RSI/Bollinger, una familia que el repo ya había declarado agotada. En los 560 genomas, 0
   tuvo neto positivo en TV y OOS.
3. **El orden correcto es mecanismo → máquina → fábrica.**
   - Un event-study con placebo decide si existe un mecanismo (OI y flujo forzado, Fase 2).
   - La Máquina audita reglas concretas con costos realistas.
   - Recién ahí la Fábrica genera parametrizaciones de un mecanismo ya validado, no indicadores
     al azar.
4. **Tres capas con responsabilidades separadas:**
   - A. Hipótesis/event-study: ¿existe el efecto, sobrevive al placebo y a la corrección múltiple?
   - B. Máquina + orquestador: ¿una regla concreta sigue siendo rentable tras costos realistas
     y OOS único?
   - C. Forward en simulación: ¿se sostiene con fills y spreads reales?
5. **Mejor uso de la Máquina:** puerta obligatoria para cualquier estrategia candidata, nueva o
   ya existente en StrategyProfiles, antes de arriesgar plata. No como generadora masiva.
6. **Disciplina de ensayos:** cada genoma y cada variante cuenta como un test. Sin ese
   contador, 40.000 combinaciones siempre van a producir "ganadoras" por azar (R45).

---

## 4. Mapa por fases

### Fase 0 — Mismo día: proteger lo construido

- **T0.1 Commit y push de la infraestructura** de ambos worktrees a una rama dedicada. Incluir
  código y tests; excluir artefactos generados (`research_loop*/`, `research_factory*/`, DBs,
  logs). Aceptación: rama en `origin`, `git status` limpio salvo artefactos ignorados.
  Riesgo actual: todo ese trabajo existe solo en un disco local **[GPT]**.
- **T0.2 Frenar el borrado automático de datos propios.**
  - OFI: retención de 30 d ⇒ exportar/copiar antes de que se pode, o subir `keep` a ≥ 400 d.
  - Liquidaciones: mantener vivo `liquidations_research`; verificar `liq_collector_health`;
    agregar supervisión (heartbeat + reinicio si no escribe > 10 min).
  - Ampliar universo de liquidaciones a BTC/ETH/SOL + top ~100 perps de Bybit por volumen 24 h
    (H14 §4). Hoy son 50 símbolos sesgados a microcaps.
  Aceptación: reporte diario de cobertura/gaps por símbolo.
- **T0.3 OI en vivo:** opcional. Con Vision cubriendo OI histórico, solo hace falta si Vision
  tiene demasiado rezago. Decidir tras T1.1.

### Fase 1 — Días 1–3: base de datos desde Vision (sin esperar)

- **T1.1 Cobertura de Vision.** Para ≥ 200 perps líquidos (universo definido **ex-ante** y
  guardado en `research/universe/` antes de mirar resultados): rango de fechas de `metrics`,
  `aggTrades`, `bookTicker`, último día publicado. Entregable: JSON de cobertura por símbolo.
- **T1.2 OI histórico.** Verificar si `oi_metrics` existe y qué tiene en
  `binance_vision_clean.db`. Si falta o termina el 2026-08-17: correr
  `agent/download_oi_metrics.py --backfill` extendiendo `OIM_D1` al último día disponible.
  QA obligatorio (copiar el esquema de H12): timestamps monótonos y alineados :00/:05, sin
  duplicados, cobertura por símbolo, y **regla anti-lookahead**: confirmar si `create_time` marca
  el fin o el inicio del bucket; si hay duda, usar un lag de un bucket (5 min), como ya hace
  `OPEN_INTEREST_COLLECTOR.md`.
- **T1.3 (nota 2026-10-16):** `bookTicker` de Vision no cubre 2025–2026. Camino real: (a) colector
  propio de bid/ask hacia adelante (~15 días para una base honesta); (b) mientras tanto, bandas de
  costo de sensibilidad (p. ej. 10 / 26 / 36 bp RT, como en M18), nunca spreads inventados.
  El event-study de Fase 2 mide el efecto **bruto** frente a placebo y control matcheado, que NO
  depende del costo: se corre ya, con veredicto de mecanismo separado del veredicto económico.
- **T1.3 Modelo de costos v2 con `bookTicker`.** Muestreo ex-ante: top-30 + 30 medios + 30
  ilíquidos por volumen, ~15 días repartidos en regímenes distintos (no todo el rango). Procesar
  un zip a la vez, **agregar en streaming** (spread efectivo mediano/p90 por símbolo y hora, tamaño
  top-of-book) y descartar los ticks crudos — el volumen es grande. Entregable: tabla
  `spread_stats` y una función `cost_bps(símbolo, hora)` conservadora. Desde acá toda auditoría
  usa `max(fee, cost_v2)`.
- **T1.4 Funding.** Reusar `funding_history.db` (425 símbolos); extender hasta la fecha final y
  persistir cobertura. Mantener la etiqueta "validación documental, no empírica" hasta tener
  Income History real.
- **T1.5 Panel de investigación único.** Un constructor de dataset a 5 m/15 m/1 h con precio,
  taker_flow, OI, ratios L/S, funding y (cuando exista) features de liquidación, todo alineado
  causalmente. Incluir tests de lookahead (desplazar series y verificar que el resultado no
  mejora).

### Fase 2 — Días 3–10: event-studies congelados (no inventar protocolos nuevos)

Usar los protocolos ya escritos en el ledger. Orden:

1. **H17 como sanidad del pipeline** (solo OHLCV, prior LOW). Si da un efecto grande, sospechar
   bug antes de celebrar.
2. **H13** (OI/precio, 4 cuadrantes; foco C: precio↓ + OI↑, 1–4 h). Parámetros del piloto ya
   congelados (barra 1 h, lookback 4 h, z rolling 7 d, umbral |z| ≥ 1, cooldown 4 h, placebo
   +48 h, control matcheado, bootstrap por símbolo). Sin grid.
3. **H15** y **H16**, reusando el mismo pipeline.
4. **H20** solo si H13 da señal.

Controles mínimos en todos: placebo temporal; muestra matcheada (misma vol y retorno previo, sin
evento); residualizar contra retorno pasado; bootstrap por símbolo; mitades temporales;
partición por régimen BTC; quitar los k mejores eventos/símbolos; costo v2.

**Criterios [PROPUESTA]** (fijarlos por escrito antes de correr):

- Mínimo 300 eventos y 30 símbolos por celda evaluada; si no, "muestra insuficiente", no se baja
  el umbral.
- Ningún símbolo > 20 % de los eventos; top-5 símbolos ≤ 50 %.
- Efecto incremental sobre el control matcheado con IC que excluya 0 en ambas mitades.
- Neto ≥ +15 bp tras `cost_v2`, y ≥ +10 bp quitando el 5 % superior de eventos.
- Corrección por comparaciones múltiples (BH, q = 0,05) sobre la familia pre-registrada
  `{H13 × cuadrantes × horizontes, H15, H16, H17, H18}`.
- Resultado ∈ {PASS, PARK, FAILED}. **FAILED cierra la hipótesis; no hay H13.1 de rescate.**

### Fase 3 — Solo si hay PASS o un PARK fuerte: convertirlo en estrategia

- Escribir el adaptador del evento en `research_loop` y correr el orquestador/cola con una
  Fábrica v2 cuyo espacio de búsqueda sea **la regla de evento** (umbrales × horizonte × salida,
  grilla chica y congelada), no genomas MA/RSI/Bollinger.
- Contar **cada genoma como un test** para la corrección múltiple (R45 probó 40.000 combinaciones:
  encontrar 1–2 "positivas" ahí era azar esperable **[REPO]**).
- Gates: TV decide, OOS una sola vez, quitar top-3 trades, 2º split independiente, motor de
  portafolio real (capital 450, 3 slots compartidos — ya hubo un bug que daba 3 slots por símbolo
  y sobreestimaba 4,8× **[REPO: PROGRESS_LOG 2026-08-03]**).
- Política de intentos del orquestador **[PROPUESTA]**: no declarar `DISCARDED` por tope de 10
  intentos sin haber probado al menos una variante de cada categoría que tenga ejecutor; y
  completar los ejecutores faltantes (salidas multiseñal, `exit_atr_trail_0_5_after_1r`,
  `exit_ema50_close_trail`) o registrar explícitamente el veredicto como catálogo parcial.
- Distinguir en `history.json` `catalog_completeness: COMPLETE | PARTIAL` y la lista de variantes
  sin ejecutor (hoy solo dice `DISCARDED_CATALOG_PARTIAL`).

### Fase 4 — Solo con Fase 3 en PASS: forward en simulación

3–4 semanas con el agente en simulación/testnet. Comparar fills y spreads reales vs. el modelo.
Recién después discutir tamaño real mínimo. **Mainnet no antes de esto.**

### Kill criteria

- H13, H15 y H16 en FAILED tras corrección múltiple ⇒ cerrar la búsqueda direccional en este
  universo de datos. Documentar en `ALPHA_HYPOTHESIS_LEDGER.md` y parar.
- Si `cost_v2` (T1.3) resulta ≥ 2× el fee actual, recalcular los vetos previos: algunos "casi
  rentables" quedarían definitivamente muertos y conviene saberlo.

### Calendario de H14 (solo hacia adelante)

Liquidaciones no tienen historia en Vision ni backfill gratuito **[REPO]**. Con la recolección
desde ~2026-09-09: ≥ 60 d ≈ **2026-11-08**, 90 d ≈ **2026-12-08** **[PROPUESTA: aritmética mía]**.
Los símbolos añadidos en T0.2 reinician su propio reloj. El test formal usa el protocolo congelado
de 5 min, no el que corrió GPT esta sesión.

---

## 5. Economía mínima

Para $150/mes con 300 trades/mes de $300 de nocional se necesitan ≈ **+16,7 bp netos por trade**
(150 / (300 × 300) = 0,00167) **[PROPUESTA: cálculo mío]**. Es consistente con los objetivos de
≥ 15–20 bp netos de H13–H16 **[REPO]** y explica por qué +0,02 % bruto no alcanza nada.
Piso histórico del proyecto citado en el repo: $150/mes sobre $450 con 3 slots.

---

## 6. Trampas ya conocidas (no repetir)

- Dependencia de outliers: MA Slope mostraba +$153 y eran 2 trades. Siempre reportar sin top-1
  y sin top-2.
- Trades "reconstruidos": ~99 % de `SimulatedTrades` viene del import legacy `trades.csv`; no
  usarlos como evidencia viva **[REPO: R44]**.
- `Status=1` en `SimulatedTrades` significa "cerrado por TP", no "cerrado" **[REPO: R45]**.
- Lookahead por `updated_at` en `klines.db`; usar `open_time` y `is_final=1` **[REPO]**.
- Archivos SPOT de Vision en microsegundos **[REPO]**.
- Mezclar venues: liquidaciones de Bybit con OI de Binance (documentar la limitación) y no
  mezclar velas de otro venue para el PnL.
- El replay de FVG con universo/paso/vetos distintos a producción no es evidencia sobre FVG.

---

## 7. Preguntas abiertas / checklist de verificación para GPT

1. ¿Qué hay realmente en `oi_metrics` (si existe) y hasta qué fecha?
2. Vision: último día publicado de `metrics`/`aggTrades`/`bookTicker`; cobertura por símbolo;
   tamaño real de un día de `bookTicker` hoy para BTC y para un alt.
3. Semántica de `create_time` en `metrics` (¿cierre o inicio del bucket?).
4. ¿El universo de OI incluye BTC/ETH/SOL? (el piloto dice que no; el inventario dice que los
   majors tienen ~100 %: hay contradicción en el repo).
5. `git status` de ambos worktrees: qué archivos son código y cuáles artefactos.
6. Qué worktree/rama contiene cada módulo (esta sesión no pudo verificarlo).
7. Si algo de este documento contradice el código real, **gana el código**; corregir este archivo.

---

## 8. Primer prompt para GPT (copiar y pegar)

```
Lee en este orden: ROADMAP_ALPHA_MICROESTRUCTURA.md, ALPHA_HYPOTHESIS_LEDGER.md (H13–H20),
DATA_INVENTORY.md, H13_PILOT_REPORT.md, H14_LIQUIDATION_CASCADE_PROTOCOL.md,
FINAL_DISCOVERY_ROUND47_48.md. No repitas ninguna familia marcada agotada.

Ejecuta SOLO la Fase 0 y la Fase 1 del roadmap, en ese orden, y reporta al terminar cada tarea:
T0.1 commit/push de la infraestructura (sin artefactos), T0.2 frenar el borrado de OFI y
supervisar liquidaciones, T1.1 cobertura de Binance Vision, T1.2 OI histórico (verifica primero
qué hay en oi_metrics), T1.3 modelo de costos v2 con bookTicker, T1.4 funding, T1.5 panel único
con tests de lookahead.

Reglas: define el universo y los criterios por escrito ANTES de mirar resultados; no toques el
agente vivo, ledger, StrategyProfiles ni producción; no actives mainnet; si algo del roadmap
contradice el código real, gana el código y corrige el archivo; todo lo no verificado se
reporta como "no verificado". No empieces la Fase 2 sin que Nico lo apruebe.
```

---

## 9. Mapa de fuentes en el repo

`ALPHA_HYPOTHESIS_LEDGER.md` · `DATA_INVENTORY.md` · `H12_TAKER_FLOW_TEST.md` (en `agent/`) ·
`H13_PILOT_REPORT.md` · `H14_LIQUIDATION_CASCADE_PROTOCOL.md` · `M18_KILL_OR_CONFIRM_ROUND8.md` ·
`FINAL_DISCOVERY_ROUND47_48.md` · `agent/OPEN_INTEREST_COLLECTOR.md` ·
`agent/download_oi_metrics.py` · `.claude/PROGRESS_LOG.md` · `IMPROVEMENT_FAMILIES.md` y
`RESEARCH_IMPROVEMENT_SOURCES.md` (en `origin/main`, commit `0473be3`).
