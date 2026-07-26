"""
Completa diciembre 2025 para TODOS los simbolos ya presentes en
klines_clean (que hoy arranca 2026-01-01) -- mismo mecanismo mensual que
download_binance_vision.py, archivo publico data.binance.vision.
"""
import os
import io
import zipfile
import sqlite3
import requests

INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
MONTH = "2025-12"


def download_month(symbol, month):
    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{month}.zip"
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return None
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
        return rows
    except Exception:
        return None


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval=?", (INTERVAL,))
    symbols = sorted(r[0] for r in cur.fetchall())
    print(f">>> Bajando {MONTH} para {len(symbols)} simbolos", flush=True)

    total = 0
    for si, symbol in enumerate(symbols):
        rows = download_month(symbol, MONTH)
        n = len(rows) if rows else 0
        if rows:
            conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
            conn.commit()
        total += n
        if (si + 1) % 20 == 0:
            print(f"[{si+1}/{len(symbols)}] {symbol}: {n} velas (total acumulado={total})", flush=True)
    print(f"\n>>> Listo. Total velas nuevas: {total}")


if __name__ == "__main__":
    main()
