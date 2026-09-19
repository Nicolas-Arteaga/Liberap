# ROUND 10 — dOI REGIME BREAK TEST

## Conclusión ejecutiva (≤10 líneas)

1. La lectura de R9 ("dOI parece beta de régimen bajista") era **incorrecta**. Con
   descomposición por régimen: el efecto dOI (H13-C A/D, operado SHORT) vive en
   **BTC UP y BTC FLAT**, y **desaparece en BTC DOWN** (CI incluye 0 en todos los
   horizontes ≤8h).
2. **Placebo limpio:** barras aleatorias en el mismo régimen dan ≈ 0 bp
   (FLAT: −0.5/+1.2/+1.6 @2h/4h/8h). El efecto NO es "el régimen revierte solo".
3. **Control de beta (OLS):** en UP, `t(dOI) = −10.2` y ΔR² = +4.8% tras controlar
   BTC/mercado/momentum/vol → **información incremental real, la más fuerte del
   proyecto**. En FLAT `t(dOI) ≈ 0` → el efecto FLAT es común-move/momentum, no dOI.
4. **Falla estabilidad temporal:** TRAIN (dic-2025 → 25-abr-2026) ≈ **0 bp** a
   horizontes operables (2h: −0.15; 4h: +5.8); VAL y OOS fuertemente positivos y
   consistentes. El signal "se encendió" en la segunda mitad de la muestra.
5. **Falla concentración:** UPFLAT @4h, quitar top-7 de 63 símbolos baja el efecto
   de 42 → 7.5 bp (−82%). Mediana por símbolo solo 10 bp. `top5_conc` 0.63.
6. **Económico:** sim con entrada `open[t+1]`, RT 24 bp + funding → UPFLAT @4h
   NET ≈ $505/mes, @8h ≈ $1234/mes — **pero mediana de trade NEGATIVA** (−14/−6 bp),
   WR < 0.5, PF 1.1–1.24: es cola derecha, no un edge robusto.
7. **VERDICT: PARK.** Evidencia incremental real (UP, OLS) + placebo limpio, pero
   sin estabilidad temporal, muy concentrado y tail-dependiente.

---

## Tablas

### (1) dOI por régimen — A+D pooled, SHORT (+ = el short ganó), close-to-close

| Régimen | n | 15m | 30m | 1h | 2h | 4h | 8h | 24h | symPos | conc |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **UP** | 1858 | +6.3* | +11.9* | +16.6* | +21.9* | +37.8* | +71.1* | +145.9* | 0.52–0.66 | 0.50–0.70 |
| **FLAT** | 5460 | +7.3* | +16.5* | +15.7* | +26.8* | +43.8* | +67.4* | +148.8* | 0.56–0.65 | 0.50–0.75 |
| **DOWN** | 3491 | +2.1 | −1.2 | −1.6 | −1.9 | +2.1 | +18.6 | +59.6* | 0.35–0.65 | 0.45–0.73 |

`*` = CI bootstrap (cluster símbolo) excluye 0. net ≈ |mean| − 20 bp.

### (2) Matched control (OI PLANO, `|z_ret|≥1 & |z_dOI|≤0.3`), misma dirección SHORT

| Régimen | 2h | 4h | 8h | 24h |
|---|--:|--:|--:|--:|
| UP  | +2.7 | +4.1 | +10.7 | +21.3 |
| FLAT | +5.1* | +8.4 | +7.8 | +18.2 |
| DOWN | −0.3 | +1.7 | +6.5 | +59.8* |

→ En UP y FLAT el bucket real (OI cambiando) es **2–8× el matched** (OI plano):
consistente con que OI aporta. En DOWN real ≈ matched ≈ 0 (salvo 24h).

### (3) Residual-BTC (A+D, resta `beta·ret_BTC` del forward)

| Régimen | 2h | 4h | 8h |
|---|--:|--:|--:|
| UP  | +24.0* | +37.3* | +66.4* |
| FLAT | +26.8* | +40.5* | +61.5* |
| DOWN | −2.3 | −0.1 | +9.3 |

→ El efecto UP/FLAT NO es beta de BTC (sobrevive residualizar).

### (4) CONTROL DE BETA — OLS `signed_fwd ~ 1 + dOI + btc_fwd + mkt_fwd + retlong + rv`

| Régimen | h | t(dOI) | ΔR² por dOI | t(btc_fwd) |
|---|---|--:|--:|--:|
| **UP** | 2h | **−10.2** | **+0.048** | +2.4 |
| **UP** | 4h | **−7.5** | **+0.025** | +1.7 |
| FLAT | 2h | −0.7 | +0.0001 | −5.3 |
| FLAT | 4h | −0.3 | +0.00002 | −6.2 |
| DOWN | 2h | +1.6 | +0.0006 | +0.6 |
| DOWN | 4h | +1.5 | +0.0006 | +0.3 |

→ **dOI aporta información incremental genuina SOLO en el régimen UP.** En FLAT el
`btc_fwd`/`mkt_fwd` absorben todo (los eventos A/D en FLAT se agrupan en pequeños
techos/pisos del mercado y la cesta entera revierte — beta-timing, no dOI-alpha).
En DOWN, nada.

### (5) MATRIZ RÉGIMEN × TRAIN/VAL/OOS (A+D SHORT, bp; `*`=CI excl 0)

| Régimen | split | 15m | 30m | 1h | 2h | 4h | 8h | 24h |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| **UP** | train (n~890) | −0 | +0 | +0 | +6 | +4 | +21* | +101* |
| **UP** | val (n~477) | +10 | +24* | +17 | +10 | +33 | +34 | −10 |
| **UP** | oos (n~491) | +15* | +21 | +46* | +61* | +103 | +198 | +379 |
| **FLAT** | train (n~1306) | +0 | −1 | −5 | −5 | +7 | +12 | +8 |
| **FLAT** | val (n~1622) | +8 | +16* | +20 | +27* | +45* | +62* | +60 |
| **FLAT** | oos (n~2532) | +11* | +26* | +23* | +43* | +62* | +99* | +278* |
| **DOWN** | train (n~1313) | +2 | −3 | +3 | +0 | −8 | −24* | −4 |
| **DOWN** | val (n~1431) | −2 | −8* | −20* | −15* | −6 | +37 | +118* |
| **DOWN** | oos (n~747) | +11* | +15 | +25* | +20 | +34 | +58 | +59 |

→ **UP y FLAT: TRAIN ≈ 0 a horizontes operables, VAL y OOS fuertemente positivos.**
El efecto es de la segunda mitad de la muestra. DOWN: signo inestable train/val/oos.

### (6) Per-symbol / leave-top-k (UP∪FLAT, @4h SHORT)

| | media (bp) |
|---|--:|
| todos (63 sym, symPos 0.62, mediana-símbolo **10.1 bp**) | +42.3 |
| − top1 | +33.6 |
| − top3 | +21.4 |
| − top5 | +12.3 |
| − top7 | **+7.5** |

→ ~11% de los símbolos (LAB, ESPORTS, DEXE, EPIC, KAITO, RIF, HOME, BEAT…) cargan
~82% del efecto. La mediana por símbolo (10 bp) **no cubre el costo** (24 bp).
**FRAGILE por concentración.**

### (7) Placebo — barras aleatorias en el mismo régimen (SHORT)

| Grupo | 2h | 4h | 8h |
|---|--:|--:|--:|
| UP | +6.8* | −6.1 | −17.5* |
| FLAT | −0.5 | +1.2 | +1.6 |
| UP∪FLAT | +1.0 | −0.3 | −2.3 |

→ **Limpio.** El evento A/D separa +44/+88 bp (UP) y +43/+66 bp (FLAT) POR ENCIMA
del baseline del régimen. El efecto no es "estar en un uptrend/rango".

### (8) Sensibilidad de threshold (diagnóstico, no optimización)

| z_evento | UP 2h/4h | FLAT 2h/4h | DOWN 2h/4h |
|---|---|---|---|
| ≥1.0 (congelado) | +21.9* / +37.8* | +26.8* / +43.8* | −1.9 / +2.1 |
| ≥1.5 | +50.0* / +64.8 | +34.7* / +56.3* | −34.8* / −21.4 |

→ UP/FLAT robustos a subir el umbral (efecto crece, no aparece/desaparece).
DOWN se hace **más negativo** al endurecer → el signo opuesto en DOWN es real, no ruido.

### (9) Dirección — A sola / D sola (SHORT), UP∪FLAT

- **A (precio↓ + OI↑)** es la pata fuerte: FLAT A-only +24*/+27*/+41*/+66*/+98*
  @30m–8h (CI excl 0 en todos). UP A-only fuerte pero ruidoso a horizontes cortos.
- **D (precio↑ + OI↓)** más débil: varias CI incluyen 0 en FLAT; en UP +18*/+26*/+37*.
- Invertido (LONG) = espejo mecánico (−1×), no informativo como placebo.

### (10) Curva de decay (UP∪FLAT SHORT, bp)

15m +7 → 30m +15 → 1h +16 → 2h +26 → **4h +42** → 8h +68 → 24h +148.
→ **Aparece lentamente y persiste/crece.** No hay pico temprano operable; el
grueso monetizable está a 4–8h de holding (drift, no reacción rápida).

### (11) Sim económica (entrada `open[t+1]`, SHORT, RT 24 bp + ~funding)

| Grupo | h | trades/mes | avg_net | **med_net** | WR | PF | NET/mes (1 slot $300) |
|---|---|--:|--:|--:|--:|--:|--:|
| UP | 4h | 257 | +13.2 bp | **−1.8** | 0.49 | 1.12 | $102 |
| UP | 8h | 257 | +45.7 bp | +21.0 | 0.53 | 1.32 | $353 |
| FLAT | 4h | 716 | +19.0 bp | **−17.7** | 0.45 | 1.13 | $408 |
| FLAT | 8h | 716 | +41.9 bp | **−14.9** | 0.47 | 1.22 | $901 |
| UP∪FLAT | 4h | 959 | +17.5 bp | **−14.0** | 0.46 | 1.13 | $505 |
| UP∪FLAT | 8h | 959 | +42.9 bp | **−6.3** | 0.49 | 1.24 | $1234 |

→ El NET/mes en papel supera el objetivo, **pero la mediana de trade es negativa**
en casi todo, WR < 0.5, PF 1.1–1.24: PnL de **cola derecha**. Además 959 eventos/mes
con holding 2–8h no son capturables con ≤450 USDT (1–2 slots) — la captura real
recorta el NET a una fracción muy incierta.

---

## ROUND 10 VERDICT

# PARK

**Por qué no FAILED:** (a) placebo de barras aleatorias por régimen ≈ 0 → el efecto
es del evento A/D, no del régimen; (b) en el régimen **UP**, `dOI` aporta
información **incremental** medida por OLS con ΔR² = +4.8% y `t = −10` tras
controlar movimiento común, momentum y vol — la evidencia incremental más fuerte
de todo el proyecto; (c) VAL y OOS coinciden en signo y magnitud; (d) el matched
control (OI plano) es 2–8× menor que el bucket real en UP/FLAT.

**Por qué no CANDIDATE — exactamente qué dimensiones faltan:**
1. **Estabilidad temporal (bloqueo principal).** TRAIN ≈ 0 bp a 2h/4h en UP y FLAT;
   todo el efecto está en la segunda mitad (may–ago 2026). Un signal que se enciende
   a mitad de muestra no es promovible.
2. **Concentración.** ~11% de los símbolos cargan ~82% del efecto; mediana por
   símbolo (10 bp) < costo (24 bp). FRAGILE.
3. **Magnitud "real".** Mediana de trade negativa, WR < 0.5, PF ≈ 1.1–1.24: depende
   de una cola de pocos aciertos grandes, no de un edge por trade.
4. **FLAT no es dOI.** El 75% de los eventos (FLAT) tienen `t(dOI) ≈ 0` en el OLS —
   son beta-timing de la cesta, no información de posicionamiento. El dOI-alpha real
   queda reducido al régimen UP (n=1858, ~25% de los eventos).

## ECONOMIC VERDICT

**No — no se puede afirmar razonablemente ≥150 USDT/mes con ≤450 USDT.**
La sim da $100–$500/mes @4h en papel, pero: mediana de trade negativa, WR < 0.5,
PnL de cola, ~960 eventos/mes imposibles de capturar con 1–2 slots, y el efecto
**no existe en la primera mitad de la muestra**. Podría ser una señal científica
real (el OLS de UP lo respalda), pero **no es una candidata económica** hasta
resolver estabilidad temporal y concentración.

## NEXT ROUND — una sola dirección

**Round 11 = TEST DE ESTACIONARIEDAD CON HISTORIA EXTENDIDA Y UNIVERSO SIN SESGO DE
LISTING.**

Concretamente y sin alternativas:
- Backfill de `oi_metrics` **hacia atrás** desde `data.binance.vision` (las métricas
  existen al menos desde 2025-11; probar 2025-06 → 2025-11) **+** klines 15m del
  mismo período para los mismos símbolos.
- Re-correr **exactamente** el test de régimen de R10 (misma definición A/D, mismos
  horizontes, mismo umbral) sobre la ventana extendida, con el **universo
  restringido a los ~40 símbolos que ya cotizaban en dic-2025** (elimina el sesgo de
  los ~20 que listaron a mitad de muestra y vaciaron TRAIN).
- Criterio de decisión único: si el efecto UP/FLAT-SHORT **sigue apareciendo solo
  después de ~abr-2026** en la ventana larga y con universo limpio → es no
  estacionario → **FAILED**. Si aparece de forma pareja a lo largo de una ventana
  ≥12 meses con TRAIN/VAL/OOS todos positivos → recién ahí se re-evalúa
  concentración y, si pasa, CANDIDATE.

No tocar producción / perfiles / SL-TP / agente / capital. `toptrader_ls_pos`,
`global_ls_acct`, aceleración de OI y ML siguen **congelados** hasta que dOI básico
resuelva estacionariedad.
