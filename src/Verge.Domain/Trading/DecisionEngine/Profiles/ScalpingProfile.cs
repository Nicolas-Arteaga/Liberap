using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class ScalpingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.60f;
    public float QuantitativeWeight => 0.25f;
    public float SentimentWeight => 0.10f;
    public float FundamentalWeight => 0.05f;

    public int EntryThreshold => 65;
    public int PrepareThreshold => 45;
    public int ContextThreshold => 30;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend, 
        MarketRegimeType.HighVolatility 
    };

    public int RequiredConfirmations => 2;

    public string GetConfirmationTimeframe(string primaryTimeframe) => "15m";

    public bool IsInvalidated(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return false;

        if (context.Technicals.Rsi < 55)
        {
            reason = $"RSI fell to {context.Technicals.Rsi:F1} (below 55)";
            return true;
        }

        if (context.Technicals.Adx < 20)
        {
            reason = $"ADX dropped to {context.Technicals.Adx:F1} (trend lost)";
            return true;
        }

        if (context.MarketRegime?.Regime == MarketRegimeType.Ranging)
        {
            reason = "Market changed to Ranging regime";
            return true;
        }

        return false;
    }

    public bool ValidateEntry(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return true;

        // RSI Momentum Check (60-75)
        if (context.Technicals.Rsi < 60 || context.Technicals.Rsi > 75)
        {
            reason = $"Scalping RSI {context.Technicals.Rsi:F1} outside momentum range (60-75)";
            return false;
        }

        // ADX Trend Strength Check
        if (context.Technicals.Adx < 22)
        {
            reason = $"Scalping ADX {context.Technicals.Adx:F1} too weak for scalp (< 22)";
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
            score *= 0.7f;
            reason += "[Ranging vs Scalp: -30%] ";
        }

        return score;
    }
}
