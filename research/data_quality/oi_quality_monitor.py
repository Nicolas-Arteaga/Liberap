"""
oi_quality_monitor.py — auditoria periodica del dataset de Open Interest.
Lee agent/data/klines.db (solo lectura) + research/universe/oi_universe.json.
Escribe:
  research/data_quality/oi_coverage_report.json
  research/data_quality/OI_COVERAGE_REPORT.md

NO modifica datos. NO oculta gaps. Pensado para correr por cron cada N horas.
"""
import os, sys, json, sqlite3, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
KLDB = os.path.join(HERE, "..", "..", "agent", "data", "klines.db")
UNIV = os.path.join(HERE, "..", "universe", "oi_universe.json")
PERIOD_MS = 300_000
GATE_DAYS = 70


def main():
    con = sqlite3.connect(f"file:{KLDB}?mode=ro", uri=True)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    try:
        expected_syms = json.load(open(UNIV))["universe"]
    except Exception:
        expected_syms = []

    have = con.execute("""
        SELECT symbol, COUNT(*) n, MIN(timestamp) lo, MAX(timestamp) hi
        FROM open_interest WHERE exchange='binance' AND period='5m'
        GROUP BY symbol
    """).fetchall()
    have_map = {r[0]: dict(rows=r[1], lo=r[2], hi=r[3]) for r in have}

    glo = con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM open_interest").fetchone()
    span_days = (glo[1] - glo[0]) / 86_400_000 if glo[0] else 0

    # duplicados: PRIMARY KEY (exchange,symbol,period,timestamp) => imposible; se verifica igual
    dup = con.execute("""
        SELECT COUNT(*) FROM (
          SELECT exchange,symbol,period,timestamp,COUNT(*) c
          FROM open_interest GROUP BY 1,2,3,4 HAVING c>1)
    """).fetchone()[0]

    per_symbol = []
    for s in sorted(set(expected_syms) | set(have_map)):
        h = have_map.get(s)
        if not h or h["rows"] < 2:
            per_symbol.append(dict(symbol=s, status="MISSING" if s in expected_syms else "extra",
                                   rows=(h["rows"] if h else 0), coverage_pct=None,
                                   last_obs_utc=None, last_obs_age_min=None,
                                   in_universe=(s in expected_syms)))
            continue
        expected = (h["hi"] - h["lo"]) // PERIOD_MS + 1
        cov = round(100.0 * h["rows"] / expected, 2)
        # gaps: intervalos consecutivos ausentes
        ts = [r[0] for r in con.execute(
            "SELECT timestamp FROM open_interest WHERE symbol=? AND period='5m' ORDER BY timestamp", (s,))]
        gaps = []
        for i in range(1, len(ts)):
            d = ts[i] - ts[i - 1]
            if d > PERIOD_MS:
                gaps.append(dict(start_utc=datetime.utcfromtimestamp(ts[i-1]/1000).isoformat(),
                                 missing_buckets=int(d // PERIOD_MS) - 1))
        out_of_order = sum(1 for i in range(1, len(ts)) if ts[i] <= ts[i-1])
        age_min = round((now_ms - h["hi"]) / 60000, 1)
        per_symbol.append(dict(
            symbol=s, status="OK" if cov >= 95 and age_min < 30 else "DEGRADED",
            rows=h["rows"], coverage_pct=cov,
            first_obs_utc=datetime.utcfromtimestamp(h["lo"]/1000).isoformat(),
            last_obs_utc=datetime.utcfromtimestamp(h["hi"]/1000).isoformat(),
            last_obs_age_min=age_min,
            n_gaps=len(gaps), biggest_gap_buckets=(max((g["missing_buckets"] for g in gaps), default=0)),
            total_missing_buckets=sum(g["missing_buckets"] for g in gaps),
            out_of_order_pairs=out_of_order,
            in_universe=(s in expected_syms)))

    in_u = [p for p in per_symbol if p["in_universe"]]
    covs = [p["coverage_pct"] for p in in_u if p["coverage_pct"] is not None]
    ge90 = [p for p in in_u if (p["coverage_pct"] or 0) >= 90 and (p.get("last_obs_age_min") or 1e9) < 60]
    freshest = max((p.get("last_obs_age_min") for p in in_u if p.get("last_obs_age_min") is not None), default=None)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "db": os.path.abspath(KLDB),
        "global_span_days": round(span_days, 2),
        "global_first_utc": datetime.utcfromtimestamp(glo[0]/1000).isoformat() if glo[0] else None,
        "global_last_utc": datetime.utcfromtimestamp(glo[1]/1000).isoformat() if glo[1] else None,
        "expected_symbols": len(expected_syms),
        "symbols_with_any_data": len([p for p in in_u if p["rows"] >= 2]),
        "symbols_missing_from_universe": [p["symbol"] for p in in_u if p["status"] == "MISSING"],
        "symbols_ge90pct_and_fresh": len(ge90),
        "median_coverage_pct_in_universe": round(statistics.median(covs), 2) if covs else None,
        "duplicate_rows": dup,
        "gate_70d": {
            "target_days": GATE_DAYS, "current_days": round(span_days, 2),
            "days_remaining": round(max(0, GATE_DAYS - span_days), 1),
            "eta_utc": None if span_days >= GATE_DAYS else
                (datetime.now(timezone.utc).timestamp() + (GATE_DAYS - span_days) * 86400),
            "symbols_ge90_ge20": len(ge90) >= 20,
        },
        "per_symbol": sorted(per_symbol, key=lambda p: (p["status"] != "OK", -(p["coverage_pct"] or 0))),
    }
    if report["gate_70d"]["eta_utc"]:
        report["gate_70d"]["eta_utc"] = datetime.utcfromtimestamp(report["gate_70d"]["eta_utc"]).isoformat()

    os.makedirs(HERE, exist_ok=True)
    json.dump(report, open(os.path.join(HERE, "oi_coverage_report.json"), "w"), indent=1, default=str)

    md = [
        "# OI COVERAGE REPORT", "",
        f"Generado: {report['generated_at_utc']}", "",
        f"- DB: `{report['db']}`",
        f"- Span histórico: **{report['global_span_days']} días** ({report['global_first_utc']} → {report['global_last_utc']})",
        f"- Universo esperado: **{report['expected_symbols']}** símbolos",
        f"- Con datos: **{report['symbols_with_any_data']}**",
        f"- Con ≥90% cobertura y frescos: **{report['symbols_ge90pct_and_fresh']}**",
        f"- Cobertura mediana (universo): **{report['median_coverage_pct_in_universe']}%**",
        f"- Filas duplicadas: **{report['duplicate_rows']}**",
        f"- Faltantes del universo: {report['symbols_missing_from_universe'] or 'ninguno'}",
        "",
        f"## Gate de 70 días",
        f"- Actual: **{report['gate_70d']['current_days']} d** · faltan **{report['gate_70d']['days_remaining']} d** · ETA ≈ **{report['gate_70d']['eta_utc']}**",
        f"- ≥20 símbolos con ≥90% + frescos: **{report['gate_70d']['symbols_ge90_ge20']}**",
        "",
        "## Por símbolo",
        "",
        "| símbolo | estado | cobertura | filas | último dato (edad min) | gaps | mayor gap (buckets) | fuera de orden |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in report["per_symbol"]:
        md.append(f"| {p['symbol']} | {p['status']} | {p.get('coverage_pct')}% | {p['rows']} | "
                  f"{p.get('last_obs_age_min')} | {p.get('n_gaps','-')} | {p.get('biggest_gap_buckets','-')} | "
                  f"{p.get('out_of_order_pairs','-')} |")
    open(os.path.join(HERE, "OI_COVERAGE_REPORT.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    print(f"span={report['global_span_days']}d  syms_ge90_fresh={report['symbols_ge90pct_and_fresh']}  "
          f"dups={dup}  gate70_eta={report['gate_70d']['eta_utc']}")
    print("escrito: research/data_quality/oi_coverage_report.json + OI_COVERAGE_REPORT.md")


if __name__ == "__main__":
    main()
