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
        Update the live price for a symbol.
        'source' tracks which exchange provided this price (binance/bybit/okx/bitget).
        The source is only updated when the new data arrives, preserving the last
        known source even when the primary exchange is temporarily offline.
        """
        change_pct = ((close - open_) / open_ * 100) if open_ > 0 else 0.0
        conn = self._conn()
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
        """, (symbol, close, open_, high, low, volume, round(change_pct, 4), source, int(time.time())))
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
            ON CONFLICT(symbol, interval, open_time) DO NOTHING
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
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(r["open_time"] / 1000)),
            "open":      r["open"],
            "high":      r["high"],
            "low":       r["low"],
            "close":     r["close"],
            "volume":    r["volume"],
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
