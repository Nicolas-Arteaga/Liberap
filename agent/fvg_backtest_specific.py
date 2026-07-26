"""
Corre fvg_short_backtest sobre una lista EXPLICITA de simbolos (no top-N
por volumen de velas) -- para comparar apples-to-apples contra un periodo
y universo de simbolos especifico (ej. los mismos que trado FVG-15m
Pulido en vivo, mismas fechas).
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.dirname(__file__))
from fvg_short_backtest import load_symbol_klines, backtest_symbol, DB_PATH

SYMBOLS = [
    "NIGHTUSDT","SNXXUSDT","STARUSDT","INTWUSDT","ZESTUSDT","HANAUSDT",
    "CBRSUSDT","HAEDALUSDT","ZBTUSDT","YGGUSDT","SQDUSDT","EVAAUSDT",
    "WDCUSDT","REUSDT","ONEUSDT","LISTAUSDT","ERAUSDT","NAORISUSDT",
    "AVAAIUSDT","SMCIUSDT","ONDSUSDT","QNTXUSDT","BLURUSDT","BNCUSDT",
    "BMNRUSDT",
]


def main():
    min_slope = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    conn = sqlite3.connect(DB_PATH)
    all_trades = []
    for sym in SYMBOLS:
        rows = load_symbol_klines(conn, sym)
        print(f"{sym}: {len(rows)} velas cargadas", flush=True)
        trades = backtest_symbol(sym, rows, min_slope)
        all_trades.extend(trades)
        if trades:
            print(f"  -> {len(trades)} trades", flush=True)

    wins = [t for t in all_trades if t["close_reason"] == "TP"]
    print(f"\n=== RESULTADO ({len(SYMBOLS)} simbolos, min_slope={min_slope}) ===")
    print(f"Total trades: {len(all_trades)}")
    print(f"Wins: {len(wins)} | WR: {len(wins)/len(all_trades)*100:.1f}%" if all_trades else "sin trades")

    with open("fvg_specific_results.json", "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=2, default=str)


if __name__ == "__main__":
    main()
