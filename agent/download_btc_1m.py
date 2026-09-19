"""
download_btc_1m.py — 1m de BTCUSDT (perp, UM futures) desde data.binance.vision.
SOLO el CDN publico, NUNCA fapi.binance.com (IP compartida con el agente live).

Motivo: el GATE de confiabilidad del backtest (2026-09-05) encontro que
`BTCMacroFilter.get_regime()` necesita velas de 1m de BTC para el pct_5m
(el path rapido del veto DUMPING). El resto de ventanas (pct_15m, pct_1h,
is_btc_bleeding, flash_crash) sale de 5m/15m que ya estan en el dataset.
Este backfill cierra el GAP 1 con la opcion B (incorporar el dato faltante).

Tabla NUEVA `btc_klines_1m` en binance_vision_clean.db (aditiva, no toca nada).

  python download_btc_1m.py            # backfill 2026-06-01 -> 2026-08-17
  python download_btc_1m.py --audit    # cobertura / spacing
"""
import os, io, sys, zipfile, sqlite3, argparse, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DB = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
BASE = "https://data.binance.vision/data/futures/um"
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
MONTHS = ["2026-06", "2026-07"]
AUG_DAYS = [f"2026-08-{d:02d}" for d in range(1, 18)]
TIMEOUT = 25


def _ensure(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS btc_klines_1m (
            symbol    TEXT NOT NULL,
            open_time INTEGER NOT NULL,
            open      REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, open_time)
        );
    """)
    conn.commit()


def _rows_from_zip(content):
    zf = zipfile.ZipFile(io.BytesIO(content))
    out = []
    for line in zf.open(zf.namelist()[0]):
        t = line.decode("utf-8").strip()
        if not t or t.startswith("open_time"):
            continue
        p = t.split(",")
        ot = int(p[0])
        if ot > 1_000_000_000_000_000:   # us -> ms (algunos archivos spot)
            ot //= 1000
        out.append((SYMBOL, ot, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    return out


def _fetch(kind, tag):
    url = f"{BASE}/{kind}/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{tag}.zip"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return tag, None
        return tag, _rows_from_zip(r.content)
    except Exception as e:
        return tag, f"ERR {e}"


def backfill():
    conn = sqlite3.connect(DB)
    _ensure(conn)
    jobs = [("monthly", m) for m in MONTHS] + [("daily", d) for d in AUG_DAYS]
    total = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_fetch, k, t) for k, t in jobs]
        for f in as_completed(futs):
            tag, rows = f.result()
            if isinstance(rows, str) or rows is None:
                print(f"  {tag}: {rows}", flush=True)
                continue
            conn.executemany("INSERT OR IGNORE INTO btc_klines_1m VALUES (?,?,?,?,?,?,?)", rows)
            total += len(rows)
            print(f"  {tag}: {len(rows):,} filas", flush=True)
    conn.commit()
    print(f"[btc-1m] listo. {total:,} filas insertadas.", flush=True)
    audit(conn)
    conn.close()


def audit(conn=None):
    own = conn is None
    if own:
        conn = sqlite3.connect(DB)
    n, mn, mx = conn.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM btc_klines_1m").fetchone()
    if not n:
        print("[btc-1m] VACIA"); return
    f = lambda x: dt.datetime.utcfromtimestamp(x / 1000)
    print(f"[btc-1m] {n:,} filas | {f(mn)} -> {f(mx)}")
    ts = [r[0] for r in conn.execute("SELECT open_time FROM btc_klines_1m ORDER BY open_time")]
    diffs = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    exact = sum(1 for d in diffs if d == 60000)
    gaps = [(f(ts[i]), (ts[i + 1] - ts[i]) // 60000) for i in range(len(ts) - 1) if ts[i + 1] - ts[i] > 60000]
    print(f"[btc-1m] spacing exacto 1m: {100*exact/len(diffs):.3f}%  | gaps>1m: {len(gaps)}")
    for when, mins in gaps[:10]:
        print(f"   gap {mins} min desde {when}")
    if own:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    audit() if a.audit else backfill()
