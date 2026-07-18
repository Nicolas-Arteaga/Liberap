"""
Verifica la hipótesis del usuario sobre confluencia multi-timeframe de
medias móviles como señal de mejor entrada (ejemplo real: XANUSDT, MA7
cruzando hacia abajo por MA25/MA50 en 15m mientras en 5m la MA25 "alcanza"
a la MA7 justo antes del mechazo final hacia la MA99).

Simplificación operacionalizable (no reproduce la narrativa vela por vela,
mide la firma numérica del fenómeno descripto): en el momento exacto de
cada entrada real (de los 185 trades del backtest, arrow_peak_trades.csv),
¿qué tan "comprimidas" (MA7 cerca de MA25) estaban las medias en 5m,
comparado con su propio promedio de las 4 horas previas de ESE símbolo?
Si la hipótesis es cierta, las entradas con medias más comprimidas en el
momento de entrar deberían ganar más / ser más rápidas.

100% sobre datos ya cacheados, cero llamadas a ninguna API.
"""
import pandas as pd
from kline_cache import get_cache

LOOKBACK_5M_CANDLES = 48  # 4 horas


def _ema(values: list, span: int) -> list:
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def compression_ratio_at(symbol: str, entry_time_ms: int, cache) -> float:
    """
    |MA7-MA25| / precio en el momento de entrada, dividido por el promedio
    de ese mismo valor en las LOOKBACK_5M_CANDLES velas de 5m previas del
    mismo símbolo. <1.0 = más comprimido que lo usual justo al entrar.
    Devuelve None si no hay suficiente historia de 5m alrededor de ese punto.
    """
    klines_5m = cache.get_klines(symbol, "5m", limit=100_000)
    if len(klines_5m) < LOOKBACK_5M_CANDLES + 30:
        return None

    # Encontrar el índice de la vela de 5m que contiene (o es la más cercana anterior a) entry_time_ms
    idx = None
    for i, k in enumerate(klines_5m):
        if k["open_time"] > entry_time_ms:
            break
        idx = i
    if idx is None or idx < LOOKBACK_5M_CANDLES + 26:
        return None

    closes = [k["close"] for k in klines_5m[: idx + 1]]
    ma7 = _ema(closes, 7)
    ma25 = _ema(closes, 25)

    gaps = [abs(ma7[j] - ma25[j]) / closes[j] for j in range(len(closes))]
    gap_now = gaps[-1]
    baseline = gaps[-1 - LOOKBACK_5M_CANDLES: -1]
    avg_baseline = sum(baseline) / len(baseline) if baseline else None
    if not avg_baseline or avg_baseline == 0:
        return None
    return gap_now / avg_baseline


def main():
    cache = get_cache()
    df = pd.read_csv("data/arrow_peak_trades.csv")

    ratios = []
    for _, row in df.iterrows():
        r = compression_ratio_at(row["symbol"], int(row["entry_time_ms"]), cache)
        ratios.append(r)
    df["compression_ratio"] = ratios

    df_valid = df.dropna(subset=["compression_ratio"]).copy()
    print(f"Trades evaluables (con suficiente historia de 5m): {len(df_valid)}/{len(df)}")

    df_valid["compressed"] = df_valid["compression_ratio"] < 0.7  # MAs notablemente más juntas que su propio promedio
    for label, group in df_valid.groupby("compressed"):
        wins = (group["pnl_pct"] > 0).sum()
        n = len(group)
        total_win = group.loc[group["pnl_pct"] > 0, "pnl_pct"].sum()
        total_loss = abs(group.loc[group["pnl_pct"] <= 0, "pnl_pct"].sum())
        pf = (total_win / total_loss) if total_loss > 0 else float("inf")
        tag = "COMPRIMIDAS (ratio<0.7)" if label else "no comprimidas"
        print(f"  {tag}: n={n} win_rate={wins/n*100:.1f}% PF={pf:.2f} avg_candles_to_exit={group['candles_to_exit'].mean():.0f}")

    print("\nCorrelación (Pearson) compression_ratio vs pnl_pct:", df_valid["compression_ratio"].corr(df_valid["pnl_pct"]))
    print("Correlación (Pearson) compression_ratio vs candles_to_exit:", df_valid["compression_ratio"].corr(df_valid["candles_to_exit"]))


if __name__ == "__main__":
    main()
