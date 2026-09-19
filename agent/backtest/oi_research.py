"""Standalone OI expansion research; no live-agent or profile dependency."""
from __future__ import annotations

import bisect
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np


@dataclass(frozen=True)
class OIConfig:
    start_ms: int
    end_ms: int
    capital: float = 150.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    stress_bps: float = 3.0
    hold_ms: int = 4 * 60 * 60 * 1000
    min_oos_trades: int = 30


def _at(times, values, ts):
    i = bisect.bisect_right(times, ts) - 1
    return values[i] if i >= 0 and ts - times[i] <= 10 * 60 * 1000 else None


def _metrics(rows, key="pnl"):
    p = [r[key] for r in rows]
    return {"trades": len(p), "net_pnl": round(sum(p), 4), "win_rate": round(100 * sum(v > 0 for v in p) / len(p), 2) if p else 0.0}


def init_ledger(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS invariant_oi_runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.commit()


def run(conn: sqlite3.Connection, config: OIConfig) -> dict:
    init_ledger(conn)
    # Hourly observations keep one causal decision per funding-like horizon.
    oi = conn.execute("SELECT symbol, open_time, sum_oi_value FROM oi_metrics WHERE open_time>=? AND open_time<? AND open_time % 3600000 = 0 ORDER BY open_time", (config.start_ms - 3600000, config.end_ms)).fetchall()
    symbols = sorted({r[0] for r in oi})
    prices = {}
    for s in symbols:
        rows = conn.execute("SELECT open_time, close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<? ORDER BY open_time", (s, config.start_ms - 2*3600000, config.end_ms + config.hold_ms)).fetchall()
        if rows: prices[s] = ([int(x[0]) for x in rows], [float(x[1]) for x in rows])
    previous, grouped = {}, {}
    for symbol, ts, value in oi:
        if symbol not in prices or value is None: continue
        if symbol in previous and previous[symbol] > 0:
            grouped.setdefault(int(ts), []).append((symbol, (float(value)/previous[symbol])-1))
        previous[symbol] = float(value)
    events=[]
    for ts, vals in grouped.items():
        if len(vals)<10: continue
        cut=float(np.quantile([abs(x[1]) for x in vals], .95))
        for symbol, oi_change in vals:
            if abs(oi_change)<cut: continue
            times, closes=prices[symbol]; before=_at(times,closes,ts-3600000); entry=_at(times,closes,ts); exit_=_at(times,closes,ts+config.hold_ms)
            if not before or not entry or not exit_: continue
            momentum=np.sign(np.log(entry)-np.log(before))
            if momentum == 0 or np.sign(oi_change) != momentum: continue
            edge=momentum*(np.log(exit_)-np.log(entry)); cost=2*(config.fee_bps+config.slippage_bps)/10000
            events.append({"timestamp":ts,"pnl":config.capital*(edge-cost),"stress_pnl":config.capital*(edge-cost-2*config.stress_bps/10000)})
    events.sort(key=lambda x:x["timestamp"]); a,b=int(len(events)*.5),int(len(events)*.75)
    train,val,oos=events[:a],events[a:b],events[b:]
    tm,vm,om,sm=_metrics(train),_metrics(val),_metrics(oos),_metrics(oos,"stress_pnl")
    result={"run_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),"mode":"oi_expansion_momentum_v1","coverage_symbols":len(symbols),"events":len(events),"train":tm,"validation":vm,"oos":om,"stressed_oos":sm,"status":"REJECTED_PENDING_COMBINATION" if vm["net_pnl"]>0 and om["net_pnl"]>0 and sm["net_pnl"]>0 and om["trades"]>=config.min_oos_trades else "REJECTED"}
    conn.execute("INSERT INTO invariant_oi_runs VALUES (?,?,?,?)",(result["run_id"],result["created_at"],json.dumps(config.__dict__),json.dumps(result)))
    conn.commit()
    return result


def list_runs(conn, limit=20):
    init_ledger(conn)
    return [json.loads(r[0]) for r in conn.execute("SELECT result_json FROM invariant_oi_runs ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()]
