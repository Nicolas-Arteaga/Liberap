"""Causal cross-venue dislocation experiment (Bybit versus Bitget)."""
from __future__ import annotations
import json, sqlite3, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np

@dataclass(frozen=True)
class CrossVenueConfig:
    start_ms: int
    end_ms: int
    capital: float = 150.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    stress_bps: float = 3.0
    min_oos_trades: int = 30

def _metrics(rows, key="pnl"):
    p=[x[key] for x in rows]
    return {"trades":len(p),"net_pnl":round(sum(p),4),"win_rate":round(100*sum(x>0 for x in p)/len(p),2) if p else 0.0}

def init_ledger(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS invariant_cross_venue_runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, result_json TEXT NOT NULL)"); conn.commit()

def run(conn: sqlite3.Connection, config: CrossVenueConfig, source_conn: sqlite3.Connection | None = None) -> dict:
    init_ledger(conn)
    source = source_conn or conn
    symbols=[r[0] for r in source.execute("""SELECT DISTINCT symbol FROM klines_multi_exchange
        WHERE exchange='bybit' AND interval='15m'
        INTERSECT SELECT DISTINCT symbol FROM klines_multi_exchange
        WHERE exchange='bitget' AND interval='15m'""").fetchall()]
    # Query symbol-by-symbol: the archive's primary key is venue/symbol/time;
    # a venue-wide join would force SQLite to scan millions of unrelated rows.
    rows=[]
    for symbol in symbols:
        rows.extend(source.execute("""SELECT b.symbol,b.open_time,b.close,g.close FROM klines_multi_exchange b
            JOIN klines_multi_exchange g ON g.symbol=b.symbol AND g.open_time=b.open_time AND g.interval=b.interval
            WHERE b.exchange='bybit' AND g.exchange='bitget' AND b.interval='15m' AND b.symbol=? AND b.open_time>=? AND b.open_time<?
            ORDER BY b.open_time""",(symbol,config.start_ms,config.end_ms)).fetchall())
    by_symbol={}
    for s,t,b,g in rows:
        if b>0 and g>0: by_symbol.setdefault(s,[]).append((int(t),float(np.log(b/g))))
    # Split by time, not by event count, then select one fixed threshold/hold from TRAIN only.
    cut1=config.start_ms+(config.end_ms-config.start_ms)//2; cut2=config.start_ms+3*(config.end_ms-config.start_ms)//4
    candidates=[]
    for threshold in (.95,.99):
      for hold in (1,4,16):
        ev=[]
        for s,series in by_symbol.items():
            d=dict(series); train=np.array([x for t,x in series if t<cut1])
            if len(train)<100: continue
            bound=float(np.quantile(np.abs(train),threshold))
            for t,spread in series:
                future=d.get(t+hold*900000)
                if future is not None and abs(spread)>=bound:
                    ev.append({"timestamp":t,"gross":spread-future})
        train=[e for e in ev if e["timestamp"]<cut1]
        candidates.append((sum(e["gross"] for e in train),threshold,hold,ev))
    _,threshold,hold,events=max(candidates,key=lambda x:x[0]) if candidates else (0,.95,1,[])
    cost=4*(config.fee_bps+config.slippage_bps)/10000; stress=cost+4*config.stress_bps/10000
    def score(items): return [{"pnl":config.capital*(e["gross"]-cost),"stress_pnl":config.capital*(e["gross"]-stress)} for e in items]
    train=score([e for e in events if e["timestamp"]<cut1]); val=score([e for e in events if cut1<=e["timestamp"]<cut2]); oos=score([e for e in events if e["timestamp"]>=cut2])
    tm,vm,om,sm=_metrics(train),_metrics(val),_metrics(oos),_metrics(oos,"stress_pnl")
    passed=vm["net_pnl"]>0 and om["net_pnl"]>0 and sm["net_pnl"]>0 and om["trades"]>=config.min_oos_trades
    r={"run_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),"mode":"cross_venue_dislocation_v1","venues":["bybit","bitget"],"coverage_symbols":len(by_symbol),"events":len(events),"policy":{"train_selected_abs_spread_quantile":threshold,"hold_15m_bars":hold,"cost_legs":4},"train":tm,"validation":vm,"oos":om,"stressed_oos":sm,"status":"PAPER_READY" if passed else "REJECTED"}
    conn.execute("INSERT INTO invariant_cross_venue_runs VALUES (?,?,?,?)",(r["run_id"],r["created_at"],json.dumps(config.__dict__),json.dumps(r)));conn.commit();return r

def list_runs(conn,limit=20):
    init_ledger(conn);return [json.loads(x[0]) for x in conn.execute("SELECT result_json FROM invariant_cross_venue_runs ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()]
