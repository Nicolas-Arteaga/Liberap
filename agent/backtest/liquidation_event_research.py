"""Causal liquidation-event research for VIRE.

The module is deliberately hard-gated: it will not manufacture a result while
event and Bybit price histories do not overlap per symbol.  Once coverage is
available it evaluates a fixed event definition, chooses continuation versus
reversion in TRAIN only, then reports validation, OOS and stressed OOS.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from backtest import liquidation_research


@dataclass(frozen=True)
class LiquidationEventConfig:
    start_ms: int
    end_ms: int
    capital: float = 150.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    stress_bps: float = 3.0
    hold_ms: int = 60 * 60 * 1000
    min_oos_trades: int = 30
    min_days: int = 30
    min_symbols: int = 20


def init_ledger(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS invariant_liquidation_event_runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.commit()


def _metrics(rows, key="pnl"):
    values = [float(row[key]) for row in rows]
    profit, loss = sum(value for value in values if value > 0), abs(sum(value for value in values if value < 0))
    curve = peak = drawdown = 0.0
    for value in values:
        curve += value; peak = max(peak, curve); drawdown = min(drawdown, curve - peak)
    return {"trades": len(values), "net_pnl": round(sum(values), 4),
            "win_rate": round(100 * sum(value > 0 for value in values) / len(values), 2) if values else 0.0,
            "profit_factor": round(profit / loss, 4) if loss else None,
            "max_drawdown": round(drawdown, 4), "avg_trade": round(sum(values) / len(values), 4) if values else 0.0}


def _diagnostics(rows):
    buckets = {}
    for row in rows:
        bucket = buckets.setdefault(row["side"], {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
        bucket["trades"] += 1; bucket["wins"] += int(row["pnl"] > 0); bucket["losses"] += int(row["pnl"] <= 0); bucket["net_pnl"] += row["pnl"]
    return {"attribution_scope": "bybit_liquidation_event_and_matched_bybit_5m_price_only",
            "by_side": [{"side": side, **data, "net_pnl": round(data["net_pnl"], 4)} for side, data in sorted(buckets.items())], "trades": rows}


def _at(times, values, ts):
    index = bisect.bisect_right(times, ts) - 1
    return values[index] if index >= 0 and ts - times[index] <= 5 * 60 * 1000 else None


def _split(events):
    events.sort(key=lambda item: item["timestamp"])
    first, second = int(len(events) * .5), int(len(events) * .75)
    return events[:first], events[first:second], events[second:]


def _blocked(gate):
    return {"run_id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "liquidation_event_v1", "coverage": gate, "events": 0,
            "strategy": {"id": "vire:liquidation-event:continuation-or-reversion:h1", "name": "VIRE Liquidation Events — gated", "family": "liquidation_event", "version": "coverage-gated", "thesis": "No se permite evaluar la respuesta posterior a liquidaciones sin precio Bybit coincidente por símbolo.", "entry": None, "exit": None, "signal_sources": ["liquidations", "bybit_price"]},
            "status": "REJECTED_COVERAGE_GATE", "rejection_reasons": ["per_symbol_historical_overlap_required"]}


def run(conn, config: LiquidationEventConfig, liquidation_db_path: str, canonical_db_path: str) -> dict:
    init_ledger(conn)
    gate = liquidation_research.assess(conn, liquidation_db_path, canonical_db_path, config.min_days, config.min_symbols)
    if gate["status"] != "ELIGIBLE_FOR_HYPOTHESIS":
        result = _blocked(gate)
        conn.execute("INSERT INTO invariant_liquidation_event_runs VALUES (?,?,?,?)", (result["run_id"], result["created_at"], json.dumps(config.__dict__), json.dumps(result)))
        conn.commit(); return result
    live = sqlite3.connect(f"file:{liquidation_db_path}?mode=ro", uri=True)
    events = live.execute("SELECT symbol, timestamp, side FROM liquidations_research WHERE timestamp>=? AND timestamp<? ORDER BY timestamp", (config.start_ms, config.end_ms)).fetchall(); live.close()
    price = sqlite3.connect(f"file:{canonical_db_path}?mode=ro", uri=True)
    symbols = sorted({row[0] for row in events})
    prices = {symbol: price.execute("SELECT open_time, close FROM klines_multi_exchange WHERE exchange='bybit' AND symbol=? AND interval='5m' AND open_time>=? AND open_time<? ORDER BY open_time", (symbol, config.start_ms, config.end_ms + config.hold_ms + 5 * 60 * 1000)).fetchall() for symbol in symbols}; price.close()
    series = {symbol: ([int(row[0]) for row in rows], [float(row[1]) for row in rows]) for symbol, rows in prices.items() if rows}
    raw, next_allowed = [], {}
    for symbol, timestamp, liquidation_side in events:
        if symbol not in series or next_allowed.get(symbol, 0) > timestamp:
            continue
        times, closes = series[symbol]; entry_time = int(timestamp) + 5 * 60 * 1000; exit_time = entry_time + config.hold_ms
        entry, exit_ = _at(times, closes, entry_time), _at(times, closes, exit_time)
        if not entry or not exit_:
            continue
        # Bybit's Sell liquidation is a forced sell/long liquidation; Buy is
        # a forced buy/short liquidation.  Direction is still selected only
        # from TRAIN, so this mapping does not choose the trade orientation.
        impulse = -1.0 if str(liquidation_side).lower() == "sell" else 1.0
        raw.append({"timestamp": int(timestamp), "symbol": symbol, "liquidation_side": liquidation_side,
                    "signed_return": impulse * math.log(exit_ / entry)})
        next_allowed[symbol] = exit_time
    train_raw, validation_raw, oos_raw = _split(raw)
    direction = 1.0 if sum(item["signed_return"] for item in train_raw) >= 0 else -1.0
    base_cost = 2 * (config.fee_bps + config.slippage_bps) / 10000; stress_cost = base_cost + 2 * config.stress_bps / 10000
    def score(items):
        side = "continuation" if direction > 0 else "reversion"
        return [{"timestamp": item["timestamp"], "entry_time_ms": item["timestamp"] + 5 * 60 * 1000, "exit_time_ms": item["timestamp"] + 5 * 60 * 1000 + config.hold_ms, "symbol": item["symbol"], "side": side, "reason": "time_exit_after_liquidation_event", "liquidation_side": item["liquidation_side"], "cost": round(config.capital * base_cost, 6), "pnl": config.capital * (direction * item["signed_return"] - base_cost), "stress_pnl": config.capital * (direction * item["signed_return"] - stress_cost)} for item in items]
    train, validation, oos = score(train_raw), score(validation_raw), score(oos_raw)
    tm, vm, om, sm = _metrics(train), _metrics(validation), _metrics(oos), _metrics(oos, "stress_pnl")
    passed = vm["net_pnl"] > 0 and om["net_pnl"] > 0 and sm["net_pnl"] > 0 and om["trades"] >= config.min_oos_trades
    version = hashlib.sha256(json.dumps({"family": "liquidation_event", "hold_ms": config.hold_ms, "costs": [config.fee_bps, config.slippage_bps, config.stress_bps]}, sort_keys=True).encode()).hexdigest()[:12]
    result = {"run_id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "mode": "liquidation_event_v1", "coverage": gate, "coverage_symbols": len(series), "events": len(raw), "strategy": {"id": "vire:liquidation-event:train-direction:h1", "name": "VIRE Liquidation Events — TRAIN Direction 1h", "family": "liquidation_event", "version": version, "thesis": "Eventos Bybit con precio coincidente: TRAIN selecciona continuación o reversión, luego se fija para VAL/OOS.", "entry": {"event": "bybit_all_liquidation", "delay_minutes": 5, "direction": "train_selected"}, "exit": {"time_exit_hours": 1}, "signal_sources": ["liquidations", "bybit_price"]}, "train": tm, "validation": vm, "oos": om, "stressed_oos": sm, "trade_diagnostics": {"validation": _diagnostics(validation), "oos": _diagnostics(oos)}, "selected_direction": "continuation" if direction > 0 else "reversion", "status": "PAPER_READY" if passed else "REJECTED"}
    conn.execute("INSERT INTO invariant_liquidation_event_runs VALUES (?,?,?,?)", (result["run_id"], result["created_at"], json.dumps(config.__dict__), json.dumps(result)))
    conn.commit(); return result


def list_runs(conn, limit=20):
    init_ledger(conn)
    return [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM invariant_liquidation_event_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
