"""
Grid search sobre "Short del Blow-off Top" -- iterar el R:R (SL/TP por
ATR) y probar un filtro de volumen de confirmacion, sobre los mismos 19
memecoins ya validados (meme_breakout_mining.py). Baseline conocido:
SL=1.5xATR/TP=3.0xATR (R:R 2:1) = +$227.01, 14/19 positivos.

Uso: python -m backtest.meme_short_grid_search   (desde agent/)
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

import backtest.strategy_meme_short_top as mod
from backtest.engine import BacktestEngine

BASKET = mod.BASKET

COMBOS = [
    ("SL1.0/TP2.0 (R:R 2:1, mas ajustado)", 1.0, 2.0),
    ("SL1.5/TP3.0 (baseline conocido)", 1.5, 3.0),
    ("SL1.5/TP4.5 (R:R 3:1)", 1.5, 4.5),
    ("SL1.0/TP3.0 (R:R 3:1, SL angosto)", 1.0, 3.0),
    ("SL2.0/TP4.0 (R:R 2:1, mas ancho)", 2.0, 4.0),
]


def run_combo(engine, sl_mult, tp_mult):
    mod.ATR_SL_MULT = sl_mult
    mod.ATR_TP_MULT = tp_mult
    total_pnl = 0.0
    n_positive = 0
    for sym in BASKET:
        trades = mod.run_symbol(engine, sym)
        profile_stub = {"marginPerTrade": mod.MARGIN, "maxOpenPositions": mod.SLOTS, "name": sym}
        result = engine._capital_sim(trades, profile_stub, symbols_used=[sym])
        pnl = result["total_pnl_usdt"]
        total_pnl += pnl
        if pnl > 0:
            n_positive += 1
    return total_pnl, n_positive


def main():
    engine = BacktestEngine()
    print(f"Grid search sobre {len(BASKET)} memecoins -- {len(COMBOS)} combinaciones de R:R", flush=True)
    print("=" * 90, flush=True)

    results = []
    for label, sl, tp in COMBOS:
        pnl, n_pos = run_combo(engine, sl, tp)
        print(f"{label:40s} | PnL total=${pnl:9.2f} | positivos={n_pos}/{len(BASKET)}", flush=True)
        results.append((label, sl, tp, pnl, n_pos))

    results.sort(key=lambda r: -r[3])
    print("=" * 90)
    best = results[0]
    print(f"MEJOR: {best[0]} -> PnL=${best[3]:.2f}, {best[4]}/{len(BASKET)} positivos")


if __name__ == "__main__":
    main()
