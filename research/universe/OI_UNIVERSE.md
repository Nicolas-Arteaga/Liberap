# OI RESEARCH UNIVERSE

Generado: 2026-09-08T01:38:58.159706+00:00  ·  **63 símbolos**

## Criterio (ex-ante, congelado)

- **Tier 0 (obligatorio):** BTCUSDT, ETHUSDT, SOLUSDT
- **Tier 1:** top 60 perps por mediana de dollar-volume de 5m sobre 30 días locales
- Filtro: cobertura ≥ 95% de barras 5m en la ventana
- Fuente: `binance_vision_clean.db / klines_5m` (perps Binance Futures)
- Ventana: 2026-07-18T23:55:00 → 2026-08-17T23:55:00
- **NO usa resultados de H13.**

## Tier 0

| símbolo | cobertura | mediana $vol 5m |
|---|---|---|
| BTCUSDT | 1.0 | 14231577  |
| ETHUSDT | 1.0 | 10724899  |
| SOLUSDT | 1.0 | 2201808  |

## Tier 1 (top por liquidez)

| # | símbolo | mediana $vol 5m | cobertura |
|---|---|---|---|
| 1 | XRPUSDT | 889,407 | 1.0 |
| 2 | ZECUSDT | 840,283 | 1.0 |
| 3 | HYPEUSDT | 792,361 | 1.0 |
| 4 | BANKUSDT | 706,730 | 1.0 |
| 5 | DOGEUSDT | 509,151 | 1.0 |
| 6 | BNBUSDT | 439,222 | 1.0 |
| 7 | AKEUSDT | 400,000 | 1.0 |
| 8 | DRAMUSDT | 375,892 | 1.0 |
| 9 | ADAUSDT | 279,316 | 1.0 |
| 10 | 1000PEPEUSDT | 270,276 | 1.0 |
| 11 | SAMSUNGUSDT | 224,195 | 1.0 |
| 12 | WLDUSDT | 213,347 | 1.0 |
| 13 | PUMPUSDT | 199,923 | 1.0 |
| 14 | LINKUSDT | 189,438 | 1.0 |
| 15 | BEATUSDT | 186,004 | 1.0 |
| 16 | SUIUSDT | 180,849 | 1.0 |
| 17 | NEARUSDT | 169,335 | 1.0 |
| 18 | KAITOUSDT | 164,591 | 1.0 |
| 19 | ENAUSDT | 152,686 | 1.0 |
| 20 | UNIUSDT | 148,400 | 1.0 |
| 21 | ONDOUSDT | 139,958 | 1.0 |
| 22 | AAVEUSDT | 137,204 | 1.0 |
| 23 | PAXGUSDT | 135,459 | 1.0 |
| 24 | BTWUSDT | 134,986 | 1.0 |
| 25 | AVAXUSDT | 132,451 | 1.0 |
| 26 | TAOUSDT | 124,303 | 1.0 |
| 27 | DEXEUSDT | 118,315 | 1.0 |
| 28 | MRVLUSDT | 114,680 | 1.0 |
| 29 | ONUSDT | 102,851 | 1.0 |
| 30 | HOMEUSDT | 95,039 | 1.0 |
| 31 | LTCUSDT | 85,442 | 1.0 |
| 32 | BCHUSDT | 77,285 | 1.0 |
| 33 | XLMUSDT | 75,699 | 1.0 |
| 34 | FILUSDT | 74,819 | 1.0 |
| 35 | DOTUSDT | 71,580 | 1.0 |
| 36 | ALLOUSDT | 71,222 | 1.0 |
| 37 | 1000SHIBUSDT | 69,632 | 1.0 |
| 38 | REUSDT | 68,402 | 1.0 |
| 39 | LABUSDT | 68,380 | 1.0 |
| 40 | XMRUSDT | 66,896 | 1.0 |
| 41 | COTIUSDT | 65,540 | 1.0 |
| 42 | TRUMPUSDT | 58,683 | 1.0 |
| 43 | ACEUSDT | 58,461 | 1.0 |
| 44 | TRXUSDT | 58,325 | 1.0 |
| 45 | XAUTUSDT | 57,657 | 1.0 |
| 46 | CAPUSDT | 57,115 | 1.0 |
| 47 | LITUSDT | 54,937 | 1.0 |
| 48 | ESPORTSUSDT | 54,853 | 1.0 |
| 49 | EPICUSDT | 54,273 | 1.0 |
| 50 | PENGUUSDT | 54,059 | 1.0 |
| 51 | INJUSDT | 52,520 | 1.0 |
| 52 | UBUSDT | 51,158 | 1.0 |
| 53 | USUSDT | 49,046 | 1.0 |
| 54 | BLESSUSDT | 46,466 | 1.0 |
| 55 | RIFUSDT | 46,295 | 1.0 |
| 56 | 1000BONKUSDT | 46,038 | 1.0 |
| 57 | ZAMAUSDT | 44,405 | 1.0 |
| 58 | ARBUSDT | 43,941 | 1.0 |
| 59 | FETUSDT | 43,379 | 1.0 |
| 60 | GIGGLEUSDT | 39,784 | 1.0 |

## Limitaciones conocidas

- La presencia en klines_5m es PROXY de disponibilidad en openInterestHist; un simbolo listado puede no tener OI historico -> se detecta como coverage baja en el monitor.
- binance_vision_clean.db se congelo el 2026-08-17; simbolos listados despues no aparecen aca. Revisar y regenerar cuando haya klines mas nuevas.
- El colector de liquidaciones usa Bybit; los nombres coinciden en su mayoria pero algunos perps de Binance no existen en Bybit -> se registran como 'no disponible' en su monitor.
