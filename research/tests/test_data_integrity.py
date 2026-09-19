"""
test_data_integrity.py — pruebas de integridad/persistencia de los datasets de
research. NO tocan la DB real: cada test trabaja sobre una DB temporal creada
con el MISMO esquema (via kline_cache). Sin llamadas a APIs.

Cubre:
  OI:   upsert idempotente, out-of-order, gap detectable, "restart" (reabrir),
        no-duplicados por PK.
  LIQ:  insert_liquidation_research idempotente (dedup), out-of-order,
        prune del live cache NO toca research, "restart" (reabrir).

Correr:  python research/tests/test_data_integrity.py
Salida:  research/tests/INTEGRITY_TEST_RESULTS.md  + exit code 0/1
"""
import os, sys, time, tempfile, sqlite3, json
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "agent"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}")
    return cond


def fresh_cache(path):
    import kline_cache
    # forzar una instancia nueva apuntando a `path`
    return kline_cache.KlineCache(db_path=path)


def main():
    tmpdir = tempfile.mkdtemp(prefix="verge_itest_")
    db = os.path.join(tmpdir, "klines.db")
    now = int(time.time() * 1000)
    B = 300_000

    # ───────────────────────── OPEN INTEREST ─────────────────────────
    c = fresh_cache(db)

    # 1. upsert idempotente: mismo bucket 2 veces -> 1 fila, valor actualizado
    recs = [{"timestamp": now - 10 * B, "open_interest": 100.0, "open_interest_value": 1000.0}]
    c.bulk_upsert_open_interest("TESTUSDT", recs)
    recs2 = [{"timestamp": now - 10 * B, "open_interest": 111.0, "open_interest_value": 1110.0}]
    c.bulk_upsert_open_interest("TESTUSDT", recs2)
    n = c._conn().execute("SELECT COUNT(*) FROM open_interest WHERE symbol='TESTUSDT'").fetchone()[0]
    v = c._conn().execute("SELECT open_interest FROM open_interest WHERE symbol='TESTUSDT'").fetchone()[0]
    check("OI upsert idempotente (1 fila)", n == 1, f"n={n}")
    check("OI upsert actualiza valor", v == 111.0, f"oi={v}")

    # 2. out-of-order: insertar un bucket ANTERIOR despues -> queda ordenado por query
    c.bulk_upsert_open_interest("TESTUSDT", [{"timestamp": now - 20 * B, "open_interest": 90.0}])
    ts = [r[0] for r in c._conn().execute(
        "SELECT timestamp FROM open_interest WHERE symbol='TESTUSDT' ORDER BY timestamp")]
    check("OI out-of-order queda ordenado al leer", ts == sorted(ts), f"ts={ts}")

    # 3. gap detectable
    c.bulk_upsert_open_interest("TESTUSDT", [{"timestamp": now - 3 * B, "open_interest": 120.0}])  # salto
    g = c.open_interest_gaps("TESTUSDT")
    check("OI gap detectable (missing>0)", g["missing"] > 0, f"gaps={g}")

    # 4. no-duplicados por PK aunque se re-inserte todo
    for _ in range(3):
        c.bulk_upsert_open_interest("TESTUSDT", recs + recs2 +
                                    [{"timestamp": now - 3 * B, "open_interest": 120.0}])
    dup = c._conn().execute("""SELECT COUNT(*) FROM (SELECT exchange,symbol,period,timestamp,COUNT(*) k
                               FROM open_interest GROUP BY 1,2,3,4 HAVING k>1)""").fetchone()[0]
    check("OI sin duplicados tras re-insert x3", dup == 0, f"dup_groups={dup}")

    # 5. "restart": cerrar y reabrir -> los datos siguen
    n_before = c._conn().execute("SELECT COUNT(*) FROM open_interest").fetchone()[0]
    try:
        c._local.conn.close()
    except Exception:
        pass
    c._local.conn = None
    c2 = fresh_cache(db)
    n_after = c2._conn().execute("SELECT COUNT(*) FROM open_interest").fetchone()[0]
    check("OI sobrevive reopen (restart)", n_after == n_before and n_after > 0, f"{n_before} -> {n_after}")

    # ───────────────────────── LIQUIDATIONS ─────────────────────────
    c = c2

    # 6. research insert idempotente (dedup por tupla natural)
    ev = dict(symbol="TESTUSDT", side="Sell", qty=10.0, price=2.5, timestamp_ms=now - 5 * B)
    r1 = c.insert_liquidation_research(**ev)
    r2 = c.insert_liquidation_research(**ev)          # duplicado exacto (resubscribe de Bybit)
    n = c._conn().execute("SELECT COUNT(*) FROM liquidations_research WHERE symbol='TESTUSDT'").fetchone()[0]
    check("LIQ research insert nuevo devuelve True", r1 is True)
    check("LIQ research duplicado devuelve False", r2 is False)
    check("LIQ research dedup (1 fila)", n == 1, f"n={n}")

    # 7. eventos genuinamente distintos NO se deduplican
    c.insert_liquidation_research(symbol="TESTUSDT", side="Buy", qty=10.0, price=2.5, timestamp_ms=now - 5 * B)
    c.insert_liquidation_research(symbol="TESTUSDT", side="Sell", qty=99.0, price=2.5, timestamp_ms=now - 5 * B)
    n = c._conn().execute("SELECT COUNT(*) FROM liquidations_research WHERE symbol='TESTUSDT'").fetchone()[0]
    check("LIQ research: eventos distintos se guardan", n == 3, f"n={n}")

    # 8. out-of-order: insertar evento viejo despues -> ordenado al leer
    c.insert_liquidation_research(symbol="TESTUSDT", side="Sell", qty=1.0, price=2.5, timestamp_ms=now - 40 * B)
    ts = [r[0] for r in c._conn().execute(
        "SELECT timestamp FROM liquidations_research WHERE symbol='TESTUSDT' ORDER BY timestamp")]
    check("LIQ research out-of-order ordenado al leer", ts == sorted(ts), f"ts={ts}")

    # 9. LIVE CACHE: meter una liquidacion vieja + una nueva
    c.insert_liquidation("TESTUSDT", "Sell", 5.0, 2.5, now - 20 * 24 * 3600 * 1000)  # 20 dias -> vieja
    c.insert_liquidation("TESTUSDT", "Sell", 5.0, 2.5, now - 1 * 3600 * 1000)        # 1h -> nueva
    live_before = c._conn().execute("SELECT COUNT(*) FROM liquidations").fetchone()[0]
    research_before = c._conn().execute("SELECT COUNT(*) FROM liquidations_research").fetchone()[0]

    # 10. EL TEST CLAVE: prune del live cache NO toca research
    c.prune_old_liquidations(keep_hours=24 * 7)   # borra >7 dias del LIVE
    live_after = c._conn().execute("SELECT COUNT(*) FROM liquidations").fetchone()[0]
    research_after = c._conn().execute("SELECT COUNT(*) FROM liquidations_research").fetchone()[0]
    check("PRUNE borra del live cache la fila vieja", live_after == live_before - 1,
          f"live {live_before} -> {live_after}")
    check("PRUNE NO toca liquidations_research", research_after == research_before,
          f"research {research_before} -> {research_after}")
    # y por si acaso: prune con keep_hours=0 (borra TODO el live) sigue sin tocar research
    c.prune_old_liquidations(keep_hours=0)
    r_final = c._conn().execute("SELECT COUNT(*) FROM liquidations_research").fetchone()[0]
    check("PRUNE keep_hours=0 vacia live pero research intacto", r_final == research_before,
          f"research={r_final}")

    # 11. "restart" del research dataset
    n_before = c._conn().execute("SELECT COUNT(*) FROM liquidations_research").fetchone()[0]
    try:
        c._local.conn.close()
    except Exception:
        pass
    c._local.conn = None
    c3 = fresh_cache(db)
    n_after = c3._conn().execute("SELECT COUNT(*) FROM liquidations_research").fetchone()[0]
    check("LIQ research sobrevive reopen (restart)", n_after == n_before and n_after > 0,
          f"{n_before} -> {n_after}")

    # ───────────────────────── resultado ─────────────────────────
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    ntot = len(RESULTS)
    md = ["# INTEGRITY TEST RESULTS", "",
          f"Generado: {datetime.now(timezone.utc).isoformat()}",
          f"DB temporal: `{db}` (descartable)", "",
          f"**{npass}/{ntot} PASS**", "",
          "| test | resultado | detalle |", "|---|---|---|"]
    for name, ok, detail in RESULTS:
        md.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    open(os.path.join(HERE, "INTEGRITY_TEST_RESULTS.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    json.dump([{"test": n, "pass": o, "detail": d} for n, o, d in RESULTS],
              open(os.path.join(HERE, "integrity_test_results.json"), "w"), indent=1)
    print(f"\n{npass}/{ntot} PASS  -> research/tests/INTEGRITY_TEST_RESULTS.md")
    sys.exit(0 if npass == ntot else 1)


if __name__ == "__main__":
    main()
