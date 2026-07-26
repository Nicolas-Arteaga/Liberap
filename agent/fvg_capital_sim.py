"""
Simula el retorno REAL con capital limitado (3 posiciones simultaneas de
$150, $450 total -- el mismo limite que MaxOpenPositions=3 en produccion)
sobre las señales ya detectadas por fvg_short_backtest.py.

El backtest original abre TODAS las señales sin límite (39 símbolos en
paralelo, capital infinito) — irreal para una cuenta con $450 en juego.
Acá se ordenan las señales por hora de apertura y se simula una cola: si
ya hay 3 posiciones abiertas, la señal nueva se DESCARTA (igual que
"[LIMIT] Profile is full, skipping" en el agente real), no espera en fila.

Uso: python fvg_capital_sim.py [resultados.json] [--margin 150] [--slots 3]
"""
import sys
import json
import argparse
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_file", nargs="?", default="fvg_short_backtest_results.json")
    ap.add_argument("--margin", type=float, default=150.0)
    ap.add_argument("--slots", type=int, default=3)
    args = ap.parse_args()

    with open(args.results_file, encoding="utf-8") as f:
        trades = json.load(f)

    for t in trades:
        qty = args.margin / t["entry"]
        close_px = t["tp"] if t["close_reason"] == "TP" else t["sl"]
        t["pnl"] = qty * (t["entry"] - close_px)  # SHORT

    trades.sort(key=lambda t: t["open_time"])

    open_slots = []  # lista de close_time de las posiciones actualmente abiertas
    accepted = []
    rejected = 0

    for t in trades:
        open_slots = [ct for ct in open_slots if ct > t["open_time"]]
        if len(open_slots) >= args.slots:
            rejected += 1
            continue
        open_slots.append(t["close_time"])
        accepted.append(t)

    total_signals = len(trades)
    print(f"Señales totales detectadas: {total_signals}")
    print(f"Aceptadas (hubo cupo, {args.slots} slots x ${args.margin:.0f}): {len(accepted)}")
    print(f"Descartadas (sin cupo, 'profile is full'): {rejected}")

    wins = [t for t in accepted if t["close_reason"] == "TP"]
    total_pnl = sum(t["pnl"] for t in accepted)
    wr = len(wins) / len(accepted) * 100 if accepted else 0
    print(f"\nWin rate (de las aceptadas): {wr:.1f}%")
    print(f"PnL total real: ${total_pnl:.2f}")

    if accepted:
        first_t = datetime.utcfromtimestamp(accepted[0]["open_time"] / 1000)
        last_t = datetime.utcfromtimestamp(accepted[-1]["close_time"] / 1000)
        days = (last_t - first_t).total_seconds() / 86400
        capital = args.margin * args.slots
        return_pct = total_pnl / capital * 100
        annualized_pct = return_pct * (365 / days) if days > 0 else 0
        print(f"\nPeríodo simulado: {first_t.date()} -> {last_t.date()} ({days:.1f} días)")
        print(f"Capital en juego: ${capital:.0f} ({args.slots} slots x ${args.margin:.0f})")
        print(f"Retorno sobre ese capital en el período: {return_pct:.1f}%")
        print(f"Retorno ANUALIZADO (proyectado, no garantizado): {annualized_pct:.1f}%")


if __name__ == "__main__":
    main()
