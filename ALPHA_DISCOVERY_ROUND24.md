# ROUND 24 — ALPHA DISCOVERY: 5 hipótesis nuevas, ninguna operable todavía, pero aparece el hallazgo más replicado del proyecto

## Resumen ejecutivo

- **¿Encontramos una estrategia?** No, ninguna de las 5 hipótesis nuevas de
  esta ronda es operable.
- **¿Cuánto produce neto por mes?** $0 — ninguna llegó a sim económica
  (todas murieron en la etapa DISCOVERY, antes de VALIDATION/EXECUTION).
- **¿PASS / CANDIDATE / FAILED?** 5× FAILED, pero **no es un cierre vacío**:
  3 de las 5 fallan por la MISMA causa raíz, y esa causa raíz es en sí
  misma la pista más fuerte y más replicada de todo el proyecto (visto ya,
  de forma independiente, en R12, R13, R15, R18 y ahora otra vez en R24).
- **¿Cuál es la siguiente acción?** R25 debe atacar esa causa raíz
  DIRECTAMENTE como su propio candidato — no como confound a evitar, sino
  como la señal a testear — con un diseño experimental que hasta ahora
  nunca se corrió (ver "Próximo paso" al final). Caso **B** del brief: señal
  insuficientemente validada todavía, pero con evidencia demasiado fuerte
  y repetida como para no profundizarla.

---

## Hipótesis investigadas (bateria, dirección congelada en TRAIN antes de mirar VAL/OOS)

| # | Hipótesis | Familia | Resultado |
|---|---|---|---|
| H1-UP | Evento extremo de 1 barra (subida) — TRAIN eligió FADE (short) | Eventos extremos | **FAILED — placebo lo reproduce casi entero** |
| H1-DOWN | Evento extremo de 1 barra (caída) — TRAIN eligió continuación (short) | Eventos extremos | **FAILED — placebo lo reproduce casi entero** |
| H2 | Doble shock de volatilidad consecutivo | Secuencias | **FAILED — no generaliza a VAL/OOS** |
| H3 | Caída extrema + recuperación parcial (20-60%) + continuación | Secuencias | **FAILED — placebo lo reproduce casi entero** |
| H4 | Ruptura fallida vs control de magnitud emparejada | Volatilidad/transición | **FAILED — el control no se distingue de la "falla"** |
| H5 | Outlier relativo cross-sectional de 4h vs mediana del universo (no beta/BTC) | Relativo entre altcoins | **FAILED — no generaliza a VAL/OOS** |

*(Nota de proceso: la primera corrida de este round tenía un bug propio en
la lógica de selección de dirección TRAIN — comparaba magnitud absoluta
entre "continuación" y "reversión" en vez de signo, y como ambas son
espejos matemáticos exactos, siempre elegía "continuación" por un empate
arbitrario de orden. Se detectó, se corrigió, y se re-corrió todo antes de
reportar. Los números de abajo ya son los corregidos.)*

---

## El hallazgo real de esta ronda: el mismo confounder aparece una quinta vez, de forma independiente

**H1-UP, H1-DOWN y H3 no fallan por ausencia de señal — fallan porque el
placebo temporal (mismo evento, ventana desplazada +25 barras sin relación
causal con el evento) reproduce CASI EXACTAMENTE la misma magnitud que la
señal real:**

| Hipótesis | Horizonte | Señal real (OOS, net) | Placebo (+25 barras, net) |
|---|---|--:|--:|
| H1-UP (fade) | 24h | +76.4bp | **+64.3bp** |
| H1-DOWN (continuación) | 24h | +48.3bp | **+53.6bp** (¡mayor que la real!) |
| H3 (drop+recuperación) | 24h | +37.6bp | **+49.6bp** (¡mayor que la real!) |

En los tres casos, apostar SHORT — sin importar si es "fade de una subida
extrema", "continuación de una caída extrema" o "tras una recuperación
parcial fallida" — genera un resultado positivo grande. Y desplazar la
ventana de medición 25 barras hacia adelante (rompiendo cualquier relación
causal con el evento específico) **da un resultado del mismo orden de
magnitud, a veces mayor**. Esto significa que ninguna de las tres
"señales" está realmente detectando el evento — están todas capturando
el mismo fenómeno de fondo: **un sesgo estructural negativo (bajista)
persistente en el universo ancho de altcoins de este dataset**, que hace
que casi cualquier apuesta SHORT sin condicionar en nada específico ya
tienda a ganar.

Esto **no es nuevo como fenómeno** — es la quinta vez independiente que
aparece en este proyecto:
- R12: el placebo aleatorio reprodujo casi exacto el resultado de "smart
  money divergence".
- R13: el placebo aleatorio (+149.5bp, PF 1.74) **superó** a los
  portfolios "inteligentes" de beta/residual-momentum.
- R15/R18: contaminación documentada como "anomalía 2026Q3" — dispersión
  cross-sectional extrema al final de la muestra.
- R24 (esta ronda): tres formulaciones completamente distintas
  (evento-único, secuencia-de-recuperación) todas colapsan al mismo
  patrón.

**Lo nuevo esta ronda es que el patrón ya no depende de una ventana
temporal específica ni de un mecanismo condicional particular — aparece
con eventos disparados en TODO el rango temporal (no solo 2026Q3) y con
tres mecanismos económicamente no relacionados entre sí.** Eso lo hace
un candidato más creíble como fenómeno de mercado real (survivorship +
estructura de emisión/venta constante en altcoins chicas — un hecho
conocido del mercado cripto, no necesariamente un artefacto de datos) que
como una simple ventana anómala.

## H2, H4, H5 — fallos limpios, sin este patrón

- **H2 (doble shock):** nunca generaliza más allá de TRAIN, ni con
  placebo contaminado ni sin él — simplemente no hay efecto sostenido.
  Familia de "secuencias de shock consecutivo" cerrada con esta
  formulación; no se prueban variantes de esta sin una razón económica
  nueva.
- **H4 (ruptura fallida vs control):** el control de magnitud emparejada
  (mismo decil de movimiento, sin exigir que la ruptura fallara) da
  resultados del mismo orden que el grupo "fallido" — **la falla del
  breakout específicamente no aporta nada que el tamaño del movimiento
  no aporte ya.** Esto resuelve limpiamente la pista abierta que había
  quedado de R23 (el "hallazgo colateral" de reversión post-ruptura):
  no era la falla, era simplemente la magnitud (y probablemente el mismo
  drift estructural de arriba). Familia cerrada con evidencia, no con
  intuición.
- **H5 (relativo cross-sectional 4h):** único intento genuino de esta
  ronda de capturar comportamiento relativo ALTCOIN-a-ALTCOIN (no BTC, no
  semanal, no beta) — la señal existe en TRAIN pero desaparece
  completamente en VAL y OOS. No hay evidencia de que reaparezca con otra
  ventana sin volver a mirar OOS primero (lo cual violaría la regla
  anti-overfitting) — cerrada, sin variantes de parámetro por ahora.

---

## Controles aplicados

Cada hipótesis pasó: TRAIN→VAL→OOS con dirección congelada en TRAIN,
placebo temporal (+25 barras), costo de 24bp RT aplicado consistentemente,
cluster-bootstrap por símbolo (no CI ingenuo por trade). Ninguna llegó a
la etapa de sim económica con capital/slots porque ninguna sobrevivió el
placebo o la generalización a VAL/OOS — correcto per Parte 15 (no mezclar
discovery con validación/ejecución hasta tener evidencia limpia).

---

## Próximo paso concreto para R25 — Caso B, no cerrar la investigación

**Testear el drift estructural directamente, como su propio candidato, en
vez de como confound a evitar.** Diseño explícito para R25:

1. Construir una canasta SHORT no-condicionada (ej. N=10-20 símbolos por
   rotación de liquidez/volatilidad, sin ningún evento disparador) y medir
   su PnL en TRAIN/VAL/OOS con el motor corregido de R23 (order-invariant,
   funding real, `portfolio_engine.py`).
2. El control correcto para ESTA hipótesis específica NO puede ser un
   placebo temporal (ya sabemos que lo reproduce, es literalmente el punto)
   — tiene que ser una comparación LONG vs SHORT del mismo universo, y una
   partición por sub-período para confirmar que el sesgo no es
   simplemente "todo 2026 bajó" sino algo más persistente y estructural
   (ej. rotación constante de qué símbolos están en la cola negativa).
3. Si el sesgo es real y persistente: es economicamente plausible (emisión/
   dilución/venta de altcoins chicas es un fenómeno de mercado conocido,
   no inventado) y podría ser la base de Strategy Candidate #1 — una
   canasta corta simple, no un evento condicional complicado.
4. Si el sesgo resulta ser, otra vez, específico de un sub-período (como
   ya pasó con R13): documentarlo como CERRADO definitivamente esta vez
   (van 5 apariciones independientes; si la sexta también resulta
   temporal, ya no amerita una séptima ronda dedicada a esto) y pasar a
   familia 4 (liquidation cascade, si el colector ya tiene cobertura) o 6
   (microestructura de 22:00 UTC, investigando el fenómeno subyacente).

No se cierra la investigación. No se declara "no existe alpha". Se
identificó, por quinta vez de forma independiente, el fenómeno más grande
y más replicado del proyecto — el paso lógico es dejar de tratarlo como
ruido a filtrar y probarlo como lo que podría ser: la señal misma.
