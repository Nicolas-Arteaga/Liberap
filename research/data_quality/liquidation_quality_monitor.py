"""
liquidation_quality_monitor.py — auditoria del RESEARCH DATASET de liquidaciones
(tabla liquidations_research) + salud del colector (liq_collector_health).
Lee agent/data/klines.db (solo lectura). Escribe:
  research/data_quality/liquidation_coverage_report.json
  research/data_quality/LIQUIDATION_COVERAGE_REPORT.md
NO modifica datos. NO oculta gaps/downtime.
"""
import os, sys, json, sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
KLDB = os.path.join(HERE, "..", "..", "agent", "data", "klines.db")
UNIV = os.path.join(HERE, "..", "universe", "oi_universe.json")
GATE_60_D = 60
GATE_90_D = 90


def main():
    con = sqlite3.connect(f"file:{KLDB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        expected = json.load(open(UNIV))["universe"]
    except Exception:
        expected = []

    def table_exists(t):
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

    has_research = table_exists("liquidations_research")
    has_health = table_exists("liq_collector_health")

    rep = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
           "db": os.path.abspath(KLDB),
           "research_table_present": has_research,
           "health_table_present": has_health}

    if not has_research:
        rep["status"] = "NO_RESEARCH_TABLE — el colector todavia no escribio (reiniciar liquidation_tracker.py)"
    else:
        g = con.execute("""SELECT COUNT(*) n, COUNT(DISTINCT symbol) s, MIN(timestamp) lo, MAX(timestamp) hi,
                                  SUM(qty*price) notional FROM liquidations_research""").fetchone()
        span_d = (g["hi"] - g["lo"]) / 86_400_000 if g["lo"] else 0
        dup = con.execute("""SELECT COUNT(*) FROM (SELECT venue,symbol,timestamp,side,price,qty,COUNT(*) c
                             FROM liquidations_research GROUP BY 1,2,3,4,5,6 HAVING c>1)""").fetchone()[0]
        by_venue = {r[0]: r[1] for r in con.execute(
            "SELECT venue,COUNT(*) FROM liquidations_research GROUP BY venue")}
        # eventos/dia
        per_day = con.execute("""SELECT strftime('%Y-%m-%d', timestamp/1000,'unixepoch') d,
                                        COUNT(*) n, COUNT(DISTINCT symbol) s, SUM(qty*price) notional
                                 FROM liquidations_research GROUP BY d ORDER BY d""").fetchall()
        # gaps: mayor silencio global (min) entre eventos consecutivos
        ts = [r[0] for r in con.execute("SELECT timestamp FROM liquidations_research ORDER BY timestamp")]
        big_gap_min = max(((ts[i+1]-ts[i])/60000 for i in range(len(ts)-1)), default=0)
        out_of_order = 0  # se insertan por evento; el orden lo da SQLite en la lectura
        # cobertura por simbolo (nº de eventos; no hay "esperado" para liquidaciones)
        per_sym = [dict(symbol=r[0], events=r[1],
                        first_utc=datetime.utcfromtimestamp(r[2]/1000).isoformat(),
                        last_utc=datetime.utcfromtimestamp(r[3]/1000).isoformat(),
                        last_age_min=round((now_ms - r[3]) / 60000, 1),
                        notional_usd=round(r[4] or 0, 2),
                        in_universe=(r[0] in expected))
                   for r in con.execute("""SELECT symbol,COUNT(*),MIN(timestamp),MAX(timestamp),SUM(qty*price)
                                           FROM liquidations_research GROUP BY symbol ORDER BY COUNT(*) DESC""")]

        rep.update({
            "rows": g["n"], "symbols": g["s"],
            "first_utc": datetime.utcfromtimestamp(g["lo"]/1000).isoformat() if g["lo"] else None,
            "last_utc": datetime.utcfromtimestamp(g["hi"]/1000).isoformat() if g["hi"] else None,
            "last_obs_age_min": round((now_ms - g["hi"]) / 60000, 1) if g["hi"] else None,
            "span_days": round(span_d, 2),
            "total_notional_usd": round(g["notional"] or 0, 2),
            "duplicate_rows": dup,
            "by_venue": by_venue,
            "biggest_inter_event_gap_min": round(big_gap_min, 1),
            "universe_symbols": len(expected),
            "universe_symbols_seen": sum(1 for p in per_sym if p["in_universe"]),
            "universe_symbols_missing": [s for s in expected if s not in {p["symbol"] for p in per_sym}],
            "events_per_day": [dict(day=r[0], events=r[1], symbols=r[2], notional_usd=round(r[3] or 0, 2)) for r in per_day],
            "gate_60d": {"target": GATE_60_D, "current": round(span_d, 2),
                         "remaining_d": round(max(0, GATE_60_D - span_d), 1)},
            "gate_90d": {"target": GATE_90_D, "current": round(span_d, 2),
                         "remaining_d": round(max(0, GATE_90_D - span_d), 1)},
            "pct_events_persisted_ok": 100.0 if dup == 0 else round(100.0 * g["n"] / (g["n"] + dup), 2),
            "per_symbol": per_sym,
        })

    if has_health:
        h = con.execute("""SELECT event, COUNT(*) FROM liq_collector_health GROUP BY event""").fetchall()
        rep["health_events"] = {r[0]: r[1] for r in h}
        last = con.execute("SELECT ts,event,symbols_subscribed,events_since_last,note FROM liq_collector_health ORDER BY ts DESC LIMIT 10").fetchall()
        rep["health_recent"] = [dict(ts_utc=datetime.utcfromtimestamp(r[0]/1000).isoformat(),
                                     event=r[1], symbols=r[2], events_since_last=r[3], note=r[4]) for r in last]
        # downtime estimado: suma de (disconnect -> next connect)
        rows = con.execute("SELECT ts,event FROM liq_collector_health WHERE event IN ('connect','disconnect') ORDER BY ts").fetchall()
        downtime_ms = 0; last_disc = None
        for ts, ev in rows:
            if ev == "disconnect":
                last_disc = ts
            elif ev == "connect" and last_disc is not None:
                downtime_ms += ts - last_disc; last_disc = None
        rep["estimated_downtime_min"] = round(downtime_ms / 60000, 1)
    else:
        rep["health_events"] = "NO_HEALTH_TABLE"

    os.makedirs(HERE, exist_ok=True)
    json.dump(rep, open(os.path.join(HERE, "liquidation_coverage_report.json"), "w"), indent=1, default=str)

    md = ["# LIQUIDATION COVERAGE REPORT", "", f"Generado: {rep['generated_at_utc']}", "",
          f"- DB: `{rep['db']}`",
          f"- Tabla research presente: **{rep['research_table_present']}**",
          f"- Tabla de salud presente: **{rep['health_table_present']}**", ""]
    if not has_research:
        md += [f"**{rep['status']}**", ""]
    else:
        md += [
            f"- Filas: **{rep['rows']:,}** · símbolos: **{rep['symbols']}** · venues: {rep['by_venue']}",
            f"- Span: **{rep['span_days']} días** ({rep['first_utc']} → {rep['last_utc']})",
            f"- Último evento hace: **{rep['last_obs_age_min']} min**",
            f"- Notional total: **${rep['total_notional_usd']:,.0f}**",
            f"- Duplicados: **{rep['duplicate_rows']}** · % persistido OK: **{rep['pct_events_persisted_ok']}%**",
            f"- Mayor silencio entre eventos: **{rep['biggest_inter_event_gap_min']} min**",
            f"- Universo: **{rep['universe_symbols_seen']}/{rep['universe_symbols']}** símbolos con ≥1 evento",
            f"- Faltan (sin ningún evento aún): {rep['universe_symbols_missing'][:30]}{' ...' if len(rep['universe_symbols_missing'])>30 else ''}",
            "",
            f"## Gates",
            f"- ≥60 d: **{rep['gate_60d']['current']}** / 60 · faltan **{rep['gate_60d']['remaining_d']} d**",
            f"- ≥90 d: **{rep['gate_90d']['current']}** / 90 · faltan **{rep['gate_90d']['remaining_d']} d**",
            "",
            f"## Eventos por día", "",
            "| día | eventos | símbolos | notional |",
            "|---|---|---|---|",
        ]
        for r in rep["events_per_day"]:
            md.append(f"| {r['day']} | {r['events']} | {r['symbols']} | ${r['notional_usd']:,.0f} |")
        md += ["", "## Salud del colector", "",
               f"- Eventos: {rep.get('health_events')}",
               f"- Downtime estimado: **{rep.get('estimated_downtime_min','?')} min**", ""]
    open(os.path.join(HERE, "LIQUIDATION_COVERAGE_REPORT.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    if has_research:
        print(f"rows={rep['rows']} syms={rep['symbols']} span={rep['span_days']}d dups={rep['duplicate_rows']} "
              f"age_min={rep['last_obs_age_min']}")
    else:
        print(rep["status"])
    print("escrito: research/data_quality/liquidation_coverage_report.json + LIQUIDATION_COVERAGE_REPORT.md")


if __name__ == "__main__":
    main()
