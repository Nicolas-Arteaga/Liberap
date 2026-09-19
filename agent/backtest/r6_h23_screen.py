"""H23 SCREEN — PERP-TAKER / SPOT-PRICE DIVERGENCE.
Mecanismo: perp takers agresivos en una dirección + spot NO confirma =
especulación apalancada sin respaldo spot -> revierte cuando el funding pega.
Participante obligado: longs (o shorts) apalancados de perp pagando funding
sin demanda spot que los sostenga.
Catalizador: sobre W=4 barras (1h), z(perp_taker_buy_frac)>=+1 AND z(perp_ret)>=+1
             AND spot_ret_W < 0.3*perp_ret_W  -> "leveraged-long sin spot".
             Simetrico para leveraged-short.
Prediccion: perp price revierte (long -> baja ; short -> sube). Entrada open[t+1].
Horizontes 15/30/60 min. Placebo +24h. Control: spot SI confirma (>=0.7*perp).
Costo asumido 16 bp RT (fee) + slip. Ventana de taker BACKWARD (causal).
"""
import os, sqlite3, json, numpy as np
HERE=os.path.dirname(__file__); ROOT=os.path.join(HERE,"..","..")
BV=os.path.join(HERE,"..","data","binance_vision_clean.db")
TOP_N=150; ROLL=2880; W=4; PLACEBO=96; HOR=[1,2,4]
FEE_RT=8.0; SLIP=[0.0,2.0,5.0]; MARGIN=150.0
rng=np.random.default_rng(20260909)

def zc(a,win):
    n=len(a); x=np.nan_to_num(a); ok=(~np.isnan(a)).astype(float)
    cs=np.concatenate([[0.0],np.cumsum(x)]); cq=np.concatenate([[0.0],np.cumsum(x*x)]); ck=np.concatenate([[0.0],np.cumsum(ok)])
    i=np.arange(n); lo=i-win; v=lo>=0; lc=np.clip(lo,0,None)
    k=np.where(v,ck[i]-ck[lc],0.0)
    m=np.where(k>0,(cs[i]-cs[lc])/np.where(k>0,k,1),np.nan)
    var=np.where(k>0,(cq[i]-cq[lc])/np.where(k>0,k,1)-m*m,np.nan)
    s=np.sqrt(np.clip(var,0,None)); out=np.full(n,np.nan); g=v&(k>=win*0.5)&(s>0)
    out[g]=(a[g]-m[g])/s[g]; return out

con=sqlite3.connect(f"file:{BV}?mode=ro",uri=True)
liq=[s for (s,) in con.execute(
 "SELECT symbol FROM taker_flow t WHERE interval='15m' GROUP BY symbol HAVING COUNT(*)>? "
 "ORDER BY (SELECT AVG(quote_volume) FROM taker_flow t2 WHERE t2.symbol=t.symbol AND t2.interval='15m') DESC LIMIT ?",
 (ROLL+400,TOP_N))]
tmin=con.execute("SELECT MIN(open_time) FROM klines_clean WHERE interval='15m'").fetchone()[0]
tmax=con.execute("SELECT MAX(open_time) FROM klines_clean WHERE interval='15m'").fetchone()[0]
third=(tmax-tmin)/3
ev=[]
nsym=0
for sym in liq:
    r=con.execute(
     "SELECT k.open_time,k.open,k.close,t.quote_volume,t.taker_buy_quote,s.close "
     "FROM klines_clean k JOIN taker_flow t ON k.symbol=t.symbol AND k.interval=t.interval AND k.open_time=t.open_time "
     "JOIN spot_klines s ON s.symbol=k.symbol AND s.interval=k.interval AND s.open_time=k.open_time "
     "WHERE k.symbol=? AND k.interval='15m' ORDER BY k.open_time",(sym,)).fetchall()
    if len(r)<ROLL+400: continue
    nsym+=1
    a=np.array(r,float); tms,o,pc,qv,tbq,sc=a[:,0],a[:,1],a[:,2],a[:,3],a[:,4],a[:,5]
    n=len(pc)
    pret=np.concatenate([np.full(W,np.nan),np.log(pc[W:]/pc[:-W])])
    sret=np.concatenate([np.full(W,np.nan),np.log(sc[W:]/sc[:-W])])
    qvW=np.convolve(np.nan_to_num(qv),np.ones(W))[:n]
    tbqW=np.convolve(np.nan_to_num(tbq),np.ones(W))[:n]
    tbrW=np.divide(tbqW,qvW,out=np.full(n,np.nan),where=qvW>0)
    zt=zc(tbrW,ROLL); zp=zc(pret,ROLL)
    lev_long = (zt>=1.0)&(zp>=1.0)&(sret < 0.3*pret)
    lev_short= (zt<=-1.0)&(zp<=-1.0)&(sret > 0.3*pret)
    ctrl_long= (zp>=1.0)&(sret>=0.7*pret)
    ctrl_short=(zp<=-1.0)&(sret<=0.7*pret)
    for kind,mask,sgn in (("lev_long",lev_long,-1),("lev_short",lev_short,1),
                          ("ctrl_long",ctrl_long,-1),("ctrl_short",ctrl_short,1)):
        last=-999
        for t in np.where(mask)[0]:
            if t<ROLL or t+1+max(HOR)+PLACEBO>=n or t-last<W: continue
            last=t; e=t+1; seg=int((tms[t]-tms[0])//third) if third>0 else 0
            rh=[sgn*np.log(o[e+h]/o[e]) for h in HOR]
            ph=[sgn*np.log(o[e+PLACEBO+h]/o[e+PLACEBO]) for h in HOR]
            ev.append((sym,kind,seg,rh,ph))
print(f"symbols con spot+perp+taker: {nsym} · eventos {len(ev)}")
months=7.6
def st(rows,hi):
    if len(rows)<40: return {"n":len(rows)}
    by={}
    for s,seg,v in rows: by.setdefault(s,[]).append(v)
    us=list(by); ss=np.array([np.sum(by[s]) for s in us]); sc_=np.array([len(by[s]) for s in us],float)
    allv=np.concatenate([np.asarray(by[s]) for s in us])
    idx=np.arange(len(us))
    bs=np.sort(np.array([ss[p].sum()/sc_[p].sum() for p in (rng.choice(idx,len(idx)) for _ in range(2000))]))*1e4
    seg={k:(round(float(np.mean([v for s,g,v in rows if g==k]))*1e4,1) if sum(1 for s,g,v in rows if g==k)>=20 else None) for k in (0,1,2)}
    return dict(n=len(allv),mean_bp=round(float(allv.mean()*1e4),1),ci_bp=[round(float(bs[100]),1),round(float(bs[1899]),1)],
               symPos=round(float((ss>0).mean()),2),conc=round(float(np.sort(ss)[::-1][:5].clip(0).sum()/(ss.clip(0).sum() or 1)),2),thirds=seg)
out={"n_sym":nsym,"n_events":len(ev),"sides":{}}
for kind in ("lev_long","lev_short"):
    base=[e for e in ev if e[1]==kind]; ctrl=[e for e in ev if e[1]=="ctrl_"+kind.split("_")[1]]
    print(f"\n=== {kind}  n={len(base)} (ctrl {len(ctrl)}) ===")
    blk={"n":len(base),"h":{}}
    for hi,h in enumerate(HOR):
        if len(base)<40:
            print(f"  n<40, skip h={h}"); continue
        R=st([(s,g,rh[hi]) for s,k,g,rh,ph in base],hi)
        P=st([(s,g,ph[hi]) for s,k,g,rh,ph in base],hi)
        C=st([(s,g,rh[hi]) for s,k,g,rh,ph in ctrl],hi)
        after={sl:round(R["mean_bp"]-(FEE_RT+2*sl),1) for sl in SLIP}
        blk["h"][h]={"real":R,"placebo":P.get("mean_bp"),"ctrl":C.get("mean_bp"),"after":after}
        print(f"  h={h*15:>3}m real={R['mean_bp']:>6}bp CI{R['ci_bp']} placebo={P.get('mean_bp')} ctrl={C.get('mean_bp')} "
              f"thirds={R['thirds']} symPos={R['symPos']} conc={R['conc']} after0/2/5={after[0.0]}/{after[2.0]}/{after[5.0]}")
    out["sides"][kind]=blk
json.dump(out,open(os.path.join(ROOT,"scratch_r6_h23.json"),"w"),indent=1,default=str)
# veredicto
prom=False
for kind in ("lev_long","lev_short"):
    for h in HOR:
        R=out["sides"][kind]["h"][h]["real"]; ci=R["ci_bp"]; a2=out["sides"][kind]["h"][h]["after"][2.0]
        p=out["sides"][kind]["h"][h]["placebo"] or 0
        if abs(R["mean_bp"])>=20 and ((ci[0]>0 and ci[1]>0) or (ci[0]<0 and ci[1]<0)) and abs(a2)>=6 \
           and R["symPos"]>=0.55 and R["conc"]<=0.6 and abs(p)<0.4*abs(R["mean_bp"]):
            prom=True
print("\nVEREDICTO H23:", "PROMISING" if prom else "FAILED")
