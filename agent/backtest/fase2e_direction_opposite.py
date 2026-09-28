"""Fase 2 A/B preregistered diagnostics: mirrored side and opposite MA exit."""
from __future__ import annotations
import argparse, bisect, json, os, pickle, sqlite3
from collections import defaultdict
import fase2_ma3_broad_matrix as m
import fase2b_ma3_exit_variants as b
import phase_slot_causal as c
from engine import BacktestEngine

SC=b.SCENARIOS; CACHE='/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl'

def mirror(t):
    return {**t,'side':1-t['side'],'sl':2*t['entry']-t['sl'],'tp':2*t['entry']-t['tp']}

def mean(v): return sum(v)/len(v) if v else None
def verdict(vals,base):
    ok=True; out={}
    for s in vals:
        d={p:mean(vals[s][p])-mean(base[s][p]) for p in ('TRAIN','VALIDATION','OOS')}
        no3=sorted(vals[s]['OOS'],reverse=True)[3:]; bn=sorted(base[s]['OOS'],reverse=True)[3:]
        out[s]={'delta':d,'oos_without_top3_delta':mean(no3)-mean(bn)}
        ok &= d['OOS']>0 and out[s]['oos_without_top3_delta']>0 and sum(x>0 for x in d.values())>=2
    return ok,out

def opposite_profile():
 p=dict(c.CASO3_PROFILE); p.update({'allowLong':True,'allowShort':False})
 q=json.loads(p['patternParamsJson'])
 q['order']={'ma7VsMa25':'less','ma7VsMa50':'less','ma7VsMa99':'less'}
 q['slope']={'targetMa':'ma7','windowCandles':3,'currentOp':'gte','currentDeg':0.2,'priorOp':'lte','priorDeg':-0.2}
 q['peakProximity']={'enabled':True,'type':'recentLow','lookbackCandles':10,'tolerancePct':1.0}
 q['exit']['slReference']='recentLow'; p['patternParamsJson']=json.dumps(q); return p

def opposite_exit(rows, opens, trade, mode, opp):
 """SL/TP 5m first; then closes at the next precomputed opposite 1h signal."""
 start=bisect.bisect_right(opens,trade['open_ms']); cap=trade['open_ms']+720*3600000
 for ot,hi,lo,cl in rows[start:]:
  age=ot+300000-trade['open_ms']
  if age>cap:return cl,'timeout_hard_720'
  if trade['side']==1:
   if hi>=trade['sl']:return trade['sl'],'SL'
   if lo<=trade['tp']:return trade['tp'],'TP'
  else:
   if lo<=trade['sl']:return trade['sl'],'SL'
   if hi>=trade['tp']:return trade['tp'],'TP'
  if ot+300000>=opp:return cl,'opposite_signal'
  if age>=48*3600000 and (mode=='unconditional' or m.pct(trade['side'],trade['entry'],cl)<0):return cl,'timeout_48'
 return rows[-1][3],'nodata'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--smoke',action='store_true');a=p.parse_args()
 with open(CACHE,'rb') as h: st=pickle.load(h)['stream']
 # M1b: raw bucket x[0] is the beginning of the pattern hour; entry occurs
 # at its close and therefore every exit/split begins at x[0] + HOUR.
 ts=[{'open_ms':x[0]+m.HOUR,'symbol':x[1],'entry':x[2],'sl':x[3],'tp':x[4],'side':x[5]} for x in st]
 if a.smoke: ts=ts[:20]
 eng=BacktestEngine(); pc=eng.ma_precompute(opposite_profile(),eng.available_symbols(),m.START,m.END,fidelity=None)
 opposite={s:sorted(fr) for s,fr in pc['ready'].items()}
 con=sqlite3.connect('file:/app/data/binance_vision_clean.db?mode=ro',uri=True); cache={}; raw=defaultdict(lambda:defaultdict(lambda:defaultdict(list))); inv=defaultdict(lambda:defaultdict(lambda:defaultdict(list))); sig=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
 for t in ts:
  rows=m.rows_for(con,t['symbol'],cache); opens=[x[0] for x in rows]; split=b.aligned_split(t['open_ms'])
  for mode,bias in SC:
   key=f'{mode}|tp_bias_{bias:+.0f}'
   for target,trade in ((raw,t),(inv,mirror(t))):
    px,_=b.exit_new(rows,opens,trade,'baseline',mode,bias,None); target[key]['baseline'][split].append(m.pct(trade['side'],trade['entry'],px)-m.BASE_ROUND_TRIP_COST_PCT)
   nxt=next((x for x in opposite.get(t['symbol'],[]) if x>t['open_ms']),None)
   if nxt is not None:
    px,_=opposite_exit(rows,opens,t,mode,nxt); sig[key]['baseline'][split].append(m.pct(t['side'],t['entry'],px)-m.BASE_ROUND_TRIP_COST_PCT)
 con.close()
 if a.smoke: print(json.dumps({'smoke':'ok','signals':len(ts)}));return
 va,da=verdict({s:inv[s]['baseline'] for s in inv},{s:raw[s]['baseline'] for s in raw})
 vb,db=verdict({s:sig[s]['baseline'] for s in sig},{s:raw[s]['baseline'] for s in raw})
 chk=mean(raw['unconditional|tp_bias_-2']['baseline']['OOS'])
 out={'a_inverted_direction':{'pass':va,'details':da},'b_opposite_signal':{'pass':vb,'details':db},'regression':{'expected':b.PRIOR_BASELINE_OOS_UNCOND_M2,'got':chk,'ok':abs(chk-b.PRIOR_BASELINE_OOS_UNCOND_M2)<1e-9},'signals':len(ts),'families_total':30}
 os.makedirs(os.path.dirname(a.output),exist_ok=True);json.dump(out,open(a.output,'w'),indent=2);print(json.dumps({'output':a.output,'a_pass':va,'b_pass':vb,'regression_ok':out['regression']['ok']}))
if __name__=='__main__':main()
