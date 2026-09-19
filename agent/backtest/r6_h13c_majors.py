"""H13-C MAJORS SUB-SCREEN — ¿el efecto "precio down + OI up -> bounce 1-4h"
del piloto H13 (que estaba en 45 alts ilíquidos) aparece en BTC/ETH/SOL, donde
un slippage de 2-5 bp es realista?  Datos: los ~7 d de OI de majors del
backfill de Round 4 (klines.db) + klines.db klines 5m.  Muestra CHICA -> screen
de existencia, no concluyente.  Ventanas causales.  Sin grid.
"""
import sqlite3, numpy as np, os
KL=os.path.join(os.path.dirname(__file__),"..","data","klines.db")
H=3600_000; BAR=300_000
LOOKBACK=12   # 1h en barras de 5m
ZWIN=576      # 2 d de barras 5m para z-score causal (muestra chica -> ventana corta)
HOR=[12,24,48,96]  # 1h,2h,4h,8h en barras de 5m
c=sqlite3.connect(f"file:{KL}?mode=ro",uri=True)

def zc(a,win):
    n=len(a);x=np.nan_to_num(a);ok=(~np.isnan(a)).astype(float)
    cs=np.concatenate([[0.],np.cumsum(x)]);cq=np.concatenate([[0.],np.cumsum(x*x)]);ck=np.concatenate([[0.],np.cumsum(ok)])
    i=np.arange(n);lo=i-win;v=lo>=0;lc=np.clip(lo,0,None)
    k=np.where(v,ck[i]-ck[lc],0.)
    m=np.where(k>0,(cs[i]-cs[lc])/np.where(k>0,k,1),np.nan)
    var=np.where(k>0,(cq[i]-cq[lc])/np.where(k>0,k,1)-m*m,np.nan)
    s=np.sqrt(np.clip(var,0,None));o=np.full(n,np.nan);g=v&(k>=win*.5)&(s>0);o[g]=(a[g]-m[g])/s[g];return o

allC=[];allP=[]
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
    oi=c.execute("SELECT timestamp,open_interest FROM open_interest WHERE symbol=? ORDER BY timestamp",(sym,)).fetchall()
    kl=c.execute("SELECT open_time,close FROM klines WHERE symbol=? AND interval='5m' AND is_final=1 ORDER BY open_time",(sym,)).fetchall()
    if len(oi)<ZWIN+200 or len(kl)<ZWIN+200: 
        print(sym,"sin datos suficientes"); continue
    oT=np.array([r[0] for r in oi]);oV=np.array([r[1] for r in oi],float)
    kT=np.array([r[0] for r in kl]);kC=np.array([r[1] for r in kl],float)
    # alinear OI a la grilla de klines por búsqueda (bucket 5m)
    oimap={(t//BAR)*BAR:v for t,v in zip(oT,oV)}
    oarr=np.array([oimap.get((t//BAR)*BAR,np.nan) for t in kT])
    n=len(kC)
    dOI=np.concatenate([np.full(LOOKBACK,np.nan),(oarr[LOOKBACK:]-oarr[:-LOOKBACK])/oarr[:-LOOKBACK]])
    ret=np.concatenate([np.full(LOOKBACK,np.nan),np.log(kC[LOOKBACK:]/kC[:-LOOKBACK])])
    zO=zc(dOI,ZWIN);zR=zc(ret,ZWIN)
    C=(zR<=-1.0)&(zO>=1.0)   # cuadrante C: precio down + OI up
    idx=np.where(C)[0];last=-999
    for t in idx:
        if t<ZWIN or t+max(HOR)+96>=n or t-last<LOOKBACK: continue
        last=t
        for h in HOR:
            allC.append((sym,h,np.log(kC[t+h]/kC[t])))          # bounce esperado -> positivo
            allP.append((sym,h,np.log(kC[t+96+h]/kC[t+96])))    # placebo +8h
    print(f"{sym}: {len(idx)} eventos C")

import collections
for lbl,data in (("REAL",allC),("PLACEBO",allP)):
    print(f"\n{lbl}:")
    for h in HOR:
        v=np.array([x[2] for x in data if x[1]==h])
        if len(v)<10: print(f"  h={h*5:>3}m n={len(v)} (chico)"); continue
        print(f"  h={h*5:>3}m n={len(v):>4}  mean={v.mean()*1e4:>7.1f} bp  median={np.median(v)*1e4:>7.1f}  %pos={100*(v>0).mean():.0f}  after12bp={v.mean()*1e4-12:.1f}")
