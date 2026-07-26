"""
Descarga klines limpios de data.binance.vision para el WATCHLIST REAL de
Verge (config.WATCHLIST, ~429 simbolos chicos/volatiles) -- no una lista
elegida a mano. Muchos de estos simbolos son nuevos/chicos y no van a
tener archivo (404 silencioso, esperado).
"""
import os
import io
import zipfile
import sqlite3
import requests
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config

MONTHS = ["2026-07", "2026-06", "2026-05"]
INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")


def download_month(symbol, month):
    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{month}.zip"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
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
        return rows
    except Exception:
        return None


def main():
    symbols = config.WATCHLIST
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_clean (
            symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        )
    """)
    total = 0
    found_symbols = 0
    for si, symbol in enumerate(symbols):
        sym_rows = 0
        for month in MONTHS:
            rows = download_month(symbol, month)
            if not rows:
                continue
            conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
            sym_rows += len(rows)
        conn.commit()
        total += sym_rows
        if sym_rows > 0:
            found_symbols += 1
        if (si + 1) % 30 == 0:
            print(f"[{si+1}/{len(symbols)}] procesados | {found_symbols} con datos | {total} velas totales", flush=True)
    print(f"\n>>> Listo. {found_symbols}/{len(symbols)} simbolos con datos. Total: {total} velas")


if __name__ == "__main__":
    main()
