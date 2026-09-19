"""
PHASE 2 §E — backfill de los símbolos UNREPLAYABLE del gate (trades reales sin
histórico en binance_vision_clean.db). SOLO data.binance.vision, nunca fapi.

21 de 22 están disponibles como UM futures (ETHBTCUSDT no: par BTC-denominado).
Baja 5m y 15m, meses 2026-06/07 + días 2026-08-01..17, a klines_5m / klines_clean
(mismo esquema y rango que el resto del dataset).

  python download_missing_symbols.py
  python download_missing_symbols.py --audit
"""
import os, io, sys, zipfile, sqlite3, argparse, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DB = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
BASE = "https://data.binance.vision/data/futures/um"
MONTHS = ["2026-06", "2026-07"]
AUG_DAYS = [f"2026-08-{d:02d}" for d in range(1, 18)]
SYMS = ["4USDT", "ATUSDT", "AVGOUSDT", "C98USDT", "COAIUSDT", "COTIUSDT", "DUSKUSDT",
        "EWTUSDT", "ICNTUSDT", "ILVUSDT", "MAVUSDT", "MINIMAXUSDT", "PENGUSDT", "REDUSDT",
        "RPLUSDT", "RVNUSDT", "SAFEUSDT", "SAPIENUSDT", "SKHYUSDT", "TZAUSDT", "UVXYUSDT"]
UNAVAILABLE = ["ETHBTCUSDT"]  # 404 — par BTC-denominado, no UM futures


def _rows(content, symbol, interval):
    zf = zipfile.ZipFile(io.BytesIO(content))
    out = []
    for line in zf.open(zf.namelist()[0]):
        t = line.decode("utf-8").strip()
        if not t or t.startswith("open_time"):
            continue
        p = t.split(",")
        ot = int(p[0])
        if ot > 1_000_000_000_000_000:
            ot //= 1000
        out.append((symbol, interval, ot, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    return out


def _fetch(symbol, interval, kind, tag):
    url = f"{BASE}/{kind}/klines/{symbol}/{interval}/{symbol}-{interval}-{tag}.zip"
    try:
        r = requests.get(url, timeout=25)
        if r.status_code != 200:
            return symbol, interval, None
        return symbol, interval, _rows(r.content, symbol, interval)
    except Exception:
        return symbol, interval, None


def backfill():
    conn = sqlite3.connect(DB)
    jobs = []
    for s in SYMS:
        for iv, table in (("5m", "klines_5m"), ("15m", "klines_clean")):
            for m in MONTHS:
                jobs.append((s, iv, "monthly", m))
            for d in AUG_DAYS:
                jobs.append((s, iv, "daily", d))
    print(f"[missing] {len(SYMS)} símbolos x 2 intervalos = {len(jobs)} requests", flush=True)
    ins = {"klines_5m": 0, "klines_clean": 0}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(_fetch, s, iv, k, t) for (s, iv, k, t) in jobs]
        for f in as_completed(futs):
            s, iv, rows = f.result()
            if not rows:
                continue
            table = "klines_5m" if iv == "5m" else "klines_clean"
            conn.executemany(
                f"INSERT OR IGNORE INTO {table} (symbol, interval, open_time, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)", rows)
            ins[table] += len(rows)
    conn.commit()
    print(f"[missing] insertadas: {ins}", flush=True)
    conn.close()
    audit()


def audit():
    conn = sqlite3.connect(DB)
    a = int(dt.datetime(2026, 7, 1).timestamp() * 1000)
    b = int(dt.datetime(2026, 8, 17).timestamp() * 1000)
    print(f"{'SYMBOL':13}{'5m rows':>10}{'15m rows':>10}   5m range")
    for s in SYMS + UNAVAILABLE:
        n5, mn5, mx5 = conn.execute(
            "SELECT COUNT(*),MIN(open_time),MAX(open_time) FROM klines_5m WHERE symbol=? AND interval='5m'", (s,)).fetchone()
        n15 = conn.execute("SELECT COUNT(*) FROM klines_clean WHERE symbol=? AND interval='15m'", (s,)).fetchone()[0]
        rng = ""
        if mn5:
            f = lambda x: dt.datetime.utcfromtimestamp(x / 1000).date().isoformat()
            rng = f"{f(mn5)} -> {f(mx5)}"
        tag = "  (NO DISPONIBLE)" if s in UNAVAILABLE else ""
        print(f"{s:13}{n5:>10}{n15:>10}   {rng}{tag}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    audit() if a.audit else backfill()
