"""
verify_oi_collector.py — ¿el colector de OI está REALMENTE operativo?
====================================================================
"Docker dice Up" NO alcanza. Este script chequea las 10 cosas que importan.
Correr DESPUÉS de `docker compose up -d oi-collector` (o del proceso host),
esperando al menos 1–2 ciclos (~10 min) para tener señal real.

    python agent/verify_oi_collector.py                 # chequeo completo
    python agent/verify_oi_collector.py --json          # salida JSON
    python agent/verify_oi_collector.py --restart-test  # incluye reinicio del contenedor

Sale con código 0 si TODO pasa, 1 si algún check crítico falla.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
from kline_cache import get_cache  # noqa: E402

import os as _os
import time as _time
PERIOD_MS = 300_000
CONTAINER = "verge-oi-collector"
LOG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "logs", "oi_collector.log")
CRITICAL = {"process_health", "rows_growing", "no_forming_bucket", "no_duplicates", "spacing_ok"}


def _docker(*args):
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:
        return f"__ERR__ {e}"


def _host_proc_alive():
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=20).stdout.lower()
        return "open_interest_collector" in out
    except Exception:
        return None


def check_container(res):
    """El colector corre como PROCESO DEL HOST (no Docker en Windows — SQLite WAL sobre
    bind mount falla). Se chequea: proceso vivo + log fresco + scan de errores."""
    # 1) contenedor (por si alguien lo corre así en Linux)
    out = _docker("inspect", "-f", "{{.State.Status}}|{{.RestartCount}}", CONTAINER)
    container_running = (not out.startswith("__ERR__")) and out.split("|")[0].strip() == "running"
    # 2) proceso host
    host_alive = _host_proc_alive()
    # 3) frescura del log
    log_age = None
    logs = ""
    if _os.path.exists(LOG_PATH):
        log_age = _time.time() - _os.path.getmtime(LOG_PATH)
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            logs = f.read()[-40000:]
    ok = bool(container_running or host_alive) and (log_age is not None and log_age < 1200)
    res["process_health"] = {
        "ok": ok, "host_process_alive": host_alive, "container_running": container_running,
        "log_age_s": round(log_age) if log_age is not None else None,
    }
    low = logs.lower()
    res["log_scan"] = {
        "cycles_seen": low.count("oi ciclo "),
        "backfill_done": "backfill inicial listo" in low,
        "http_errors": low.count("http 4") + low.count("http 5"),
        "rate_limited": low.count("http 429") + low.count("http 418") + low.count(" 429 ") + low.count(" 418 "),
        "breaker_skips": low.count("saltados (breaker"),
        "crashes": low.count("oi loop crash"),
        "last_line": logs.strip().splitlines()[-1] if logs.strip() else "(sin logs)",
    }


def check_data(res, restart_test=False):
    c = get_cache()
    conn = c._conn()
    now_ms = int(time.time() * 1000)

    total = conn.execute("SELECT COUNT(*) FROM open_interest").fetchone()[0]
    syms = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM open_interest")]
    res["dataset"] = {"total_rows": total, "symbols": len(syms)}
    if total == 0:
        res["rows_growing"] = {"ok": False, "detail": "0 filas — el colector todavía no escribió nada (o no arrancó)"}
        for k in ("no_forming_bucket", "no_duplicates", "spacing_ok", "latency", "gaps", "symbol_coverage"):
            res[k] = {"ok": None, "detail": "sin datos aún"}
        return

    # rows growing: dos lecturas separadas por ~20s
    time.sleep(20)
    total2 = conn.execute("SELECT COUNT(*) FROM open_interest").fetchone()[0]
    # también contra updated_at reciente (por si justo cae entre ciclos)
    recent_writes = conn.execute(
        "SELECT COUNT(*) FROM open_interest WHERE updated_at >= ?", (int(time.time()) - 900,)).fetchone()[0]
    res["rows_growing"] = {
        "ok": (total2 > total) or (recent_writes > 0),
        "delta_20s": total2 - total, "written_last_15min": recent_writes,
    }

    # no bucket en formación: ningún timestamp > now - PERIOD_MS
    forming = conn.execute("SELECT COUNT(*) FROM open_interest WHERE timestamp > ?",
                           (now_ms - PERIOD_MS,)).fetchone()[0]
    res["no_forming_bucket"] = {"ok": forming == 0, "rows_in_forming_bucket": forming}

    # duplicados (la PK ya los previene; verificar de todas formas)
    dups = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT exchange,symbol,period,timestamp,COUNT(*) c
            FROM open_interest GROUP BY 1,2,3,4 HAVING c > 1)
    """).fetchone()[0]
    res["no_duplicates"] = {"ok": dups == 0, "duplicate_keys": dups}

    # spacing: sobre el símbolo con más filas, % de gaps consecutivos == 1 período
    top_sym = conn.execute(
        "SELECT symbol,COUNT(*) n FROM open_interest GROUP BY symbol ORDER BY n DESC LIMIT 1").fetchone()
    ts = [r[0] for r in conn.execute(
        "SELECT timestamp FROM open_interest WHERE symbol=? ORDER BY timestamp", (top_sym[0],))]
    diffs = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    exact = sum(1 for d in diffs if d == PERIOD_MS)
    res["spacing_ok"] = {
        "ok": (len(diffs) == 0) or (exact / len(diffs) >= 0.95),
        "symbol": top_sym[0], "rows": top_sym[1],
        "pct_exact_5m": round(100 * exact / len(diffs), 1) if diffs else None,
        "max_gap_min": max(diffs) // 60000 if diffs else None,
    }

    # LATENCIA DE CAPTURA ONGOING: para cada símbolo, el bucket MÁS RECIENTE (el que escribió
    # el último ciclo). updated_at(s) - timestamp/1000 = cuánto tardó en verse ese bucket.
    # (Los del backfill quedan fuera: no son el MAX(timestamp) de su símbolo.)
    lat = sorted(r[0] for r in conn.execute("""
        SELECT o.updated_at - o.timestamp/1000
        FROM open_interest o
        JOIN (SELECT symbol, MAX(timestamp) mt FROM open_interest WHERE period='5m' GROUP BY symbol) m
          ON o.symbol=m.symbol AND o.timestamp=m.mt
        WHERE o.updated_at IS NOT NULL
    """) if r[0] is not None)
    res["latency"] = {
        "ok": (not lat) or (lat[len(lat) // 2] < 900),   # < 15 min mediana del bucket más nuevo por símbolo
        "n_symbols": len(lat),
        "median_s": lat[len(lat) // 2] if lat else None,
        "p90_s": lat[int(len(lat) * 0.9)] if lat else None,
        "note_": "lag de captura del bucket más reciente por símbolo (5m period → esperar 5–10 min es normal)",
    }

    # GAPS: se separan (a) huecos en la ventana RECIENTE (últimos 3d — acá el collector NO debería
    # tener huecos) de (b) símbolos con menos historia en el archivo de 30d de la fuente
    # (listados recientes — no es un bug del collector).
    rec_cut = now_ms - 3 * 86_400_000
    recent_gap_syms, source_limited = [], []
    worst = None
    for s in syms:
        g = c.open_interest_gaps(s, period_ms=PERIOD_MS)
        if g["coverage_pct"] is None:
            continue
        if worst is None or g["coverage_pct"] < worst[1]:
            worst = (s, g["coverage_pct"], g["missing"])
        # Símbolos "líquidos" (cobertura general >=95%): NO deben tener huecos internos → si los
        # tienen, es bug del collector. Símbolos con cobertura <95% = la fuente (Binance
        # openInterestHist) devuelve OI esparso para ese perp fino/nuevo → informativo, no bug.
        if g["coverage_pct"] >= 95:
            rr = [x[0] for x in conn.execute(
                "SELECT timestamp FROM open_interest WHERE exchange='binance' AND symbol=? AND period='5m' AND timestamp>=? ORDER BY timestamp",
                (s, rec_cut))]
            internal_missing = (((rr[-1] - rr[0]) // PERIOD_MS + 1) - len(rr)) if len(rr) >= 2 else 0
            if internal_missing > 3:
                recent_gap_syms.append((s, internal_missing))
        else:
            source_limited.append((s, g["coverage_pct"]))
    res["gaps"] = {
        # el collector está sano si los símbolos líquidos no tienen huecos internos.
        "ok": len(recent_gap_syms) == 0,
        "collector_gaps_on_liquid_symbols": recent_gap_syms[:15],   # esto SÍ sería un bug
        "n_liquid_ok": len(syms) - len(source_limited) - len(recent_gap_syms),
        "source_sparse_symbols": [f"{s}={p}%" for s, p in source_limited[:15]],
        "note_": "source_sparse = Binance devuelve OI esparso para ese perp (fino/nuevo). H11 los filtra con OI_COVERAGE_MIN.",
        "worst_overall": worst,
    }
    res["symbol_coverage"] = {"ok": len(syms) >= 20, "symbols_with_data": len(syms)}

    # idempotencia (proxy del restart-test para proceso host, sin matar nada):
    # re-escribir el mismo lote de un símbolo NO debe cambiar el conteo ni crear duplicados.
    if restart_test:
        before = total2
        import open_interest_collector as oic  # noqa
        import requests as _rq
        sess = _rq.Session()
        sym0 = top_sym[0]
        cnt_before = c.count_open_interest(sym0)
        recs = oic.fetch_recent(sess, sym0, limit=12)
        if recs:
            c.bulk_upsert_open_interest(sym0, recs, exchange="binance", period="5m")
            c.bulk_upsert_open_interest(sym0, recs, exchange="binance", period="5m")  # 2x a propósito
        cnt_after = c.count_open_interest(sym0)
        after = conn.execute("SELECT COUNT(*) FROM open_interest").fetchone()[0]
        dups2 = conn.execute("""SELECT COUNT(*) FROM (SELECT exchange,symbol,period,timestamp,COUNT(*) c
            FROM open_interest GROUP BY 1,2,3,4 HAVING c>1)""").fetchone()[0]
        forming2 = conn.execute("SELECT COUNT(*) FROM open_interest WHERE timestamp > ?",
                                (int(time.time() * 1000) - PERIOD_MS,)).fetchone()[0]
        res["restart_behaviour"] = {
            "ok": (cnt_after - cnt_before) <= 12 and dups2 == 0 and forming2 == 0,
            "symbol_tested": sym0, "sym_rows_before": cnt_before, "sym_rows_after_2x_upsert": cnt_after,
            "total_rows_before": before, "total_rows_after": after,
            "duplicates_after": dups2, "forming_bucket_after": forming2,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--restart-test", action="store_true")
    args = ap.parse_args()

    res = {"checked_at_utc": datetime.now(timezone.utc).isoformat()}
    check_container(res)
    check_data(res, restart_test=args.restart_test)

    if args.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        print(f"\n═══ VERIFICACIÓN OI COLLECTOR · {res['checked_at_utc']} ═══")
        for k, v in res.items():
            if k == "checked_at_utc":
                continue
            if isinstance(v, dict) and "ok" in v:
                mark = "✅" if v["ok"] else ("⚠️ " if v["ok"] is None else "❌")
                crit = " (CRÍTICO)" if k in CRITICAL else ""
                print(f"  {mark} {k}{crit}: " + ", ".join(f"{kk}={vv}" for kk, vv in v.items() if kk != "ok"))
            else:
                print(f"  ·  {k}: {v}")

    crit_fail = [k for k in CRITICAL if isinstance(res.get(k), dict) and res[k].get("ok") is False]
    if crit_fail:
        print(f"\n❌ NO OPERATIVO — checks críticos fallando: {crit_fail}")
        sys.exit(1)
    if any(isinstance(res.get(k), dict) and res[k].get("ok") is None for k in CRITICAL):
        print("\n⚠️  INDETERMINADO — todavía sin datos suficientes. Reintentar en 15–30 min.")
        sys.exit(1)
    print("\n✅ OPERATIVO — el colector está acumulando historia limpia.")
    sys.exit(0)


if __name__ == "__main__":
    main()
