"""
KlineCache - SQLite Persistent Cache for Market Data
=====================================================
Single source of truth for all OHLCV data.

Schema:
  klines(symbol, interval, open_time PK, open, high, low, close, volume, is_final, updated_at)
  live_prices(symbol PK, close, open, high, low, volume, change_pct, updated_at)

Features:
  - Thread-safe with per-connection isolation (SQLite WAL mode)
  - UPSERT on conflict: live klines update high/low/close incrementally
  - Indexed reads: (symbol, interval) → O(log n)
  - get_klines() returns format compatible with Nexus-15
  - get_live_price() with staleness check (returns 0.0 if stale)
  - Automatic schema migration (safe to deploy over existing DB)
  - get_stats() for /health endpoint

Usage:
    from kline_cache import get_cache
    cache = get_cache()
    cache.upsert_kline("BTCUSDT", "15m", kline_dict)
    klines = cache.get_klines("BTCUSDT", "15m", limit=50)
    price  = cache.get_live_price("BTCUSDT")
"""

import os
import time
import sqlite3
import threading
import logging
from typing import Optional

logger = logging.getLogger("KlineCache")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH   = os.path.join(_DATA_DIR, "klines.db")

# How old a live price can be before we consider it stale
LIVE_PRICE_MAX_AGE_S = 90  # 90 seconds (one WS tick every ~2s, so this is very safe)


class KlineCache:
    """
    Thread-safe SQLite cache for klines and live prices.
    Uses WAL mode for concurrent reads + writes without blocking.
    Never instantiate directly — use get_cache().
    """

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._local   = threading.local()  # Per-thread connection (thread-safe)
        self._init_schema()
        logger.info(f"[KlineCache] Ready. DB: {db_path}")

    def _conn(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection (created on first access per thread)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")   # Concurrent reads + writes
            conn.execute("PRAGMA synchronous=NORMAL") # Safe + fast (not FULL)
            conn.execute("PRAGMA cache_size=-8000")   # 8 MB page cache
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        """Create tables and indexes if they don't exist. Safe to run on existing DB."""
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS klines (
                symbol      TEXT    NOT NULL,
                interval    TEXT    NOT NULL,
                open_time   INTEGER NOT NULL,
                open        REAL    NOT NULL,
                high        REAL    NOT NULL,
                low         REAL    NOT NULL,
                close       REAL    NOT NULL,
                volume      REAL    NOT NULL,
                is_final    INTEGER NOT NULL DEFAULT 0,
                updated_at  INTEGER NOT NULL,
                PRIMARY KEY (symbol, interval, open_time)
            );

            CREATE INDEX IF NOT EXISTS idx_klines_lookup
                ON klines (symbol, interval, open_time DESC);

            CREATE TABLE IF NOT EXISTS live_prices (
                symbol      TEXT    PRIMARY KEY,
                close       REAL    NOT NULL,
                open        REAL    NOT NULL,
                high        REAL    NOT NULL,
                low         REAL    NOT NULL,
                volume      REAL    NOT NULL,
                change_pct  REAL    NOT NULL DEFAULT 0.0,
                source      TEXT    NOT NULL DEFAULT 'binance',
                updated_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orderbook_ofi (
                symbol      TEXT    NOT NULL,
                timestamp   INTEGER NOT NULL,
                ofi         REAL    NOT NULL,
                bid_volume  REAL    NOT NULL,
                ask_volume  REAL    NOT NULL,
                levels      INTEGER NOT NULL,
                PRIMARY KEY (symbol, timestamp)
            );

            CREATE INDEX IF NOT EXISTS idx_ofi_lookup
                ON orderbook_ofi (symbol, timestamp DESC);

            CREATE TABLE IF NOT EXISTS funding_rates (
                symbol        TEXT    NOT NULL,
                funding_time  INTEGER NOT NULL,
                funding_rate  REAL    NOT NULL,
                updated_at    INTEGER NOT NULL,
                PRIMARY KEY (symbol, funding_time)
            );

            CREATE INDEX IF NOT EXISTS idx_funding_lookup
                ON funding_rates (symbol, funding_time DESC);

            CREATE TABLE IF NOT EXISTS whale_events (
                symbol      TEXT    NOT NULL,
                timestamp   INTEGER NOT NULL,
                value       REAL    NOT NULL,
                tx_hash     TEXT,
                source      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_whale_lookup
                ON whale_events (symbol, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_whale_txhash
                ON whale_events (tx_hash);

            CREATE TABLE IF NOT EXISTS liquidations (
                symbol      TEXT    NOT NULL,
                timestamp   INTEGER NOT NULL,
                side        TEXT    NOT NULL,
                qty         REAL    NOT NULL,
                price       REAL    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_liquidations_lookup
                ON liquidations (symbol, timestamp DESC);
        """)
        conn.commit()
        # Safe migration: add 'source' column to existing databases
        try:
            conn.execute("ALTER TABLE live_prices ADD COLUMN source TEXT NOT NULL DEFAULT 'binance'")
            conn.commit()
            logger.info("[KlineCache] Migrated live_prices: added 'source' column.")
        except Exception:
            pass  # Column already exists — normal on fresh installs

    # ──────────────────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────────────────

    def upsert_kline(self, symbol: str, interval: str, kline: dict):
        """
        Insert or update a kline entry.
        On conflict: update high (max), low (min), close, volume, is_final.
        kline dict must contain: open_time (ms), open, high, low, close, volume, is_final.
        """
        conn = self._conn()
        conn.execute("""
            INSERT INTO klines (symbol, interval, open_time, open, high, low, close, volume, is_final, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                high       = MAX(high, excluded.high),
                low        = MIN(low, excluded.low),
                close      = excluded.close,
                volume     = excluded.volume,
                is_final   = excluded.is_final,
                updated_at = excluded.updated_at
        """, (
            symbol,
            interval,
            int(kline["open_time"]),
            float(kline["open"]),
            float(kline["high"]),
            float(kline["low"]),
            float(kline["close"]),
            float(kline["volume"]),
            1 if kline.get("is_final") else 0,
            int(time.time()),
        ))
        conn.commit()

    def upsert_live_price(self, symbol: str, close: float, open_: float,
                          high: float, low: float, volume: float,
                          source: str = "binance"):
        """
        Update the live price for a symbol with source-priority logic.
        Priority: binance (1) > bybit (2) > okx (3) > bitget (4).
        A lower priority source cannot overwrite a higher priority one unless it is stale (> 10s).
        """
        priorities = {"binance": 1, "bybit": 2, "okx": 3, "bitget": 4, "pyth": 5}
        new_prio = priorities.get(source.lower(), 99)
        
        change_pct = ((close - open_) / open_ * 100) if open_ > 0 else 0.0
        now = int(time.time())
        
        conn = self._conn()
        
        # 1. Fetch current source and age
        row = conn.execute("SELECT source, updated_at FROM live_prices WHERE symbol = ?", (symbol,)).fetchone()
        
        if row:
            old_source = row["source"]
            old_prio = priorities.get(old_source.lower(), 99)
            age = now - row["updated_at"]
            
            # If current source is better and not stale, ignore this update
            if old_prio < new_prio and age < 10:
                return

        # 2. Perform the update
        conn.execute("""
            INSERT INTO live_prices (symbol, close, open, high, low, volume, change_pct, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                close      = excluded.close,
                open       = excluded.open,
                high       = MAX(high, excluded.high),
                low        = MIN(low, excluded.low),
                volume     = excluded.volume,
                change_pct = excluded.change_pct,
                source     = excluded.source,
                updated_at = excluded.updated_at
        """, (symbol, close, open_, high, low, volume, round(change_pct, 4), source, now))
        conn.commit()

    def bulk_upsert_klines(self, symbol: str, interval: str, klines: list):
        """
        Efficiently insert a batch of historical klines (e.g. from REST seed or on-demand fetch).
        klines: list of dicts with open_time, open, high, low, close, volume.
        """
        if not klines:
            return
        now = int(time.time())
        conn = self._conn()
        conn.executemany("""
            INSERT INTO klines (symbol, interval, open_time, open, high, low, close, volume, is_final, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                open       = excluded.open,
                high       = MAX(high, excluded.high),
                low        = MIN(low, excluded.low),
                close      = excluded.close,
                volume     = excluded.volume,
                is_final   = excluded.is_final,
                updated_at = excluded.updated_at
        """, [
            (symbol, interval,
             int(k["open_time"]),
             float(k["open"]), float(k["high"]), float(k["low"]),
             float(k["close"]), float(k["volume"]), now)
            for k in klines
        ])
        conn.commit()

    # ──────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────

    def get_klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> list:
        """
        Returns klines for a symbol, oldest first (Nexus-15 compatible format).
        Returns empty list if no data available.
        """
        conn = self._conn()
        rows = conn.execute("""
            SELECT open_time, open, high, low, close, volume
            FROM klines
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time DESC
            LIMIT ?
        """, (symbol, interval, limit)).fetchall()

        # Reverse so oldest is first (chronological order for ML)
        return [{
            "open_time":  r["open_time"],  # ms timestamp — used for staleness check in binance_fetcher
            "timestamp":  time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(r["open_time"] / 1000)),
            "open":       r["open"],
            "high":       r["high"],
            "low":        r["low"],
            "close":      r["close"],
            "volume":     r["volume"],
        } for r in reversed(rows)]

    def get_live_price(self, symbol: str) -> float:
        """
        Returns the latest live price for a symbol.
        Returns 0.0 if no data or if data is stale (> LIVE_PRICE_MAX_AGE_S seconds old).
        """
        conn = self._conn()
        row = conn.execute(
            "SELECT close, updated_at FROM live_prices WHERE symbol = ?", (symbol,)
        ).fetchone()

        if row is None:
            return 0.0
        age = time.time() - row["updated_at"]
        if age > LIVE_PRICE_MAX_AGE_S:
            logger.debug(f"[KlineCache] Stale live price for {symbol} (age={age:.0f}s)")
            return 0.0
        return float(row["close"])

    def get_ticker(self, symbol: str) -> Optional[dict]:
        """
        Returns the live ticker data for Tier 2 pre-filtering.
        { close, open, change_pct, volume, updated_at, age_s, is_fresh }
        Returns None if no data.
        """
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM live_prices WHERE symbol = ?", (symbol,)
        ).fetchone()

        if row is None:
            return None

        age = time.time() - row["updated_at"]
        return {
            "symbol":      symbol,
            "close":       row["close"],
            "open":        row["open"],
            "high":        row["high"],
            "low":         row["low"],
            "volume":      row["volume"],
            "change_pct":  row["change_pct"],
            "source":      row["source"] if "source" in row.keys() else "binance",
            "age_s":       round(age, 1),
            "is_fresh":    age <= LIVE_PRICE_MAX_AGE_S,
            "has_history": self.has_history(symbol),  # True if ≥25 closed candles in cache
        }

    def get_all_tickers(self) -> list:
        """Returns all live tickers in a format compatible with .NET SymbolTickerModel."""
        conn = self._conn()
        # Only return fresh tickers (< 90s old)
        now = time.time()
        rows = conn.execute(
            "SELECT * FROM live_prices WHERE updated_at >= ?", 
            (int(now - LIVE_PRICE_MAX_AGE_S),)
        ).fetchall()
        
        tickers = []
        for r in rows:
            tickers.append({
                "symbol":             r["symbol"],
                "lastPrice":          r["close"],
                "priceChange":        round(r["close"] - r["open"], 8),
                "priceChangePercent": r["change_pct"],
                "volume":             r["volume"],
                "highPrice":          r["high"],
                "lowPrice":           r["low"]
            })
        return tickers

    def has_history(self, symbol: str, interval: str = "15m", min_candles: int = 25) -> bool:
        """Returns True if symbol has enough closed candles for analysis."""
        conn = self._conn()
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM klines
            WHERE symbol = ? AND interval = ? AND is_final = 1
        """, (symbol, interval)).fetchone()
        return row["cnt"] >= min_candles

    def get_symbols_with_history(self, interval: str = "15m", min_candles: int = 25) -> list:
        """
        Returns all symbols that have enough closed candles for Nexus-15 analysis.
        This enables the agent to scan everything in the cache, not just a fixed rotation.
        """
        conn = self._conn()
        rows = conn.execute("""
            SELECT symbol, COUNT(*) as cnt
            FROM klines
            WHERE interval = ? AND is_final = 1
            GROUP BY symbol
            HAVING cnt >= ?
            ORDER BY cnt DESC
        """, (interval, min_candles)).fetchall()
        return [row["symbol"] for row in rows]

    # ──────────────────────────────────────────────────────────
    # Order Flow Imbalance (OFI) — order book imbalance
    # ──────────────────────────────────────────────────────────

    def upsert_ofi(self, symbol: str, ofi: float, bid_volume: float, ask_volume: float, levels: int):
        """
        Guarda un snapshot de Order Flow Imbalance. El caller (orderbook_ws.py)
        ya decide la frecuencia de escritura (throttle) — acá solo se persiste,
        mismo criterio que upsert_kline/upsert_live_price (no deciden su
        propia cadencia, la reciben del caller).
        """
        conn = self._conn()
        now = int(time.time())
        conn.execute("""
            INSERT INTO orderbook_ofi (symbol, timestamp, ofi, bid_volume, ask_volume, levels)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timestamp) DO UPDATE SET
                ofi        = excluded.ofi,
                bid_volume = excluded.bid_volume,
                ask_volume = excluded.ask_volume,
                levels     = excluded.levels
        """, (symbol, now, ofi, bid_volume, ask_volume, levels))
        conn.commit()

    def get_latest_ofi(self, symbol: str, max_age_s: int = 60) -> Optional[dict]:
        """
        Último OFI conocido para un símbolo, para uso en vivo (filtro de
        estrategia). Devuelve None si no hay dato o está más viejo que
        max_age_s — mismo criterio de staleness que get_live_price, nunca
        un valor viejo servido sin indicarlo.
        """
        conn = self._conn()
        row = conn.execute("""
            SELECT timestamp, ofi, bid_volume, ask_volume, levels
            FROM orderbook_ofi
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol,)).fetchone()
        if row is None:
            return None
        age = time.time() - row["timestamp"]
        if age > max_age_s:
            return None
        return {
            "symbol":     symbol,
            "ofi":        row["ofi"],
            "bid_volume": row["bid_volume"],
            "ask_volume": row["ask_volume"],
            "levels":     row["levels"],
            "age_s":      round(age, 1),
        }

    def get_ofi_before(self, symbol: str, timestamp_ms: int) -> Optional[float]:
        """
        Último OFI conocido antes o en timestamp_ms (ms, formato open_time de
        klines) — para backtesting sin lookahead, mismo principio que ya usa
        agent/backtest_engine.py para las MAs (nunca datos posteriores al
        índice de vela evaluado). Devuelve None si no hay ningún snapshot
        anterior a ese punto (ej. backtesteando un período previo a que este
        símbolo empezara a capturarse).
        """
        conn = self._conn()
        row = conn.execute("""
            SELECT ofi FROM orderbook_ofi
            WHERE symbol = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol, timestamp_ms // 1000)).fetchone()
        return row["ofi"] if row else None

    def get_ofi_series_aligned(self, symbol: str, open_times_ms: list) -> list:
        """
        Reconstruye una serie de OFI alineada a una lista de open_time (ms,
        ascendente — mismo orden que get_klines()) de velas: un valor por
        vela, el último OFI conocido a esa vela o antes (None si todavía no
        había captura en ese punto — nunca inventa un valor).

        Mismo principio de precómputo O(n) que _precompute_ma_series en
        backtest_engine.py (una sola pasada mergeando dos listas ya
        ordenadas) en vez de una query SQL por vela — evita repetir el
        problema de escalado O(n²) que ya apareció una vez en este proyecto.
        Requiere agent/backtest_engine.py para usarla en un backtest real
        (spec: "Exposición del OFI al motor de backtesting").
        """
        if not open_times_ms:
            return []
        conn = self._conn()
        rows = conn.execute("""
            SELECT timestamp, ofi FROM orderbook_ofi
            WHERE symbol = ?
            ORDER BY timestamp ASC
        """, (symbol,)).fetchall()

        result = []
        idx = 0
        last_ofi = None
        n = len(rows)
        for ot_ms in open_times_ms:
            ot_s = ot_ms // 1000
            while idx < n and rows[idx]["timestamp"] <= ot_s:
                last_ofi = rows[idx]["ofi"]
                idx += 1
            result.append(last_ofi)
        return result

    # ──────────────────────────────────────────────────────────
    # Funding rate
    # ──────────────────────────────────────────────────────────

    def bulk_upsert_funding(self, symbol: str, records: list):
        """
        records: lista de {funding_time (ms), funding_rate}, tal como devuelve
        /fapi/v1/fundingRate. Idempotente (upsert por PK symbol+funding_time)
        así que re-backfillear el mismo período no duplica ni requiere lógica
        de "ya lo tengo" — mismo criterio que bulk_upsert_klines.
        """
        if not records:
            return
        now = int(time.time())
        conn = self._conn()
        conn.executemany("""
            INSERT INTO funding_rates (symbol, funding_time, funding_rate, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, funding_time) DO UPDATE SET
                funding_rate = excluded.funding_rate,
                updated_at   = excluded.updated_at
        """, [
            (symbol, int(r["funding_time"]), float(r["funding_rate"]), now)
            for r in records
        ])
        conn.commit()

    def get_latest_funding(self, symbol: str) -> Optional[dict]:
        """
        Último funding rate conocido (settlement real, no una estimación en
        vivo). A diferencia de get_live_price/get_latest_ofi no hay chequeo
        de staleness por edad: el funding solo cambia cada ~8h, así que un
        valor de unas horas de antigüedad sigue siendo el vigente, no un
        dato viejo — es None únicamente si el símbolo nunca se backfilleó.
        """
        conn = self._conn()
        row = conn.execute("""
            SELECT funding_time, funding_rate FROM funding_rates
            WHERE symbol = ?
            ORDER BY funding_time DESC
            LIMIT 1
        """, (symbol,)).fetchone()
        if row is None:
            return None
        return {"symbol": symbol, "funding_rate": row["funding_rate"], "funding_time": row["funding_time"]}

    def count_funding_periods(self, symbol: str) -> int:
        """Cuántos períodos de funding ya están cacheados para este símbolo."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM funding_rates WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row["c"]

    def get_funding_before(self, symbol: str, timestamp_ms: int) -> Optional[float]:
        """Último funding rate vigente antes o en timestamp_ms — sin lookahead, para backtest."""
        conn = self._conn()
        row = conn.execute("""
            SELECT funding_rate FROM funding_rates
            WHERE symbol = ? AND funding_time <= ?
            ORDER BY funding_time DESC
            LIMIT 1
        """, (symbol, timestamp_ms)).fetchone()
        return row["funding_rate"] if row else None

    def get_funding_series_aligned(self, symbol: str, open_times_ms: list) -> list:
        """
        Mismo patrón O(n) que get_ofi_series_aligned: un funding rate por
        vela (el último vigente a esa vela o antes), en vez de una query por
        vela.
        """
        if not open_times_ms:
            return []
        conn = self._conn()
        rows = conn.execute("""
            SELECT funding_time, funding_rate FROM funding_rates
            WHERE symbol = ?
            ORDER BY funding_time ASC
        """, (symbol,)).fetchall()

        result = []
        idx = 0
        last_rate = None
        n = len(rows)
        for ot_ms in open_times_ms:
            while idx < n and rows[idx]["funding_time"] <= ot_ms:
                last_rate = rows[idx]["funding_rate"]
                idx += 1
            result.append(last_rate)
        return result

    # ──────────────────────────────────────────────────────────
    # On-chain whale activity
    # ──────────────────────────────────────────────────────────

    def insert_whale_event(self, symbol: str, value: float, source: str, tx_hash: str = None):
        """Registra una transferencia on-chain de tamaño 'ballena' detectada en vivo."""
        conn = self._conn()
        conn.execute(
            "INSERT INTO whale_events (symbol, timestamp, value, tx_hash, source) VALUES (?, ?, ?, ?, ?)",
            (symbol, int(time.time()), value, tx_hash, source)
        )
        conn.commit()

    def has_whale_tx(self, tx_hash: str) -> bool:
        """Dedupe: True si ya se registró esta tx (evita inflar count/total_value re-insertando lo mismo en cada poll)."""
        if not tx_hash:
            return False
        conn = self._conn()
        return conn.execute("SELECT 1 FROM whale_events WHERE tx_hash = ? LIMIT 1", (tx_hash,)).fetchone() is not None

    def get_whale_activity(self, symbol: str, window_minutes: int = 15) -> Optional[dict]:
        """
        Actividad de ballenas real en los últimos window_minutes. Devuelve
        None SOLO si esta fuente nunca capturó nada para este símbolo (sin
        cobertura, ej. no es BTC y no hay ETHERSCAN_API_KEY configurada) —
        no confundir con {"count": 0, ...}, que significa "cobertura real,
        pero sin actividad ballena en la ventana" (spec 4.3/4.5: nunca un
        score inventado, y distinguir "sin dato" de "dato real en cero").
        """
        conn = self._conn()
        has_any = conn.execute(
            "SELECT 1 FROM whale_events WHERE symbol = ? LIMIT 1", (symbol,)
        ).fetchone()
        if has_any is None:
            return None
        cutoff = int(time.time()) - window_minutes * 60
        rows = conn.execute("""
            SELECT value, source FROM whale_events
            WHERE symbol = ? AND timestamp >= ?
        """, (symbol, cutoff)).fetchall()
        return {
            "symbol": symbol,
            "count": len(rows),
            "total_value": round(sum(r["value"] for r in rows), 4),
            "source": rows[0]["source"] if rows else "onchain",
            "window_minutes": window_minutes,
        }

    def prune_old_whale_events(self, keep_hours: int = 72):
        conn = self._conn()
        cutoff = int(time.time()) - keep_hours * 3600
        conn.execute("DELETE FROM whale_events WHERE timestamp < ?", (cutoff,))
        conn.commit()

    # ──────────────────────────────────────────────────────────
    # Liquidaciones (Bybit allLiquidation — Binance forceOrder no
    # disponible en este entorno, ver liquidation_tracker.py)
    # ──────────────────────────────────────────────────────────

    def insert_liquidation(self, symbol: str, side: str, qty: float, price: float, timestamp_ms: int = None):
        """side: 'Sell' = se liquidó un LONG (venta forzada) | 'Buy' = se liquidó un SHORT (compra forzada)."""
        conn = self._conn()
        ts = int(timestamp_ms) if timestamp_ms is not None else int(time.time() * 1000)
        conn.execute(
            "INSERT INTO liquidations (symbol, timestamp, side, qty, price) VALUES (?, ?, ?, ?, ?)",
            (symbol, ts, side, qty, price)
        )
        conn.commit()

    def get_liquidation_cascade(
        self, symbol: str, recent_minutes: int = 15, baseline_hours: int = 4,
        threshold_multiplier: float = 3.0, min_cascade_usd: float = 20_000.0,
        at_timestamp_ms: int = None,
    ) -> Optional[dict]:
        """
        Compara el volumen liquidado (USD, qty*price) por lado en la ventana
        reciente contra el promedio por-ventana de las baseline_hours previas
        del MISMO símbolo — spec: "supera el umbral respecto al promedio del
        símbolo", no un umbral fijo global (símbolos chicos y grandes tienen
        escalas muy distintas).

        at_timestamp_ms: si se pasa (backtest), usa ese instante como "ahora"
        en vez de time.time() — permite reconstruir el estado histórico sin
        lookahead (spec: "Historial reconstruible para backtesting").

        Devuelve None si el símbolo nunca tuvo liquidaciones capturadas (sin
        cobertura) — no un {"cascade": False} vacío que parezca dato real.
        """
        conn = self._conn()
        now_ms = int(at_timestamp_ms) if at_timestamp_ms is not None else int(time.time() * 1000)
        has_any = conn.execute("SELECT 1 FROM liquidations WHERE symbol = ? AND timestamp <= ? LIMIT 1", (symbol, now_ms)).fetchone()
        if has_any is None:
            return None

        recent_cutoff = now_ms - recent_minutes * 60_000
        baseline_cutoff = now_ms - baseline_hours * 3_600_000

        def _sums(lo, hi):
            rows = conn.execute("""
                SELECT side, SUM(qty * price) as v FROM liquidations
                WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
                GROUP BY side
            """, (symbol, lo, hi)).fetchall()
            return {r["side"]: r["v"] for r in rows}

        recent = _sums(recent_cutoff, now_ms + 1)
        baseline = _sums(baseline_cutoff, recent_cutoff)
        num_buckets = max(1.0, (baseline_hours * 60.0) / recent_minutes)

        result = {"symbol": symbol, "recent_minutes": recent_minutes, "cascade_side": None, "magnitude": 0.0}
        for side in ("Sell", "Buy"):  # Sell=longs liquidados, Buy=shorts liquidados
            recent_v = recent.get(side, 0.0) or 0.0
            baseline_avg = (baseline.get(side, 0.0) or 0.0) / num_buckets
            if recent_v >= min_cascade_usd and recent_v >= threshold_multiplier * max(baseline_avg, 1.0):
                if recent_v > result["magnitude"]:
                    result["cascade_side"] = side
                    result["magnitude"] = round(recent_v, 2)
        return result

    def get_liquidation_events_before(self, symbol: str, timestamp_ms: int, lookback_ms: int) -> list:
        """Eventos crudos en [timestamp_ms - lookback_ms, timestamp_ms] — building block para backtest."""
        conn = self._conn()
        rows = conn.execute("""
            SELECT timestamp, side, qty, price FROM liquidations
            WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (symbol, timestamp_ms - lookback_ms, timestamp_ms)).fetchall()
        return [dict(r) for r in rows]

    def prune_old_liquidations(self, keep_hours: int = 24 * 7):
        conn = self._conn()
        cutoff = int(time.time() * 1000) - keep_hours * 3_600_000
        conn.execute("DELETE FROM liquidations WHERE timestamp < ?", (cutoff,))
        conn.commit()

    def prune_old_ofi(self, keep_hours: int = 24 * 30):
        """
        Borra snapshots de OFI más viejos que keep_hours. Con throttle de
        escritura de ~30s/símbolo, 30 días son ~2.6M filas totales para 30
        símbolos — manejable con el índice (symbol, timestamp); sin este
        prune la tabla crece sin límite (mismo riesgo que prune_old_klines,
        que existe pero nunca se llama — acá sí se llama, ver orderbook_ws.py).
        """
        conn = self._conn()
        cutoff = int(time.time()) - keep_hours * 3600
        conn.execute("DELETE FROM orderbook_ofi WHERE timestamp < ?", (cutoff,))
        conn.commit()

    def count_klines(self, symbol: str, interval: str = "15m") -> int:
        """Returns total kline count for a symbol."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM klines WHERE symbol = ? AND interval = ?",
            (symbol, interval)
        ).fetchone()
        return row["cnt"]

    # ──────────────────────────────────────────────────────────
    # Stats / housekeeping
    # ──────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Summary for /health endpoint."""
        conn = self._conn()
        # Per-source breakdown (how many live prices came from each exchange)
        source_rows = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM live_prices GROUP BY source"
        ).fetchall()
        sources = {row["source"]: row["cnt"] for row in source_rows}
        return {
            "total_klines":          conn.execute("SELECT COUNT(*) as c FROM klines").fetchone()["c"],
            "symbols_with_history":  conn.execute("SELECT COUNT(DISTINCT symbol) as c FROM klines").fetchone()["c"],
            "live_prices":           conn.execute("SELECT COUNT(*) as c FROM live_prices").fetchone()["c"],
            "live_prices_by_source": sources,
            "orderbook_ofi_rows":    conn.execute("SELECT COUNT(*) as c FROM orderbook_ofi").fetchone()["c"],
            "orderbook_ofi_symbols": conn.execute("SELECT COUNT(DISTINCT symbol) as c FROM orderbook_ofi").fetchone()["c"],
            "db_path":               self._db_path,
        }

    def prune_old_klines(self, keep_per_symbol: int = 200, interval: str = "15m"):
        """
        Delete old klines beyond keep_per_symbol per symbol.
        Safe to call periodically to prevent DB bloat.
        """
        conn = self._conn()
        conn.execute("""
            DELETE FROM klines
            WHERE interval = ? AND open_time NOT IN (
                SELECT open_time FROM klines k2
                WHERE k2.symbol = klines.symbol AND k2.interval = klines.interval
                ORDER BY open_time DESC
                LIMIT ?
            )
        """, (interval, keep_per_symbol))
        conn.commit()
        logger.debug(f"[KlineCache] Pruned old klines (keeping {keep_per_symbol}/symbol).")


# ──────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ──────────────────────────────────────────────────────────────

_cache:      Optional[KlineCache] = None
_cache_lock: threading.Lock       = threading.Lock()


def get_cache() -> KlineCache:
    """Returns the global KlineCache singleton. Thread-safe."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = KlineCache()
    return _cache
