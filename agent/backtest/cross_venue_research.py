"""Causal cross-venue dislocation experiment (Bybit versus Bitget)."""
from __future__ import annotations
import hashlib, json, sqlite3, uuid
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
    profit,loss=sum(x for x in p if x>0),abs(sum(x for x in p if x<0)); curve=peak=dd=0.0
    for value in p: curve+=value;peak=max(peak,curve);dd=min(dd,curve-peak)
    return {"trades":len(p),"net_pnl":round(sum(p),4),"win_rate":round(100*sum(x>0 for x in p)/len(p),2) if p else 0.0,"profit_factor":round(profit/loss,4) if loss else None,"max_drawdown":round(dd,4),"avg_trade":round(sum(p)/len(p),4) if p else 0.0}

def _diagnostics(rows):
    return {"attribution_scope":"bybit_bitget_dislocation_mean_reversion_with_four_leg_costs","by_exit":[{"reason":"time_exit","trades":len(rows),"wins":sum(x["pnl"]>0 for x in rows),"losses":sum(x["pnl"]<=0 for x in rows),"net_pnl":round(sum(x["pnl"] for x in rows),4)}],"trades":rows}

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
                    ev.append({"timestamp":t,"symbol":s,"spread":spread,"gross":spread-future})
        train=[e for e in ev if e["timestamp"]<cut1]
        candidates.append((sum(e["gross"] for e in train),threshold,hold,ev))
    _,threshold,hold,events=max(candidates,key=lambda x:x[0]) if candidates else (0,.95,1,[])
    cost=4*(config.fee_bps+config.slippage_bps)/10000; stress=cost+4*config.stress_bps/10000
    def score(items): return [{"timestamp":e["timestamp"],"entry_time_ms":e["timestamp"],"exit_time_ms":e["timestamp"]+hold*900000,"symbol":e["symbol"],"side":"long_bybit_short_bitget" if e["spread"]<0 else "short_bybit_long_bitget","reason":"time_exit_after_dislocation","gross_dislocation_return":round(config.capital*e["gross"],6),"cost":round(config.capital*cost,6),"pnl":config.capital*(e["gross"]-cost),"stress_pnl":config.capital*(e["gross"]-stress)} for e in items]
    train=score([e for e in events if e["timestamp"]<cut1]); val=score([e for e in events if cut1<=e["timestamp"]<cut2]); oos=score([e for e in events if e["timestamp"]>=cut2])
    tm,vm,om,sm=_metrics(train),_metrics(val),_metrics(oos),_metrics(oos,"stress_pnl")
    passed=vm["net_pnl"]>0 and om["net_pnl"]>0 and sm["net_pnl"]>0 and om["trades"]>=config.min_oos_trades
    version=hashlib.sha256(json.dumps({"family":"cross_venue_dislocation","threshold":threshold,"hold":hold,"fees":config.fee_bps,"slippage":config.slippage_bps,"stress":config.stress_bps},sort_keys=True).encode()).hexdigest()[:12]
    r={"run_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),"mode":"cross_venue_dislocation_v1","venues":["bybit","bitget"],"coverage_symbols":len(by_symbol),"events":len(events),"policy":{"train_selected_abs_spread_quantile":threshold,"hold_15m_bars":hold,"cost_legs":4},"strategy":{"id":f"vire:cross-venue-dislocation:bybit-bitget:q{int(threshold*100)}:h{hold}","name":f"VIRE Cross-Venue Dislocation — Bybit/Bitget q{int(threshold*100)} {hold} bars","family":"cross_venue_dislocation","version":version,"thesis":"Una dislocación extrema entre Bybit y Bitget puede converger; se mide después de cuatro piernas de ejecución.","entry":{"abs_spread_quantile":threshold,"side":"buy_discounted_venue_sell_premium_venue"},"exit":{"time_exit_15m_bars":hold},"signal_sources":["bybit_price","bitget_price"]},"train":tm,"validation":vm,"oos":om,"stressed_oos":sm,"trade_diagnostics":{"validation":_diagnostics(val),"oos":_diagnostics(oos)},"status":"PAPER_READY" if passed else "REJECTED"}
    conn.execute("INSERT INTO invariant_cross_venue_runs VALUES (?,?,?,?)",(r["run_id"],r["created_at"],json.dumps(config.__dict__),json.dumps(r)));conn.commit();return r

def list_runs(conn,limit=20):
    init_ledger(conn);return [json.loads(x[0]) for x in conn.execute("SELECT result_json FROM invariant_cross_venue_runs ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()]
