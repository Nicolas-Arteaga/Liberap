# ROUND 29 — OI EVENT SEQUENCES (Open Interest como disparador primario)

## ¿Encontramos una nueva fuente de alpha? **No.**

- **¿Cuánto produce neto?** $0 — ninguna de las 8 formulaciones
  predeclaradas sobrevivió la cadena TRAIN→VAL→OOS completa.
- **¿Con cuánto capital?** No aplica — no se llegó a `portfolio_engine.py`.
- **Mecanismo:** ninguno confirmado — 8 mecanismos probados, todos
  descartados con causa específica documentada abajo.
- **¿Es robusta? PASS/CANDIDATE/FAILED?** **FAILED**, con un caso límite
  (rama E) que requiere explicación detallada porque a primera vista
  parece prometedor y NO lo es.
- **Siguiente acción:** cerrar OI-como-disparador-primario con esta
  formulación y pasar a comportamiento relativo entre altcoins vía
  divergencia de OI (no beta-hedge de precio, ya cerrado en R13) —
  prioridad indicada por el propio brief si esta familia fallaba.

---

## FASE 0 — Auditoría de cobertura (antes de investigar nada)

`oi_metrics` tiene 63 símbolos en total, pero con cobertura MUY desigual
— desde 14,832 filas (símbolo listado en junio 2026) hasta 127,578 filas
(historia completa desde 2025-06-01). Se definió el universo
**Feature-Complete** como los símbolos con ≥120,000 filas de OI
(equivalente a ≥14 meses de los 14.5 disponibles, sin huecos
estructurales) — **43 símbolos**, no 63. No se usó forward-fill ni se
inventó OI para el resto; los 20 símbolos con historia parcial quedaron
fuera de esta ronda por decisión explícita, no por descuido.

Cobertura verificada: klines_clean + oi_metrics alineados exactamente por
timestamp (`open_time % 900000 == 0`, mismo método causal de R9), sin
huecos que requieran relleno artificial en los 43 símbolos elegidos.

## FASE 1-2 — 8 formulaciones predeclaradas, dirección TRAIN-decidida

| # | Evento | Eventos | ¿Señal en algún horizonte? |
|---|---|--:|---|
| A | OI expansion anormal (percentil causal ≥97%) | 33,211 | Sí, pero muere en costos y placebo |
| B | OI contraction anormal (percentil causal ≤3%) | 34,073 | Sí, pero signo se invierte en OOS |
| C | OI acceleration (2da diferencia extrema) | 36,886 | Sí, pero muere en VAL/OOS |
| D | OI shock (expansion o contraction) | 59,533 | Sí, pero muere en VAL/OOS |
| E | Expansion + confirmación de volumen | 15,095 | **El más prometedor — pero falla en VAL (ver abajo)** |
| F | Contracción + confirmación de volumen | 16,274 | Sí, pero signo se invierte en OOS |
| G | Expansion + precio NO confirma | 13,495 | Sí, pero muere en VAL/OOS |
| H | Contracción + precio sube (short covering) | 13,520 | Sí, pero muere en VAL/OOS |

## Detalle de por qué cada rama muere

- **A (expansion, h=8h):** TRAIN significativo (+4.8bp), OOS también
  significativo (+13.47bp) — pero **el costo de 24bp nunca se supera en
  ningún segmento** (net siempre negativo) y **el placebo temporal
  reproduce casi la misma magnitud** (5.35bp) que el TRAIN real. Muerte
  doble: ni el costo ni el placebo lo dejan pasar.
- **B (contraction, h=15m):** TRAIN positivo y significativo, pero **OOS
  es significativo con signo OPUESTO** (−1.4bp vs TRAIN +4.44bp) —
  inestabilidad de signo, exactamente el patrón que el proyecto cierra sin
  dudar desde R10/R11.
- **C (acceleration, h=15m):** TRAIN significativo pero minúsculo (2.4bp),
  VAL y OOS no significativos. Sin generalización.
- **D (shock, h=15m):** mismo patrón que C — TRAIN significativo y
  pequeño, VAL/OOS planos.
- **F (contraction+volumen, h=15m):** TRAIN y VAL significativos y del
  mismo signo (+11.4bp / +2.32bp) — el candidato con más apariencia de
  progresión limpia — pero **OOS es significativo con signo invertido**
  (−3.73bp). Rota exactamente en el último paso de la cadena.
- **G, H:** TRAIN significativo en 1-2 horizontes cortos, sin
  confirmación en VAL ni OOS en ningún caso.

### E (expansion+volumen, h=8h) — el caso que exige explicación, no solo una tabla

Esta es la rama más tentadora del round: TRAIN +15.02bp (sig.), **OOS
+35.28bp con net=+11.28bp — el ÚNICO resultado de las 8 ramas que supera
el costo de 24bp en algún segmento.** Si esto se reportara aislado, se
vería como un candidato real.

**Pero VAL es negativo (gross=−1.56bp) y NO significativo — rompe la
cadena TRAIN→VAL→OOS exactamente en el paso de confirmación.** El propio
protocolo de esta ronda (Fase 6) es explícito: "usar TRAIN para elegir,
VAL para confirmar, OOS como prueba final" — VAL no confirma, así que OOS
no puede tratarse como validación, por más atractivo que sea el número.
Además, el placebo temporal (+25 barras) también es significativo
(15.1bp) — casi la mitad de la magnitud del TRAIN real — indicando
contaminación parcial por el mismo tipo de drift que mató hipótesis en
R24. Con n_OOS=4,692 (bastante más chico que TRAIN=8,151), el resultado
OOS es también más vulnerable a que unos pocos eventos grandes dominen el
promedio — no se investigó más porque la regla explícita del brief prohíbe
"seleccionar la mejor combinación después de ver resultados", y usar el
número de OOS para rescatar una rama que VAL ya descartó sería
exactamente eso.

**Veredicto de E: FAILED, no CANDIDATE.** No se descarta por ser
"decepcionante" — se descarta porque el propio protocolo pre-declarado
(que este mismo brief exige) dice que VAL debe confirmar antes de mirar
OOS, y acá VAL dijo que no.

## FASE 3 — Información incremental de OI

No se llegó a ejecutar la comparación completa (precio solo / precio+
volumen / OI solo / OI+precio / OI+volumen / OI+precio+volumen) porque
**ninguna rama sobrevivió el filtro básico TRAIN→VAL→OOS** que es
prerrequisito para que la pregunta de información incremental tenga
sentido — hacer esa comparación sobre una señal que ya está muerta habría
sido gastar cómputo sin ganar nada. Coherente con la disciplina de
"discovery antes que validación" establecida desde R23.

## FASE 5 — Controles duros

No se aplicaron los controles completos (BTC/momentum/volatilidad/hora)
por la misma razón — ninguna rama llegó a merecerlos.

## FASE 7 — Estrategia económica

**Ninguna.** No se construyó sim con `portfolio_engine.py`. Sería simular
una estrategia sin mecanismo, exactamente lo que el proyecto decidió dejar
de hacer desde R22.5/R23.

---

## Veredicto final: FAILED, con causa raíz distinta para cada rama

A diferencia de rondas anteriores donde el problema era uniforme (todo el
drift estructural de R24, o toda la falta de señal de R27), esta ronda
mostró **patrones de fallo genuinamente distintos por rama**: costo+placebo
(A), inversión de signo OOS (B, F), ausencia total de generalización (C,
D, G, H), y ruptura de la cadena en VAL específicamente (E). Esto es
evidencia de que el Open Interest, en esta ventana y con este universo de
43 símbolos feature-complete, **no contiene información direccional
robusta y explotable cuando se usa como disparador primario** — ni en su
nivel, ni en su cambio, ni en su aceleración, ni combinado con volumen o
con desacuerdo de precio.

---

## Próxima familia (R30) — completamente distinta

Por prioridad ya indicada en R28 y reconfirmada acá: **comportamiento
relativo entre altcoins vía divergencia de OI entre pares del mismo
sector/comportamiento**, explícitamente NO beta-hedge de precio (esa
construcción ya se cerró en R13 con el placebo aleatorio superándola). La
idea: en vez de comparar retorno relativo entre altcoins (lo que ya
falló), comparar **cambio de posicionamiento relativo** (ΔOI normalizado)
entre pares que históricamente se mueven juntos — una altcoin que
construye posición de forma anormalmente distinta a sus pares del mismo
grupo podría contener información que el precio solo no captura. Universo
disponible: los mismos 43 símbolos feature-complete de OI de esta ronda.
