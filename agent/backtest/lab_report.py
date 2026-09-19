"""
Resumen legible del laboratorio (agent/backtest/strategy_lab.py) -- para
correr a la mañana y ver de una: cuantas se probaron, cuantas pasaron el
filtro, y el detalle completo (WR, $/mes, estabilidad entre mitades) de
las mejores, ordenadas por $/mes.

Uso: python -m backtest.lab_report   (desde agent/)
"""
import json
import os

TESTED_LOG = os.path.join(os.path.dirname(__file__), "lab_tested_all.jsonl")
FOUND_PATH = os.path.join(os.path.dirname(__file__), "found_strategies.jsonl")
PROGRESS_PATH = os.path.join(os.path.dirname(__file__), "lab_progress.log")


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def main():
    tested = load_jsonl(TESTED_LOG)
    found = load_jsonl(FOUND_PATH)

    print("=" * 100)
    print(f"LABORATORIO DE ESTRATEGIAS -- resumen")
    print("=" * 100)
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if lines:
            print(f"Ultimo progreso: {lines[-1].strip()}")
    print(f"Total probadas (con detalle guardado): {len(tested)}")
    print(f"Total que pasaron el filtro (ambas mitades positivas, estables, >=$150/mes): {len(found)}")

    with_data = [t for t in tested if not t["result"].get("insufficient_data")]
    print(f"Con datos suficientes para evaluar: {len(with_data)}")

    if not with_data:
        print("\nTodavia no hay estrategias evaluables -- dejar correr mas.")
        return

    with_data.sort(key=lambda t: t["result"].get("monthly", -999999), reverse=True)

    print("\n" + "=" * 100)
    print("TOP 15 por $/mes (pasen o no el filtro estricto -- para ver el panorama completo)")
    print("=" * 100)
    print(f"{'entry_type':14s} {'tf':4s} {'side':6s} {'MAs':9s} {'SL/RR':9s} {'n':6s} {'WR%':6s} {'$/mes':9s} {'mitad1/mitad2':16s} {'pasa?':6s}")
    for row in with_data[:15]:
        s, r = row["strat"], row["result"]
        ma = f"{s['ma_pair'][0]}/{s['ma_pair'][1]}"
        slrr = f"{s['atr_sl_mult']}x/{s['rr_mult']}x"
        mitad = f"${r.get('pnl_h1','?')}/${r.get('pnl_h2','?')}"
        print(f"{s['entry_type']:14s} {s['tf_min']:<4d} {s['side']:6s} {ma:9s} {slrr:9s} "
              f"{r['n']:<6d} {r['wr_pct']:<6.1f} {r['monthly']:<9.2f} {mitad:16s} {'SI' if r.get('passes_bar') else 'no'}")

    if found:
        print("\n" + "=" * 100)
        print(f"GANADORAS REALES (pasan TODOS los filtros) -- {len(found)}")
        print("=" * 100)
        found_sorted = sorted(found, key=lambda t: t["result"]["monthly"], reverse=True)
        for row in found_sorted:
            s, r = row["strat"], row["result"]
            print(f"\n{json.dumps(s, indent=2)}")
            print(f"  n={r['n']} WR={r['wr_pct']}% PnL total=${r['pnl_total']} (${r['monthly']}/mes)")
            print(f"  1ra mitad: n={r['n_h1']} WR={r['wr_h1']}% PnL=${r['pnl_h1']}")
            print(f"  2da mitad: n={r['n_h2']} WR={r['wr_h2']}% PnL=${r['pnl_h2']}")
    else:
        print("\nTodavia ninguna paso el filtro completo (estable + >= $150/mes). Ver el TOP 15 arriba para lo mas cercano.")


if __name__ == "__main__":
    main()
