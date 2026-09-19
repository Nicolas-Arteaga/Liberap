# VERGE — PORTFOLIO & CAPITAL PROTOCOL (FASE 8)

**Fecha:** 2026-09-06
Se ejecuta **solo después** de tener ≥ 1 candidato con veredicto PASS (o
varios INVESTIGATE) en `VALIDATION_PROTOCOL.md`. No antes.

---

## 0. Principio

La estructura de capital **no** es una restricción a priori. Se decide con
datos, **después** de demostrar edge individual. Opciones sobre la mesa:

- `1 × 450 USDT`
- `2 × 225 USDT`
- `3 × 150 USDT`
- **sizing dinámico basado en riesgo** (vol-target / fractional Kelly
  recortado)

El objetivo agregado sigue siendo **≥ 150 USDT netos/mes** (idealmente por
cada estrategia productiva; como mínimo del portfolio combinado con el
capital total realmente comprometido).

---

## 1. Precondición

- Cada estrategia candidata tiene su **snapshot congelado** (Fase 4) y su
  **reporte de Fase 7** completo.
- Se conocen, por estrategia y por bloque temporal: serie de PnL diaria,
  nº de posiciones simultáneas, símbolos operados, timestamps de entrada y
  salida, exposición.
- Nada de esto se re-optimiza en Fase 8. La combinación se optimiza; las
  estrategias no.

---

## 2. Análisis de interacción (sobre TRAIN + VALIDATION, nunca FINAL-OOS)

1. **Correlación de retornos** entre estrategias (PnL diario). Objetivo:
   combinar estrategias con corr baja o negativa.
2. **Solapamiento de símbolos y de timing** — ¿compiten por los mismos
   símbolos en las mismas ventanas? Cuantificar el % de señales en conflicto.
3. **Solapamiento de exposición** — ¿los drawdowns coinciden en el tiempo?
   (un portfolio de 3 estrategias que caen juntas no diversifica nada).
4. **Capacidad** — ¿el edge de cada estrategia aguanta el tamaño de posición
   que implicaría su asignación de capital? Re-verificar slippage al nuevo
   tamaño (una estrategia de microcaps no escala de $150 a $450 sin mover el
   mercado).

---

## 3. Regla de resolución de conflictos (causal, fija)

Cuando 2+ estrategias del portfolio quieren abrir en el **mismo símbolo** en
la misma barra, y el sizing lo impide:

- Prioridad por **expectancy histórica congelada** de cada estrategia
  (la del reporte de Fase 7, no recalculada con el trade en cuestión).
- Empate ⇒ la estrategia con **menos posiciones abiertas** en ese momento.
- Empate ⇒ orden alfabético del ID de estrategia (determinista, arbitrario,
  documentado).
- **Nunca** usar el resultado futuro del trade para decidir quién entra.

Esta regla se congela antes de correr la validación OOS del portfolio.

---

## 4. Optimización de asignación (SOLO sobre TRAIN)

Se prueban las 4 estructuras + sizing dinámico, optimizando **solo en TRAIN**:

| Estructura | Qué se optimiza en TRAIN | Restricción |
|---|---|---|
| `3 × 150` | qué 3 estrategias | capital total 450; máx 3 pos/estrategia |
| `2 × 225` | qué 2 estrategias | capital total 450 |
| `1 × 450` | qué estrategia | — |
| **sizing dinámico** | target de vol del portfolio, cap de fracción de Kelly (≤ 0.3), floor/ceiling de posición | capital total ≤ suma de asignaciones; nunca > 450 por estrategia; sin apalancar el portfolio por encima de 1× agregado |

Criterio de selección en TRAIN: **maximizar el PnL/mes del portfolio ajustado
por drawdown** (p. ej. PnL_mes / MaxDD, o Calmar), no el PnL bruto.

---

## 5. Validación OOS de la asignación final

- La estructura ganadora en TRAIN se corre **una sola vez** sobre
  **VALIDATION** y luego **una sola vez** sobre **FINAL-OOS**.
- Si el portfolio ganador en TRAIN no supera el gate en FINAL-OOS ⇒ se baja
  a la 2.ª mejor estructura de TRAIN y se reporta la degradación; **no** se
  re-optimiza contra FINAL-OOS.
- Métricas del portfolio en FINAL-OOS: las mismas de `VALIDATION_PROTOCOL.md
  §7.1`, más:
  - PnL/mes del portfolio y por estrategia.
  - **Capital total realmente comprometido** (pico de margen simultáneo) vs
    capital asignado — la utilización real.
  - DD del portfolio (no la suma de DDs individuales).
  - Correlación realizada de las estrategias en FINAL-OOS vs la de TRAIN
    (si diverge mucho, la diversificación era espuria).
  - Contribución de cada estrategia al PnL y al DD del portfolio.

---

## 6. Veredicto de Fase 8

| Veredicto | Condición |
|---|---|
| **DEPLOY-READY** | el portfolio (estructura + asignación) supera el gate económico en FINAL-OOS a 2 bp, con DD% ≤ 25% del capital total, y ninguna estrategia individual aporta > 70% del PnL ni > 70% del DD. |
| **SINGLE-STRATEGY** | ninguna combinación mejora al mejor candidato individual ⇒ desplegar 1 sola (`1 × 450` o el sizing que corresponda). |
| **NOT READY** | el portfolio no supera el gate, o la diversificación de TRAIN no se sostiene OOS, o la capacidad no aguanta el tamaño. Volver a Discovery. |

---

## 7. Qué NO se hace en Fase 8

- Optimizar la asignación mirando FINAL-OOS.
- Re-tunear parámetros de estrategia "para que combinen mejor".
- Añadir una 4.ª estrategia no validada para "rellenar".
- Apalancar el portfolio por encima de 1× agregado.
- Contar capital que no está realmente disponible (si el margen simultáneo
  pico supera el capital asignado, la estructura es inválida).
- Declarar el portfolio productivo antes de FINAL-OOS.
