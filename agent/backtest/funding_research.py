"""Causal, standalone funding-crowding research for VIRE.

This intentionally does not import the live agent, dashboard, profiles or
legacy explorers.  It produces an auditable TRAIN/VAL/OOS experiment only.
"""
from __future__ import annotations

import bisect
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np


@dataclass(frozen=True)
class FundingConfig:
    start_ms: int
    end_ms: int
    capital: float = 150.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    stress_bps: float = 3.0
    hold_ms: int = 8 * 60 * 60 * 1000
    min_oos_trades: int = 15


def _price_maps(conn: sqlite3.Connection, symbols: list[str], start: int, end: int) -> dict[str, tuple[list[int], list[float]]]:
    out = {}
    for symbol in symbols:
        rows = conn.execute("SELECT open_time, close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<? ORDER BY open_time", (symbol, start, end)).fetchall()
        if len(rows) >= 2:
            out[symbol] = ([int(r[0]) for r in rows], [float(r[1]) for r in rows])
    return out


def _at(times: list[int], values: list[float], timestamp: int) -> float | None:
    i = bisect.bisect_right(times, timestamp) - 1
    return values[i] if 0 <= i < len(values) and timestamp - times[i] <= 10 * 60 * 1000 else None


def _metrics(trades: list[dict], key: str = "pnl") -> dict:
    pnls = [t[key] for t in trades]
    return {"trades": len(pnls), "net_pnl": round(sum(pnls), 4),
            "win_rate": round(100 * sum(p > 0 for p in pnls) / len(pnls), 2) if pnls else 0.0,
            "best_trade_share": round(max(pnls) / sum(pnls), 4) if pnls and sum(pnls) > 0 else 1.0}


def init_ledger(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS invariant_funding_runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.commit()


def run(conn: sqlite3.Connection, config: FundingConfig) -> dict:
    init_ledger(conn)
    rows = conn.execute("SELECT symbol, calc_time, funding_rate FROM funding_hist WHERE calc_time>=? AND calc_time<? ORDER BY calc_time", (config.start_ms, config.end_ms)).fetchall()
    symbols = sorted({str(r[0]) for r in rows})
    prices = _price_maps(conn, symbols, config.start_ms - config.hold_ms, config.end_ms + config.hold_ms)
    # Cross-sectional extreme is known at the funding timestamp, not future data.
    by_time: dict[int, list[tuple[str, float]]] = {}
    # The signal is the rate published at ts.  Funding paid at that instant is
    # not credited to a position opened after ts; PnL uses the *next* observed
    # funding payment, which is an outcome just like the later exit price.
    rate_at: dict[tuple[str, int], float] = {}
    for symbol, ts, rate in rows:
        if symbol in prices:
            by_time.setdefault(int(ts), []).append((str(symbol), float(rate)))
            rate_at[(str(symbol), int(ts))] = float(rate)
    events = []
    for ts, values in by_time.items():
        if len(values) < 10:
            continue
        abs_rates = np.array([abs(rate) for _, rate in values])
        for percentile in (0.90, 0.95):
            cut = float(np.quantile(abs_rates, percentile))
            for symbol, rate in values:
                if abs(rate) < cut or rate == 0:
                    continue
                times, closes = prices[symbol]
                entry, exit_ = _at(times, closes, ts + 5 * 60 * 1000), _at(times, closes, ts + 5 * 60 * 1000 + config.hold_ms)
                if not entry or not exit_:
                    continue
                side = -1 if rate > 0 else 1  # fade crowded side
                gross = side * (np.log(exit_) - np.log(entry))
                next_rate = rate_at.get((symbol, int(ts) + config.hold_ms))
                if next_rate is None:
                    continue
                funding = -side * next_rate
                cost = 2 * (config.fee_bps + config.slippage_bps) / 10000
                edge = gross + funding
                events.append({"timestamp": ts, "symbol": symbol, "percentile": percentile,
                               "pnl": config.capital * (edge - cost),
                               "stress_pnl": config.capital * (edge - cost - 2 * config.stress_bps / 10000)})
    events.sort(key=lambda e: e["timestamp"])
    a, b = int(len(events) * .50), int(len(events) * .75)
    train, val, oos = events[:a], events[a:b], events[b:]
    scores = {p: _metrics([e for e in train if e["percentile"] == p]) for p in (0.90, 0.95)}
    policy = max(scores, key=lambda p: scores[p]["net_pnl"])
    val_m, oos_m = _metrics([e for e in val if e["percentile"] == policy]), _metrics([e for e in oos if e["percentile"] == policy])
    stressed_oos = _metrics([e for e in oos if e["percentile"] == policy], "stress_pnl")
    result = {"run_id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "funding_crowding_contrarian_v2_causal_settlement", "coverage_symbols": len(symbols), "events": len(events),
            "policy": {"absolute_funding_percentile": policy, "hold_hours": config.hold_ms / 3600000},
            "train": scores[policy], "validation": val_m, "oos": oos_m, "stressed_oos": stressed_oos,
            "status": "REJECTED_PENDING_COMBINATION" if val_m["net_pnl"] > 0 and oos_m["net_pnl"] > 0 and stressed_oos["net_pnl"] > 0 and oos_m["trades"] >= config.min_oos_trades else "REJECTED"}
    conn.execute("INSERT INTO invariant_funding_runs VALUES (?,?,?,?)", (result["run_id"], result["created_at"], json.dumps(config.__dict__), json.dumps(result)))
    conn.commit()
    return result


def list_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    init_ledger(conn)
    rows = conn.execute("SELECT result_json FROM invariant_funding_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [json.loads(row[0]) for row in rows]
