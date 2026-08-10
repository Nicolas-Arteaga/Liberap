"""
Detector de pares "sombra de BTC" (pedido del usuario 2026-08-02): pares
que siguen la MISMA FORMA de movimiento que BTC en 15m -- no la misma
escala de precio. La idea real detras de esto: un patron geometrico de
medias moviles (compresion de MA7/25/50/99 + cruce violento tras
agotamiento de la caida) puede repetirse identico en BTC y en un "clon"
suyo, pero en BTC el % de movimiento resultante es insignificante (precio
grande, moverse 200 USD es nada), mientras que en un par de precio chico
(0.01-0.10 USDT) el MISMO % relativo de movimiento es una ganancia real.

Metodo: correlacion de Pearson sobre RETORNOS (% change vela a vela, no
precio absoluto -- para no confundir "ambos suben con el mercado" con
"se mueven igual de forma") de cada simbolo contra BTC, en la misma
ventana temporal (velas de 15m alineadas por open_time). Barre un pequeño
rango de lag (BTC puede liderar el movimiento por 1-3 velas, patron comun
en altcoins que "siguen" a BTC con retraso) y se queda con el mejor lag
por simbolo.

Uso: python -m backtest.find_btc_shadows   (desde agent/)
"""
import sys
import os
import sqlite3
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
MAX_LAG = 3           # velas de 15m (0 a 3 = hasta 45 min de retraso)
MIN_OVERLAP = 500      # minimo de velas superpuestas para confiar en la correlacion
TOP_N = 15


def load_closes(conn, symbol: str) -> dict:
    """Devuelve {open_time: close} para klines_clean de este simbolo."""
    cur = conn.cursor()
    cur.execute(
        "SELECT open_time, close FROM klines_clean WHERE symbol=? ORDER BY open_time ASC",
        (symbol,)
    )
    return {row[0]: float(row[1]) for row in cur.fetchall()}


def to_returns(times_sorted: list, closes: dict) -> list:
    """Serie de retornos porcentuales vela a vela, alineada a times_sorted."""
    out = []
    prev = None
    for t in times_sorted:
        c = closes.get(t)
        if c is None or prev is None or prev == 0:
            out.append(None)
        else:
            out.append((c - prev) / prev)
        prev = c if c is not None else prev
    return out


def pearson(xs: list, ys: list) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < MIN_OVERLAP:
        return None
    xv = [p[0] for p in pairs]
    yv = [p[1] for p in pairs]
    try:
        return statistics.correlation(xv, yv)
    except Exception:
        return None


def best_lag_correlation(btc_returns: list, sym_returns: list) -> tuple:
    """Prueba lag 0..MAX_LAG (BTC lidera por `lag` velas) y devuelve (mejor_corr, mejor_lag)."""
    best_corr, best_lag = None, 0
    n = len(btc_returns)
    for lag in range(0, MAX_LAG + 1):
        if lag == 0:
            xs, ys = btc_returns, sym_returns
        else:
            xs, ys = btc_returns[:n - lag], sym_returns[lag:]
        c = pearson(xs, ys)
        if c is not None and (best_corr is None or abs(c) > abs(best_corr)):
            best_corr, best_lag = c, lag
    return best_corr, best_lag


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_clean")
    symbols = sorted(r[0] for r in cur.fetchall())
    symbols = [s for s in symbols if s != "BTCUSDT"]
    print(f"Simbolos a comparar contra BTCUSDT: {len(symbols)}", flush=True)

    btc_closes = load_closes(conn, "BTCUSDT")
    btc_times_sorted = sorted(btc_closes.keys())
    btc_returns = to_returns(btc_times_sorted, btc_closes)
    print(f"BTCUSDT: {len(btc_times_sorted)} velas cargadas", flush=True)

    results = []
    for idx, symbol in enumerate(symbols):
        try:
            sym_closes = load_closes(conn, symbol)
            if len(sym_closes) < MIN_OVERLAP:
                continue
            sym_returns_aligned = to_returns(btc_times_sorted, sym_closes)
            corr, lag = best_lag_correlation(btc_returns, sym_returns_aligned)
            if corr is not None:
                overlap = sum(1 for a, b in zip(btc_returns, sym_returns_aligned) if a is not None and b is not None)
                results.append({"symbol": symbol, "corr": corr, "lag": lag, "overlap": overlap})
        except Exception:
            pass
        if (idx + 1) % 100 == 0:
            print(f"  progreso: {idx+1}/{len(symbols)}", flush=True)

    results.sort(key=lambda r: -abs(r["corr"]))

    print("=" * 90)
    print(f"{'Simbolo':15s} | {'Correlacion':>11s} | {'Lag (velas 15m)':>16s} | {'Velas superpuestas':>18s}")
    for r in results[:TOP_N]:
        print(f"{r['symbol']:15s} | {r['corr']:11.4f} | {r['lag']:16d} | {r['overlap']:18d}")
    print("=" * 90)
    strong = [r for r in results if r["corr"] >= 0.6]
    print(f"Pares con correlacion >= 0.6 (sombra fuerte de BTC): {len(strong)}")
    for r in strong:
        print(f"  {r['symbol']} (corr={r['corr']:.3f}, lag={r['lag']})")


if __name__ == "__main__":
    main()
