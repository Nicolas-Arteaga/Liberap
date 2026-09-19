"""
ROUND 48 -- ULTIMA ronda de discovery. Dos mecanismos NUEVOS (no
combinatoria ciega), formalizados a partir de features de transicion ya
construidas en R46 pero NUNCA usadas como mecanismo propio (solo como
control):

D1 "Capitulacion-Reversion": precio cerca del extremo de 50 velas
   (pos_in_range50 muy bajo para LONG / muy alto para SHORT) + sorpresa
   de volumen (vol_surge alto, evento de volumen) + habia compresion
   previa (compression_ratio<1 antes del evento) -- la idea de trader:
   "el mercado se comprimio, vino un evento de volumen en un extremo, y
   eso agota el movimiento previo -- reversion, no continuacion".

D2 "Expansion-tras-Compresion" (direccional, sigue la vela de ruptura):
   compression_ratio<1 en la barra previa (estaba comprimido) Y la
   barra de entrada ya muestra expansion (ATR relativo alto) + volumen
   alto -- "el mercado estaba comprimido y esta barra es la ruptura,
   seguir la direccion de esa barra".

Control: C2 de R46/47 (ya sabemos que FAILED economicamente, se reporta
solo como referencia de la tabla final, no se vuelve a validar de cero).
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


def pct(rows, feat, q, cond=None):
    vals = [r[feat] for r in rows if r.get(feat) is not None and np.isfinite(r[feat]) and (cond is None or cond(r))]
    return float(np.percentile(vals, q)) if len(vals) >= 30 else None


def main():
    rows = load()
    n = len(rows)
    i1 = int(n * 0.6); i2 = int(n * 0.8)
    train_rows, val_rows, oos_rows = rows[:i1], rows[i1:i2], rows[i2:]

    # thresholds derivados SOLO de TRAIN
    pos_lo_long = pct(train_rows, "pos_in_range50", 20, lambda r: r["side"] == 1)   # cerca del piso
    pos_hi_short = pct(train_rows, "pos_in_range50", 80, lambda r: r["side"] == -1)  # cerca del techo
    vol_surge_p80 = pct(train_rows, "vol_surge", 80)
    compression_p40 = pct(train_rows, "compression_ratio", 40)  # <p40 = estaba comprimido
    atr_p70 = pct(train_rows, "atr_rel", 70)

    print("=== D1 CAPITULACION-REVERSION -- thresholds (TRAIN) ===")
    print(f"pos_in_range50 LONG <= {pos_lo_long:.3f} (cerca del piso de 50 velas)")
    print(f"pos_in_range50 SHORT >= {pos_hi_short:.3f} (cerca del techo de 50 velas)")
    print(f"vol_surge >= {vol_surge_p80:.3f} (sorpresa de volumen, p80)")
    print(f"compression_ratio antes del evento <= {compression_p40:.3f} (estaba comprimido, p40)\n")

    def d1_long(r):
        return (r["side"] == 1 and f(r, "pos_in_range50") is not None and f(r, "pos_in_range50") <= pos_lo_long
                and f(r, "vol_surge") is not None and f(r, "vol_surge") >= vol_surge_p80
                and f(r, "compression_ratio") is not None and f(r, "compression_ratio") <= compression_p40)

    def d1_short(r):
        return (r["side"] == -1 and f(r, "pos_in_range50") is not None and f(r, "pos_in_range50") >= pos_hi_short
                and f(r, "vol_surge") is not None and f(r, "vol_surge") >= vol_surge_p80
                and f(r, "compression_ratio") is not None and f(r, "compression_ratio") <= compression_p40)

    print("=== D2 EXPANSION-TRAS-COMPRESION -- thresholds (TRAIN) ===")
    print(f"compression_ratio <= {compression_p40:.3f} (estaba comprimido)")
    print(f"atr_rel >= {atr_p70:.3f} (la barra de entrada ya expande, p70)")
    print(f"vol_surge >= {vol_surge_p80:.3f} (con volumen)")
    print("direccion: sigue el signo de ret_1 de la barra de entrada (LONG si ret_1>0, SHORT si ret_1<0)\n")

    def d2(r):
        base = (f(r, "compression_ratio") is not None and f(r, "compression_ratio") <= compression_p40
                and f(r, "atr_rel") is not None and f(r, "atr_rel") >= atr_p70
                and f(r, "vol_surge") is not None and f(r, "vol_surge") >= vol_surge_p80
                and f(r, "ret_1") is not None)
        if not base:
            return False
        implied_side = 1 if r["ret_1"] > 0 else -1
        return r["side"] == implied_side

    variants = {"D1 Capitulacion-Reversion LONG": d1_long,
                "D1 Capitulacion-Reversion SHORT": d1_short,
                "D2 Expansion-tras-Compresion (direccional)": d2}

    def run_pf(rule, pop_rows):
        matched = [r for r in pop_rows if rule(r)]
        if not matched:
            return [], []
        cands = []
        for r in matched:
            exit_ts = int(np.datetime64(r["closed"]).astype("datetime64[ms]").astype(np.int64))
            cands.append(dict(ts=r["ts"], symbol=r["symbol"], score=1.0, exit_ts=exit_ts,
                               pnl=r["pnl"], win=r["win"], mfe=r["mfe"], closed=r["closed"]))
        by_ts = collections.defaultdict(list)
        for c in cands:
            by_ts[c["ts"]].append(c)
        free_at = [0, 0, 0]
        accepted = []
        for ts in sorted(by_ts):
            acc, rej = allocate_timestamp(by_ts[ts], free_at, 3)
            accepted.extend(acc)
        return accepted, matched

    half = n // 2
    mid1, mid2 = rows[:half], rows[half:]

    summary_rows = []
    for name, rule in variants.items():
        print("\n" + "=" * 100)
        print(name)
        print("=" * 100)
        row_summary = {"name": name}
        for label, pop_rows in (("TRAIN", train_rows), ("VAL", val_rows), ("OOS", oos_rows)):
            acc, matched = run_pf(rule, pop_rows)
            n_acc = len(acc); pnl = sum(c["pnl"] for c in acc)
            wr = sum(1 for c in acc if c["win"]) / n_acc if n_acc else 0
            print(f"  [{label:5s}] matched={len(matched):4d} aceptados={n_acc:4d} "
                  f"(rechaz={len(matched)-n_acc})  wr={wr:.1%}  PnL={pnl:8.1f}")
            row_summary[label] = pnl
            if label == "OOS":
                oos_acc = acc

        acc1, m1 = run_pf(rule, mid1); acc2, m2 = run_pf(rule, mid2)
        pnl1 = sum(c["pnl"] for c in acc1); pnl2 = sum(c["pnl"] for c in acc2)
        split_ok = len(acc1) >= 5 and len(acc2) >= 5 and pnl1 > 0 and pnl2 > 0
        print(f"  [2do split] mitad1: n={len(acc1)} pnl={pnl1:7.1f}  |  mitad2: n={len(acc2)} pnl={pnl2:7.1f}  "
              f"-> {'SOBREVIVE' if split_ok else 'NO sobrevive'}")
        row_summary["split_ok"] = split_ok

        if oos_acc:
            days_oos = max(1, (np.datetime64(oos_rows[-1]["closed"]) - np.datetime64(oos_rows[0]["opened"])).astype("timedelta64[D]").astype(int))
            pnl_oos = sum(c["pnl"] for c in oos_acc)
            trades_mo = len(oos_acc) / days_oos * 30
            pnl_mo = pnl_oos / days_oos * 30
            pnls_sorted = sorted(c["pnl"] for c in oos_acc)
            wo_best = pnl_oos - pnls_sorted[-1]
            wo_top3 = pnl_oos - sum(pnls_sorted[-3:]) if len(pnls_sorted) >= 3 else None
            syms = collections.Counter(c["symbol"] for c in oos_acc)
            top_sym, top_sym_n = syms.most_common(1)[0]
            print(f"  [ECONOMIA OOS] n={len(oos_acc)} trades/mes={trades_mo:.1f}  PnL/mes=${pnl_mo:.1f}  "
                  f"MFE_prom={np.mean([c['mfe'] for c in oos_acc]):.0f}bp")
            print(f"  [CONCENTRACION] simbolo top={top_sym} ({top_sym_n}/{len(oos_acc)})")
            print(f"  [ROBUSTEZ] sin_mejor={wo_best:.1f}  sin_top3={wo_top3 if wo_top3 is not None else 'n/a'}")
            row_summary["oos_monthly"] = pnl_mo
            row_summary["wo_top3"] = wo_top3
        else:
            print("  [ECONOMIA OOS] 0 trades en OOS.")
            row_summary["oos_monthly"] = None
            row_summary["wo_top3"] = None

        summary_rows.append(row_summary)

    print("\n" + "=" * 100)
    print("TABLA FINAL R48")
    print("=" * 100)
    for r in summary_rows:
        print(r)


if __name__ == "__main__":
    main()
