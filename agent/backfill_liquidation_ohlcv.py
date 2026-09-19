"""Rate-limited Bybit 5m OHLCV backfill matching stored liquidation events.

Writes only to the persistent canonical SQLite DB; it never touches Docker
volumes, live positions or the agent.  Checkpoints are implicit via the
primary key and every request is serialized to stay far below venue limits.
"""
import os
import sqlite3
import time
import json
from urllib.parse import urlencode
from urllib.request import urlopen

DB = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
LIQ_DB = os.path.join(os.path.dirname(__file__), "data", "klines.db")
SLEEP_S = 0.25


def main():
    live = sqlite3.connect(f"file:{LIQ_DB}?mode=ro", uri=True)
    symbols = [r[0] for r in live.execute("SELECT DISTINCT symbol FROM liquidations_research ORDER BY symbol")]
    first, last = live.execute("SELECT MIN(timestamp), MAX(timestamp) FROM liquidations_research").fetchone()
    live.close()
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS klines_multi_exchange (exchange TEXT, symbol TEXT, interval TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY(exchange,symbol,interval,open_time))")
    # include pre/post-event room for entry and exit research.
    start, end = int(first) - 24*3600000, int(last) + 24*3600000
    total = 0
    for number, symbol in enumerate(symbols, 1):
        cursor, rows = end, []
        while cursor > start:
            url = "https://api.bybit.com/v5/market/kline?" + urlencode({"category":"linear", "symbol":symbol, "interval":"5", "end":cursor, "limit":1000})
            try:
                with urlopen(url, timeout=20) as response:
                    status, payload = response.status, json.loads(response.read())
            except Exception:
                break
            if status == 429:
                time.sleep(5); continue
            data = payload.get("result", {}).get("list", [])
            if not data: break
            batch = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in data]
            rows.extend(x for x in batch if start <= x[0] <= end)
            oldest = min(x[0] for x in batch)
            if oldest <= start: break
            cursor = oldest - 1
            time.sleep(SLEEP_S)
        conn.executemany("INSERT OR IGNORE INTO klines_multi_exchange VALUES (?,?,?,?,?,?,?,?,?)", [("bybit", symbol, "5m", *r) for r in rows])
        conn.commit(); total += len(rows)
        print(f"[{number}/{len(symbols)}] {symbol}: {len(rows)} velas; total={total}", flush=True)
        time.sleep(SLEEP_S)
    print(f"Backfill completado: {total} velas Bybit 5m", flush=True)


if __name__ == "__main__":
    main()
