"""
download_funding_hist.py — Backfill del histórico de FUNDING RATE desde
data.binance.vision (monthly). SÓLO CDN público.

  data.binance.vision/data/futures/um/monthly/fundingRate/{S}/{S}-fundingRate-{YYYY-MM}.zip
  CSV: calc_time (ms), funding_interval_hours, last_funding_rate

Destino: tabla NUEVA `funding_hist` en binance_vision_clean.db. PK (symbol, calc_time).
Universo EX-ANTE: research/universe/oi_universe.json.
Ventana: 2025-12 .. 2026-08.
"""
import os, io, json, zipfile, sqlite3, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "binance_vision_clean.db")
UNIV = os.path.join(HERE, "..", "research", "universe", "oi_universe.json")
BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


def main():
    conn = sqlite3.connect(DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS funding_hist (
            symbol TEXT NOT NULL, calc_time INTEGER NOT NULL,
            interval_hours INTEGER, funding_rate REAL,
            PRIMARY KEY (symbol, calc_time));
        CREATE INDEX IF NOT EXISTS idx_fh ON funding_hist (symbol, calc_time);
    """)
    conn.commit()
    syms = json.load(open(UNIV))["universe"]
    jobs = [(s, m) for s in syms for m in MONTHS]

    def fetch(s, m):
        url = f"{BASE}/{s}/{s}-fundingRate-{m}.zip"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                return s, m, r.status_code, None
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            rows = []
            with zf.open(zf.namelist()[0]) as f:
                for line in f:
                    line = line.decode().strip()
                    if not line or line.startswith("calc_time"):
                        continue
                    p = line.split(",")
                    rows.append((s, int(p[0]), int(float(p[1])), float(p[2])))
            return s, m, 200, rows
        except Exception as e:
            return s, m, f"ERR {e}", None

    total = 0; n404 = 0
    with ThreadPoolExecutor(max_workers=32) as ex:
        for fut in as_completed([ex.submit(fetch, s, m) for s, m in jobs]):
            s, m, st, rows = fut.result()
            if rows:
                conn.executemany("INSERT OR IGNORE INTO funding_hist VALUES (?,?,?,?)", rows)
                total += len(rows)
            elif st == 404:
                n404 += 1
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM funding_hist").fetchone()[0]
    ns = conn.execute("SELECT COUNT(DISTINCT symbol) FROM funding_hist").fetchone()[0]
    mn, mx = conn.execute("SELECT MIN(calc_time),MAX(calc_time) FROM funding_hist").fetchone()
    def d(x): return dt.datetime.utcfromtimestamp(x/1000).strftime("%Y-%m-%d")
    print(f"funding_hist: {n} filas, {ns} símbolos, {d(mn)}..{d(mx)}  (nuevas={total}, 404={n404})")


if __name__ == "__main__":
    main()
