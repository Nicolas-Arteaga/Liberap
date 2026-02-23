using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public interface ITradingStyleProfile
{
    // Weights (summing to 1.0)
    float TechnicalWeight { get; }
    float QuantitativeWeight { get; }
    float SentimentWeight { get; }
    float FundamentalWeight { get; }
    
    // Decision Thresholds
    int EntryThreshold { get; }
    int PrepareThreshold { get; }
    int ContextThreshold { get; }
    
    // Valid Market Regimes for this style
    List<MarketRegimeType> ValidRegimes { get; }
    
    // Hard entry validation (setups)
    bool ValidateEntry(MarketContext context, out string reason);
    
    // Contextual penalties / bonuses
    float ApplyPenalties(MarketContext context, float score, out string reason);
}
