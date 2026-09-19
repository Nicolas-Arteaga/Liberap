"""
build_oi_universe.py — define EX-ANTE el universo de research para el colector
de Open Interest (y, por defecto, tambien el de liquidaciones).

CRITERIO (congelado, NO depende de resultados de H13):
  Tier 0  (obligatorio, siempre): BTC, ETH, SOL
  Tier 1  : top N perps por LIQUIDEZ, medida como la MEDIANA del dollar-volume
            de 5m sobre los ultimos LOOKBACK_DAYS de datos locales
            (binance_vision_clean.db / klines_5m), que son perps de Binance
            Futures -> su presencia ahi es proxy de disponibilidad en el
            endpoint openInterestHist.
  Filtro  : el simbolo tiene que tener >= MIN_COVERAGE de barras de 5m en la
            ventana (descarta deslistados / listings muy nuevos sin historia).

Salida:
  research/universe/oi_universe.json   (machine-readable)
  research/universe/OI_UNIVERSE.md     (humano)

NO se llama a ninguna API. Solo lee datos locales. Reproducible.
"""
import os, sys, json, sqlite3, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
BV = os.path.join(HERE, "..", "..", "agent", "data", "binance_vision_clean.db")

TIER0 = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIER1_N = 60
LOOKBACK_DAYS = 30
MIN_COVERAGE = 0.95          # perps cripto operan 24/7 -> exigimos ~cobertura total.
                            # Los perps tokenizados de acciones/commodities tienen
                            # gaps de fin de semana y quedan afuera por este filtro
                            # + la blocklist de abajo.
BAR_MS = 300_000

# Roots de perps tokenizados de acciones/commodities/ETFs de Binance: son otra
# clase de activo (gapean con la apertura/cierre bursatil, no son microestructura
# cripto). Se excluyen EX-ANTE del universo de research de OI/liquidaciones.
EQUITY_COMMODITY_ROOTS = {
    "XAU", "XAG", "XPT", "XPD", "WTI", "CL", "BZ", "NG", "HG",          # commodities
    "SPCX", "SOXL", "SOXS", "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",     # equities / ETFs
    "GOOGL", "GOOG", "META", "MSTR", "COIN", "HOOD", "CRCL", "MU",
    "SNDK", "SKHYNIX", "SKHY", "KORU", "SNDL", "AMD", "INTC", "PLTR",
    "SMCI", "ARM", "AVGO", "TSM", "QCOM", "ORCL", "ADBE", "NFLX", "DIS",
    "BABA", "NKE", "SBUX", "PYPL", "SQ", "UBER", "ABNB", "RBLX", "SNAP",
    "EWY", "EWJ", "XLE", "XLF", "SPY", "QQQ", "IWM", "GLD", "SLV", "USO",
    "MU", "WOLF", "VRT", "APP", "NBIS", "RKLB", "ONDS", "ASTS", "LUNR",
}


def _root(sym: str) -> str:
    for q in ("USDT", "USDC", "USD"):
        if sym.endswith(q):
            return sym[:-len(q)]
    return sym


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    tmax = con.execute("SELECT MAX(open_time) FROM klines_5m").fetchone()[0]
    tmin = tmax - LOOKBACK_DAYS * 86_400_000
    expected_bars = LOOKBACK_DAYS * 288

    rows = con.execute("""
        SELECT symbol, COUNT(*) n,
               -- dollar volume por barra = close * volume ; guardamos la lista para la mediana
               GROUP_CONCAT(CAST(close*volume AS INT)) dv
        FROM klines_5m
        WHERE interval='5m' AND open_time BETWEEN ? AND ?
        GROUP BY symbol
    """, (tmin, tmax)).fetchall()

    cand = []
    excluded_equity = []
    for sym, n, dv in rows:
        cov = n / expected_bars
        if cov < MIN_COVERAGE:
            continue
        if not sym.endswith("USDT"):
            continue
        if _root(sym) in EQUITY_COMMODITY_ROOTS:
            excluded_equity.append(sym)
            continue
        vals = [int(x) for x in dv.split(",") if x]
        if not vals:
            continue
        med_dv = statistics.median(vals)
        cand.append({"symbol": sym, "coverage": round(cov, 3),
                     "median_5m_dollar_vol": int(med_dv),
                     "bars": n})

    cand.sort(key=lambda c: -c["median_5m_dollar_vol"])

    # Tier 1 = top N por liquidez, excluyendo los de Tier 0 (van aparte)
    tier1 = [c for c in cand if c["symbol"] not in TIER0][:TIER1_N]
    tier0_rows = []
    for s in TIER0:
        m = next((c for c in cand if c["symbol"] == s), None)
        tier0_rows.append(m or {"symbol": s, "coverage": None,
                                "median_5m_dollar_vol": None, "bars": 0,
                                "note": "sin datos locales en la ventana; se recolecta igual (obligatorio)"})

    universe = [c["symbol"] for c in tier0_rows] + [c["symbol"] for c in tier1]
    # dedup preservando orden
    seen = set(); universe = [s for s in universe if not (s in seen or seen.add(s))]

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "criterion": {
            "tier0": "BTC/ETH/SOL obligatorio",
            "tier1": f"top {TIER1_N} perps por mediana de dollar-volume 5m sobre {LOOKBACK_DAYS}d locales",
            "min_coverage": MIN_COVERAGE,
            "data_source": "binance_vision_clean.db / klines_5m (perps Binance Futures)",
            "window_utc": [datetime.utcfromtimestamp(tmin/1000).isoformat(),
                           datetime.utcfromtimestamp(tmax/1000).isoformat()],
            "note": "seleccion EX-ANTE por liquidez/disponibilidad; NO usa resultados de H13",
        },
        "tier0": tier0_rows,
        "tier1": tier1,
        "universe": universe,
        "n": len(universe),
        "excluded_equity_commodity": sorted(excluded_equity),
        "known_limitations": [
            "La presencia en klines_5m es PROXY de disponibilidad en openInterestHist; "
            "un simbolo listado puede no tener OI historico -> se detecta como coverage baja en el monitor.",
            "binance_vision_clean.db se congelo el 2026-08-17; simbolos listados despues "
            "no aparecen aca. Revisar y regenerar cuando haya klines mas nuevas.",
            "El colector de liquidaciones usa Bybit; los nombres coinciden en su mayoria "
            "pero algunos perps de Binance no existen en Bybit -> se registran como 'no disponible' en su monitor.",
        ],
    }

    os.makedirs(HERE, exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "oi_universe.json"), "w"), indent=1)

    md = [f"# OI RESEARCH UNIVERSE\n",
          f"Generado: {out['generated_at_utc']}  ·  **{out['n']} símbolos**\n",
          "## Criterio (ex-ante, congelado)\n",
          f"- **Tier 0 (obligatorio):** {', '.join(TIER0)}",
          f"- **Tier 1:** top {TIER1_N} perps por mediana de dollar-volume de 5m sobre {LOOKBACK_DAYS} días locales",
          f"- Filtro: cobertura ≥ {MIN_COVERAGE:.0%} de barras 5m en la ventana",
          f"- Fuente: `binance_vision_clean.db / klines_5m` (perps Binance Futures)",
          f"- Ventana: {out['criterion']['window_utc'][0]} → {out['criterion']['window_utc'][1]}",
          "- **NO usa resultados de H13.**\n",
          "## Tier 0\n",
          "| símbolo | cobertura | mediana $vol 5m |",
          "|---|---|---|"]
    for c in tier0_rows:
        md.append(f"| {c['symbol']} | {c.get('coverage')} | {c.get('median_5m_dollar_vol')} {c.get('note','')} |")
    md += ["\n## Tier 1 (top por liquidez)\n",
           "| # | símbolo | mediana $vol 5m | cobertura |",
           "|---|---|---|---|"]
    for i, c in enumerate(tier1, 1):
        md.append(f"| {i} | {c['symbol']} | {c['median_5m_dollar_vol']:,} | {c['coverage']} |")
    md += ["\n## Limitaciones conocidas\n"]
    for l in out["known_limitations"]:
        md.append(f"- {l}")
    open(os.path.join(HERE, "OI_UNIVERSE.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    print(f"universo: {out['n']} simbolos  (Tier0 {len(TIER0)} + Tier1 {len(tier1)})")
    print("Tier 0:", [c["symbol"] for c in tier0_rows])
    print("Tier 1 (primeros 15):", [c["symbol"] for c in tier1[:15]])
    print("escrito: research/universe/oi_universe.json + OI_UNIVERSE.md")


if __name__ == "__main__":
    main()
