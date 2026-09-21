import argparse,json,sqlite3,os
from datetime import datetime

BASE=300000; CAP=48*3600000
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def reason(x): return x if x in ('SL','TP') else 'TIMEOUT'
def run(conn,x,tp_first=False,timeout_h=48):
 o=ms(x['open_utc']); side='short' if x['sl']>x['entry'] else 'long'
 cap=timeout_h*3600000; rows=conn.execute("SELECT open_time,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<=? ORDER BY open_time",(x['sym'],o,o+cap+BASE)).fetchall()
 if not rows:return None
 for t,h,l,c in rows:
  age=t+BASE-o
  hits=[('TP',x['tp']) if (l<=x['tp'] if side=='short' else h>=x['tp']) else None,('SL',x['sl']) if (h>=x['sl'] if side=='short' else l<=x['sl']) else None]
  hits=[v for v in hits if v]
  if hits:
   r,p=(hits[0] if tp_first else (hits[-1] if len(hits)==2 else hits[0])); return r,t+BASE,p
  if age>=cap:return 'TIMEOUT',t+BASE,c
 return 'NODATA',rows[-1][0]+BASE,rows[-1][3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--scratch',required=True);p.add_argument('--output',required=True);p.add_argument('--db',default='/app/data/binance_vision_clean.db');p.add_argument('--smoke',action='store_true');p.add_argument('--tp-first',action='store_true');p.add_argument('--timeout-hours',type=int,default=48);a=p.parse_args()
 src=json.load(open(a.scratch)); src=src[:1] if a.smoke else src; conn=sqlite3.connect(f'file:{a.db}?mode=ro',uri=True); out=[]
 for x in src:
  r=run(conn,x,a.tp_first,a.timeout_hours); side='short' if x['sl']>x['entry'] else 'long'
  if not r:out.append({'symbol':x['sym'],'missing':True});continue
  rsn,ct,px=r; realret=((x['entry']-x['exit_px'])/x['entry']*100 if side=='short' else (x['exit_px']-x['entry'])/x['entry']*100); replayret=((x['entry']-px)/x['entry']*100 if side=='short' else (px-x['entry'])/x['entry']*100)
  out.append({'symbol':x['sym'],'reason_real':reason(x.get('real_outcome')),'reason_replay':rsn,'reason_match':reason(x.get('real_outcome'))==rsn,'close_delta_min':(ct-ms(x['close_utc']))/60000,'return_real_pct':realret,'return_replay_pct':replayret,'return_delta_pp':replayret-realret})
 conn.close();valid=[x for x in out if not x.get('missing')]; payload={'tolerance_pp':.25,'intrabar_priority':'TP_first' if a.tp_first else 'SL_first','timeout_hours':a.timeout_hours,'total':len(src),'valid':len(valid),'reason_matches':sum(x['reason_match'] for x in valid),'return_within_tolerance':sum(abs(x['return_delta_pp'])<=.25 for x in valid),'trades':out};os.makedirs(os.path.dirname(a.output),exist_ok=True);json.dump(payload,open(a.output,'w'),indent=2);print(json.dumps({k:payload[k] for k in payload if k!='trades'}))
if __name__=='__main__':main()
