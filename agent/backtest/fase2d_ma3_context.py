"""Preregistered Fase 2d context surface on the frozen MA3 stream.

Diagnostic-only: 15 fixed views; no production selection or profile change.
"""
from __future__ import annotations

import argparse, bisect, json, os, pickle, random, sqlite3, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

import fase2_ma3_broad_matrix as m
import fase2b_ma3_exit_variants as b

CACHE_DEFAULT = "/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl"
SCENARIOS = b.SCENARIOS
EXPECTED = b.PRIOR_BASELINE_OOS_UNCOND_M2
SPLITS = ("TRAIN", "VALIDATION", "OOS")


def day(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()


def bootstrap_delta(rows, mask, rounds=1000, seed=20260925):
    """95% CI of mean(view)-mean(complement), resampling UTC days."""
    byday = defaultdict(list)
    for row, take in zip(rows, mask): byday[row["day"]].append((row["net"], take))
    days = sorted(byday)
    if not days or not any(mask) or all(mask): return None, len(days)
    rng, samples = random.Random(seed), []
    for _ in range(rounds):
        picked = [rng.choice(days) for _ in days]
        yes, no = [], []
        for d in picked:
            for val, take in byday[d]: (yes if take else no).append(val)
        if yes and no: samples.append(sum(yes)/len(yes)-sum(no)/len(no))
    samples.sort()
    return [samples[int(.025*(len(samples)-1))], samples[int(.975*(len(samples)-1))]], len(days)


def summary(rows, predicate):
    picked = [r for r in rows if predicate(r)]
    comp = [r for r in rows if not predicate(r)]
    values, other = [r["net"] for r in picked], [r["net"] for r in comp]
    delta = (sum(values)/len(values)-sum(other)/len(other)) if values and other else None
    ci, days = bootstrap_delta(rows, [predicate(r) for r in rows])
    return {"n_signals":len(picked), "n_days":len({r['day'] for r in picked}),
            "mean_net_return_pct":sum(values)/len(values) if values else None,
            "median_net_return_pct":statistics.median(values) if values else None,
            "delta_vs_complement_pp":delta, "delta_ci95_day_block_pp":ci,
            "bootstrap_effective_days":days}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",required=True); ap.add_argument("--cache",default=CACHE_DEFAULT); ap.add_argument("--smoke",action="store_true"); ap.add_argument("--progress")
    args=ap.parse_args()
    if args.progress:
        os.makedirs(os.path.dirname(args.progress), exist_ok=True)
    with open(args.cache,"rb") as h: stream=pickle.load(h)["stream"]
    trades=[{"open_ms":x[0],"symbol":x[1],"entry":x[2],"sl":x[3],"tp":x[4],"side":x[5]} for x in stream]
    if args.smoke: trades=trades[:2]
    conn=sqlite3.connect("file:/app/data/binance_vision_clean.db?mode=ro",uri=True); cache={}; rows=[]
    btc=m.rows_for(conn,"BTCUSDT",{}); bo=[x[0] for x in btc]
    for number, trade in enumerate(trades, 1):
        sym=trade["symbol"]
        if sym not in cache:
            kl=m.rows_for(conn,sym,{}); cache[sym]=(kl,[x[0] for x in kl])
        kl,opens=cache[sym]
        # Features are causal: closed BTC/symbol 5m candles before the entry.
        i=bisect.bisect_left(opens,trade["open_ms"]); prior=kl[max(0,i-288):i]
        if len(prior)<288: continue
        bi=bisect.bisect_left(bo,trade["open_ms"]); bp=btc[max(0,bi-288):bi]
        if len(bp)<288: continue
        btc24=(bp[-1][3]/bp[0][3]-1)*100
        rets=[(prior[j][3]/prior[j-1][3]-1) for j in range(1,len(prior))]
        vol=statistics.pstdev(rets)*100
        base={"split":m.split_for(trade["open_ms"]),"day":day(trade["open_ms"]),"symbol":sym,
              "hour_bucket":f"{datetime.fromtimestamp(trade['open_ms']/1000,tz=timezone.utc).hour//6*6:02d}-{datetime.fromtimestamp(trade['open_ms']/1000,tz=timezone.utc).hour//6*6+5:02d}",
              "btc_regime":"bear" if btc24 < -2 else "bull" if btc24 > 2 else "flat","vol":vol}
        for mode,bias in SCENARIOS:
            px,_=b.exit_new(kl,opens,trade,"baseline",mode,bias,None)
            rows.append({**base,"scenario":f"{mode}|tp_bias_{bias:+.0f}","net":m.pct(trade['side'],trade['entry'],px)-m.BASE_ROUND_TRIP_COST_PCT})
        if args.progress and number % 100 == 0:
            with open(args.progress,"w",encoding="utf8") as h: json.dump({"status":"running","processed":number,"total":len(trades)},h)
    conn.close()
    if args.smoke:
        print(json.dumps({"smoke":"ok","signals":len(trades),"scored_rows":len(rows)})); return
    train=[r for r in rows if r["split"]=="TRAIN" and r["scenario"]=="unconditional|tp_bias_-2"]
    cuts=statistics.quantiles([r["vol"] for r in train],n=3,method="inclusive")
    top=[s for s,_ in Counter(r["symbol"] for r in train).most_common(5)]
    views=[("hour_"+h,lambda r,h=h:r["hour_bucket"]==h) for h in ("00-05","06-11","12-17","18-23")]
    views += [("btc_"+x,lambda r,x=x:r["btc_regime"]==x) for x in ("bear","flat","bull")]
    views += [("vol_low",lambda r:r["vol"]<=cuts[0]),("vol_mid",lambda r:cuts[0]<r["vol"]<=cuts[1]),("vol_high",lambda r:r["vol"]>cuts[1])]
    views += [("symbol_"+s,lambda r,s=s:r["symbol"]==s) for s in top]
    surface={}
    for name,pred in views:
        surface[name]={}
        for scenario in sorted({r["scenario"] for r in rows}):
            part=[r for r in rows if r["scenario"]==scenario]
            surface[name][scenario]={sp:summary([r for r in part if r["split"]==sp],pred) for sp in SPLITS}
    candidates=[]
    for name in surface:
        ok=True
        for scenario in surface[name].values():
            tr,va=scenario["TRAIN"],scenario["VALIDATION"]
            ok &= tr["n_signals"]>=50 and va["n_signals"]>=25 and (tr["mean_net_return_pct"] or 0)>0 and (va["mean_net_return_pct"] or 0)>0 and (tr["delta_vs_complement_pp"] or 0)>0 and (va["delta_vs_complement_pp"] or 0)>0
        if ok:candidates.append(name)
    base=[r["net"] for r in rows if r["scenario"]=="unconditional|tp_bias_-2" and r["split"]=="OOS"]
    out={"label":"HIPOTESIS; raw population, not production selection","families_tested":28,"views_fixed":len(views),"top_symbols_from_train":top,"vol_train_cutpoints":cuts,"candidates_before_oos":candidates,"surface":surface,"regression":{"expected":EXPECTED,"got":sum(base)/len(base),"ok":abs(sum(base)/len(base)-EXPECTED)<1e-9},"holdout2":"not read"}
    os.makedirs(os.path.dirname(args.output),exist_ok=True)
    with open(args.output,"w",encoding="utf8") as h:json.dump(out,h,ensure_ascii=False,indent=2)
    if args.progress:
        with open(args.progress,"w",encoding="utf8") as h: json.dump({"status":"completed","processed":len(trades),"total":len(trades),"output":args.output,"regression_ok":out["regression"]["ok"]},h)
    print(json.dumps({"output":args.output,"signals":len(trades),"scored_rows":len(rows),"candidates_before_oos":candidates,"regression_ok":out["regression"]["ok"]},ensure_ascii=False))
if __name__=="__main__":main()
