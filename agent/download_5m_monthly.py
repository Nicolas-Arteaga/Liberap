"""
Baja velas de 5m (dic2025-jun2026, meses cerrados) para los 428 simbolos ya
presentes en klines_clean -- necesario para que el motor de backtest evalue
cada 5 min como el agente real (LOOP_INTERVAL_SECONDS=300), no cada 15 min.
Root cause real 2026-07-26: con paso de 15m, el motor generaba ~1.7
señales/dia en TODO el universo vs ~3.6 trades/dia aceptados reales en MA
Slope Caso 3 -- el patron (giro de pendiente muy angosto) se pierde en la
ventana de 15 min si el cruce del umbral dura menos que eso.
Guarda en tabla klines_5m (mismo esquema que klines_clean).
"""
import os
import io
import zipfile
import sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

INTERVAL = "5m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
MAX_WORKERS = 24


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_5m (
            symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        )
    """)
    conn.commit()


def download_month(symbol, month):
    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{month}.zip"
    try:
        resp = requests.get(url, timeout=25)
        if resp.status_code != 200:
            return symbol, month, None
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        name = zf.namelist()[0]
        rows = []
        with zf.open(name) as f:
            first = True
            for line in f:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                if first and line.startswith("open_time"):
                    first = False
                    continue
                first = False
                parts = line.split(",")
                open_time = int(parts[0])
                o, h, l, c, v = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
                rows.append((symbol, INTERVAL, open_time, o, h, l, c, v))
        return symbol, month, rows
    except Exception:
        return symbol, month, None


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m'")
    symbols = sorted(r[0] for r in cur.fetchall())
    print(f">>> {len(symbols)} simbolos x {len(MONTHS)} meses = {len(symbols)*len(MONTHS)} requests, {MAX_WORKERS} workers", flush=True)

    jobs = [(s, m) for s in symbols for m in MONTHS]
    total = 0
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(download_month, s, m) for s, m in jobs]
        for fut in as_completed(futures):
            symbol, month, rows = fut.result()
            done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO klines_5m VALUES (?,?,?,?,?,?,?,?)", rows)
                total += len(rows)
            if done % 200 == 0:
                conn.commit()
                print(f"  progreso: {done}/{len(jobs)} requests, {total} velas", flush=True)
    conn.commit()
    print(f"\n>>> Listo. Total velas 5m (mensual): {total}")


if __name__ == "__main__":
    main()
