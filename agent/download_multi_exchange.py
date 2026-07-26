"""
Descarga historico de Bybit/OKX/Bitget (15m, dic2025-jul2026) para los
simbolos que produccion realmente lee de CADA exchange
(config.get_primary_exchange_for_symbol, multi_source_fetcher.py) en vez de
Binance -- root cause real 2026-07-26: risk_manager.py::_apply_structural_tp_cap
usa self.fetcher.get_klines_for_nexus, que en produccion rota por exchange
segun el simbolo (~75% de los simbolos NO son Binance), mientras el backtest
solo tenia datos de Binance -> topes de TP estructural calculados con datos
de OTRO mercado, rechazando trades que en la realidad SI abrieron (caso real
NVDAUSDT 2026-07-11, ver PROGRESS_LOG).

Guarda en agent/data/binance_vision_clean.db, tabla klines_multi_exchange
(mismo esquema que klines_clean + columna exchange) -- NO pisa klines_clean
(que sigue siendo la fuente Binance-only para deteccion de señal, que SI
siempre lee Binance directo en produccion, ver _read_ma_geometry).
"""
import os
import sqlite3
import time
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binance_vision_clean.db")
START_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 7, 26, tzinfo=timezone.utc).timestamp() * 1000)
INTERVAL = "15m"


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_multi_exchange (
            exchange TEXT, symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (exchange, symbol, interval, open_time)
        )
    """)
    conn.commit()


# ── Bybit: linear perpetual, mismo formato de simbolo que Binance ──
def fetch_bybit(symbol: str) -> list:
    rows = []
    end = END_MS
    for _ in range(60):  # paginacion hacia atras, ~1000 velas x pagina
        try:
            r = requests.get(
                "https://api.bybit.com/v5/market/kline",
                params={"category": "linear", "symbol": symbol, "interval": "15", "end": end, "limit": 1000},
                timeout=15,
            )
            data = r.json().get("result", {}).get("list", [])
        except Exception:
            break
        if not data:
            break
        batch = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in data]
        batch = [b for b in batch if b[0] >= START_MS]
        rows.extend(batch)
        oldest = min(int(k[0]) for k in data)
        if oldest <= START_MS or len(data) < 2:
            break
        end = oldest - 1
    return rows


# ── OKX: SWAP perpetual, formato BASE-USDT-SWAP ──
def fetch_okx(symbol: str) -> list:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    inst_id = f"{base}-USDT-SWAP"
    rows = []
    after = None
    for _ in range(60):
        params = {"instId": inst_id, "bar": "15m", "limit": 100}
        if after:
            params["after"] = after
        try:
            r = requests.get("https://www.okx.com/api/v5/market/history-candles", params=params, timeout=15)
            data = r.json().get("data", [])
        except Exception:
            break
        if not data:
            break
        batch = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in data]
        batch = [b for b in batch if b[0] >= START_MS]
        rows.extend(batch)
        oldest = min(int(k[0]) for k in data)
        if oldest <= START_MS or len(data) < 2:
            break
        after = str(oldest)
    return rows


# ── Bitget: USDT-FUTURES, mismo formato de simbolo que Binance ──
def fetch_bitget(symbol: str) -> list:
    rows = []
    end = END_MS
    for _ in range(120):  # bitget limita 200/pagina
        try:
            r = requests.get(
                "https://api.bitget.com/api/v2/mix/market/history-candles",
                params={"symbol": symbol, "granularity": "15m", "productType": "USDT-FUTURES",
                        "endTime": end, "limit": 200},
                timeout=15,
            )
            data = r.json().get("data", [])
        except Exception:
            break
        if not data:
            break
        batch = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in data]
        batch = [b for b in batch if b[0] >= START_MS]
        rows.extend(batch)
        oldest = min(int(k[0]) for k in data)
        if oldest <= START_MS or len(data) < 2:
            break
        end = oldest - 1
    return rows


FETCHERS = {"bybit": fetch_bybit, "okx": fetch_okx, "bitget": fetch_bitget}


def main():
    wl = config.WATCHLIST
    by_ex = {"bybit": [], "okx": [], "bitget": []}
    for s in wl:
        ex = config.get_primary_exchange_for_symbol(s)
        if ex in by_ex:
            by_ex[ex].append(s)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    total = 0
    for ex, symbols in by_ex.items():
        print(f">>> {ex}: {len(symbols)} simbolos", flush=True)
        fetcher = FETCHERS[ex]
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(fetcher, sym): sym for sym in symbols}
            done = 0
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    rows = fut.result()
                except Exception as e:
                    rows = []
                    print(f"  ! {ex}/{sym}: {e}")
                if rows:
                    conn.executemany(
                        "INSERT OR IGNORE INTO klines_multi_exchange VALUES (?,?,?,?,?,?,?,?,?)",
                        [(ex, sym, INTERVAL, *r) for r in rows],
                    )
                    conn.commit()
                    total += len(rows)
                done += 1
                if done % 20 == 0:
                    print(f"  [{ex}] {done}/{len(symbols)} simbolos, total velas={total}", flush=True)
        print(f">>> {ex} listo", flush=True)

    print(f"\n>>> TOTAL velas multi-exchange: {total}")


if __name__ == "__main__":
    main()
