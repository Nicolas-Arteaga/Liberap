"""
SCAR Data Store — SQLite persistence for whale signals and token templates.
Uses aiosqlite for async I/O. DB file lives at python-service/scar_data.db.
"""
import os
import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, List, Dict

logger = logging.getLogger("SCAR_DB")

# Path is relative to python-service/ working directory
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "scar_data.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    conn = _get_conn()
    try:
        c = conn.cursor()

        # Table 1: Daily signals per token
        c.execute("""
            CREATE TABLE IF NOT EXISTS scar_daily_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                flag_whale_withdrawal INTEGER DEFAULT 0,
                flag_supply_drying    INTEGER DEFAULT 0,
                flag_price_stable     INTEGER DEFAULT 0,
                flag_funding_negative INTEGER DEFAULT 0,
                flag_silence          INTEGER DEFAULT 0,
                score_grial           INTEGER DEFAULT 0,
                prediction            TEXT,
                withdrawal_proxy_used INTEGER DEFAULT 1,
                UNIQUE(token_symbol, date)
            )
        """)

        # Table 2: Historical cycles (pump events)
        c.execute("""
            CREATE TABLE IF NOT EXISTS scar_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_symbol      TEXT NOT NULL,
                start_date        TEXT NOT NULL,
                end_date          TEXT,
                score_grial       INTEGER,
                prediction        TEXT,
                actual_pump_date  TEXT,
                actual_pump_pct   REAL,
                was_correct       INTEGER,
                created_at        TEXT DEFAULT (datetime('now'))
            )
        """)

        # Table 3: Token templates (learned from past cycles)
        c.execute("""
            CREATE TABLE IF NOT EXISTS scar_templates (
                token_symbol          TEXT PRIMARY KEY,
                avg_withdrawal_days   REAL,
                avg_withdrawal_usd    REAL,
                avg_supply_reduction  REAL,
                last_pump_date        TEXT,
                last_pump_price       REAL,
                total_cycles          INTEGER DEFAULT 0,
                last_updated          TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
        logger.info("✅ SCAR DB initialized at %s", DB_PATH)
    except Exception as e:
        logger.error("❌ SCAR DB init error: %s", e)
    finally:
        conn.close()


def upsert_daily_signal(
    symbol: str,
    flag_whale: bool,
    flag_supply: bool,
    flag_price: bool,
    flag_funding: bool,
    flag_silence: bool,
    score: int,
    prediction: str,
) -> None:
    today = date.today().isoformat()
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO scar_daily_signals
                (token_symbol, date, flag_whale_withdrawal, flag_supply_drying,
                 flag_price_stable, flag_funding_negative, flag_silence,
                 score_grial, prediction, withdrawal_proxy_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(token_symbol, date) DO UPDATE SET
                flag_whale_withdrawal = excluded.flag_whale_withdrawal,
                flag_supply_drying    = excluded.flag_supply_drying,
                flag_price_stable     = excluded.flag_price_stable,
                flag_funding_negative = excluded.flag_funding_negative,
                flag_silence          = excluded.flag_silence,
                score_grial           = excluded.score_grial,
                prediction            = excluded.prediction
        """, (symbol, today, int(flag_whale), int(flag_supply), int(flag_price),
              int(flag_funding), int(flag_silence), score, prediction))
        conn.commit()
    finally:
        conn.close()


def get_history(symbol: str, days: int = 30) -> List[Dict]:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM scar_daily_signals
            WHERE token_symbol = ?
            ORDER BY date DESC
            LIMIT ?
        """, (symbol, days)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_template(symbol: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM scar_templates WHERE token_symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_template(symbol: str, avg_days: float, last_pump_date: Optional[str],
                    last_pump_price: Optional[float], total_cycles: int) -> None:
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO scar_templates
                (token_symbol, avg_withdrawal_days, last_pump_date,
                 last_pump_price, total_cycles, last_updated)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(token_symbol) DO UPDATE SET
                avg_withdrawal_days = excluded.avg_withdrawal_days,
                last_pump_date      = excluded.last_pump_date,
                last_pump_price     = excluded.last_pump_price,
                total_cycles        = excluded.total_cycles,
                last_updated        = excluded.last_updated
        """, (symbol, avg_days, last_pump_date, last_pump_price, total_cycles))
        conn.commit()
    finally:
        conn.close()


def get_top_setups(limit: int = 10) -> List[Dict]:
    """Return the most recent day's signals ordered by score_grial desc."""
    conn = _get_conn()
    try:
        today = date.today().isoformat()
        rows = conn.execute("""
            SELECT * FROM scar_daily_signals
            WHERE date = ?
            ORDER BY score_grial DESC
            LIMIT ?
        """, (today, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_alerts(threshold: int = 3) -> List[Dict]:
    """Return today's signals with score_grial >= threshold."""
    conn = _get_conn()
    try:
        today = date.today().isoformat()
        rows = conn.execute("""
            SELECT * FROM scar_daily_signals
            WHERE date = ? AND score_grial >= ?
            ORDER BY score_grial DESC
        """, (today, threshold)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
