"""Fase 2: trayectoria por vida real y horizontes fijos; sólo velas, sin PnL USD."""
import argparse, json, sqlite3
from datetime import datetime

BASE=300000; H=(48,96,208)
def ms(x): return int(datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()*1000)
def pct(e,p,side): return ((e-p)/e if side=='short' else (p-e)/e)*100
def main():
 p=argparse.ArgumentParser();p.add_argument('--scratch',required=True);p.add_argument('--output',required=True);p.add_argument('--db',default='/app/data/binance_vision_clean.db');p.add_argument('--smoke',action='store_true');a=p.parse_args()
 src=json.load(open(a.scratch)); src=src[:1] if a.smoke else src; c=sqlite3.connect(f'file:{a.db}?mode=ro',uri=True); out=[]; missing=[]
 for x in src:
  side='short' if x['sl']>x['entry'] else 'long'; opened=ms(x['open_utc']); closed=ms(x['close_utc']); end=max(closed,opened+208*3600000)
  rs=c.execute("SELECT open_time,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time>=? AND open_time<=? ORDER BY open_time",(x['sym'],opened,end+BASE)).fetchall()
  if not rs: missing.append(x['sym']);continue
  wins={'life':closed-opened,**{str(h):h*3600000 for h in H}}; windows={}
  for name,dur in wins.items():
   rows=[r for r in rs if r[0]+BASE-opened<=dur]
   if not rows: windows[name]=None;continue
   fav=[(r[0]+BASE-opened,pct(x['entry'],r[2] if side=='short' else r[1],side)) for r in rows]; adv=[pct(x['entry'],r[1] if side=='short' else r[2],side) for r in rows]
   t,mfe=max(fav,key=lambda z:z[1]); final=pct(x['entry'],rows[-1][3],side); give=mfe-final; cens=t>=.9*dur
   windows[name]={'window_hours':dur/3600000,'mfe_pct':mfe,'mae_pct':min(adv),'giveback_pct':give,'time_to_mfe_hours':t/3600000,'return_pct':final,'mfe_censored_last_10pct':cens,'mfe_ge_2':mfe>=2,'mfe_ge_5':mfe>=5,'mfe_ge_10':mfe>=10,'giveback_ge_50pct_mfe':mfe>0 and give>=.5*mfe}
  out.append({'strategy':'MA Slope Caso 3','symbol':x['sym'],'side':side,'opened_at':x['open_utc'],'closed_at':x['close_utc'],'windows':windows})
 c.close(); summary={}
 for name in ['life','48','96','208']:
  vals=[x['windows'][name] for x in out if x['windows'].get(name)]
  counts={}
  for t in (2,5,10):
   eligible=[v for v in vals if v['mfe_pct']>=t]
   counts[f'mfe_ge_{t}_pct']=len(eligible)
   counts[f'giveback_ge_50pct_mfe_among_ge_{t}_pct']=sum(v['giveback_ge_50pct_mfe'] for v in eligible)
  counts['mfe_censored_last_10pct']=sum(v['mfe_censored_last_10pct'] for v in vals)
  counts['n']=len(vals)
  summary[name]=counts
 json.dump({'method':'5m candles only; no exit model or PnL USD','n_input':len(src),'n_with_klines':len(out),'missing_symbols':missing,'summary':summary,'trades':out},open(a.output,'w'),indent=2)
 print(json.dumps({'n_input':len(src),'n_with_klines':len(out),'summary':summary}))
if __name__=='__main__':main()
