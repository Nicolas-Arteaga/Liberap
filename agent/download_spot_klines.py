"""
download_spot_klines.py — Backfill de klines SPOT de Binance para el test de BASIS (H10).

Mecanismo: SÓLO data.binance.vision (CDN de archivos públicos, mismo método que ya usa
Verge para el backfill de futures — NO es el vector de ban de fapi.binance.com).
NO usa endpoints REST de Binance.

  data.binance.vision/data/spot/monthly/klines/{S}/{iv}/{S}-{iv}-{YYYY-MM}.zip   (backfill)
  data.binance.vision/data/spot/daily/klines/{S}/{iv}/{S}-{iv}-{YYYY-MM-DD}.zip  (mes en curso)

Destino: tabla NUEVA `spot_klines` en binance_vision_clean.db (aditiva, no toca
`klines_clean` ni nada existente). Misma forma que klines_clean.

Modos:
  python download_spot_klines.py --probe          # sólo determina overlap/cobertura, no baja nada
  python download_spot_klines.py --backfill       # baja el rango completo para los símbolos con overlap
  python download_spot_klines.py --audit          # reporta cobertura/gaps/alineación de lo ya bajado
"""
import os, io, sys, csv, zipfile, sqlite3, argparse, calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
BASE = "https://data.binance.vision/data/spot"
INTERVALS = ["15m"]                       # 15m matchea klines_clean (el panel de 8,5m). 5m = agregar aquí si hace falta resolución.
MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
          "2026-05", "2026-06", "2026-07"]  # 2026-08 se baja por 'daily' (mes parcial en la fuente)
AUG_DAYS = [f"2026-08-{d:02d}" for d in range(1, 18)]   # futures va hasta 2026-08-17
MAX_WORKERS = 48
TIMEOUT = 20


def _ensure_table(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS spot_klines (
            symbol    TEXT NOT NULL,
            interval  TEXT NOT NULL,
            open_time INTEGER NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        );
        CREATE INDEX IF NOT EXISTS idx_spot_lookup ON spot_klines (symbol, interval, open_time);
    """)
    conn.commit()


def _futures_symbols(conn):
    return sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m'"))


def _url(kind, sym, iv, tag):
    return f"{BASE}/{kind}/klines/{sym}/{iv}/{sym}-{iv}-{tag}.zip"


def _fetch_zip(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.content
    except Exception:
        return None


def _parse_zip(content, sym, iv):
    rows = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
        with zf.open(zf.namelist()[0]) as f:
            for line in f:
                s = line.decode("utf-8").strip()
                if not s or s.startswith("open_time"):
                    continue
                p = s.split(",")
                ot = int(p[0])
                if ot > 1_000_000_000_000_000:   # Binance cambió los archivos SPOT a microsegundos (~2025).
                    ot //= 1000                    # normalizar a ms para alinear con klines_clean (perp = ms).
                rows.append((sym, iv, ot, float(p[1]), float(p[2]),
                             float(p[3]), float(p[4]), float(p[5])))
    except Exception:
        return []
    return rows


# ─────────────── PROBE: ¿qué símbolos spot existen? ───────────────
def probe():
    conn = sqlite3.connect(DB_PATH)
    fut = _futures_symbols(conn)
    print(f"[probe] {len(fut)} símbolos futures. Chequeando existencia de spot (monthly 2026-06, 15m)...", flush=True)

    def check(sym):
        # HEAD-like: pedir el .CHECKSUM es más liviano que el .zip
        for probe_month in ("2026-06", "2026-03"):
            u = _url("monthly", sym, "15m", probe_month) + ".CHECKSUM"
            try:
                r = requests.get(u, timeout=TIMEOUT)
                if r.status_code == 200:
                    return sym, True
            except Exception:
                pass
        return sym, False

    have, missing = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed([ex.submit(check, s) for s in fut]):
            sym, ok = f.result()
            (have if ok else missing).append(sym)
    have.sort(); missing.sort()
    print(f"\n[probe] spot con overlap exacto de nombre: {len(have)} / {len(fut)}")
    print(f"[probe] sin spot (futures-only o nombre distinto p.ej 1000X): {len(missing)}")
    print("  primeros sin-spot:", missing[:40])
    # rango de listing spot para una muestra
    print("\n[probe] rango de historia spot para 8 símbolos de muestra (monthly disponibles):")
    for sym in have[:8]:
        avail = []
        for m in ["2025-11", "2025-12", "2026-01", "2026-06", "2026-07"]:
            if requests.get(_url("monthly", sym, "15m", m) + ".CHECKSUM", timeout=TIMEOUT).status_code == 200:
                avail.append(m)
        print(f"    {sym:14s} meses monthly OK: {avail}")
    out = os.path.join(os.path.dirname(__file__), "data", "spot_overlap_symbols.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["symbol", "has_spot"])
        for s in have: w.writerow([s, 1])
        for s in missing: w.writerow([s, 0])
    print(f"\n[probe] lista escrita -> {out}")
    conn.close()
    return have


# ─────────────── BACKFILL ───────────────
def backfill():
    conn = sqlite3.connect(DB_PATH)
    _ensure_table(conn)
    csv_path = os.path.join(os.path.dirname(__file__), "data", "spot_overlap_symbols.csv")
    if not os.path.exists(csv_path):
        print("Corré --probe primero."); return
    syms = [r["symbol"] for r in csv.DictReader(open(csv_path)) if r["has_spot"] == "1"]
    print(f"[backfill] {len(syms)} símbolos × {len(INTERVALS)} intervals × ({len(MONTHS)} meses + {len(AUG_DAYS)} días)", flush=True)

    jobs = []
    for sym in syms:
        for iv in INTERVALS:
            for m in MONTHS:
                jobs.append(("monthly", sym, iv, m))
            for d in AUG_DAYS:
                jobs.append(("daily", sym, iv, d))
    print(f"[backfill] {len(jobs)} requests, {MAX_WORKERS} workers", flush=True)

    total = done = miss = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(lambda k, s, i, t: (s, i, _fetch_zip(_url(k, s, i, t))), k, s, i, t): (k, s, i, t)
                for (k, s, i, t) in jobs}
        for f in as_completed(futs):
            sym, iv, content = f.result()
            done += 1
            if content:
                rows = _parse_zip(content, sym, iv)
                if rows:
                    conn.executemany(
                        "INSERT OR IGNORE INTO spot_klines VALUES (?,?,?,?,?,?,?,?)", rows)
                    total += len(rows)
            else:
                miss += 1
            if done % 400 == 0:
                conn.commit()
                print(f"  {done}/{len(jobs)} · {total} velas · {miss} 404s", flush=True)
    conn.commit()
    print(f"\n[backfill] listo. {total} velas spot insertadas, {miss} archivos ausentes.")
    conn.close()


# ─────────────── AUDIT ───────────────
def audit():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for iv, exp_ms in (("15m", 900_000), ("5m", 300_000)):
        r = cur.execute("SELECT COUNT(*) n, COUNT(DISTINCT symbol) s, MIN(open_time) a, MAX(open_time) b "
                        "FROM spot_klines WHERE interval=?", (iv,)).fetchone()
        if not r["n"]:
            print(f"[audit] {iv}: sin datos"); continue
        import datetime as dt
        print(f"[audit] {iv}: {r['n']:,} velas · {r['s']} símbolos · "
              f"{dt.datetime.utcfromtimestamp(r['a']/1000).date()} -> {dt.datetime.utcfromtimestamp(r['b']/1000).date()}")
        # overlap real spot∩perp + alineación de precio en una muestra
        perp_tbl = "klines_clean" if iv == "15m" else "klines_5m"
        sample = [x[0] for x in cur.execute(
            "SELECT DISTINCT symbol FROM spot_klines WHERE interval=? ORDER BY symbol LIMIT 6", (iv,))]
        for sym in sample:
            sp = dict(cur.execute("SELECT open_time,close FROM spot_klines WHERE symbol=? AND interval=?",
                                  (sym, iv)).fetchall())
            pp = dict(cur.execute(f"SELECT open_time,close FROM {perp_tbl} WHERE symbol=? AND interval=?",
                                  (sym, iv)).fetchall())
            common = sorted(set(sp) & set(pp))
            if not common:
                print(f"    {sym}: sin barras comunes"); continue
            import statistics
            basis = [ (pp[t]-sp[t])/sp[t]*1e4 for t in common ]  # bp: perp - spot
            print(f"    {sym:12s} común={len(common)} basis(perp-spot) mediana={statistics.median(basis):+.1f}bp "
                  f"p5={sorted(basis)[len(basis)//20]:+.1f} p95={sorted(basis)[len(basis)*19//20]:+.1f}bp")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    if a.probe: probe()
    elif a.backfill: backfill()
    elif a.audit: audit()
    else: ap.print_help()
