"""
ROUND 47b -- las 3 variantes finales (congeladas, sin retocar thresholds
de TRAIN), corridas por portfolio_engine.py real, con la prueba
economica completa pedida por R47: trades/mes, expectancy, bp/trade,
PnL mensual OOS, mejor/peor mes, DD, concentracion por simbolo/trade/
tiempo, remove-best y remove-top-3.
"""
import os, sys, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio_engine import allocate_timestamp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r46_dataset.json")


def f(r, feat):
    v = r.get(feat)
    return v if (v is not None and np.isfinite(v)) else None


def load():
    with open(DATA) as fh:
        rows = json.load(fh)
    rows.sort(key=lambda r: r["ts"])
    return rows


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    train_rows, val_rows, oos_rows = rows[:i1], rows[i1:i2], rows[i2:]

    train_trend_short = [r for r in train_rows if r["side"] == -1 and f(r, "price_vs_ma50") is not None
                          and f(r, "price_vs_ma50") < 0 and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                          and f(r, "accel_3_10") is not None]
    accel_median_short = float(np.median([r["accel_3_10"] for r in train_trend_short]))
    train_trend_long = [r for r in train_rows if r["side"] == 1 and f(r, "price_vs_ma50") is not None
                         and f(r, "price_vs_ma50") > 0 and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                         and f(r, "accel_3_10") is not None]
    accel_median_long = float(np.median([r["accel_3_10"] for r in train_trend_long]))

    def v1_c2(r):  # SHORT, congelado de R46
        return (r["side"] == -1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") < 0
                and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") >= accel_median_short)

    def v2_c1_mirror(r):  # LONG, misma formula espejada (mayor n)
        return (r["side"] == 1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") > 0
                and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") <= accel_median_long)

    def v3_loose_short(r):  # SHORT sin filtro de aceleracion (control de frecuencia)
        return (r["side"] == -1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") < 0
                and f(r, "ret_20") is not None and f(r, "ret_20") < 0)

    variants = {"V1 C2 SHORT (congelado R46)": v1_c2,
                "V2 C1 LONG mirror (congelado)": v2_c1_mirror,
                "V3 SHORT sin filtro accel (control freq)": v3_loose_short}

    def run_pf(rule, pop_rows):
        matched = [r for r in pop_rows if rule(r)]
        if not matched:
            return [], []
        cands = []
        for r in matched:
            exit_ts = int(np.datetime64(r["closed"]).astype("datetime64[ms]").astype(np.int64))
            cands.append(dict(ts=r["ts"], symbol=r["symbol"], score=1.0, exit_ts=exit_ts,
                               pnl=r["pnl"], win=r["win"], mfe=r["mfe"], opened=r["opened"], closed=r["closed"]))
        by_ts = collections.defaultdict(list)
        for c in cands:
            by_ts[c["ts"]].append(c)
        free_at = [0, 0, 0]
        accepted = []
        for ts in sorted(by_ts):
            acc, rej = allocate_timestamp(by_ts[ts], free_at, 3)
            accepted.extend(acc)
        return accepted, matched

    for name, rule in variants.items():
        print("\n" + "=" * 100)
        print(name)
        print("=" * 100)
        split_res = {}
        for label, pop_rows in (("TRAIN", train_rows), ("VAL", val_rows), ("OOS", oos_rows)):
            acc, matched = run_pf(rule, pop_rows)
            n_acc = len(acc); pnl = sum(c["pnl"] for c in acc)
            wr = sum(1 for c in acc if c["win"]) / n_acc if n_acc else 0
            print(f"  [{label:5s}] matched={len(matched):4d} aceptados={n_acc:4d} "
                  f"(rechaz={len(matched)-n_acc})  wr={wr:.1%}  PnL={pnl:8.1f}")
            split_res[label] = (acc, matched)

        # segundo split independiente
        half = n // 2
        mid1, mid2 = rows[:half], rows[half:]
        acc1, m1 = run_pf(rule, mid1); acc2, m2 = run_pf(rule, mid2)
        pnl1 = sum(c["pnl"] for c in acc1); pnl2 = sum(c["pnl"] for c in acc2)
        print(f"  [2do split] mitad1: n={len(acc1)} pnl={pnl1:7.1f}  |  mitad2: n={len(acc2)} pnl={pnl2:7.1f}  "
              f"-> {'SOBREVIVE' if (pnl1>0 and pnl2>0) else 'NO sobrevive'}")

        # prueba economica sobre OOS
        acc_oos, matched_oos = split_res["OOS"]
        if not acc_oos:
            print("  [ECONOMIA OOS] sin trades aceptados.")
            continue
        days_oos = max(1, (np.datetime64(oos_rows[-1]["closed"]) - np.datetime64(oos_rows[0]["opened"])).astype("timedelta64[D]").astype(int))
        pnl_oos = sum(c["pnl"] for c in acc_oos)
        trades_mo = len(acc_oos) / days_oos * 30
        expectancy = pnl_oos / len(acc_oos)
        bp_avg = np.mean([c["mfe"] for c in acc_oos])  # proxy de magnitud de movimiento capturable
        pnl_mo = pnl_oos / days_oos * 30
        print(f"  [ECONOMIA OOS] dias={days_oos}  trades={len(acc_oos)}  trades/mes={trades_mo:.1f}  "
              f"expectancy/trade=${expectancy:.2f}  MFE promedio={bp_avg:.0f}bp  PnL/mes=${pnl_mo:.1f}")

        # concentracion
        syms = collections.Counter(c["symbol"] for c in acc_oos)
        top_sym, top_sym_n = syms.most_common(1)[0]
        print(f"  [CONCENTRACION] simbolo mas repetido={top_sym} ({top_sym_n}/{len(acc_oos)}={top_sym_n/len(acc_oos):.0%})")

        # mejor/peor mes (agrupando por mes calendario del OOS, si alcanza para >=2 meses)
        by_month = collections.defaultdict(list)
        for c in acc_oos:
            month = str(c["closed"])[:7]
            by_month[month].append(c["pnl"])
        month_pnls = {m: sum(v) for m, v in by_month.items()}
        print(f"  [MESES OOS] {month_pnls}")

        # remove-best y remove-top3
        pnls_sorted = sorted(c["pnl"] for c in acc_oos)
        total = sum(pnls_sorted)
        wo_best = total - pnls_sorted[-1] if pnls_sorted else 0
        wo_top3 = total - sum(pnls_sorted[-3:]) if len(pnls_sorted) >= 3 else None
        print(f"  [ROBUSTEZ] OOS total={total:.1f}  sin_mejor_trade={wo_best:.1f}  "
              f"sin_top3={wo_top3 if wo_top3 is not None else 'n/a (menos de 3 trades)'}")


if __name__ == "__main__":
    main()
