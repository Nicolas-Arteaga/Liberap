"""
download_klines_back.py — extiende klines_clean (15m) HACIA ATRÁS para el universo
ex-ante (oi_universe.json). SÓLO data.binance.vision. INSERT OR IGNORE (no pisa nada).
Ventana por env: KB_D0 / KB_D1  (default 2025-06-01 .. 2025-11-30).
"""
import os, io, json, zipfile, sqlite3, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "binance_vision_clean.db")
UNIV = os.path.join(HERE, "..", "research", "universe", "oi_universe.json")
BASE = "https://data.binance.vision/data/futures/um/daily/klines"
INTERVAL = "15m"
D0 = dt.date(*map(int, os.environ.get("KB_D0", "2025-06-01").split("-")))
D1 = dt.date(*map(int, os.environ.get("KB_D1", "2025-11-30").split("-")))
MAX_WORKERS = 48


def days():
    d = D0
    while d <= D1:
        yield d.strftime("%Y-%m-%d"); d += dt.timedelta(days=1)


def fetch(sym, day):
    url = f"{BASE}/{sym}/{INTERVAL}/{sym}-{INTERVAL}-{day}.zip"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return sym, r.status_code, None
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        with zf.open(zf.namelist()[0]) as f:
            for line in f:
                line = line.decode().strip()
                if not line or line.startswith("open_time"):
                    continue
                p = line.split(",")
                rows.append((sym, INTERVAL, int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
        return sym, 200, rows
    except Exception as e:
        return sym, f"ERR {e}", None


def main():
    conn = sqlite3.connect(DB)
    syms = json.load(open(UNIV))["universe"]
    jobs = [(s, d) for s in syms for d in days()]
    print(f">>> klines_back {INTERVAL}: {len(syms)} símbolos × {len(list(days()))} días = {len(jobs)} req  ({D0}..{D1})", flush=True)
    tot = 0; n404 = 0; done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in as_completed([ex.submit(fetch, s, d) for s, d in jobs]):
            sym, st, rows = fut.result(); done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
                tot += len(rows)
            elif st == 404:
                n404 += 1
            if done % 1500 == 0:
                conn.commit(); print(f"  {done}/{len(jobs)} filas={tot} 404={n404}", flush=True)
    conn.commit()
    r = conn.execute("SELECT MIN(open_time),MAX(open_time),COUNT(*) FROM klines_clean WHERE interval='15m'").fetchone()
    def d(x): return dt.datetime.utcfromtimestamp(x/1000).strftime("%Y-%m-%d")
    print(f">>> listo. filas nuevas={tot} 404={n404}. klines_clean 15m ahora: {d(r[0])}..{d(r[1])} ({r[2]} filas)")
    conn.close()


if __name__ == "__main__":
    main()
