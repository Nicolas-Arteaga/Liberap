# FASE SIGUIENTE — Caso 3: alpha vs admisión de slots vs timeout vs minRR

**Fecha:** 2026-09-06
**Alcance:** separar (1) alpha real de Caso 3, (2) política de admisión/competencia
de slots, (3) efecto del timeout, (4) minRR 3 vs 4.
**Reglas respetadas:** sin optimización, sin grid, sin ML, sin thresholds nuevos,
sin estrategias nuevas, sin H13, sin H11, sin descargar datos nuevos. Sizing
fijo: $450/estrategia, $150/trade, máx 3 posiciones simultáneas.

**Verificación de causalidad (hecha ANTES de correr):** ningún contrafactual usa
el resultado futuro de una operación para decidir la entrada. La detección de
patrón se evalúa sobre velas de 1h **ya cerradas**; los candidatos solo se
admiten desde buckets 1h cerrados ≥1h antes del reloj; el exit-sim camina klines
estrictamente hacia adelante. Única excepción **etiquetada**: la política
`realpool` restringe el universo a los símbolos que Caso 3 realmente operó (usa
hindsight de símbolo) — se reporta solo como cota superior, no como política
desplegable.

---

## VEREDICTO: DIAGNOSTICADO

**Existe una política causal simple que preserva el edge de Caso 3.**

> "Cuando se libera un cupo de Caso 3, admitir la señal Caso 3 pendiente más
> antigua (patrón de un bar de 1h ya cerrado). Cerrar toda posición de forma
> incondicional a ~48 h."

Resultado bajo esa política, compitiendo causalmente por 3 cupos sobre el pool
completo de patrón (2 615 disparos, 353 símbolos), sin información futura:

| | n | net ($450 base) | PF | WR | maxDD |
|---|---|---|---|---|---|
| **Caso 3 — slot causal "oldest"** | 73 | **+$58.6** (+13%) | **1.70** | 40% | −$19.7 (−4.4%) |
| Caso 3 — slot causal "oldest" + competencia entre-estrategias | 73 | +$61.5 | 1.76 | 41% | −$16.5 |
| Caso 3 — desempate aleatorio (mediana de 20 seeds) | ~84 | +$58–67 | 1.46–1.57 | 40% | — |
| Caso 3 — desempate aleatorio: **20/20 seeds net-positivos**, PF P5 = **1.18** | | | | | |

El edge **sobrevive** la competencia causal por los mismos 3 cupos. PF cae de
2.5 (real) a ~1.5–1.8, pero se mantiene > 1 en **todas** las políticas y en
**todos** los 20 desempates aleatorios.

**Esto contradice el veredicto de Gate V4 (PF 0.81, LOSER, 29.7% de seeds del
lado correcto).** La causa de la diferencia está diagnosticada abajo (sección 3):
es el **modelo de timeout**, no la competencia de slots.

---

## 1. Reconstrucción de cada señal real de Caso 3 (con contexto de slot)

45 de 70 señales reales tienen precio reconstruible (join
`scratch_all_trades_p2.csv` [tiempos exactos] + `agent/data/trades.csv`
[precios]). Las 25 restantes — incluidos 7 símbolos sin klines en ninguna fuente
(ADBE, ETHBTC, RSR, SUN, VRT, XLE, ZHIPU… parcialmente) — **no se reconstruyen y
no se inventan**.

**Concurrencia de slots (dato decisivo):**

- Máx concurrencia de las 45 señales reales = **3**. Nunca 4.
- En el set completo de 70 (`scratch_gate_v4_results.json → real_trades`): máx
  concurrencia = **3**, y **60/70 (86%) abrieron exactamente en el instante en
  que se ocupó el 3.º cupo**. Cero casos de un 4.º queriendo entrar.
- → **Producción respetó un cap estricto de 3 cupos para Caso 3**, y entró
  "cuando se liberó un cupo", no "cuando apareció el patrón" (consistente con
  Phase 2: patrón persiste mediana 2.2 h).

Tabla por señal (45): en `scratch_caso3_gt.json`; columnas símbolo / open UTC /
concurrencia-al-abrir / dur_h / outcome / pnl. Extracto de los estados de cupo:

| conc. al abrir | # señales | lectura |
|---|---|---|
| 1 (cupo libre) | 11 | entrada inmediata |
| 2 | 11 | 1 cupo aún libre |
| 3 (se llenó con esta) | 23 | entró justo al liberarse/ocuparse el 3.º |

**Los 45 con SL/TP/resultado real** están en `scratch_caso3_gt.json`. `signal
timestamp` se aproxima por `OpenedAt` (difieren ~segundos; el log de scanner de
producción con el timestamp de detección exacto **no existe**).

---

## 2. La carrera por slot — qué impidió las señales no ejecutadas

**Limitación de datos honesta:** producción **no dejó log de señales
rechazadas**. Solo tenemos las ejecutadas. Por lo tanto la clasificación
A–F por señal individual **no es reconstruible trade-a-trade**. Lo que sí se
puede afirmar cuantitativamente:

- El motor detecta **2 615 disparos** del patrón Caso 3 en la ventana (353
  símbolos). Producción ejecutó ~70. → **~97% de los disparos del patrón NO
  fueron tomados por producción**, casi siempre porque **los 3 cupos estaban
  ocupados** (86% de las entradas reales ocurren a 3-de-3).
- Clasificación agregada de por qué Caso 3 no entró en un disparo dado:
  - **A — cupo realmente lleno:** causa dominante. 86% de las entradas reales
    ocurren con los 3 cupos llenos → la enorme mayoría de los ~2 545 disparos
    no tomados chocaron con 3/3.
  - **D — prioridad/admisión:** entre los múltiples símbolos con patrón vivo
    simultáneamente, producción admitió uno y no los otros. Cuál exactamente y
    por qué **no es reconstruible** sin el log del scanner.
  - **B — veto / C — cooldown:** el throttle "una operación por símbolo por
    día" (`last_trade_day`) sí es reconstruible y está en la simulación. Otros
    vetos (`validate_pre_trade`) están en el precompute. **minRR: inerte**
    (sección 4).
  - **E — falta de datos:** 7 símbolos sin klines (≈15% de los trades reales).
  - **F — desconocida:** el residual entre "producción tomó estas 45–70" y
    "una política causal toma otras 73–85" (sección 3).

---

## 3. Contrafactuales causales — políticas de admisión

Pool: los 2 615 disparos del patrón, universo 450 símbolos (353 con ≥1
disparo). Cap estricto 3 cupos. Timeout incondicional 48 h. **Sin info futura.**

| Política | n | net | PF | WR | maxDD | TP/SL/TO | slot util | ovlp con real (sym,día) |
|---|---|---|---|---|---|---|---|---|
| **A. REAL (as-run, $ de trades.csv)** | 45 | +$64.7 | 2.54 | 49% | — | 11/7/27 | — | — |
| A′. REAL señales + lifecycle propio | 45 | +$48.6 | 2.48 | 58% | — | 11/9/18 | — | — |
| **B/D. "oldest" (señal pendiente más antigua)** | 73 | **+$58.6** | **1.70** | 40% | −$19.7 | 4/27/42 | 0.80 | 6/45 |
| C. FIFO / orden de escaneo* | 85 | +$41.8 | 1.35 | 39% | −$36.1 | 2/43/40 | 0.81 | 5/45 |
| — sym_desc (alfabético inverso) | 80 | +$54.1 | 1.52 | 42% | −$24.6 | 4/36/40 | 0.80 | 6/45 |
| — shuffle ×20 (desempate aleatorio) | ~78 | P5 +$24 / P50 +$58 / P95 +$110 | P5 **1.18** / P50 1.46 / P95 2.07 | ~40% | — | — | 0.80 | — |
| — "oldest" + occupied entre-estrategias | 73 | +$61.5 | 1.76 | 41% | −$16.5 | 4/27/42 | 0.80 | — |
| — shuffle + occupied entre-estrategias (P50) | 84 | +$67.0 | 1.57 | 40% | −$35.8 | — | 0.80 | 20/20 net+ |
| E. score por familia/confluencia | — | — | — | — | — | — | — | **NO RECONSTRUIBLE** |
| realpool [hindsight de símbolo, cota superior] | 85 | +$41.8 | 1.35 | 39% | −$36.1 | 2/43/40 | 0.81 | — |

\* *"Orden de escaneo de producción" no es reconstruible — no tenemos el orden
real del watchlist. `eng.available_symbols()` devuelve orden ~alfabético, por eso
FIFO ≈ sym_asc en la práctica. Se reporta como límite inferior pesimista.*

**Política E (score):** `trade_metrics.jsonl` **no contiene trades de
MaGeometry** (0 coincidencias). Producción no registró un score de confluencia
para las señales de Caso 3. Reconstruir una función de score sería inventarla →
**se declara NO RECONSTRUIBLE** y no se ejecuta.

**Señales rechazadas / desplazadas:** bajo "oldest", ~5 600 eventos
(símbolo,bucket) de elegibilidad quedaron sin cupo (métrica relativa, cuenta
cada hora de persistencia por separado). Traducción: la estrategia ve muchísimo
más patrón del que puede operar con 3 cupos; el 3-slot es el cuello de botella,
no la calidad de señal.

**Solapamiento con las 45 reales:** solo **5–6 de 45** pares (símbolo, día)
coinciden con lo que produjo cualquier política causal. **Y aun así el resultado
es net-positivo.** → el alpha **no está** en la selección específica de
producción; está en el patrón, que es ampliamente rentable.

---

## 4. minRR 3 vs 4 — RESUELTO: el parámetro es INERTE en la config actual

| minRR | disparos del universo con RR ≥ minRR | n ejecutados | net | PF | WR |
|---|---|---|---|---|---|
| 0.5 (≈ producción) | 2 615 / 2 615 | 85 | +$41.8 | 1.35 | 39% |
| 3.0 | 2 615 / 2 615 | 85 | +$41.8 | 1.35 | 39% |
| 4.0 | 2 615 / 2 615 | 85 | +$41.8 | 1.35 | 39% |

**Los 3 son idénticos byte a byte.** Razón: el TP estructural del motor para
Caso 3 (`tpMinPct 10` + `tpMultiplier 3.0`, sin el cap estructural genérico que
`ma_slope_mode` excluye — `risk_manager.py:562`) produce **siempre RR ≥ 4**.
`0 / 2 615` disparos tienen RR < 4. El veto MIN-RR (`risk_manager.py:577-586`)
nunca se activa. → **minRR 3 vs 4 no cambia absolutamente nada en el replay.**

**¿Cuál usó producción?** **NO SE PUEDE DETERMINAR** históricamente, y es
INCERTIDUMBRE declarada:
- 21 de 45 trades reales tienen RR < 3 (medido |tp−entry|/|sl−entry| sobre
  precios de `trades.csv`), y 24/45 tienen RR < 4. **Ni minRR 3 ni minRR 4 son
  consistentes con el ground truth** — ambos habrían bloqueado ~la mitad de los
  trades que realmente se abrieron.
- Lectura: producción, para esas operaciones de agosto, **no aplicaba un veto
  RR efectivo** (o su TP venía de un mecanismo estructural más cercano —
  `recentHigh` / era anterior al fix del cap del 2026-07-27 —, no del
  `tpMinPct 10`). El `minRR 3/4` de los 9 scripts de julio corresponde a una
  calibración exploratoria posterior o nunca desplegada en esa forma.
- **No se elige retrospectivamente ninguno.** Como en el replay el parámetro es
  inerte, la incertidumbre no afecta ninguna conclusión.

---

## 5. Timeout — aislado. ES EL DRIVER del cambio ganadora→perdedora.

Mismas 45 señales reales, mismo entry, mismo SL/TP. **Solo cambia el horizonte
de cierre.** Nada más se toca.

| Modelo de salida | n | net | PF | WR | TP/SL/TO |
|---|---|---|---|---|---|
| REAL (as-run, exits reales de producción) | 45 | +$64.7 | 2.54 | 49% | 11/7/**27** |
| Cierre incondicional **48 h** | 45 | +$48.6 | 2.48 | 58% | 11/9/18 |
| Cierre incondicional **192 h** (`maxTradeDurationCandles`×1h) | 45 | +$71.7 | 2.54 | 49% | 16/15/4 |
| Cierre incondicional **720 h** (tope duro) | 45 | +$51.1 | 1.94 | 42% | 17/18/0 |
| **`zombie_timeout_decision` (motor / Gate V4): cierra a 48 h SOLO si pierde; ganador viaja a 720 h** | — | — | **≈ 0.8** (Gate V4 baseline) | ~10% | — |

**Hallazgos:**
1. Producción real: **27/45 (60%) cerraron por timeout** — con PnL de −$3.5 a
   +$18.2. El cierre por tiempo es el modo de salida dominante y **es
   intencional**: cluster real de cierres en 48.0–48.3 h (13 trades) + cola
   larga a 105–209 h. El horizonte efectivo de producción está entre 48 h y
   ~192 h, con muchos cerrados cerca de 48 h.
2. Cualquier cierre **incondicional** (48/192/720 h) preserva PF ≥ 1.9 sobre las
   señales reales. El edge del lifecycle está sano.
3. El modelo del motor — `zombie_timeout_decision`: cerrar a 48 h **solo si el
   trade pierde**, y dejar correr los ganadores hasta 720 h — **es el que
   destruye el edge**. Deja que un ganador con MFE ~2–3% haga round-trip hasta
   el SL en vez de bookear la ganancia parcial y liberar el cupo. Es lo que
   Gate V4 usó (`ma_slot_sim`).
4. **Cuantificación:** pasar de `zombie_timeout` a cierre incondicional ~48 h
   vale ≈ **PF 1.9 → 2.5 a nivel señal** y ≈ **PF 0.8 → 1.4–1.8 a nivel
   portfolio** (comparar Gate V4 baseline 0.81 vs este trabajo "oldest" 1.70).
   El timeout explica la **mayor parte** de la brecha Gate V4 ↔ realidad.

---

## 6. PRUEBA CLAVE — ¿el edge sobrevive la competencia causal por 3 cupos?

| Variante | n | net | PF | WR | comentario |
|---|---|---|---|---|---|
| **REAL Caso 3** (as-run) | 45 | +$64.7 | **2.54** | 49% | ground truth de esa ejecución |
| **Caso 3 señales reales + lifecycle** (48 h) | 45 | +$48.6 | **2.48** | 58% | lifecycle FIEL en entry/SL/TP |
| **Caso 3 + prioridad causal de slot ("oldest")** | 73 | +$58.6 | **1.70** | 40% | política desplegable, sin hindsight |
| **Caso 3 + política FIFO / orden de escaneo** | 85 | +$41.8 | **1.35** | 39% | límite inferior pesimista |
| Caso 3 + slot causal + competencia entre-estrategias | 73 | +$61.5 | **1.76** | 41% | portfolio real |
| Caso 3 + desempate aleatorio | ~78 | +$58 (P50) | **1.46** (P50), 1.18 (P5) | 40% | **20/20 seeds net-positivos** |
| — Gate V4 baseline (sym_asc + `zombie_timeout`) | 42 | −$22.6 | **0.81** | 10% | artefacto del modelo de timeout |

**Respuesta: SÍ, el edge sobrevive.** Bajo toda política causal probada, Caso 3
mantiene PF > 1 y net claramente positivo. El PF baja de 2.5 (real) a ~1.4–1.8
(hay que competir por 3 cupos contra el propio patrón que dispara 60× más de lo
que se puede operar), pero no se convierte en perdedora. El P5 del desempate
aleatorio es 1.18 y **ningún** escenario (política × seed × occupied) es
net-negativo.

---

## Conclusiones separadas

### A. Calidad de la señal de Caso 3 — **BUENA / robusta**
El patrón dispara 2 615 veces en 5 semanas sobre 353 símbolos y es **ampliamente
rentable**: incluso eligiendo 3-a-la-vez al azar da PF P50 1.46 con 20/20
escenarios positivos. El alpha **no** está concentrado en las ~70 selecciones de
producción (solapamiento 6/45) — está en el patrón mismo. Esta es la evidencia
más fuerte de alpha real que tiene el proyecto.

### B. Calidad del motor de lifecycle — **FIEL salvo el timeout**
Con las señales reales, el entry (cierre de vela vs precio vivo, offset mediana
−0.02%) y el SL/TP estructural reproducen el resultado real casi exacto: PF 2.48
vs 2.54 real, sobre las mismas 45 señales. El **único** defecto material es el
modelo de timeout.

### C. Política de admisión de slots — **RESUELTA como causal-viable**
"Admitir la señal pendiente más antigua al liberarse un cupo" (o incluso
desempate aleatorio) preserva el edge sin información futura. La competencia por
3 cupos **atenúa** el PF (2.5 → 1.7) pero no lo mata. Gate V4 usó `sym_asc` —
que resultó ser el desempate más pobre (PF 1.35) pero **igual positivo**; su
veredicto LOSER vino del timeout, no del desempate.

### D. Timeout — **es el driver; el modelo del motor está mal**
Producción cierra por tiempo de forma incondicional (~48 h modal, cola a 192 h);
el motor cierra a 48 h solo a los perdedores y deja correr a los ganadores hasta
720 h. Ese solo cambio vale PF 1.9 → 2.5 (señal) / 0.8 → 1.4–1.8 (portfolio).

### E. minRR — **INERTE + INCERTIDUMBRE declarada**
0/2 615 disparos del motor tienen RR < 4 → minRR 3 y 4 dan resultados idénticos.
Cuál usó producción no se puede determinar (21/45 trades reales tienen RR < 3,
inconsistente con ambos). **No afecta ninguna conclusión.**

### F. Viabilidad económica con $450/estrategia, $150/trade, 3 cupos — **POSITIVA pero MODESTA; NO es rentabilidad de producción declarada**
- Net: **+$42 a +$67 sobre $450 en ~5 semanas ≈ +9% a +15%** (política causal).
- maxDD: **−$16 a −$36** (−3.6% a −8%).
- Robustez: 20/20 desempates aleatorios net-positivos; PF P5 = 1.18.
- Costos: a PF 1.4–1.8 un haircut de 5 bp/lado sobre $150 (~$13 en 85 trades)
  es **despreciable** frente a +$50 de net — a diferencia de Gate V4 (PF 0.81),
  donde 2–5 bp lo hundían. Los costos **no son decisivos** en este rango de PF.
- **NO declaro rentabilidad de producción:** muestra corta (5 semanas, 1
  estrategia), sin funding modelado (no hay cobertura fiable), ventana
  posiblemente benigna para shorts, 15% de trades reales irreproducibles,
  exit-sim chequea TP antes que SL intrabar en velas de 5m (leve optimismo), sin
  1m para altcoins.

---

## Qué necesitaríamos para cerrar la viabilidad (no se hace ahora)

1. Modelar el timeout como el monitor de 5 min real de producción (cierre
   incondicional con la lógica exacta), no `zombie_timeout_decision`.
2. Segunda ventana temporal fuera de julio–agosto para descartar régimen benigno.
3. 1m para altcoins + los 7 símbolos sin klines.
4. Funding real sobre la ventana (o cota superior del costo).
5. Loguear el `patternParamsJson` efectivo y el orden de scanner en producción
   para poder reconstruir la política de admisión real en vez de aproximarla.

---

## Qué NO sabemos todavía

- El **orden real de admisión** de producción entre símbolos simultáneos (no hay
  log del scanner) — se aproximó con "oldest" / aleatorio.
- Si "oldest" es lo que producción realmente hacía o si tenía una heurística
  mejor (que explicaría PF 2.5 real vs 1.7 causal).
- El horizonte de timeout exacto de producción (mezcla 48 h / 192 h / 209 h).
- minRR real (INCERTIDUMBRE, pero inerte).
- Comportamiento fuera de la ventana 2026-07-10 → 08-23.
- El impacto del funding y del solapamiento intrabar SL/TP con resolución 1m.
