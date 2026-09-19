"""
ROUND 45d -- para los 5 candidatos que sobrevivieron TRAIN/VAL/OOS (r45c):
1) segundo split temporal INDEPENDIENTE (mitad1 vs mitad2 del dataset
   completo, una particion que no participo en la seleccion de reglas)
2) backtest real con portfolio_engine.py: capital 450, 3 slots, notional
   150/slot, sizing/fees/funding REALES ya registrados por trade (estos
   son trades ya cerrados de la reconstruccion -- no se re-simula el
   exit, se usa el RealizedPnl/EntryFee/ExitFee/TotalFundingPaid ya
   guardados por cada trade real que matchea la regla).
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio_engine import allocate_timestamp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r45_dataset.json")

CANDIDATES = [
    dict(name="Momentum-Wick LONG", side=1,
         rule=lambda r: (r.get("ret_3") is not None and r.get("upper_wick_ratio") is not None)),
    dict(name="Volume-Body LONG", side=1, rule=None),
    dict(name="Momentum-Body LONG", side=1, rule=None),
    dict(name="Fade SHORT", side=-1, rule=None),
    dict(name="Momentum-LowerWick LONG", side=1, rule=None),
]

# thresholds computed on TRAIN in r45c (percentiles) -- hardcoded here
# re-derived from the SAME TRAIN population for reproducibility.


def load():
    with open(DATA) as f:
        rows = json.load(f)
    rows.sort(key=lambda r: r["ts"])
    return rows


def pct(rows, feat, q):
    vals = np.array([r[feat] for r in rows if r.get(feat) is not None and np.isfinite(r[feat])])
    return float(np.nanpercentile(vals, q))


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    train_rows = rows[:i1]

    # thresholds derived ONLY from TRAIN (as in r45c)
    ret3_p80 = pct(train_rows, "ret_3", 80)
    uwr_p40 = pct(train_rows, "upper_wick_ratio", 40)
    vr_p60 = pct(train_rows, "vol_rel", 60)
    br_p60 = pct(train_rows, "body_ratio", 60)
    lwr_p60 = pct(train_rows, "lower_wick_ratio", 60)
    pvm7_p40 = pct(train_rows, "price_vs_ma7", 40)

    def f(r, feat):
        v = r.get(feat)
        return v if (v is not None and np.isfinite(v)) else None

    rules = {
        "Momentum-Wick LONG": lambda r: r["side"] == 1 and f(r, "ret_3") is not None and f(r, "ret_3") >= ret3_p80
                              and f(r, "upper_wick_ratio") is not None and f(r, "upper_wick_ratio") < uwr_p40,
        "Volume-Body LONG": lambda r: r["side"] == 1 and f(r, "vol_rel") is not None and f(r, "vol_rel") >= vr_p60
                              and f(r, "body_ratio") is not None and f(r, "body_ratio") >= br_p60,
        "Momentum-Body LONG": lambda r: r["side"] == 1 and f(r, "ret_3") is not None and f(r, "ret_3") >= ret3_p80
                              and f(r, "body_ratio") is not None and f(r, "body_ratio") >= br_p60,
        "Fade SHORT": lambda r: r["side"] == -1 and f(r, "price_vs_ma7") is not None and f(r, "price_vs_ma7") < pvm7_p40
                              and f(r, "lower_wick_ratio") is not None and f(r, "lower_wick_ratio") < lwr_p60,
        "Momentum-LowerWick LONG": lambda r: r["side"] == 1 and f(r, "ret_3") is not None and f(r, "ret_3") >= ret3_p80
                              and f(r, "lower_wick_ratio") is not None and f(r, "lower_wick_ratio") < lwr_p60,
    }

    base_wr = sum(1 for r in rows if r["win"]) / len(rows)
    print(f"Dataset completo: {len(rows)} trades, base win-rate={base_wr:.1%}\n")

    half = n // 2
    mid1, mid2 = rows[:half], rows[half:]

    print("=" * 78)
    print("SEGUNDO SPLIT TEMPORAL INDEPENDIENTE (mitad1 vs mitad2, no usado para elegir reglas)")
    print("=" * 78)
    survivors = []
    for name, rule in rules.items():
        pop1 = [r for r in mid1 if rule(r)]
        pop2 = [r for r in mid2 if rule(r)]
        n1, n2 = len(pop1), len(pop2)
        wr1 = sum(1 for r in pop1 if r["win"]) / n1 if n1 else 0
        wr2 = sum(1 for r in pop2 if r["win"]) / n2 if n2 else 0
        pnl1 = sum(r["pnl"] for r in pop1); pnl2 = sum(r["pnl"] for r in pop2)
        ok = n1 >= 10 and n2 >= 10 and pnl1 > 0 and pnl2 > 0
        print(f"  {name:26s} mitad1: n={n1:4d} wr={wr1:.1%} pnl={pnl1:8.1f}  |  "
              f"mitad2: n={n2:4d} wr={wr2:.1%} pnl={pnl2:8.1f}  -> {'SOBREVIVE' if ok else 'NO sobrevive'}")
        if ok:
            survivors.append(name)
    print(f"\nSobreviven el segundo split (positivos en AMBAS mitades, n>=10): {survivors}\n")

    if not survivors:
        print("NINGUN candidato sobrevive el segundo split independiente. FIN.")
        return

    print("=" * 78)
    print("PORTFOLIO ENGINE (capital=450 USDT, 3 slots, notional=150/slot,")
    print("fees/slippage/funding YA incluidos en RealizedPnl de cada trade real)")
    print("=" * 78)

    def run_pf(name, rule, pop_rows, label):
        matched = [r for r in pop_rows if rule(r)]
        if not matched:
            print(f"  [{label}] {name}: 0 trades")
            return 0, 0.0, 0.0
        cands = [dict(ts=r["ts"], symbol=r["symbol"], score=1.0, exit_ts=r["ts"] + 1,
                      pnl=r["pnl"], win=r["win"]) for r in matched]
        free_at = [0, 0, 0]
        # orden cronologico, exit_ts real de cada trade
        for c, r in zip(cands, matched):
            c["exit_ts"] = int(np.datetime64(r["closed"]).astype("datetime64[ms]").astype(np.int64))
        cands.sort(key=lambda c: c["ts"])
        import collections
        by_ts = collections.defaultdict(list)
        for c in cands:
            by_ts[c["ts"]].append(c)
        accepted = []
        for ts in sorted(by_ts):
            acc, rej = allocate_timestamp(by_ts[ts], free_at, 3)
            accepted.extend(acc)
        n_acc = len(accepted)
        pnl_acc = sum(c["pnl"] for c in accepted)
        wr_acc = sum(1 for c in accepted if c["win"]) / n_acc if n_acc else 0
        rejected_n = len(matched) - n_acc
        print(f"  [{label}] {name:26s} matched={len(matched):4d}  aceptados(cap)={n_acc:4d} "
              f"(rechazados por concurrencia={rejected_n})  wr={wr_acc:.1%}  PnL neto={pnl_acc:8.2f}")
        return n_acc, wr_acc, pnl_acc

    train_rows2, val_rows2, oos_rows2 = rows[:i1], rows[i1:i2], rows[i2:]
    summary = []
    for name in survivors:
        rule = rules[name]
        print(f"\n--- {name} ---")
        n_tr, wr_tr, pnl_tr = run_pf(name, rule, train_rows2, "TRAIN")
        n_va, wr_va, pnl_va = run_pf(name, rule, val_rows2, "VAL")
        n_oo, wr_oo, pnl_oo = run_pf(name, rule, oos_rows2, "OOS")
        days_oos = (np.datetime64(oos_rows2[-1]["closed"]) - np.datetime64(oos_rows2[0]["opened"])).astype("timedelta64[D]").astype(int)
        oos_monthly = pnl_oo / max(days_oos, 1) * 30
        summary.append(dict(name=name, n_train=n_tr, pnl_train=pnl_tr, n_val=n_va, pnl_val=pnl_va,
                             n_oos=n_oo, pnl_oos=pnl_oo, oos_monthly=oos_monthly))

    print("\n" + "=" * 78)
    print("TABLA FINAL (post portfolio-engine, capital-constrained)")
    print("=" * 78)
    print(f"{'Candidato':28s} {'Trades':>7s} {'TRAIN':>9s} {'VAL':>9s} {'OOS':>9s} {'OOS/mes':>9s} {'Resultado':>10s}")
    for s in summary:
        total_trades = s["n_train"] + s["n_val"] + s["n_oos"]
        result = "PASS" if s["pnl_oos"] > 0 else "FAILED"
        print(f"{s['name']:28s} {total_trades:7d} {s['pnl_train']:9.1f} {s['pnl_val']:9.1f} "
              f"{s['pnl_oos']:9.1f} {s['oos_monthly']:9.1f} {result:>10s}")

    with open(os.path.join(HERE, "..", "..", "scratch_r45_portfolio_summary.json"), "w") as fo:
        json.dump(summary, fo)


if __name__ == "__main__":
    main()
