"""M1: auditoría simple y explicable de MA3, sólo lectura."""
from __future__ import annotations
import json, os, sys, random, datetime
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import lab_core as C
import lab_integrity as I
from lab_adapters import get_adapter

STRATEGY=os.environ.get('LAB_AUDIT_STRATEGY','ma3')
OUT=os.environ.get('LAB_AUDIT_OUT',f'/app/backtest/lab_artifacts/m1-{STRATEGY}-20260926')
def mean(x): return sum(x)/len(x) if x else None
def pct(n,d): return 100*n/d if d else None
def fmt(x): return 'n/a' if x is None else f'{x:.2f}'
WHY = {
 'ENTRADA':'El intervalo incluye valores negativos y positivos: la señal no demuestra por sí sola que anticipe el movimiento.',
 'COSTOS':'La diferencia entre bruto y neto muestra cuánto margen pierde la estrategia antes de poder ejecutar un trade real.',
 'PAYOFF':'La comparación con el equilibrio muestra si el tamaño de ganadores compensa la frecuencia de pérdidas.',
 'SALIDA':'Una ganancia flotante que vuelve a pérdida no paga el resultado final; aquí se cuantifica ese desperdicio.',
 'SL':'El contrafactual separa un stop protector de uno que corta ganadores que habrían alcanzado el objetivo.',
 'TIMEOUT':'El retorno de las posiciones que expiran indica si el tiempo está cerrando riesgo útil o capital estancado.'}

def headline(net, gross, cost, main, severity):
 if net >= 0:
  return f'La estrategia GANA {fmt(net)} % neto por trade, pero es frágil: el edge bruto ({fmt(gross)} %) apenas supera el costo ({fmt(cost)} %). ' + (f'El daño más alto medido es {main} ({severity[main]}/100).' if severity[main] >= 20 else 'Ninguna causa domina con el umbral de severidad actual.')
 return f'La estrategia PIERDE {fmt(net)} % neto por trade. La causa de mayor severidad medida es {main} ({severity[main]}/100).'

def severity_scores(fwd24, gross, cost, breakeven, win_rate, gave_back_pct, sl_cf_pct, timeout_pct, timeout_mean):
 """Escala fija 0..100; M3 considera grave un puntaje desde 20."""
 cost_deficit=max(0.0, cost-(gross or 0.0))
 return {'ENTRADA':min(100,round(max(0,-(fwd24 or 0))*20)),
         'COSTOS':min(100,round(100*cost_deficit/max(cost,1e-12))),
         'PAYOFF':min(100,round(max(0,(breakeven or 0)-(win_rate or 0)))),
         'SALIDA':round(gave_back_pct or 0), 'SL':round(sl_cf_pct or 0),
         'TIMEOUT':min(100,round((timeout_pct or 0)*max(0,-(timeout_mean or 0))))}
def write_progress(status, processed=0, total=0, **extra):
 payload={'id':f'm1-{STRATEGY}-20260926','status':status,'processed':processed,'total':total,
          'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra}
 os.makedirs(OUT,exist_ok=True)
 with open(OUT+'/progress.json','w',encoding='utf8') as f: json.dump(payload,f,indent=2)

def day_block_ci(rows, horizon, rounds=1000):
 by_day=defaultdict(list)
 for row in rows:
  value=row['fwd'][horizon]
  if value is not None: by_day[row['day']].append(value)
 days=sorted(by_day)
 if not days: return {'mean':None,'lo':None,'hi':None,'n_days':0,'n':0}
 rng=random.Random(20260926+horizon); samples=[]
 for _ in range(rounds):
  selected=[days[rng.randrange(len(days))] for _ in days]
  values=[v for day in selected for v in by_day[day]]
  samples.append(mean(values))
 samples.sort()
 return {'mean':mean([v for values in by_day.values() for v in values]),
         'lo':samples[int(.025*(rounds-1))], 'hi':samples[int(.975*(rounds-1))],
         'n_days':len(days),'n':sum(map(len,by_day.values()))}

def main():
 a=get_adapter(STRATEGY); entries=a.entries(); by=defaultdict(list)
 for t in entries: by[t['symbol']].append(t)
 rows=[]; integrity=[]; write_progress('running',0,len(entries),started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 for symbol_index,(sym,ts) in enumerate(by.items(),1):
  kl=a.candles(sym); op=[r[0] for r in kl]; hs=C.hourly_series(kl); hst=[x[0] for x in hs]
  for t in ts:
   audit=C.audit_trade(kl,op,a.bar_ms,t,C.atr_before(hs,hst,t['open_ms']),a.split_of(t['open_ms']),a.cost_pct)
   rows.append(audit); integrity.append(I.check_trade(a,t,kl,audit))
  if symbol_index % 25 == 0 or symbol_index == len(by): write_progress('running',len(rows),len(entries),symbols_done=symbol_index,symbols_total=len(by))
 wins=[r for r in rows if r['ret']>0]; losses=[r for r in rows if r['ret']<=0]
 fwd={h:day_block_ci(rows,h) for h in C.FWD_HOURS}
 integrity_report=I.summarize(a,integrity,rows)
 gross=mean([r['ret']+a.cost_pct for r in rows]); net=mean([r['ret'] for r in rows])
 wr=pct(len(wins),len(rows)); aw=mean([r['ret'] for r in wins]); al=abs(mean([r['ret'] for r in losses])); breakeven=100*al/(al+aw) if aw and al else None
 reached=[r for r in rows if r['mfe']>=2]; gave=sum(r['ret']<0 for r in reached)
 sl=[r for r in rows if r['reason']=='SL']; slcf=sum(bool(r['cf_sl_reaches_tp']) for r in sl)
 timeout=[r for r in rows if r['reason'].startswith('timeout')]
 reasons={k:{'n':len(v),'pct':pct(len(v),len(rows)),'mean_return':mean([x['ret'] for x in v])} for k,v in ((k,[r for r in rows if r['reason']==k]) for k in sorted(set(r['reason'] for r in rows)))}
 timeout_mean=mean([r['ret'] for r in timeout])
 # Frecuencia sola no es daño: una causa suma severidad sólo si deteriora retorno.
 severity=severity_scores(fwd[24]['mean'],gross,a.cost_pct,breakeven,wr,pct(gave,len(reached)),pct(slcf,len(sl)),pct(len(timeout),len(rows)),timeout_mean)
 main_area=max(severity,key=severity.get)
 result={'valid':integrity_report['valid'],'integrity':integrity_report,'n':len(rows),'forward_return_pct_day_block_ci':fwd,'gross_edge_pct':gross,'cost_pct':a.cost_pct,'net_expectancy_pct':net,'win_rate_pct':wr,'break_even_win_rate_pct':breakeven,'avg_win_pct':aw,'avg_loss_pct':al,'reached_2pct_n':len(reached),'reached_2pct_ended_loss_pct':pct(gave,len(reached)),'sl_n':len(sl),'sl_cf_reaches_tp_pct':pct(slcf,len(sl)),'timeout_n':len(timeout),'timeout_pct':pct(len(timeout),len(rows)),'timeout_mean_return_pct':timeout_mean,'reasons':reasons,'severity':severity,'severity_formula':'ENTRADA=max(0,-media_24h*20); COSTOS=max(0,-edge_bruto*20); PAYOFF=max(0,win_equilibrio-win_real); SALIDA=porcentaje que llegó a +2% y terminó en pérdida; SL=porcentaje contrafactual que habría llegado al TP; TIMEOUT=porcentaje_timeout*max(0,-retorno_timeout). Frecuencia sin daño no suma. Todo limitado a 0..100.','main_area':main_area,'fidelity':a.fidelity_result}
 label=a.definition.display_name
 lines=[f'# Auditoría {label} — {len(rows)} trades','## Chequeos de integridad']
 lines += [f'- {name}: {data["status"]}.' for name,data in integrity_report['checks'].items()]
 if not integrity_report['valid']:
  lines += ['','**INFORME INVÁLIDO: falló un chequeo de integridad; no se publican veredictos.**']
 else:
  lines += ['## TITULAR',headline(net,gross,a.cost_pct,main_area,severity), '## Resultado simple',f'- Win rate {fmt(wr)} %; equilibrio {fmt(breakeven)} %; ganancia media {fmt(aw)} % y pérdida media {fmt(al)} %.','## Hallazgos']
 facts={'ENTRADA':f'Retorno medio 1/4/12/24/48h con IC bootstrap por día: '+', '.join(f'{h}h={fmt(fwd[h]["mean"])}% [{fmt(fwd[h]["lo"])}, {fmt(fwd[h]["hi"])}], n={fwd[h]["n"]}, días={fwd[h]["n_days"]}' for h in C.FWD_HOURS),'COSTOS':f'Bruto {fmt(gross)}% y costo {a.cost_pct:.2f}%','PAYOFF':f'Win rate {fmt(wr)}% vs equilibrio {fmt(breakeven)}%','SALIDA':f'{len(reached)} llegaron a +2%; {fmt(pct(gave,len(reached)))}% terminaron perdiendo','SL':f'{len(sl)} SL; {fmt(pct(slcf,len(sl)))}% habría llegado a TP sin SL','TIMEOUT':f'{len(timeout)} timeout ({fmt(pct(len(timeout),len(rows)))}%), retorno {fmt(mean([r["ret"] for r in timeout]))}%'}
 if integrity_report['valid']:
  for k in severity: lines += [f'### [{k}] — severidad {severity[k]}/100',f'QUÉ PASA: {facts[k]}.',f'POR QUÉ IMPORTA: {WHY[k]}',f'EVIDENCIA: n={len(rows)}, `result.json`.', 'CONFIANZA: BAJA; no son selecciones reales de producción.', 'Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.']
  lines += ['## Motivos de salida','| Motivo | N | % | Retorno medio |','|---|---:|---:|---:|']+[f'| {k} | {v["n"]} | {fmt(v["pct"])} | {fmt(v["mean_return"])} |' for k,v in reasons.items()]+['## Qué no se pudo evaluar', a.fidelity_note, '## Qué haría alguien no técnico con esto','- No cambiaría la estrategia en producción a partir de este informe.','- Vigilaría las ganancias que superan +2 % porque muchas terminan en pérdida.','- Esperaría la validación contra el ledger antes de modificar la salida.']
 os.makedirs(OUT,exist_ok=True)
 with open(OUT+'/result.json','w',encoding='utf8') as f: json.dump(result,f,indent=2)
 with open(OUT+'/manual_inputs.json','w',encoding='utf8') as f: json.dump({'returns_pct':[r['ret'] for r in rows]},f)
 open(OUT+'/informe.md','w',encoding='utf8').write('\n'.join(lines))
 write_progress('completed',len(rows),len(entries),finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),result='result.json')
 print(json.dumps({'out':OUT,'n':len(rows),'main':main_area}))
if __name__=='__main__':main()
