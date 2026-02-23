using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class DayTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.50f;
    public float QuantitativeWeight => 0.25f;
    public float SentimentWeight => 0.15f;
    public float FundamentalWeight => 0.10f;

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 35;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend 
    };

    public bool ValidateEntry(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return true;

        // RSI Continuation Zone (50-70)
        if (context.Technicals.Rsi < 50 || context.Technicals.Rsi > 70)
        {
            reason = $"Day RSI {context.Technicals.Rsi:F1} outside continuation zone (50-70)";
            return false;
        }

        // ADX Strong Trend
        if (context.Technicals.Adx < 25)
        {
            reason = $"Day ADX {context.Technicals.Adx:F1} weak for DayTrade (< 25)";
            return false;
        }

        return true;
    }

    public float ApplyPenalties(MarketContext context, float score, out string reason)
    {
        reason = string.Empty;

        // Ranging Penalty
        if (context.MarketRegime?.Regime == MarketRegimeType.Ranging)
        {
            score *= 0.8f;
            reason += "[Ranging vs Day: -20%] ";
        }

        // RSI Extension Penalty
        if (context.Technicals?.Rsi > 75)
        {
            score *= 0.6f;
            reason += "[RSI Extendido: -40%] ";
        }

        return score;
    }
}
