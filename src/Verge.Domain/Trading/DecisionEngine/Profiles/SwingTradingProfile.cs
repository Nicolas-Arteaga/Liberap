using System;
using System.Collections.Generic;
using System.Linq;

namespace Verge.Trading.DecisionEngine.Profiles;

public class SwingTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.40f;
    public float QuantitativeWeight => 0.25f;
    public float SentimentWeight => 0.20f;
    public float FundamentalWeight => 0.15f;

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 35;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend,
        MarketRegimeType.Ranging
    };

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
}
