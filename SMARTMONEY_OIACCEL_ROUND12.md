# ROUND 12 — SMART MONEY DIVERGENCE → ECONOMIC ALPHA

**Fecha:** 2026-09-15 · Sin descargas nuevas (ya teníamos 14.5 meses de
`data.binance.vision`: OI 5m + L/S ratios + funding + OHLCV, universo restringido
de 45 símbolos, igual que R11). Script: `agent/backtest/r12_smartmoney.py`.

## ECONOMIC RESULT

`Validated net PnL/month: $0`
`Target: $150/month`
`Target achieved: NO`

(el mejor número de backtest fue $35/mes — ver por qué no cuenta como "validado"
más abajo)

---

## Tabla resumen

| Mechanism | OOS (raw @4h) | Net/month (mejor config) | Symbols | PF | Concentration | Verdict |
|---|---|---:|---:|---:|---:|---|
| **Retail vs Smart Money (RL_SS)** | −21.1 bp | −$21 a −$247 (todas negativas salvo la nota abajo) | 45 | 0.63–0.95 | 0.5–0.7 | **FAILED** |
| **Retail vs Smart Money (RS_SL)** | +4.6 bp | **$29** (mejor caso, 8h/1 slot) | 45 | 1.09 | 0.6–0.7 | **FAILED** |
| **OI Acceleration (confirm)** | −6.7 bp | −$164 a −$234 | 45 | 0.60–0.70 | 0.5–0.9 | **FAILED** |
| **OI Acceleration (diverge)** | −16.1 bp | **$35** (mejor caso, 4h/1 slot) | 45 | 1.06 | 0.5–0.8 | **FAILED** |

---

## MECANISMO 1 — Retail vs Smart-Money Divergence

`D = z(global_ls_acct) − z(toptrader_ls_pos)`, extremos en percentiles causales
P90/95/97.5/99 (dos lados: RL_SS = retail-long/smart-short, RS_SL =
retail-short/smart-long). Universo 45 símbolos, TRAIN ≤ 2026-02-07 / VAL ≤
2026-05-14 / OOS > eso.

**Event study (P95, raw fwd, + = precio sube):**
- RL_SS (n=31 454): **negativo en todos los horizontes**, CI excluye 0 desde 2h
  (−3.2 → −45.2 bp @24h). Dirección coherente con "crowding retail long vence
  smart-money short → cae" — pero…
- RS_SL (n=44 498): también mayormente negativo o plano (no el espejo esperado de
  "sube"). La asimetría rompe la hipótesis simétrica de partida.

**TRAIN/VAL/OOS (@4h):** RL_SS: train −3.0 / val **+4.2** / oos **−21.1** — el
signo se invierte dos veces. RS_SL: train −4.4 / val −5.8 / oos **+4.6** — también
inestable. **Ningún lado mantiene signo en los tres bloques.**

**Sensibilidad de threshold:** monotónico y consistente (P90→P99: RL_SS −6.5→−8.6
bp; RS_SL −1.0→−7.2 bp) — estadísticamente prolijo, pero no resuelve la
inestabilidad temporal.

**PLACEBOS — el resultado decisivo:**
| Control | 2h | 4h | 8h |
|---|--:|--:|--:|
| Real RL_SS | −3.15 | −7.38 | −14.74 |
| Matched (\|z_D\|≤0.3, sin divergencia) | −1.92 | −3.32 | −7.58 |
| Time-shift +24h | −3.86 | −7.30 | −14.22 |
| Random-ranking (símbolo al azar) | −4.40 | −6.92 | −20.67 |

**Los tres placebos reproducen el efecto "real" casi exactamente.** El matched
control (sin ninguna divergencia extrema) da la mitad de magnitud pero mismo
signo; time-shift y random-ranking lo reproducen punto por punto. Esto significa
que el evento de divergencia **no aporta nada**: lo que se mide es el **drift
negativo genérico de la muestra** (altcoins medianas/chicas con drift bajista neto
en esta ventana), no un efecto de posicionamiento.

**Regresión incremental** (`fwd ~ D + momentum(15m/1h/4h/24h) + vol + volumen +
BTC + OI`, n≈497 000): `t(D) = −4.6 a −6.5` (significativo por el tamaño de
muestra) pero **ΔR² por D = 0.00001 — prácticamente cero**. D no aporta
información económica, solo ruido estadísticamente detectable a gran n.

**Sim económica:** de 16 configuraciones (2 lados × 2 direcciones × 2 horizontes ×
2 tamaños de slot), **15 pierden dinero** (−$21 a −$311/mes). La única positiva:
RS_SL_SHORT @8h/1 slot = **+$29/mes** — muy por debajo de 150, con mediana de mes
negativa (m[P5/50/95] = [−203/−40/+578], la media positiva depende de la cola).

**Veredicto: FAILED.** Placebo positivo (Fase 5, criterio explícito del brief) +
inestabilidad temporal + ΔR²≈0 + económicamente nulo.

---

## MECANISMO 2 — OI Acceleration (fallback, ejecutado en el mismo round)

`oi1 = dOI` (H13-C) · `oi2 = oi1[t] − oi1[t−1h]` (2da diferencia = aceleración) ·
evento `|z(oi2)| ≥ 1.5`, separado en **confirmado** (aceleración y precio mismo
signo) vs **divergente** (signos opuestos). Dirección de la sim fijada por el
signo de **TRAIN únicamente** (no post-hoc sobre VAL/OOS) y evaluada solo en
VAL+OOS.

**TRAIN/VAL/OOS (@4h):** confirm: train −6.6 / val **+3.9** / oos −6.7. diverge:
train −2.7 / val **+2.2** / oos **−16.1**. Igual patrón que M1: **el signo no se
sostiene**, VAL contradice a TRAIN y OOS.

**Sim económica (dirección = SHORT fijada por TRAIN, evaluada en VAL+OOS):**
7 de 8 configuraciones pierden dinero (−$52 a −$234/mes). La única positiva:
diverge SHORT @4h/1 slot = **+$35/mes**, con mediana mensual **negativa** (−$66) —
otra vez, la media positiva depende de la cola (P95 = +$391).

**Veredicto: FAILED.** Mismo patrón que M1: efecto estadísticamente detectable
pero económicamente nulo y no estacionario.

---

## Por qué ambos mecanismos fallan de la misma forma (hallazgo metodológico)

En los dos mecanismos, sin importar la dirección de la hipótesis, el **retorno
forward crudo de eventos extremos en este universo de 45 altcoins tiende a ser
negativo** — y ese negativo se reproduce casi exactamente en matched-control,
time-shift y random-ranking. Esto es consistente con un hecho estructural conocido
de cripto: **los altcoins medianos/chicos tienden a depreciarse en términos
relativos sobre ventanas de meses** (dilución, fin de ciclos de hype, dominancia
de BTC). No es un artefacto de bug — los tres placebos coinciden — es la deriva
de base de la muestra, y confirma que el protocolo de controles está funcionando
correctamente (detecta y descarta el efecto).

---

# ROUND 12 VERDICT

# FAILED

Ambos mecanismos (Retail-vs-Smart-Money y OI Acceleration) fallan por las mismas
tres razones exigidas como criterio de FAILED: **inestabilidad temporal** (signo
se invierte entre TRAIN/VAL/OOS), **placebo positivo** (matched/time-shift/random
reproducen el efecto — solo en M1, explícito), y **magnitud económica
insuficiente** (mejor caso real ~$35/mes, y con mediana mensual negativa).

# MAX VALIDATED MONTHLY PNL

**$0.** Los ~$29–35/mes de las mejores configuraciones NO cuentan como validados:
dependen de la cola de la distribución mensual (mediana negativa en ambos casos),
no sostienen signo entre TRAIN/VAL/OOS, y en M1 el placebo reproduce el efecto.

# DISTANCE TO TARGET

`$150 − $0 = $150` (sin avance neto este round respecto al objetivo económico).

# NEXT ROUND

**Round 13: testear directamente el drift estructural altcoin-vs-BTC como
mecanismo propio** — no un evento de señal sino una **prima de riesgo
sistemática**: canasta corta de altcoins de alta beta/alta vol (financiada con
BTC o USDT) sobre horizontes de días-semanas, con el mismo rigor (TRAIN/VAL/OOS,
placebo, costos + funding reales, capital ≤450, sim causal). Es la única pista
económicamente coherente que dejaron los placebos de este round (el drift negativo
que "contaminó" M1 y M2 por igual) y es un mecanismo genuinamente distinto — no
una variante de dOI, taker, L/S o aceleración. Si tampoco alcanza $150/mes de
forma estable → declarar con evidencia sólida que el objetivo no es alcanzable con
los datos y el universo disponibles, y as recién ahí evaluar una fuente de datos
nueva (no antes).

---

## Infraestructura

Sin cambios — colectores OI/liquidaciones en background (research, no
producción). Nada de producción / perfiles / SL-TP / agente / capital tocado.
