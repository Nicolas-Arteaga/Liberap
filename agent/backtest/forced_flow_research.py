"""Causal forced-flow proxy research using historical OI, taker flow and price.

This is deliberately *not* labelled liquidation data.  It searches for the
observable footprint of a deleveraging event (OI contraction, aggressive flow
and displacement) over the months for which those three inputs overlap.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np


@dataclass(frozen=True)
class ForcedFlowConfig:
    start_ms: int
    end_ms: int
    capital: float = 150.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    stress_bps: float = 3.0
    hold_ms: int = 60 * 60 * 1000
    min_oos_trades: int = 30


def _at(times, values, ts):
    i = bisect.bisect_right(times, ts) - 1
    return values[i] if i >= 0 and ts - times[i] <= 20 * 60 * 1000 else None


def _metrics(rows, key="pnl"):
    values = [r[key] for r in rows]
    profit, loss = sum(v for v in values if v > 0), abs(sum(v for v in values if v < 0))
    curve = peak = drawdown = 0.0
    for value in values:
        curve += value; peak = max(peak, curve); drawdown = min(drawdown, curve - peak)
    return {"trades": len(values), "net_pnl": round(sum(values), 4),
            "win_rate": round(100 * sum(v > 0 for v in values) / len(values), 2) if values else 0.0,
            "profit_factor": round(profit / loss, 4) if loss else None, "max_drawdown": round(drawdown, 4),
            "avg_trade": round(sum(values) / len(values), 4) if values else 0.0}


def _diagnostics(rows):
    sides = {}
    for row in rows:
        bucket = sides.setdefault(row["side"], {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
        bucket["trades"] += 1; bucket["wins"] += int(row["pnl"] > 0); bucket["losses"] += int(row["pnl"] <= 0); bucket["net_pnl"] += row["pnl"]
    return {"attribution_scope": "oi_contraction_taker_flow_and_price_displacement_proxy_not_liquidation_truth",
            "by_side": [{"side": side, **data, "net_pnl": round(data["net_pnl"], 4)} for side, data in sorted(sides.items())], "trades": rows}


def init_ledger(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS invariant_forced_flow_runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.commit()


def _split(events):
    events.sort(key=lambda x: x["timestamp"])
    train_end = int(len(events) * .5)
    validation_end = int(len(events) * .75)
    return events[:train_end], events[train_end:validation_end], events[validation_end:]


def run(conn: sqlite3.Connection, config: ForcedFlowConfig) -> dict:
    init_ledger(conn)
    # The raw inputs are known at close of the 15m bar. Entry is the next bar,
    # so neither the price exit nor an unobserved future OI sample is used.
    rows = conn.execute("""
        SELECT t.symbol, t.open_time, t.quote_volume, t.taker_buy_quote,
               o.sum_oi_value
        FROM taker_flow t JOIN oi_metrics o
          ON o.symbol=t.symbol AND o.open_time=t.open_time
        WHERE t.interval='15m' AND t.open_time>=? AND t.open_time<?
          AND t.quote_volume>0 AND o.sum_oi_value>0
        ORDER BY t.symbol, t.open_time
    """, (config.start_ms - 15 * 60 * 1000, config.end_ms)).fetchall()
    symbols = sorted({r[0] for r in rows})
    prices = {}
    for symbol in symbols:
        p = conn.execute("SELECT open_time, close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<? ORDER BY open_time", (symbol, config.start_ms - 2 * 60 * 60 * 1000, config.end_ms + config.hold_ms + 5 * 60 * 1000)).fetchall()
        if p:
            prices[symbol] = ([int(x[0]) for x in p], [float(x[1]) for x in p])

    # Fixed, pre-registered event definition. Percentiles are calculated per
    # timestamp across symbols, which uses only data observable at that instant.
    prior_oi, grouped = {}, {}
    for symbol, ts, quote, buy_quote, oi_value in rows:
        if symbol not in prices:
            continue
        prev = prior_oi.get(symbol)
        if prev:
            oi_delta = float(oi_value) / prev - 1.0
            imbalance = 2.0 * float(buy_quote) / float(quote) - 1.0
            grouped.setdefault(int(ts), []).append((symbol, oi_delta, imbalance))
        prior_oi[symbol] = float(oi_value)

    raw = []
    next_allowed = {}
    for ts, observations in grouped.items():
        if len(observations) < 12:
            continue
        oi_cut = float(np.quantile([abs(v[1]) for v in observations], .95))
        flow_cut = float(np.quantile([abs(v[2]) for v in observations], .90))
        for symbol, oi_delta, imbalance in observations:
            if abs(oi_delta) < oi_cut or abs(imbalance) < flow_cut:
                continue
            times, closes = prices[symbol]
            before = _at(times, closes, ts - 15 * 60 * 1000)
            signal_close = _at(times, closes, ts)
            entry = _at(times, closes, ts + 5 * 60 * 1000)
            exit_ = _at(times, closes, ts + 5 * 60 * 1000 + config.hold_ms)
            if not before or not signal_close or not entry or not exit_ or next_allowed.get(symbol, 0) > ts:
                continue
            displacement = np.sign(np.log(signal_close) - np.log(before))
            # A contraction plus same-direction aggressive flow is the proxy
            # footprint; direction is learned only from the TRAIN partition.
            if displacement == 0 or np.sign(imbalance) != displacement or oi_delta >= 0:
                continue
            raw.append({"timestamp": ts, "symbol": symbol,
                        "signed_return": float(displacement * (np.log(exit_) - np.log(entry)))})
            next_allowed[symbol] = ts + config.hold_ms

    train_raw, val_raw, oos_raw = _split(raw)
    # Direction choice (continuation vs reversion) is selected once on TRAIN;
    # it cannot be re-selected on validation/OOS.
    train_sum = sum(x["signed_return"] for x in train_raw)
    direction = 1.0 if train_sum >= 0 else -1.0
    cost = 2 * (config.fee_bps + config.slippage_bps) / 10000
    stress_cost = cost + 2 * config.stress_bps / 10000
    def scored(items):
        side = "long" if direction > 0 else "short"
        return [{"timestamp": x["timestamp"], "entry_time_ms": x["timestamp"] + 5 * 60 * 1000,
                 "exit_time_ms": x["timestamp"] + 5 * 60 * 1000 + config.hold_ms, "symbol": x["symbol"], "side": side,
                 "reason": "time_exit_after_forced_flow_proxy", "gross_proxy_return": round(config.capital * direction * x["signed_return"], 6),
                 "cost": round(config.capital * cost, 6), "pnl": config.capital * (direction * x["signed_return"] - cost),
                 "stress_pnl": config.capital * (direction * x["signed_return"] - stress_cost)} for x in items]
    train, validation, oos = scored(train_raw), scored(val_raw), scored(oos_raw)
    tm, vm, om, sm = _metrics(train), _metrics(validation), _metrics(oos), _metrics(oos, "stress_pnl")
    passed = vm["net_pnl"] > 0 and om["net_pnl"] > 0 and sm["net_pnl"] > 0 and om["trades"] >= config.min_oos_trades
    version = hashlib.sha256(json.dumps({"family":"forced_flow_proxy","direction":"continuation" if direction > 0 else "reversion","hold_ms":config.hold_ms,"fee_bps":config.fee_bps,"slippage_bps":config.slippage_bps,"stress_bps":config.stress_bps}, sort_keys=True).encode()).hexdigest()[:12]
    result = {"run_id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "forced_flow_proxy_v1", "label": "proxy; not liquidation ground truth",
              "coverage_symbols": len(prices), "events": len(raw),
              "strategy": {"id":f"vire:forced-flow-proxy:{'continuation' if direction > 0 else 'reversion'}:h{config.hold_ms//3600000}", "name":f"VIRE Forced-Flow Proxy — {'Continuation' if direction > 0 else 'Reversion'} {config.hold_ms//3600000}h", "family":"forced_flow_proxy", "version":version, "thesis":"Contracción extrema de OI, flujo tomador y desplazamiento alineado pueden revelar un desapalancamiento observable; es un proxy, no liquidación confirmada.", "entry":{"oi_contraction_percentile":0.95,"taker_imbalance_percentile":0.90,"direction":"train_selected"}, "exit":{"time_exit_hours":config.hold_ms/3600000}, "signal_sources":["open_interest","taker_flow","price"]},
              "train": tm, "validation": vm, "oos": om, "stressed_oos": sm,
              "trade_diagnostics":{"validation":_diagnostics(validation),"oos":_diagnostics(oos)},
              "selected_direction": "continuation" if direction > 0 else "reversion",
              "status": "PAPER_READY" if passed else "REJECTED"}
    conn.execute("INSERT INTO invariant_forced_flow_runs VALUES (?,?,?,?)", (result["run_id"], result["created_at"], json.dumps(config.__dict__), json.dumps(result)))
    conn.commit()
    return result


def list_runs(conn, limit=20):
    init_ledger(conn)
    return [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM invariant_forced_flow_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
