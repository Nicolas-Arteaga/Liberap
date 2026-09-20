# MISIÓN: Laboratorio de Diagnóstico de Estrategias (Verge)

> Este documento es la única fuente de verdad de la misión actual. Si algo del chat lo contradice, gana este documento. Si creés que está mal, decilo y esperá respuesta; no lo reinterpretes en silencio.

## 0. Contexto y período de prueba

Tu trabajo de los días 18–20/09 fue auditado por otra IA (Claude) a pedido del usuario. Conclusión, sin adornos:

**Lo que hiciste bien (conservar):**
- Honestidad al rechazar hipótesis (pares, funding, OI) y bloquear liquidaciones por falta de cobertura. No forzaste candidatos.
- Diagnosticaste la causa raíz de la lentitud (el backtest reutilizaba el lector de MA de producción que consultaba Binance por punto temporal) y la arreglaste con un replay cacheado: de 6–8 h a ~2,5 min.
- Detectaste que MA Slope Caso 3 quedó como configuración reconstruida tras el reset de Docker, y pusiste la regla correcta: si el simulador no reproduce la baseline real, no se optimiza nada.

**Dónde te desviaste (corregir):**
1. Construiste VIRE, otro descubridor de estrategias (pares, funding, OI, liquidaciones sobre 400 símbolos). Es el mismo enfoque de los ~48 rounds previos que no dio nada, y en 3 días dio 0 candidatos. Lo que el usuario necesita es una **máquina de diagnóstico**, no otro buscador.
2. Tus porcentajes de avance (45% → 60% → 88%) no eran comparables entre sí, mientras "hacia candidato" estuvo clavado en 20–25%. Un porcentaje que no se puede verificar no es información.
3. Mandaste heartbeats vacíos ("sin cambios"), no avisaste cuando una corrida terminó, y respondiste sobre el ranking de estrategias leyendo la capa equivocada (`source = Nexus`, que es el motor y no una estrategia).
4. Construiste un replay nuevo y rápido **sin calibrarlo contra trades reales**. Un motor más rápido pero no validado es un motor rápido que puede mentir.

**Estás a prueba.** El usuario compara tu trabajo contra el de Claude Code. Cada afirmación tuya será contrastada contra archivos y logs. Un número sin fuente verificable cuenta como error.

## 1. Objetivo (una frase)

Construir dentro de Verge una máquina que, dada una estrategia existente, **explique con evidencia por qué gana o pierde y en qué componente exacto está el problema**: entrada (dirección/señal), salida (TP/trailing/giveback), stop loss, timing, símbolo o régimen. No se busca que encuentre estrategias nuevas ni que garantice rentabilidad.

Origen del requisito: si una estrategia da negativa, no se puede saber si falla la entrada o la salida sin aislar variables. Ejemplo real: 153 trades llegaron a ≥ +30 USDT flotantes y devolvieron casi todo. Eso es una salida mala sobre una entrada que quizá tiene edge, y un test de tipo "toca TP o SL" lo descarta sin verlo.

## 2. Alcance

**Dentro:** MA Slope Caso 3 y Band Touch 15m (las dos únicas que se mantienen positivas en real). Motor de replay, calibración, matriz de diagnóstico, informe y UI.

**Fuera (prohibido tocar):**
- VIRE / búsqueda de hipótesis nuevas. Congelado; no lo borres ni lo extiendas.
- Producción: `StrategyProfiles`, el agente, paper, live. Solo lectura.
- Nuevas fuentes de datos, nuevas familias de señales, ML.
- Las otras 14 estrategias (pueden entrar luego, no ahora).

## 3. Reglas de trabajo (no negociables)

**R1. Nada de números sin fuente.** Todo número que reportes viene de un archivo o comando que dejás indicado (ruta + comando). Distinguí siempre *medido* de *inferido*. Si no lo medí, digo "no medido".

**R2. Gates con umbrales fijados antes de correr.** Los umbrales de cada fase están abajo. No los cambies después de ver resultados. Si creés que uno está mal, proponé el cambio y esperá respuesta antes de correr.

**R3. Un fallo se reporta como fallo.** "No reproduce", "no pasó el gate", "bloqueado" son resultados válidos y valiosos. Cerrar una fase con un gate no cumplido, presentándolo como aprobado, es la peor falta posible.

**R4. Cero avance por fase a medias.** No arranques la fase N+1 si la fase N no cumplió su gate. Si un gate no se puede cumplir, parás y explicás por qué (ver §7).

**R5. Aislamiento total.** Todo lo nuevo vive en un espacio de investigación separado (ledger propio). Las variantes se llaman `<Estrategia> · Lab vN`. Ninguna toca configuración real.

**R6. Anti-sobreajuste obligatorio en Fase 2.** Split temporal TRAIN/VAL/OOS decidido antes de ver resultados; contar cuántas variantes se probaron (el ganador de N intentos vale menos cuanto mayor es N); prueba sin los 3 mejores trades; estrés de costos. Ver §5.

**R7. Velocidad.** Una corrida completa (451 símbolos × 243 días) debe tardar ≤ 10 min. Si una corrida excede 30 min sin avance, cortala y buscá el cuello de botella; no esperes en silencio.

## 4. Protocolo de reporte al usuario

Prohibido: porcentajes de avance de "la máquina", heartbeats sin contenido, respuestas de una sola vez y silencio después.

Permitido y obligatorio:
- **Cada corrida larga** se lanza en background con un archivo de progreso (`lab/runs/<id>/progress.json`: inicio, alcance, símbolos hechos/total, estado). Al lanzarla decí: `ID`, comando, hora de inicio, ETA medida (no supuesta).
- **Al terminar cualquier corrida**, avisás **en ese mismo momento**, sin que el usuario pregunte, con: ID, inicio, fin, duración, exit code, ruta del resultado y el resultado en ≤ 6 líneas.
- **Si no hay nada nuevo, no escribas.** Silencio = trabajando; el usuario puede mirar `progress.json`.
- **Estado de fases** con el checklist de §5 (cuántos ítems verificados de cuántos), no con porcentajes.
- Registro append-only en `MISION_LOG.md`: fecha/hora, qué se hizo, qué se midió, qué falló. Sin adornos.

Formato de cierre de cada fase (usá exactamente esto):
```
FASE N — <PASS | FAIL | BLOCKED>
Gate: <criterio> → <valor medido> (umbral <X>)
Evidencia: <rutas>
Qué falló / qué no se pudo medir: <...>
Siguiente paso propuesto: <...>
```

## 5. Fases

### Fase 0 — Comprensión (≤ 30 min)
1. Leé: este documento, `BACKTEST_RELIABILITY_PHASE3_REPORT.md` (y los reportes Phase 1 y 2 de esa serie), `CASO3_SLOT_CAUSAL_REPORT.md`, `DIAG_CASO3_WR_REPORT.md`, `BACKUP_AND_RECOVERY.md`.
2. Entregá un resumen de ≤ 15 líneas: qué probó el Gate V4, cuál fue su veredicto y por qué importa para esta misión.
3. **Hecho conocido que debés verificar y confirmar o refutar con evidencia:** el Gate V4 concluyó que el motor de backtest convirtió una ganadora real (MA Slope Caso 3, PF real ≈ 1.85) en perdedora (mediana PF en replay ≈ 0.81), con PF por seed entre 0.33 y 1.61 y solo ~30% de seeds del lado correcto. O sea, el motor tenía un sesgo sistemático que deprime resultados. Dejá escrito si tu replay nuevo hereda ese sesgo o lo corrige, y cómo lo sabés.
4. Auditá qué fuente de trades reales es confiable para calibrar. Ojo: la base fue reconstruida tras un reset de Docker y el PnL de esos trades **no es confiable**. Tabla: fuente, cantidad, período, campos, ¿PnL confiable? sí/no/parcial y por qué. Si ninguna sirve para calibrar PnL, decilo (todavía se puede calibrar señales/entradas).

**Gate 0:** resumen + tabla de fuentes entregados. Esperá confirmación del usuario antes de Fase 1.

### Fase 1 — Calibrar el motor (esta fase es la más importante)
Objetivo: demostrar que el replay reproduce lo que pasó en real, o encontrar por qué no.

1. Congelá una baseline inmutable de cada estrategia (nombre, parámetros, hash de configuración, período, símbolos, cupos). Marcá explícitamente cuáles parámetros están reconstruidos/aproximados y cuáles son históricos íntegros.
2. Corré el replay sobre **exactamente el mismo período y universo** que los trades reales disponibles (p. ej. los ~6 días de evidencia real de cada estrategia), con las mismas reglas de cupos (3 × $150), fees y vetos.
3. Compará señal por señal contra los trades reales:
   - Tasa de match de trades reales (símbolo + lado + entrada ±1 vela).
   - Trades del replay sin contraparte real y trades reales sin contraparte en el replay.
   - Diferencia en salida (motivo, hora, precio) en los trades que sí matchean.
   - PnL agregado real vs replay (solo si la fuente de PnL real es confiable; si no, comparar en R o en % de precio y decirlo).
4. Si no reproduce, **diagnosticá causas** una por una, midiendo el efecto de cada una aislada: orden de evaluación TP/SL dentro de la vela, fill de entrada, fees/slippage, competencia por cupos, timeouts, datos faltantes, configuración reconstruida distinta de la real. Cada causa arreglada se verifica con la comparación de arriba.

**Gate 1 (umbrales fijos):**
- ≥ 80% de los trades reales matcheados por el replay (símbolo + lado + entrada ±1 vela), y
- en los matcheados, ≥ 80% con mismo motivo de salida, y
- PnL agregado del replay dentro de ±25% del real **o**, si el PnL real no es confiable, dirección del PnL y ranking entre estrategias iguales al real.

Si no cumple tras corregir causas identificables (máximo 3 iteraciones de arreglo), parás: **FASE 1 = FAIL**, informás cuál es la mejor explicación medida y qué se necesitaría (datos, trades reales limpios) para poder cerrarla. No pasás a Fase 2.

### Fase 2 — Matriz de diagnóstico (solo si Gate 1 = PASS)
Sobre la **misma entrada congelada**, variando **una variable por vez** respecto a la baseline:

| # | Variante | Qué diagnostica |
|---|----------|-----------------|
| 1 | Long base | Rendimiento estándar |
| 2 | Short invertido (misma señal) | ¿La señal está invertida o es contra-tendencia? |
| 3 | Long + salida corta (TP ajustado) | Ambición: ¿la entrada sirve pero el TP es irreal? |
| 4 | Short + salida corta | Ídem para el lado short |
| 5 | Long + salida por señal opuesta | ¿Mejor salir por señal que por precio fijo? |
| 6 | Short + salida por señal opuesta | Ídem |
| 7 | Long + SL estricto por ATR | ¿El ruido te saca antes? |
| 8 | Short + SL estricto por ATR | Ídem |
| 9+ | Giveback 10/20/30/40/50%, break-even, lock +5/+10/+20, trailing ATR, trailing MFE, timeout | Dónde se pierde lo ganado |

Por cada variante y por cada estrategia, medí: PnL, PF, win rate, expectativa por trade, drawdown, MFE y MAE promedio y mediana, **giveback** (MFE máximo vs PnL final), tiempo hasta MFE, distribución por símbolo, lado, hora, régimen, y concentración (PnL sin los top 1 y top 3 trades).

Reglas anti-sobreajuste (R6):
- Split temporal TRAIN/VAL/OOS fijado y registrado **antes** de correr. La decisión de qué variante "mejora" se toma en TRAIN+VAL; OOS se mira una sola vez al final.
- Registrar el número total de variantes probadas y reportarlo junto a cualquier ganadora.
- Una mejora solo cuenta si: mejora OOS, sobrevive sin los top 3 trades, sobrevive a costos +50%, y la misma dirección se ve en al menos 2/3 de los sub-períodos.
- Parámetros continuos (TP, ATR, giveback): usar una grilla corta y reportar la superficie completa, no solo el máximo. Un pico aislado no es un hallazgo.

**Gate 2:** para cada estrategia, un **veredicto de atribución** con evidencia, en una de estas formas: "el problema principal está en la entrada / la salida / el SL / el filtro X / no hay edge", con el número que lo respalda y su nivel de confianza. "No hay evidencia suficiente" es un veredicto válido.

### Fase 3 — Informe y UI (solo si Gate 2 entregado)
- Un comando (`lab diagnose <estrategia>` o equivalente) que imprime el veredicto y la tabla de la matriz en ≤ 40 líneas, para poder leerlo sin abrir archivos gigantes.
- Una pantalla por estrategia en la UI existente (Laboratorio o Research, la que corresponda) con: baseline vs variantes, gráfico de MFE/giveback, dónde gana y dónde pierde, veredicto y estado del gate de calibración. Todo leído del ledger real, nada hardcodeado.
- Verificar la pantalla realmente cargada con datos (captura o volcado del DOM), no solo que el endpoint responde 200.

## 6. Qué NO debés hacer

- No abras frentes nuevos. Si ves una idea interesante, anotala en `MISION_LOG.md` bajo "Ideas (no ejecutadas)".
- No reportes "la máquina está al X%". Reportá fases con gate cumplido/no cumplido.
- No declares una estrategia "buena" por un mes positivo, un trade grande o un PnL en el train. El usuario ya sabe que ambas pierden en promedio y no tienen edge demostrado; el objetivo es entender dónde y por qué, no forzar una ganadora.
- No optimices contra el set completo y después presentes OOS como si no lo hubieras visto.
- No respondas sobre rankings de estrategias con `source` o motor: la identidad es `StrategyProfileId` + versión de parámetros.

## 7. Cuándo parar y preguntar

Parás y le escribís al usuario solo si: (a) un gate no se puede cumplir y necesitás una decisión (datos, costo, alcance), (b) necesitás tocar algo de la lista "prohibido", (c) encontrás una contradicción en este documento. En cualquier otro caso seguís trabajando sin pedir permisos.

Al parar, formato:
```
BLOQUEADO — <fase>
Qué intenté: <...>
Qué medí: <...>
Qué necesito del usuario: <decisión concreta, con 2–3 opciones y tu recomendación>
```

## 8. Definición de terminado

La misión termina cuando existen, verificables por el usuario:
1. Gate 1 = PASS (motor calibrado con evidencia) **o** un informe FAIL honesto con la explicación medida.
2. Si Gate 1 = PASS: veredicto de atribución por estrategia con su tabla de matriz y anti-sobreajuste aplicado.
3. Comando + pantalla de UI funcionando con datos reales.
4. Todo commiteado en una rama propia, con `MISION_LOG.md` al día.

Nada de esto requiere que encuentres una estrategia rentable. Sí requiere que lo que digas sea cierto.
