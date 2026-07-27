"""
Sincronizacion on-demand de datos historicos (klines_5m / klines_clean) --
generaliza los scripts sueltos de hoy (download_5m_julio.py,
download_binance_vision_daily_all_v2.py) en dos funciones reusables:

  check_coverage(symbols, start_ms, end_ms) -> que falta
  sync_coverage(symbols, start_ms, end_ms, progress_cb) -> descarga SOLO eso

Usa siempre archivos DIARIOS de data.binance.vision (funciona para
cualquier dia pasado, cerrado o no, a diferencia de los mensuales que solo
existen para meses ya completos) -- mas simple de razonar que mezclar
mensual/diario, el volumen extra de requests no importa (paralelo, ya
probado hoy a 48-64 workers).
"""
import os
import io
import zipfile
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
MAX_WORKERS = 48

# (tabla, intervalo) que se sincronizan
TARGETS = [
    ("klines_5m", "5m"),
    ("klines_clean", "15m"),
]


def _day_range(start_ms: int, end_ms: int) -> list:
    start = datetime.utcfromtimestamp(start_ms / 1000).date()
    end = datetime.utcfromtimestamp(end_ms / 1000).date()
    days = []
    d = start
    while d <= end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def check_coverage(symbols: list, start_ms: int, end_ms: int, db_path: str = DB_PATH) -> dict:
    """
    Devuelve {table: {symbol: [dias_faltantes]}} -- un dia se considera
    presente si hay AL MENOS una vela con open_time dentro de ese dia UTC
    para ese simbolo/intervalo (chequeo barato, no exhaustivo vela a vela).
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    days = _day_range(start_ms, end_ms)
    missing = {}

    for table, interval in TARGETS:
        missing[table] = {}
        for symbol in symbols:
            cur.execute(
                f"SELECT DISTINCT DATE(open_time/1000, 'unixepoch') FROM {table} "
                "WHERE symbol=? AND interval=? AND open_time BETWEEN ? AND ?",
                (symbol, interval, start_ms, end_ms),
            )
            present_days = set(r[0] for r in cur.fetchall())
            gaps = [d for d in days if d not in present_days]
            if gaps:
                missing[table][symbol] = gaps
    conn.close()
    return missing


def _download_day(symbol: str, interval: str, day: str) -> Optional[list]:
    url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
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
                rows.append((symbol, interval, open_time, o, h, l, c, v))
        return rows
    except Exception:
        return None


def sync_coverage(
    symbols: list,
    start_ms: int,
    end_ms: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    db_path: str = DB_PATH,
) -> dict:
    """
    Descarga SOLO los huecos detectados por check_coverage. Devuelve un
    resumen {table: {velas_nuevas, simbolos_completados, simbolos_sin_datos}}.
    """
    gaps = check_coverage(symbols, start_ms, end_ms, db_path=db_path)

    jobs = []
    for table, interval in TARGETS:
        for symbol, days in gaps.get(table, {}).items():
            for day in days:
                jobs.append((table, interval, symbol, day))

    conn = sqlite3.connect(db_path)
    total_new_rows = {t: 0 for t, _ in TARGETS}
    no_data_symbols = {t: set() for t, _ in TARGETS}

    done = 0
    total = len(jobs)
    if progress_cb:
        progress_cb(0, total)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_download_day, symbol, interval, day): (table, interval, symbol, day)
                   for table, interval, symbol, day in jobs}
        for fut in as_completed(futures):
            table, interval, symbol, day = futures[fut]
            rows = fut.result()
            done += 1
            if rows:
                conn.executemany(f"INSERT OR IGNORE INTO {table} VALUES (?,?,?,?,?,?,?,?)", rows)
                total_new_rows[table] += len(rows)
            else:
                no_data_symbols[table].add(symbol)
            if done % 200 == 0:
                conn.commit()
            if progress_cb:
                progress_cb(done, total)

    conn.commit()
    conn.close()

    return {
        "jobs_total": total,
        "by_table": {
            table: {
                "new_rows": total_new_rows[table],
                "symbols_without_data": sorted(no_data_symbols[table]),
            }
            for table, _ in TARGETS
        },
    }
