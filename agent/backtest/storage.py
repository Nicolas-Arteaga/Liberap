"""
Persistencia de corridas de backtest -- tabla SQLite local dentro de
agent/data/binance_vision_clean.db (NO Postgres/.NET, a proposito: evita el
acoplamiento con el backend .NET, que requiere parar manualmente el proceso
de Visual Studio del usuario para cada migracion EF -- friccion real y
recurrente ya documentada en PROGRESS_LOG.md). Cada corrida es una fila
nueva, nunca se pisa una anterior.
"""
import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id TEXT PRIMARY KEY,
            strategy_profile_id TEXT,
            strategy_name TEXT,
            strategy_type TEXT,
            start_date TEXT,
            end_date TEXT,
            run_at TEXT,
            total_pnl_usdt REAL,
            win_rate_pct REAL,
            accepted_trades INTEGER,
            result_json TEXT
        )
    """)
    conn.commit()


def save_run(conn: sqlite3.Connection, result: dict, profile: dict, start_date: str, end_date: str) -> str:
    init_db(conn)
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO backtest_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            profile.get("id"),
            profile.get("name"),
            profile.get("strategyType"),
            start_date,
            end_date,
            datetime.now(timezone.utc).isoformat(),
            result.get("total_pnl_usdt"),
            result.get("win_rate_pct"),
            result.get("accepted_trades"),
            json.dumps(result, default=str),
        ),
    )
    conn.commit()
    return run_id


def list_runs(conn: sqlite3.Connection, strategy_profile_id: str = None) -> list:
    init_db(conn)
    cur = conn.cursor()
    if strategy_profile_id:
        cur.execute(
            "SELECT id, strategy_profile_id, strategy_name, strategy_type, start_date, end_date, "
            "run_at, total_pnl_usdt, win_rate_pct, accepted_trades FROM backtest_runs "
            "WHERE strategy_profile_id=? ORDER BY run_at DESC",
            (strategy_profile_id,),
        )
    else:
        cur.execute(
            "SELECT id, strategy_profile_id, strategy_name, strategy_type, start_date, end_date, "
            "run_at, total_pnl_usdt, win_rate_pct, accepted_trades FROM backtest_runs "
            "ORDER BY run_at DESC"
        )
    cols = ["id", "strategyProfileId", "strategyName", "strategyType", "startDate", "endDate",
            "runAt", "totalPnlUsdt", "winRatePct", "acceptedTrades"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict:
    init_db(conn)
    cur = conn.cursor()
    cur.execute("SELECT result_json FROM backtest_runs WHERE id=?", (run_id,))
    row = cur.fetchone()
    if not row:
        return None
    return json.loads(row[0])
