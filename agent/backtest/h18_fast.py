"""H18 SCREEN (fast) — mismo diseño que h18_btc_shock_screen.py pero agregación
barata: media poolada + bootstrap sobre EVENTOS (no concatenando por símbolo).
Escribe scratch_h18_screen.json."""
import os, sqlite3, math, statistics, random, json, bisect, collections
HERE=os.path.dirname(__file__); ROOT=os.path.join(HERE,"..","..")
BV=os.path.join(HERE,"..","data","binance_vision_clean.db")
H=3600_000; Z_WIN=720; BETA_WIN=168; P_SHOCK=0.95; HORIZONS=[1,2,4]; PLACEBO=48; COOLDOWN=6
MIN_DV=50_000; random.seed(20260909)

def load_1h(con,sym,a,b):
    rows=con.execute("SELECT open_time,close,volume FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time BETWEEN ? AND ? ORDER BY open_time",(sym,a,b)).fetchall()
    by={}
    for ot,c,v in rows:
        hk=(ot//H)*H; d=by.setdefault(hk,[None,0.0]); d[0]=c; d[1]+=c*v
    ks=sorted(by); return ks,[by[k][0] for k in ks],[by[k][1] for k in ks]

def ols_beta(x,y):
    n=len(x)
    if n<20: return None
    mx=sum(x)/n; my=sum(y)/n
    sxx=sum((xi-mx)**2 for xi in x)
    if sxx<=0: return None
    return sum((x[i]-mx)*(y[i]-my) for i in range(n))/sxx

def boot(vals,n=3000):
    if len(vals)<30: return None
    N=len(vals); ms=[]
    for _ in range(n):
        s=0.0
        for _ in range(N): s+=vals[random.randrange(N)]
        ms.append(s/N)
    ms.sort()
    return [round(ms[int(.05*n)]*1e4,1), round(statistics.mean(vals)*1e4,1), round(ms[int(.95*n)]*1e4,1)]

con=sqlite3.connect(f"file:{BV}?mode=ro",uri=True)
tmin=con.execute("SELECT MIN(open_time) FROM klines_5m").fetchone()[0]
tmax=con.execute("SELECT MAX(open_time) FROM klines_5m").fetchone()[0]
bt,bc,_=load_1h(con,"BTCUSDT",tmin,tmax)
blr=[None]+[math.log(bc[i]/bc[i-1]) if bc[i-1] else None for i in range(1,len(bc))]
shocks=[]
for i in range(Z_WIN,len(bt)-max(HORIZONS)-PLACEBO):
    hist=[abs(x) for x in blr[i-Z_WIN:i] if x is not None]
    if len(hist)<200 or blr[i] is None: continue
    thr=sorted(hist)[int(P_SHOCK*len(hist))]
    if abs(blr[i])>=thr and abs(blr[i])>0.003: shocks.append((i,bt[i],blr[i]))
btpos={t:j for j,t in enumerate(bt)}
syms=[r[0] for r in con.execute("SELECT symbol FROM klines_5m WHERE interval='5m' GROUP BY symbol HAVING COUNT(*)>40000") if r[0]!="BTCUSDT"]

lag={h:[] for h in HORIZONS}; fol={h:[] for h in HORIZONS}; plac={h:[] for h in HORIZONS}
half={0:{h:[] for h in HORIZONS},1:{h:[] for h in HORIZONS}}
nlag=nfol=0; mid=len(bt)//2
for sym in syms:
    kt,kc,kdv=load_1h(con,sym,tmin,tmax)
    if len(kt)<Z_WIN+max(HORIZONS)+10: continue
    tset={t:j for j,t in enumerate(kt)}
    lr=[None]+[math.log(kc[i]/kc[i-1]) if kc[i-1] else None for i in range(1,len(kc))]
    last=-999
    for (bi,bts,bret) in shocks:
        j=tset.get(bts)
        if j is None or j<BETA_WIN or j+max(HORIZONS)>=len(kt) or j-last<COOLDOWN: continue
        seg=[d for d in kdv[j-24:j] if d]
        if not seg or statistics.median(seg)<MIN_DV: continue
        xs=[];ys=[]
        for k in range(j-BETA_WIN,j):
            bk=btpos.get(kt[k])
            if bk is not None and blr[bk] is not None and lr[k] is not None:
                xs.append(blr[bk]); ys.append(lr[k])
        beta=ols_beta(xs,ys)
        if beta is None or lr[j] is None: continue
        exp=beta*bret
        if abs(exp)<1e-6: continue
        resid=lr[j]-exp; dirn=1 if bret>0 else -1
        is_lag=(resid*dirn<0) and (abs(resid)>=0.5*abs(exp))
        is_fol=abs(resid)<=0.25*abs(exp)
        if not (is_lag or is_fol): continue
        last=j; hbucket=0 if j<mid else 1
        def fwd(bj,h):
            return dirn*math.log(kc[bj+h]/kc[bj]) if (bj+h<len(kc) and kc[bj] and kc[bj+h]) else None
        tgt=lag if is_lag else fol
        if is_lag: nlag+=1
        else: nfol+=1
        for h in HORIZONS:
            v=fwd(j,h)
            if v is not None:
                tgt[h].append(v)
                if is_lag: half[hbucket][h].append(v)
            if is_lag and bi+PLACEBO<len(bt):
                pj=tset.get(bt[bi+PLACEBO])
                if pj is not None:
                    pv=fwd(pj,h)
                    if pv is not None: plac[h].append(pv)

out={"n_btc_shocks":len(shocks),"n_laggard":nlag,"n_follower":nfol,"horizons":{}}
print(f"shocks={len(shocks)} laggard={nlag} follower={nfol}")
print(f"{'h':>3} | {'laggard [P5,mean,P95]bp':>28} | {'follower mean':>14} | {'incr':>7} | {'placebo':>9} | {'half0/half1':>14}")
promising=False
for h in HORIZONS:
    L=boot(lag[h]); F=boot(fol[h]); P=boot(plac[h])
    incr=round(L[1]-F[1],1) if (L and F) else None
    h0=round(statistics.mean(half[0][h])*1e4,1) if len(half[0][h])>=10 else None
    h1=round(statistics.mean(half[1][h])*1e4,1) if len(half[1][h])>=10 else None
    out["horizons"][h]={"laggard":L,"follower":F,"placebo":P,"incr_bp":incr,"half0":h0,"half1":h1}
    print(f"{h:>3} | {str(L):>28} | {str(F[1] if F else None):>14} | {str(incr):>7} | {str(P[1] if P else None):>9} | {h0}/{h1}")
    if L and F and P and L[0]>0 and (incr or 0)>0 and abs(P[1])<0.4*abs(L[1]) and L[1]>=16 and h0 and h1 and (h0>0)==(h1>0):
        promising=True
verdict="PROMISING" if promising else "FAILED"
out["verdict"]=verdict
print("VEREDICTO H18 (screen):",verdict)
json.dump(out,open(os.path.join(ROOT,"scratch_h18_screen.json"),"w"),indent=1)
