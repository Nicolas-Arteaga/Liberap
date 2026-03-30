using System;
using System.Collections.Generic;
using System.Linq;

namespace Verge.Trading.Bot;

/// <summary>
/// Calculador puro de indicadores técnicos.
/// Todas las funciones son estáticas — sin estado, testables de forma aislada.
/// Trabaja sobre List&lt;MarketCandleModel&gt; que ya usa el resto de la app.
/// </summary>
public static class IndicatorCalculator
{
    // ─────────────────────────────────────────────
    // MOVING AVERAGES
    // ─────────────────────────────────────────────

    /// <summary>
    /// Simple Moving Average (SMA).
    /// Promedio aritmético de los últimos N cierres.
    /// </summary>
    public static decimal SMA(IReadOnlyList<decimal> closes, int period)
    {
        if (closes.Count < period) return closes.LastOrDefault();
        return closes.TakeLast(period).Average();
    }

    /// <summary>
    /// Weighted Moving Average (WMA).
    /// Ponderación lineal: el precio más reciente tiene mayor peso.
    /// Necesario para calcular el HMA.
    /// </summary>
    public static decimal WMA(IReadOnlyList<decimal> closes, int period)
    {
        if (closes.Count < period) return closes.LastOrDefault();
        var slice = closes.TakeLast(period).ToList();
        decimal weightedSum = 0;
        decimal weightTotal = 0;
        for (int i = 0; i < slice.Count; i++)
        {
            decimal weight = i + 1;
            weightedSum += slice[i] * weight;
            weightTotal += weight;
        }
        return weightTotal == 0 ? 0 : weightedSum / weightTotal;
    }

    /// <summary>
    /// Hull Moving Average (HMA) — el indicador estrella de VERGE.
    /// Fórmula: WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    /// Reduce el lag del SMA sin el ruido del EMA. Ideal para scalping.
    /// </summary>
    public static decimal HMA(IReadOnlyList<decimal> closes, int period)
    {
        if (closes.Count < period) return closes.LastOrDefault();

        int halfPeriod = period / 2;
        int sqrtPeriod = (int)Math.Sqrt(period);

        // Necesitamos calcular WMA sobre una serie derivada
        // Para eso construimos una lista de valores (2*WMA(n/2) - WMA(n)) por cada punto
        int lookback = period + sqrtPeriod;
        if (closes.Count < lookback) return SMA(closes, period);

        var derivedSeries = new List<decimal>();
        for (int i = halfPeriod; i <= closes.Count; i++)
        {
            var subset = closes.Skip(i - halfPeriod).Take(halfPeriod).ToList();
            var subsetFull = closes.Skip(i - period < 0 ? 0 : i - period).Take(period).ToList();
            if (subsetFull.Count < period) continue;
            decimal wmaHalf = WMA(subset, halfPeriod);
            decimal wmaFull = WMA(subsetFull, period);
            derivedSeries.Add(2m * wmaHalf - wmaFull);
        }

        return WMA(derivedSeries, Math.Min(sqrtPeriod, derivedSeries.Count));
    }

    // ─────────────────────────────────────────────
    // INDICADORES DE VOLATILIDAD
    // ─────────────────────────────────────────────

    /// <summary>
    /// Average True Range (ATR) — mide la volatilidad real vela a vela.
    /// True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    /// ATR = promedio de los últimos N True Ranges.
    /// Usamos este valor para calibrar SL y leverage dinámico.
    /// </summary>
    public static decimal ATR(IReadOnlyList<MarketCandleModel> candles, int period = 14)
    {
        if (candles.Count < period + 1) return 0;

        var trValues = new List<decimal>();
        for (int i = 1; i < candles.Count; i++)
        {
            var curr = candles[i];
            var prev = candles[i - 1];
            decimal tr = Math.Max(
                curr.High - curr.Low,
                Math.Max(
                    Math.Abs(curr.High - prev.Close),
                    Math.Abs(curr.Low - prev.Close)
                )
            );
            trValues.Add(tr);
        }

        return trValues.TakeLast(period).Average();
    }

    // ─────────────────────────────────────────────
    // DETECCIÓN DE CRUCES
    // ─────────────────────────────────────────────

    /// <summary>
    /// CrossedAbove: la línea rápida estaba debajo de la lenta en t-1
    /// y ahora está por encima en t. → Señal LONG.
    /// </summary>
    public static bool CrossedAbove(decimal prevFast, decimal prevSlow, decimal currFast, decimal currSlow)
        => prevFast <= prevSlow && currFast > currSlow;

    /// <summary>
    /// CrossedBelow: la línea rápida estaba encima de la lenta en t-1
    /// y ahora está por debajo en t. → Señal SHORT.
    /// </summary>
    public static bool CrossedBelow(decimal prevFast, decimal prevSlow, decimal currFast, decimal currSlow)
        => prevFast >= prevSlow && currFast < currSlow;

    // ─────────────────────────────────────────────
    // CÁLCULO DE LEVERAGE DINÁMICO
    // ─────────────────────────────────────────────

    /// <summary>
    /// Calcula el leverage óptimo basado en la volatilidad relativa del símbolo.
    /// Lógica: a menor ATR% → mercado tranquilo → más leverage (máx 20x).
    ///         a mayor ATR% → mercado volátil → menos leverage (mín 8x).
    /// 
    /// ATR% = ATR / PrecioActual * 100
    /// </summary>
    public static int CalculateDynamicLeverage(decimal atr, decimal price, int minLeverage, int maxLeverage)
    {
        if (price == 0) return minLeverage;
        decimal atrPct = atr / price * 100m;

        // Escala inversa: menos volatilidad = más leverage
        int leverage = atrPct switch
        {
            <= 0.30m => maxLeverage,         // Muy tranquilo → 20x
            <= 0.50m => (int)(maxLeverage * 0.90), // → ~18x
            <= 0.75m => (int)(maxLeverage * 0.75), // → ~15x
            <= 1.00m => (int)(maxLeverage * 0.62), // → ~12x
            <= 1.50m => (int)(maxLeverage * 0.50), // → ~10x
            _        => minLeverage          // Muy volátil → 8x
        };

        return Math.Clamp(leverage, minLeverage, maxLeverage);
    }
}
