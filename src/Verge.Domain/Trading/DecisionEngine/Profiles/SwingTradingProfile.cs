using System;
using System.Collections.Generic;
using System.Linq;

namespace Verge.Trading.DecisionEngine.Profiles;

public class SwingTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.40f;
    public float QuantitativeWeight => 0.25f;
    public float SentimentWeight => 0.20f;
    public float FundamentalWeight => 0.20f;
    public float InstitutionalWeight => 0.0f;
    public float DecayFactor => 0.5f; // Slow decay for swing
    public float MaxStagnationMinutes => 120f; // Alert after 2 hours for swing trading trading

    public int EntryThreshold => 75;
    public int PrepareThreshold => 55;
    public int ContextThreshold => 40;
    public float TrailingMultiplier => 3.0f;
    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend,
        MarketRegimeType.Ranging
    };

    public int RequiredConfirmations => 3;

    public string GetConfirmationTimeframe(string primaryTimeframe) => "4h";

    public bool IsInvalidated(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return false;

        if (context.Technicals.Adx < 20)
        {
            reason = $"ADX {context.Technicals.Adx:F1} fell below 20 (no trend)";
            return true;
        }

        return false;
    }

    public bool ValidateEntry(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Candles == null || context.Candles.Count < 21)
        {
            reason = "Swing: Insufficient candles for breakout detection (< 21)";
            return false;
        }

        // Breakout Logic: Current price vs High/Low of last 20 candles (excluding current)
        var lookback = 20;
        var relevantCandles = context.Candles.Skip(Math.Max(0, context.Candles.Count - lookback - 1)).Take(lookback).ToList();
        
        decimal localHigh = relevantCandles.Max(c => c.High);
        decimal localLow = relevantCandles.Min(c => c.Low);
        decimal currentPrice = context.Candles.Last().Close;

        bool isBreakoutUp = currentPrice > localHigh;
        bool isBreakoutDown = currentPrice < localLow;

        if (!isBreakoutUp && !isBreakoutDown)
        {
            reason = $"Swing: Price ${currentPrice:N2} inside local range (${localLow:N2} - ${localHigh:N2})";
            return false;
        }

        return true;
    }

    public float ApplyPenalties(MarketContext context, float score, out string reason)
    {
        reason = string.Empty;

        // ADX Lack of Trend Penalty
        if (context.Technicals?.Adx < 20)
        {
            score *= 0.5f;
            reason += "[ADX < 20 vs Swing: -50%] ";
        }

        return score;
    }

    public (int Entry, int Prepare, int Context) GetAdjustedThresholds(double? winRate)
    {
        int entry = EntryThreshold;
        int prepare = PrepareThreshold;
        int context = ContextThreshold;

        if (winRate.HasValue)
        {
            if (winRate < 0.45) { entry += 10; prepare += 10; }
            else if (winRate > 0.75) { entry -= 5; }
        }

        return (entry, prepare, context);
    }
}
