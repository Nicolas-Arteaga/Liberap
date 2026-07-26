"""
v2: igual que download_binance_vision_daily_all.py pero con descargas HTTP
en paralelo (ThreadPoolExecutor) -- la version secuencial tardaba horas
(428 simbolos x 25 dias = 10700 requests). La escritura a SQLite queda
SIEMPRE en el hilo principal (un solo writer, sin locks concurrentes).
Nombre de archivo nuevo a proposito -- no pisa nada anterior.
"""
import os
import io
import zipfile
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
DAYS = [f"2026-07-{d:02d}" for d in range(1, 26)]
MAX_WORKERS = 64


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
    cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval=?", (INTERVAL,))
    symbols = sorted(r[0] for r in cur.fetchall())
    print(f">>> Completando julio (1-25) para {len(symbols)} simbolos, {MAX_WORKERS} workers HTTP en paralelo", flush=True)

    jobs = [(s, d) for s in symbols for d in DAYS]
    total_rows = 0
    done = 0
    per_symbol = {s: 0 for s in symbols}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(download_day, s, d) for s, d in jobs]
        for fut in as_completed(futures):
            symbol, day, rows = fut.result()
            done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
                total_rows += len(rows)
                per_symbol[symbol] += len(rows)
            if done % 500 == 0:
                conn.commit()
                print(f"  progreso: {done}/{len(jobs)} requests, {total_rows} velas insertadas", flush=True)

    conn.commit()
    print(f"\n>>> Listo. Total velas nuevas: {total_rows}")
    sin_datos = [s for s, n in per_symbol.items() if n == 0]
    print(f">>> Simbolos sin NINGUN dato de julio nuevo: {len(sin_datos)}")
    if sin_datos:
        print("   ", sin_datos[:30])


if __name__ == "__main__":
    main()
