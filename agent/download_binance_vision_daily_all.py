"""
Completa julio 2026 (dias 1-25) para TODOS los simbolos que ya estan en
klines_clean, via archivos DIARIOS de data.binance.vision (archivo publico,
sin auth, distinto de la API en vivo -- no hay riesgo de ban). Los ZIPs
mensuales solo existen para meses ya cerrados, por eso julio nunca se bajo.
"""
import os
import io
import zipfile
import sqlite3
import requests

INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
DAYS = [f"2026-07-{d:02d}" for d in range(1, 26)]


def download_day(symbol, day):
    url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{day}.zip"
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval=?", (INTERVAL,))
    symbols = sorted(r[0] for r in cur.fetchall())
    print(f">>> Completando julio (1-25) para {len(symbols)} simbolos", flush=True)

    total = 0
    for si, symbol in enumerate(symbols):
        sym_rows = 0
        for day in DAYS:
            rows = download_day(symbol, day)
            if not rows:
                continue
            conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
            sym_rows += len(rows)
        conn.commit()
        total += sym_rows
        if (si + 1) % 20 == 0:
            print(f"[{si+1}/{len(symbols)}] {symbol}: total acumulado={total}", flush=True)
    print(f"\n>>> Listo. Total velas nuevas: {total}")


if __name__ == "__main__":
    main()
