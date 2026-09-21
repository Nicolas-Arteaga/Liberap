"""Fase 1: isolate shared global slots using historical occupied intervals."""
from __future__ import annotations
import argparse, json, os, sqlite3
from collections import defaultdict
from datetime import datetime
from fase1_caso3_replay_compare import BAR_MS, compare, millis, norm_reason, return_pct, summarize
from phase_slot_causal import build_candstream, sim_exit, pnl_of


def run(cs, conn, reservations):
    by_bucket = defaultdict(list)
    for b, sym, e, sl, tp, side, score in cs["stream"]:
        by_bucket[b].append((sym,e,sl,tp,side))
    iv, slots = cs["interval_ms"], cs["slots"]
    start = min(b for b, *_ in cs["stream"])
    end = max(b for b, *_ in cs["stream"])
    own, done, last_day, reservation_index = {}, [], {}, 0
    reservations = sorted(reservations)
    now = start
    while now <= end:
        for sym in list(own):
            if own[sym]["close_ms"] <= now:
                done.append(own.pop(sym))
        while reservation_index < len(reservations) and reservations[reservation_index][0] <= now:
            reservation_index += 1
        shared = sum(1 for o,c in reservations[:reservation_index] if c > now)
        free = max(0, slots - shared - len(own))
        bucket = now - now % iv
        pending = {}
        for candidate_bucket in (bucket-iv, bucket-2*iv, bucket-3*iv):
            for candidate in by_bucket.get(candidate_bucket, ()):
                pending.setdefault(candidate[0], candidate)
        day = datetime.utcfromtimestamp(now/1000).date()
        eligible = [candidate for candidate in pending.values() if candidate[0] not in own and last_day.get(candidate[0]) != day]
        eligible.sort(key=lambda candidate: candidate[0])
        for sym,e,sl,tp,side in eligible[:free]:
            reason,xpx,cms = sim_exit(conn,sym,side,e,sl,tp,now,48)
            trade=dict(symbol=sym,side="short" if side==1 else "long",open_time=now,entry=e,exit_px=xpx,reason=norm_reason(reason),close_ms=cms)
            trade["return_pct"]=return_pct(trade["side"],e,xpx); trade["pnl"]=pnl_of(side,e,xpx)
            own[sym]=trade; last_day[sym]=day
        now += 5*60*1000
    done.extend(own.values())
    return done


def main():
    p=argparse.ArgumentParser(); p.add_argument('--scratch',required=True); p.add_argument('--mask',required=True); p.add_argument('--output',required=True); p.add_argument('--smoke',action='store_true'); a=p.parse_args()
    cs=build_candstream()
    if a.smoke:
        mask=json.load(open(a.mask)); print(json.dumps({'smoke':'ok','mask_symbols':len(mask),'mask_intervals':sum(len(v) for v in mask.values()),'signals':len(cs['stream'])})); return
    source=json.load(open(a.scratch)); real=[]
    for x in source:
        side='short' if x['sl']>x['entry'] else 'long'; real.append({'symbol':x['sym'],'side':side,'open_time':millis(x['open_utc']),'reason':norm_reason(x.get('real_outcome')),'return_pct':return_pct(side,x['entry'],x['exit_px'])})
    mask=json.load(open(a.mask)); reservations=[tuple(interval) for values in mask.values() for interval in values]
    conn=sqlite3.connect('file:/app/data/binance_vision_clean.db?mode=ro',uri=True); base=run(cs,conn,[]); shared=run(cs,conn,reservations); conn.close()
    measurable=[x for x in real if x['symbol'] in set(cs['active_order'])]
    bc,sc=compare(base,real,BAR_MS),compare(shared,real,BAR_MS)
    payload={'isolation':'global_shared_slots_only','coverage':{'csv_openings':3057,'mask_symbols':len(mask),'mask_intervals':len(reservations)},'base':{'summary':summarize(bc,base,len(real),len(measurable)),'comparison':bc},'shared_slots':{'summary':summarize(sc,shared,len(real),len(measurable)),'comparison':sc}}
    os.makedirs(os.path.dirname(a.output),exist_ok=True); json.dump(payload,open(a.output,'w'),ensure_ascii=False,indent=2); print(json.dumps({'output':a.output,'base':payload['base']['summary'],'shared':payload['shared_slots']['summary']}))
if __name__=='__main__': main()
