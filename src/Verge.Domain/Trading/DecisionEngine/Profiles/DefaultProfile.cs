using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class DefaultProfile : ITradingStyleProfile
{
    // Default weights from legacy engine
    public float TechnicalWeight => 0.40f;
    public float QuantitativeWeight => 0.20f;
    public float SentimentWeight => 0.20f;
    public float FundamentalWeight => 0.20f;

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 30;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend, 
        MarketRegimeType.Ranging 
    };

    public int RequiredConfirmations => 1;

    public string GetConfirmationTimeframe(string primaryTimeframe) => primaryTimeframe;

    public bool IsInvalidated(MarketContext context, out string reason)
    {
        reason = string.Empty;
        return false;
    }

    public bool ValidateEntry(MarketContext context, out string reason)
    {
        reason = string.Empty;
        return true; // No hard conditions by default
    }

    public float ApplyPenalties(MarketContext context, float score, out string reason)
    {
        reason = string.Empty;
        return score;
    }
}
