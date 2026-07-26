"""
Igual que download_binance_vision.py pero con archivos DIARIOS, para los
simbolos chicos exactos que trado FVG-15m Pulido en vivo (22-24 jul 2026)
-- comparacion apples-to-apples real, no las 39 monedas grandes.
"""
import os
import io
import zipfile
import sqlite3
import requests

SYMBOLS = [
    "NIGHTUSDT","SNXXUSDT","STARUSDT","INTWUSDT","ZESTUSDT","HANAUSDT",
    "CBRSUSDT","HAEDALUSDT","ZBTUSDT","YGGUSDT","SQDUSDT","EVAAUSDT",
    "WDCUSDT","REUSDT","ONEUSDT","LISTAUSDT","ERAUSDT","NAORISUSDT",
    "AVAAIUSDT","SMCIUSDT","ONDSUSDT","QNTXUSDT","BLURUSDT","BNCUSDT",
    "BMNRUSDT",
]

DAYS = [f"2026-07-{d:02d}" for d in range(18, 26)]  # 18..25 inclusive

INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")


def download_day(symbol, day):
    url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{day}.zip"
    try:
        resp = requests.get(url, timeout=20)
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
    except Exception as e:
        print(f"  ! {symbol} {day}: {e}")
        return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_clean (
            symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        )
    """)
    total = 0
    for si, symbol in enumerate(SYMBOLS):
        sym_rows = 0
        for day in DAYS:
            rows = download_day(symbol, day)
            if not rows:
                continue
            conn.executemany("INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows)
            sym_rows += len(rows)
        conn.commit()
        total += sym_rows
        print(f"[{si+1}/{len(SYMBOLS)}] {symbol}: {sym_rows} velas (total={total})", flush=True)
    print(f"\n>>> Listo. Total: {total} velas")


if __name__ == "__main__":
    main()
