"""
Descarga klines historicos REALES y SIN HUECOS desde data.binance.vision
(archivo estatico S3 de Binance para backtesting masivo -- infraestructura
completamente separada de la API de trading en vivo, sin riesgo de ban:
ver PROGRESS_LOG sobre el ban real de 2026-07-12 por pegarle a la API
normal desde este mismo entorno).

Guarda todo en agent/data/binance_vision_clean.db (tabla klines_clean),
mismo esquema que kline_cache.py para poder reusar el resto del pipeline.
"""
import os
import io
import zipfile
import sqlite3
import requests

SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT",
    "AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
    "ARBUSDT","OPUSDT","SUIUSDT","INJUSDT","TIAUSDT","SEIUSDT","FILUSDT",
    "ETCUSDT","TRXUSDT","BCHUSDT","UNIUSDT","AAVEUSDT","MKRUSDT","RUNEUSDT",
    "FTMUSDT","GALAUSDT","SANDUSDT","MANAUSDT","AXSUSDT","CHZUSDT","ENJUSDT",
    "XLMUSDT","ALGOUSDT","VETUSDT","EOSUSDT","WLDUSDT",
]

MONTHS = ["2026-07","2026-06","2026-05","2026-04","2026-03","2026-02","2026-01"]

INTERVAL = "15m"
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_clean (
            symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        )
    """)
    conn.commit()
    return conn


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
    except Exception as e:
        print(f"  ! {symbol} {month}: {e}")
        return None


def main():
    conn = init_db()
    total_rows = 0
    for si, symbol in enumerate(SYMBOLS):
        sym_rows = 0
        for month in MONTHS:
            rows = download_month(symbol, month)
            if not rows:
                continue
            conn.executemany(
                "INSERT OR IGNORE INTO klines_clean VALUES (?,?,?,?,?,?,?,?)", rows
            )
            sym_rows += len(rows)
        conn.commit()
        total_rows += sym_rows
        print(f"[{si+1}/{len(SYMBOLS)}] {symbol}: {sym_rows} velas (total acumulado={total_rows})", flush=True)
    print(f"\n>>> Listo. Total: {total_rows} velas en {DB_PATH}")


if __name__ == "__main__":
    main()
