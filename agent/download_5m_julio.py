"""
Completa julio 2026 (dias 1-25) en 5m para los simbolos ya en klines_5m --
mismo mecanismo que download_binance_vision_daily_all_v2.py pero INTERVAL=5m.
"""
import os
import io
import zipfile
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

INTERVAL = "5m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
DAYS = [f"2026-07-{d:02d}" for d in range(1, 26)]
MAX_WORKERS = 48


def download_day(symbol, day):
    url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{day}.zip"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return symbol, day, None
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        name = zf.namelist()[0]
        rows = []
        with zf.open(name) as f:
            for line in f:
                line = line.decode("utf-8").strip()
                if not line or line.startswith("open_time"):
                    continue
                parts = line.split(",")
                open_time = int(parts[0])
                o, h, l, c, v = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
                rows.append((symbol, INTERVAL, open_time, o, h, l, c, v))
        return symbol, day, rows
    except Exception:
        return symbol, day, None


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_5m WHERE interval='5m'")
    symbols = sorted(r[0] for r in cur.fetchall())
    print(f">>> julio (1-25) para {len(symbols)} simbolos, {MAX_WORKERS} workers", flush=True)

    jobs = [(s, d) for s in symbols for d in DAYS]
    total_rows = 0
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(download_day, s, d) for s, d in jobs]
        for fut in as_completed(futures):
            symbol, day, rows = fut.result()
            done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO klines_5m VALUES (?,?,?,?,?,?,?,?)", rows)
                total_rows += len(rows)
            if done % 500 == 0:
                conn.commit()
                print(f"  progreso: {done}/{len(jobs)} requests, {total_rows} velas", flush=True)
    conn.commit()
    print(f"\n>>> Listo. Total velas julio 5m: {total_rows}")


if __name__ == "__main__":
    main()
