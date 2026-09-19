"""
ROUND 46c -- formaliza el mecanismo descubierto en r46b (tendencia
establecida + SIN aceleracion reciente de corto plazo = corre mas lejos;
tendencia establecida + CON aceleracion reciente/spike = revierte) en
reglas ejecutables, y las valida TRAIN/VAL/OOS + 2do split + portfolio
engine + remove-best-trade, exactamente igual disciplina que R45.

Candidatas (estructurales, NO combinatoria ciega -- nacen de la
comparacion BIG_WIN vs REVERSAL_LOSS de r46b):

  C1 "Trend Continuation No-Chase LONG": uptrend establecido
     (price_vs_ma50>0, ret_20>0) + SIN spike reciente (accel_3_10 por
     debajo de su mediana en ese contexto) -- la apuesta es que esto
     filtra afuera las persecuciones de blow-off que revierten (REVERSAL_LOSS)
     y se queda con la continuacion mas "aburrida" que corre (BIG_WIN).

  C2 "Trend Continuation No-Chase SHORT": espejo bajista.

  C3 "Established Momentum, ignore accel" LONG: version mas simple, solo
     exige price_vs_ma50>0 y ret_10 alto (sin condicion de accel) --
     control para saber si el filtro anti-chase realmente aporta o si
     alcanza con "tendencia fuerte" solo.
"""
import os, sys, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio_engine import allocate_timestamp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "scratch_r46_dataset.json")


def load():
    with open(DATA) as f:
        rows = json.load(f)
    rows.sort(key=lambda r: r["ts"])
    return rows


def f(r, feat):
    v = r.get(feat)
    return v if (v is not None and np.isfinite(v)) else None


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    train_rows, val_rows, oos_rows = rows[:i1], rows[i1:i2], rows[i2:]
    base_wr = sum(1 for r in train_rows if r["win"]) / len(train_rows)
    print(f"TRAIN={len(train_rows)} ({train_rows[0]['opened'][:10]}..{train_rows[-1]['opened'][:10]})  "
          f"VAL={len(val_rows)} ({val_rows[0]['opened'][:10]}..{val_rows[-1]['opened'][:10]})  "
          f"OOS={len(oos_rows)} ({oos_rows[0]['opened'][:10]}..{oos_rows[-1]['opened'][:10]})")
    print(f"Base win-rate TRAIN: {base_wr:.1%}\n")

    # umbral de accel_3_10 derivado SOLO de TRAIN, condicionado a estar en tendencia establecida
    train_trend_long = [r for r in train_rows if r["side"] == 1 and f(r, "price_vs_ma50") is not None
                         and f(r, "price_vs_ma50") > 0 and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                         and f(r, "accel_3_10") is not None]
    accel_median_long = float(np.median([r["accel_3_10"] for r in train_trend_long])) if train_trend_long else 0.0

    train_trend_short = [r for r in train_rows if r["side"] == -1 and f(r, "price_vs_ma50") is not None
                          and f(r, "price_vs_ma50") < 0 and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                          and f(r, "accel_3_10") is not None]
    accel_median_short = float(np.median([r["accel_3_10"] for r in train_trend_short])) if train_trend_short else 0.0

    ret10_p60_long = float(np.percentile([r["ret_10"] for r in train_rows if r["side"] == 1 and f(r, "ret_10") is not None], 60))

    print(f"n(trend LONG en TRAIN)={len(train_trend_long)}  accel_3_10 mediana={accel_median_long:.5f}")
    print(f"n(trend SHORT en TRAIN)={len(train_trend_short)}  accel_3_10 mediana={accel_median_short:.5f}")
    print(f"ret_10 p60 (LONG, TRAIN)={ret10_p60_long:.5f}\n")

    def c1_long(r):
        return (r["side"] == 1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") > 0
                and f(r, "ret_20") is not None and f(r, "ret_20") > 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") <= accel_median_long)

    def c2_short(r):
        return (r["side"] == -1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") < 0
                and f(r, "ret_20") is not None and f(r, "ret_20") < 0
                and f(r, "accel_3_10") is not None and f(r, "accel_3_10") >= accel_median_short)

    def c3_long_control(r):
        return (r["side"] == 1 and f(r, "price_vs_ma50") is not None and f(r, "price_vs_ma50") > 0
                and f(r, "ret_10") is not None and f(r, "ret_10") >= ret10_p60_long)

    candidates = {"C1 Trend-Continuation-NoChase LONG": c1_long,
                  "C2 Trend-Continuation-NoChase SHORT": c2_short,
                  "C3 Trend-only (control, sin filtro accel) LONG": c3_long_control}

    print("=" * 100)
    print("PASO A -- TRAIN / VAL / OOS (reglas fijas, umbrales solo de TRAIN)")
    print("=" * 100)
    for name, rule in candidates.items():
        for label, pop_rows in (("TRAIN", train_rows), ("VAL", val_rows), ("OOS", oos_rows)):
            pop = [r for r in pop_rows if rule(r)]
            n_ = len(pop)
            wr = sum(1 for r in pop if r["win"]) / n_ if n_ else 0
            pnl = sum(r["pnl"] for r in pop)
            mfe_med = np.median([r["mfe"] for r in pop]) if pop else 0
            print(f"  [{label:5s}] {name:46s} n={n_:4d} wr={wr:.1%} pnl={pnl:8.1f} mfe_mediana={mfe_med:6.0f}bp")
        print()

    print("=" * 100)
    print("PASO B -- 2do split independiente (mitad1 vs mitad2)")
    print("=" * 100)
    half = n // 2
    mid1, mid2 = rows[:half], rows[half:]
    survivors = []
    for name, rule in candidates.items():
        pop1 = [r for r in mid1 if rule(r)]; pop2 = [r for r in mid2 if rule(r)]
        n1, n2 = len(pop1), len(pop2)
        pnl1 = sum(r["pnl"] for r in pop1); pnl2 = sum(r["pnl"] for r in pop2)
        ok = n1 >= 10 and n2 >= 10 and pnl1 > 0 and pnl2 > 0
        print(f"  {name:46s} mitad1 n={n1:4d} pnl={pnl1:8.1f}  |  mitad2 n={n2:4d} pnl={pnl2:8.1f}  -> "
              f"{'SOBREVIVE' if ok else 'NO sobrevive'}")
        if ok:
            survivors.append(name)
    print(f"\nSobreviven: {survivors}\n")

    if not survivors:
        print("NINGUNA candidata sobrevive el 2do split. FIN (ver reporte para el analisis del mecanismo igual).")
        return

    print("=" * 100)
    print("PASO C -- Portfolio engine (capital 450, 3 slots, notional 150, fees/funding reales)")
    print("=" * 100)

    def run_pf(rule, pop_rows):
        matched = [r for r in pop_rows if rule(r)]
        if not matched:
            return 0, 0.0, 0.0, 0
        cands = []
        for r in matched:
            exit_ts = int(np.datetime64(r["closed"]).astype("datetime64[ms]").astype(np.int64))
            cands.append(dict(ts=r["ts"], symbol=r["symbol"], score=1.0, exit_ts=exit_ts, pnl=r["pnl"], win=r["win"]))
        by_ts = collections.defaultdict(list)
        for c in cands:
            by_ts[c["ts"]].append(c)
        free_at = [0, 0, 0]
        accepted = []
        for ts in sorted(by_ts):
            acc, rej = allocate_timestamp(by_ts[ts], free_at, 3)
            accepted.extend(acc)
        n_acc = len(accepted)
        pnl_acc = sum(c["pnl"] for c in accepted)
        wr_acc = sum(1 for c in accepted if c["win"]) / n_acc if n_acc else 0
        return n_acc, wr_acc, pnl_acc, len(matched) - n_acc

    results = {}
    for name in survivors:
        rule = candidates[name]
        print(f"\n--- {name} ---")
        row_res = {}
        for label, pop_rows in (("TRAIN", train_rows), ("VAL", val_rows), ("OOS", oos_rows)):
            n_acc, wr_acc, pnl_acc, rej = run_pf(rule, pop_rows)
            print(f"  [{label}] aceptados={n_acc:4d} (rechaz.concurrencia={rej})  wr={wr_acc:.1%}  PnL neto={pnl_acc:8.2f}")
            row_res[label] = (n_acc, wr_acc, pnl_acc)
        results[name] = row_res

        # remove-best-trade en OOS
        oos_matched = [r for r in oos_rows if rule(r)]
        if oos_matched:
            pnls = sorted(r["pnl"] for r in oos_matched)
            total = sum(pnls); best = pnls[-1]
            print(f"  [ROBUSTEZ] OOS total(sin filtrar por cupos)={total:.1f}  sin_mejor_trade={total-best:.1f}")

    print("\n" + "=" * 100)
    print("TABLA FINAL")
    print("=" * 100)
    print(f"{'Candidato':46s} {'TRAIN':>9s} {'VAL':>9s} {'OOS':>9s}")
    for name, r in results.items():
        print(f"{name:46s} {r['TRAIN'][2]:9.1f} {r['VAL'][2]:9.1f} {r['OOS'][2]:9.1f}")


if __name__ == "__main__":
    main()
