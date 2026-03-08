using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class DefaultProfile : ITradingStyleProfile
{
    // Default weights from legacy engine
    public float TechnicalWeight => 0.40f;
    public float QuantitativeWeight => 0.20f;
    public float SentimentWeight => 0.20f;
    public float FundamentalWeight => 0.10f;
    public float InstitutionalWeight => 0.0f;
    public float DecayFactor => 0.5f; // Default conservative decay
    public float MaxStagnationMinutes => 60f; // Alert after 1 hour for default style

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 30;
    public float TrailingMultiplier => 2.0f;

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

    public (int Entry, int Prepare, int Context) GetAdjustedThresholds(double? winRate)
    {
        int entry = EntryThreshold;
        int prepare = PrepareThreshold;
        int context = ContextThreshold;

        if (winRate.HasValue)
        {
            if (winRate < 0.45) { entry += 10; prepare += 10; context += 5; }
            else if (winRate < 0.55) { entry += 5; prepare += 5; }
            else if (winRate > 0.75) { entry -= 5; prepare -= 5; }
        }

        return (entry, prepare, context);
    }
}
