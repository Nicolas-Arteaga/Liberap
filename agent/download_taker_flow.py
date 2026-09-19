"""
download_taker_flow.py — Backfill de columnas taker/flow de los klines de futures
(H12, ver agent/H12_TAKER_FLOW_TEST.md). SÓLO data.binance.vision (CDN público),
NUNCA fapi.binance.com.

  data.binance.vision/data/futures/um/monthly/klines/{S}/15m/{S}-15m-{YYYY-MM}.zip
  data.binance.vision/data/futures/um/daily/klines/{S}/15m/{S}-15m-{YYYY-MM-DD}.zip

Columnas del CSV (12): open_time,open,high,low,close,volume,close_time,quote_volume,
count,taker_buy_volume,taker_buy_quote_volume,ignore   (open_time en MS)

Destino: tabla NUEVA `taker_flow` en binance_vision_clean.db (aditiva, no toca
`klines_clean`). Se guarda volume también, para re-verificar contra klines_clean.

Modos:
  python download_taker_flow.py --backfill   # baja 429 símbolos × 260 días
  python download_taker_flow.py --audit      # cobertura / integridad / universo final
"""
import os, io, sys, zipfile, sqlite3, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DB = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
BASE = "https://data.binance.vision/data/futures/um"
INTERVAL = "15m"
MONTHS = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
AUG_DAYS = [f"2026-08-{d:02d}" for d in range(1, 18)]   # klines_clean llega hasta 2026-08-17
MAX_WORKERS = 48
TIMEOUT = 20


def _ensure(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS taker_flow (
            symbol           TEXT NOT NULL,
            interval         TEXT NOT NULL,
            open_time        INTEGER NOT NULL,
            volume           REAL,
            quote_volume     REAL,
            trade_count      INTEGER,
            taker_buy_volume REAL,
            taker_buy_quote  REAL,
            PRIMARY KEY (symbol, interval, open_time)
        );
        CREATE INDEX IF NOT EXISTS idx_taker_lookup ON taker_flow (symbol, interval, open_time);
    """)
    conn.commit()


def _symbols(conn):
    return sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m'"))


def _url(kind, s, tag):
    return f"{BASE}/{kind}/klines/{s}/{INTERVAL}/{s}-{INTERVAL}-{tag}.zip"


def _fetch(kind, s, tag):
    try:
        r = requests.get(_url(kind, s, tag), timeout=TIMEOUT)
        if r.status_code != 200:
            return s, None
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        for line in zf.open(zf.namelist()[0]):
            t = line.decode("utf-8").strip()
            if not t or t.startswith("open_time"):
                continue
            p = t.split(",")
            ot = int(p[0])
            if ot > 1_000_000_000_000_000:   # por si algún archivo viene en µs (spot lo hace)
                ot //= 1000
            rows.append((s, INTERVAL, ot, float(p[5]), float(p[7]), int(p[8]),
                         float(p[9]), float(p[10])))
        return s, rows
    except Exception:
        return s, None


def backfill():
    conn = sqlite3.connect(DB)
    _ensure(conn)
    syms = _symbols(conn)
    jobs = [("monthly", s, m) for s in syms for m in MONTHS] + \
           [("daily", s, d) for s in syms for d in AUG_DAYS]
    print(f"[taker] {len(syms)} símbolos × ({len(MONTHS)} meses + {len(AUG_DAYS)} días) = {len(jobs)} requests, {MAX_WORKERS} workers", flush=True)
    total = done = miss = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(_fetch, k, s, t) for (k, s, t) in jobs]
        for f in as_completed(futs):
            s, rows = f.result()
            done += 1
            if rows:
                conn.executemany("INSERT OR IGNORE INTO taker_flow VALUES (?,?,?,?,?,?,?,?)", rows)
                total += len(rows)
            else:
                miss += 1
            if done % 500 == 0:
                conn.commit()
                print(f"  {done}/{len(jobs)} · {total:,} barras · {miss} archivos ausentes", flush=True)
    conn.commit()
    print(f"\n[taker] listo. {total:,} barras insertadas, {miss} archivos ausentes.", flush=True)
    conn.close()


def audit():
    import datetime as dt
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    t0 = int(dt.datetime(2025, 12, 1).timestamp() * 1000)
    t1 = int(dt.datetime(2026, 8, 17).timestamp() * 1000)
    exp = (t1 - t0) // 900000

    tk = {r[0]: r[1] for r in cur.execute(
        "SELECT symbol,COUNT(*) FROM taker_flow WHERE interval='15m' AND open_time>=? AND open_time<? GROUP BY symbol", (t0, t1))}
    kc = {r[0]: r[1] for r in cur.execute(
        "SELECT symbol,COUNT(*) FROM klines_clean WHERE interval='15m' AND open_time>=? AND open_time<? GROUP BY symbol", (t0, t1))}
    all_syms = sorted(kc)
    LIQ = 1_000_000

    downloaded, discarded, universe = [], [], []
    total_bars = valid_bars = 0
    mismatches = 0
    for s in all_syms:
        n_tk = tk.get(s, 0)
        n_kc = kc.get(s, 0)
        cov = n_tk / exp if exp else 0
        if n_tk == 0:
            discarded.append((s, "sin taker_flow", round(cov, 3)))
            continue
        downloaded.append((s, round(cov, 3), n_tk, n_kc))
        # integridad: en la intersección de open_time, ¿volume coincide y taker<=volume?
        rows = cur.execute("""
            SELECT tf.taker_buy_volume, tf.volume, kc.volume
            FROM taker_flow tf JOIN klines_clean kc
              ON kc.symbol=tf.symbol AND kc.interval=tf.interval AND kc.open_time=tf.open_time
            WHERE tf.symbol=? AND tf.interval='15m'""", (s,)).fetchall()
        for tbb, tvol, kvol in rows:
            total_bars += 1
            ok_v = (kvol == 0 and tvol == 0) or abs(tvol - kvol) <= 1e-4 * max(abs(kvol), 1)
            ok_t = (tbb is not None) and (0 <= tbb <= tvol + 1e-6 * max(tvol, 1))
            if ok_v and ok_t:
                valid_bars += 1
            if not ok_v:
                mismatches += 1
        # liquidez (dólar-volumen mediano trailing, aprox: mediana global de quote_volume)
        mq = cur.execute("SELECT quote_volume FROM taker_flow WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
        med_qv = sorted(x[0] for x in mq if x[0] is not None)
        med_qv = med_qv[len(med_qv) // 2] if med_qv else 0
        if cov >= 0.95 and med_qv >= LIQ:
            universe.append((s, round(cov, 3), int(med_qv)))

    # gaps: sobre un símbolo del universo, ¿spacing exacto de 15m?
    gap_report = []
    for s, _, _ in universe[:5] + universe[-5:]:
        ts = [x[0] for x in cur.execute("SELECT open_time FROM taker_flow WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,))]
        if len(ts) >= 2:
            diffs = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
            exact = sum(1 for d in diffs if d == 900000)
            gap_report.append((s, round(100 * exact / len(diffs), 1), max(diffs) // 60000))

    print("=" * 70)
    print(f"VENTANA: 2025-12-01 → 2026-08-17  ({exp} barras 15m esperadas/símbolo)")
    print(f"SÍMBOLOS en klines_clean: {len(all_syms)}")
    print(f"SÍMBOLOS con taker_flow descargado: {len(downloaded)}")
    print(f"SÍMBOLOS descartados (sin taker_flow): {len(discarded)}")
    print(f"  {[d[0] for d in discarded][:40]}")
    print(f"\nINTEGRIDAD (intersección open_time taker_flow ∩ klines_clean):")
    print(f"  barras comparadas: {total_bars:,}")
    print(f"  barras con taker VÁLIDA (volume coincide ≤1bp Y 0≤taker_buy≤volume): {valid_bars:,} ({100*valid_bars/max(total_bars,1):.3f}%)")
    print(f"  discrepancias de volumen vs klines_clean: {mismatches}")
    print(f"\nUNIVERSO FINAL (cov ≥95% Y quote_volume mediano ≥ ${LIQ:,}/15m): {len(universe)} símbolos")
    print(f"  ejemplos: {[u[0] for u in universe[:15]]}")
    print(f"  cobertura del universo: min={min(u[1] for u in universe):.3f} median={sorted(u[1] for u in universe)[len(universe)//2]:.3f}")
    print(f"\nSPACING (muestra del universo): " + " | ".join(f"{s}:{p}%exact,maxgap{g}min" for s, p, g in gap_report))
    # cobertura por bucket temporal (para los splits)
    for lbl, a, b in (("discovery", "2025-12-01", "2026-03-31"), ("validation", "2026-04-01", "2026-05-31"), ("final_oos", "2026-06-01", "2026-08-17")):
        aa = int(dt.datetime.strptime(a, "%Y-%m-%d").timestamp() * 1000)
        bb = int(dt.datetime.strptime(b, "%Y-%m-%d").timestamp() * 1000)
        usyms = set(u[0] for u in universe)
        n = cur.execute("SELECT COUNT(*) FROM taker_flow WHERE interval='15m' AND open_time>=? AND open_time<? AND symbol IN (%s)" % ",".join("?" * len(usyms)),
                        [aa, bb] + list(usyms)).fetchone()[0]
        exp_split = ((bb - aa) // 900000) * len(usyms)
        print(f"  {lbl}: {n:,} barras / {exp_split:,} esperadas = {100*n/max(exp_split,1):.1f}%  (universo)")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    if a.backfill: backfill()
    elif a.audit: audit()
    else: ap.print_help()
