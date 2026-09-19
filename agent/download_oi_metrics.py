"""
download_oi_metrics.py — Backfill del histórico de MÉTRICAS de futuros (Open
Interest + long/short ratios + taker ratio) desde data.binance.vision.

  data.binance.vision/data/futures/um/daily/metrics/{S}/{S}-metrics-{YYYY-MM-DD}.zip

CSV (8 cols):
  create_time (UTC 'YYYY-MM-DD HH:MM:SS', grilla :00/:05), symbol,
  sum_open_interest (base), sum_open_interest_value (USD),
  count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
  count_long_short_ratio, sum_taker_long_short_vol_ratio

SÓLO data.binance.vision (CDN público). NUNCA fapi.binance.com / api.binance.com.

Destino: tabla NUEVA `oi_metrics` en binance_vision_clean.db (aditiva; no toca
klines_clean / taker_flow / nada). PK (symbol, open_time). Idempotente
(INSERT OR IGNORE).

Universo: EX-ANTE congelado -> research/universe/oi_universe.json ('universe').
Ventana: 2025-12-01 .. 2026-08-17 (igual que klines_clean).

  python download_oi_metrics.py --backfill
  python download_oi_metrics.py --audit
"""
import os, io, sys, json, zipfile, sqlite3, argparse, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "binance_vision_clean.db")
UNIV = os.path.join(HERE, "..", "research", "universe", "oi_universe.json")
BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
MAX_WORKERS = 48
TIMEOUT = 20
D0 = dt.date(*map(int, os.environ.get("OIM_D0", "2025-12-01").split("-")))
D1 = dt.date(*map(int, os.environ.get("OIM_D1", "2026-08-17").split("-")))


def _ensure(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS oi_metrics (
            symbol            TEXT NOT NULL,
            open_time         INTEGER NOT NULL,      -- ms UTC, = create_time
            sum_oi            REAL,                  -- sum_open_interest (base)
            sum_oi_value      REAL,                  -- sum_open_interest_value (USD)
            toptrader_ls_acct REAL,                  -- count_toptrader_long_short_ratio
            toptrader_ls_pos  REAL,                  -- sum_toptrader_long_short_ratio
            global_ls_acct    REAL,                  -- count_long_short_ratio
            taker_ls_vol      REAL,                  -- sum_taker_long_short_vol_ratio
            PRIMARY KEY (symbol, open_time)
        );
        CREATE INDEX IF NOT EXISTS idx_oimetrics ON oi_metrics (symbol, open_time);
    """)
    conn.commit()


def _days():
    d = D0
    while d <= D1:
        yield d.strftime("%Y-%m-%d")
        d += dt.timedelta(days=1)


def _universe():
    return json.load(open(UNIV))["universe"]


def _parse_ct(s):
    # 'YYYY-MM-DD HH:MM:SS' UTC
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _fetch(sym, day):
    url = f"{BASE}/{sym}/{sym}-metrics-{day}.zip"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return sym, day, r.status_code, None
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        with zf.open(zf.namelist()[0]) as f:
            for i, line in enumerate(f):
                line = line.decode("utf-8").strip()
                if not line or line.startswith("create_time"):
                    continue
                p = line.split(",")
                if len(p) < 8:
                    continue
                def fl(x):
                    try:
                        return float(x)
                    except Exception:
                        return None
                rows.append((p[1], _parse_ct(p[0]), fl(p[2]), fl(p[3]), fl(p[4]), fl(p[5]), fl(p[6]), fl(p[7])))
        return sym, day, 200, rows
    except Exception as e:
        return sym, day, f"ERR {e}", None


def backfill():
    conn = sqlite3.connect(DB)
    _ensure(conn)
    syms = _universe()
    days = list(_days())
    jobs = [(s, d) for s in syms for d in days]
    print(f">>> oi_metrics backfill: {len(syms)} símbolos × {len(days)} días = {len(jobs)} requests", flush=True)
    total = 0; done = 0; s404 = 0; serr = 0
    per_sym = {s: 0 for s in syms}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(_fetch, s, d) for s, d in jobs]
        for fut in as_completed(futs):
            sym, day, st, rows = fut.result()
            done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO oi_metrics VALUES (?,?,?,?,?,?,?,?)", rows)
                total += len(rows); per_sym[sym] += len(rows)
            elif st == 404:
                s404 += 1
            else:
                serr += 1
            if done % 1000 == 0:
                conn.commit()
                print(f"  {done}/{len(jobs)}  filas={total}  404={s404}  err={serr}", flush=True)
    conn.commit()
    print(f"\n>>> listo. filas nuevas={total}  404={s404}  err={serr}")
    zero = [s for s, n in per_sym.items() if n == 0]
    print(f">>> símbolos sin datos: {len(zero)} {zero}")
    conn.close()


def audit():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tot = conn.execute("SELECT COUNT(*) FROM oi_metrics").fetchone()[0]
    nsym = conn.execute("SELECT COUNT(DISTINCT symbol) FROM oi_metrics").fetchone()[0]
    gmin, gmax = conn.execute("SELECT MIN(open_time),MAX(open_time) FROM oi_metrics").fetchone()
    def d(ms): return dt.datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d %H:%M")
    print(f"oi_metrics: {tot} filas · {nsym} símbolos · {d(gmin)} .. {d(gmax)}")
    # grilla 5m
    off = conn.execute("SELECT COUNT(*) FROM oi_metrics WHERE open_time % 300000 <> 0").fetchone()[0]
    print(f"filas fuera de la grilla 5m: {off}")
    # cobertura por símbolo
    print(f"\n{'symbol':14s} {'rows':>8s} {'first':16s} {'last':16s} {'cov%':>6s} {'gaps':>6s}")
    expect_full = None
    rows = conn.execute("SELECT symbol,COUNT(*),MIN(open_time),MAX(open_time) FROM oi_metrics GROUP BY symbol ORDER BY symbol").fetchall()
    for s, n, mn, mx in rows:
        span_bars = (mx - mn) // 300000 + 1
        cov = 100.0 * n / span_bars if span_bars else 0
        gaps = span_bars - n
        print(f"{s:14s} {n:8d} {d(mn):16s} {d(mx):16s} {cov:6.1f} {gaps:6d}")
    # muestra de valores
    print("\nmuestra BTCUSDT (primeras 3, últimas 3):")
    for r in conn.execute("SELECT * FROM oi_metrics WHERE symbol='BTCUSDT' ORDER BY open_time LIMIT 3"):
        print("  ", r)
    for r in conn.execute("SELECT * FROM oi_metrics WHERE symbol='BTCUSDT' ORDER BY open_time DESC LIMIT 3"):
        print("  ", r)
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        backfill()
    if a.audit:
        audit()
    if not (a.backfill or a.audit):
        ap.print_help()
