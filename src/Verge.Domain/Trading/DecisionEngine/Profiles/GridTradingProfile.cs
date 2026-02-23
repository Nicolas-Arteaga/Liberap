using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class GridTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.35f;
    public float QuantitativeWeight => 0.30f;
    public float SentimentWeight => 0.20f;
    public float FundamentalWeight => 0.15f;

    public int EntryThreshold => 65;
    public int PrepareThreshold => 45;
    public int ContextThreshold => 30;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.Ranging, 
        MarketRegimeType.LowVolatility 
    };

    public int RequiredConfirmations => 2;

    public string GetConfirmationTimeframe(string primaryTimeframe) => "1h";

    public bool IsInvalidated(MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return false;

        if (context.Technicals.Adx > 20)
        {
            reason = $"ADX {context.Technicals.Adx:F1} rose above 20 (potential trend break)";
            return true;
        }

        return false;
    }

    public bool ValidateEntry(MarketContext context, out string reason)
    {
        reason = string.Empty;

        // Range Confirmation
        if (context.Technicals?.Adx > 20)
        {
            reason = $"Grid: ADX {context.Technicals.Adx:F1} indicates active trend (> 20)";
            return false;
        }

        return true;
    }

    public float ApplyPenalties(MarketContext context, float score, out string reason)
    {
        reason = string.Empty;

        // ADX Penalty - Grid hates trends
        if (context.Technicals?.Adx > 25)
        {
            score *= 0.2f;
            reason += "[ADX > 25 vs Grid: -80%] ";
        }

        return score;
    }
}
