# Handoff técnico completo — Laboratorio de Diagnóstico

## Alcance vigente

La misión dejó de ser descubrir u optimizar estrategias. El objetivo es una máquina de **diagnóstico** para estrategias existentes, inicialmente **MA Slope Caso 3 (MA3)** y **Band Touch**, que explique entradas, salidas, costes, payoff y límites de fidelidad. No modifica producción, `StrategyProfiles` ni ejecuta órdenes. El ledger de escaneo sigue sin desplegarse: requiere aprobación explícita y reinicio del agente.

## Regla de evidencia

Cada número debe tener ruta y comando. Los hallazgos son HIPÓTESIS hasta que el ledger permita registrar la selección y cierre reales. Antes de una corrida: `py_compile` y smoke test. No descargar velas con `curl` a Binance; el agente comparte IP. Los artefactos actuales quedan versionados por pedido expreso del usuario.

## Diagnóstico de fidelidad ya realizado

### Fase 1 / 1B: calibración contra producción

- Detección MA3: 37 de 38 entradas con klines se detectaban a ±20 minutos; no implica que el replay reproduzca la selección.
- Replay sin restricciones produjo aproximadamente 1.225 candidatos frente a 45 operaciones reales. La brecha principal es la selección/admisión de producción, no la detección.
- Fidelidad de salida: FAIL caracterizado. Los motivos de salida no se pudieron reproducir de forma suficiente porque producción mezcla reglas sin ledger histórico; los `TIMEOUT` agrupaban duraciones de 6,8 a 207 horas.
- El Gate V4 había observado PF real 1,85 frente a 0,81 del replay; no usar el replay como PnL de producción.

### Corrección crítica de MA3

Se confirmó que la población bruta MA3 estaba desalineada una hora: el stream contenía `b` al inicio de hora pero el motor evaluaba en `b + 3.600.000`; el precio de entrada era el cierre de la última vela 5m de esa hora. Muestreo: 300/300 `b` al minuto 0 y 300/300 entradas iguales al cierre terminal. El adaptador ahora fija `open_ms = b + interval_ms`.

Baselines OOS antiguos (`v1 DESALINEADO`) versus alineados:

| Escenario | v1 | alineado |
| --- | ---: | ---: |
| unconditional / TP bias -2 | 0,3071030655 | 0,3180237011 |
| unconditional / TP bias +2 | 0,4386099148 | 0,4504469093 |
| conditional / TP bias -2 | 0,0585023628 | 0,0548301563 |
| conditional / TP bias +2 | 0,5078174313 | 0,5053421017 |

Las conclusiones previas de Fase 2/2b/2d/A sobre esa población deben leerse como calculadas con entrada desalineada y pendientes de rerun cuando corresponda. El impacto cuantificado en los baselines fue pequeño, pero no se borra la advertencia.

## Fase 2: variantes y límites

- Población MA3: 9.400 señales sobre 243 días para el análisis amplio; no representa la selección real de producción.
- Se probaron 13 variantes de salida. Ninguna superó el criterio preregistrado de mejorar OOS, sobrevivir sin los top 3 trades, costes +50% y los cuatro escenarios de timeout/fill.
- El giveback descriptivo existe, pero reglas simples no lo corrigieron de forma robusta.
- Band Touch usa 82 entradas reales y velas 15m del agente; una medición anterior de 65 trades excluyó 17 que no tenían dos velas completas. No extrapolarlo a producción sin marcar ese límite.

## M1b: integridad implementada

Los chequeos deben aparecer arriba de todo informe y hacen el informe INVÁLIDO si fallan:

1. precio de entrada observable;
2. no usar velas anteriores a `open_ms`;
3. retorno a 1h con varianza distinta de cero;
4. ninguna salida antes de la entrada;
5. splits por instante real de entrada;
6. N por split y N efectivo en días.

Para replay (MA3), el precio se compara con el cierre de la vela que **termina** en `open_ms`. Para entradas reales (Band), debe estar dentro del rango de la vela que contiene `open_ms`, con tolerancia de 0,1%.

La corrección de `forward_returns` permite entradas reales desalineadas dentro de una vela y distingue hueco real. Tests cubren: caso alineado, desalineado dentro de tolerancia, hueco y replay desalineado que debe invalidar.

## Estado de implementación y rutas

- CLI: `agent/backtest/lab_diagnose.py`
- Núcleo: `agent/backtest/lab_core.py`
- Integridad: `agent/backtest/lab_integrity.py`
- Adaptadores: `agent/backtest/lab_adapters/ma3.py` y `agent/backtest/lab_adapters/band_touch.py`
- Informes: `agent/backtest/lab_report.py` y resultados en `agent/backtest/lab_artifacts/`
- Registro de misión: `MISION_LOG.md`

Los tests relevantes son `test_lab_core_audit`, `test_lab_integrity` y `test_lab_report_text`. La última suite registrada antes de este handoff fue 9/9 PASS.

## Trabajo pendiente explícito

1. Verificar y, si hace falta, regenerar los dos informes CLI tras el último cambio de integridad y redacción.
2. M2: informe Band Touch en el mismo formato de MA3.
3. M3: poblaciones sintéticas por causa, 30 poblaciones NULL, falsos positivos por hallazgo <=5%, e inyección desalineada que debe marcar INVÁLIDO.
4. M4: página UI que cargue informe/result.json vía API, con horarios `America/Argentina/Buenos_Aires`, y verificación DOM/captura.

No iniciar nuevas fases de investigación, VIRE ni despliegue de ledger hasta que estos hitos estén auditados.

## Información deliberadamente omitida

Este handoff reemplaza una exportación cruda de chat que queda conservada sólo en el escritorio local del usuario. Se omiten credenciales, tokens, contraseñas, claves API, datos de sesión y conversaciones personales. El contenido técnico, decisiones, límites, rutas, resultados y próximos pasos necesarios para continuar se conserva aquí.
