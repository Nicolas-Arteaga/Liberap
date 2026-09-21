import argparse,json,sqlite3,os
from datetime import datetime

BASE=300000; CAP=48*3600000
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def reason(x): return x if x in ('SL','TP') else 'TIMEOUT'
def fill_price(side, level, close, next_open, model):
 if model == 'level': return level
 if model == 'close': return close
 if model == 'next_open': return next_open if next_open is not None else close
 if model == 'worst': return max(level,close) if side=='short' else min(level,close)
 if model == 'best': return min(level,close) if side=='short' else max(level,close)
 raise ValueError('unknown fill model: '+model)
def run(conn,x,tp_first=False,timeout_h=48,fill='level',conditional_timeout=False,hard_timeout_h=720):
 o=ms(x['open_utc']); side='short' if x['sl']>x['entry'] else 'long'
 cap=timeout_h*3600000; hard_cap=hard_timeout_h*3600000 if conditional_timeout else cap
 rows=conn.execute("SELECT open_time,open,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<=? ORDER BY open_time",(x['sym'],o,o+hard_cap+BASE)).fetchall()
 if not rows:return None
 for i,(t,op,h,l,c) in enumerate(rows):
  age=t+BASE-o
  hits=[('TP',x['tp']) if (l<=x['tp'] if side=='short' else h>=x['tp']) else None,('SL',x['sl']) if (h>=x['sl'] if side=='short' else l<=x['sl']) else None]
  hits=[v for v in hits if v]
  if hits:
   r,level=(hits[0] if tp_first else (hits[-1] if len(hits)==2 else hits[0]))
   next_open=rows[i+1][1] if i+1<len(rows) else None
   return r,t+BASE,fill_price(side,level,c,next_open,fill)
  if age>=cap:
   pnl=((x['entry']-c)/x['entry'] if side=='short' else (c-x['entry'])/x['entry'])
   if not conditional_timeout or pnl<0 or age>=hard_cap:return 'TIMEOUT',t+BASE,c
 return 'NODATA',rows[-1][0]+BASE,rows[-1][4]
def main():
 p=argparse.ArgumentParser();p.add_argument('--scratch',required=True);p.add_argument('--output',required=True);p.add_argument('--db',default='/app/data/binance_vision_clean.db');p.add_argument('--smoke',action='store_true');p.add_argument('--tp-first',action='store_true');p.add_argument('--timeout-hours',type=int,default=48);p.add_argument('--fill',choices=['level','close','next_open','worst','best'],default='level');p.add_argument('--conditional-timeout',action='store_true');p.add_argument('--hard-timeout-hours',type=int,default=720);a=p.parse_args()
 src=json.load(open(a.scratch)); src=src[:1] if a.smoke else src; conn=sqlite3.connect(f'file:{a.db}?mode=ro',uri=True); out=[]
 for x in src:
  r=run(conn,x,a.tp_first,a.timeout_hours,a.fill,a.conditional_timeout,a.hard_timeout_hours); side='short' if x['sl']>x['entry'] else 'long'
  if not r:out.append({'symbol':x['sym'],'missing':True});continue
  rsn,ct,px=r; realret=((x['entry']-x['exit_px'])/x['entry']*100 if side=='short' else (x['exit_px']-x['entry'])/x['entry']*100); replayret=((x['entry']-px)/x['entry']*100 if side=='short' else (px-x['entry'])/x['entry']*100)
  out.append({'symbol':x['sym'],'reason_real':reason(x.get('real_outcome')),'reason_replay':rsn,'reason_match':reason(x.get('real_outcome'))==rsn,'close_delta_min':(ct-ms(x['close_utc']))/60000,'return_real_pct':realret,'return_replay_pct':replayret,'return_delta_pp':replayret-realret})
 conn.close();valid=[x for x in out if not x.get('missing')]; payload={'tolerance_pp':.25,'intrabar_priority':'TP_first' if a.tp_first else 'SL_first','timeout_hours':a.timeout_hours,'conditional_timeout':a.conditional_timeout,'hard_timeout_hours':a.hard_timeout_hours if a.conditional_timeout else None,'fill_model':a.fill,'total':len(src),'valid':len(valid),'reason_matches':sum(x['reason_match'] for x in valid),'return_within_tolerance':sum(abs(x['return_delta_pp'])<=.25 for x in valid),'trades':out};os.makedirs(os.path.dirname(a.output),exist_ok=True);json.dump(payload,open(a.output,'w'),indent=2);print(json.dumps({k:payload[k] for k in payload if k!='trades'}))
if __name__=='__main__':main()
