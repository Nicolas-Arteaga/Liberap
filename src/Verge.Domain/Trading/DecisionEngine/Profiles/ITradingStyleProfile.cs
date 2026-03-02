using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public interface ITradingStyleProfile
{
    // Weights (summing to 1.0)
    float TechnicalWeight { get; }
    float QuantitativeWeight { get; }
    float SentimentWeight { get; }
    float FundamentalWeight { get; }
    
    // Institutional 1% metrics: Decay & Stagnation
    float DecayFactor { get; }
    float MaxStagnationMinutes { get; }
    
    // Decision Thresholds
    int EntryThreshold { get; }
    int PrepareThreshold { get; }
    int ContextThreshold { get; }
    
    // Valid Market Regimes for this style
    List<MarketRegimeType> ValidRegimes { get; }
    
    // Phase 2: Signal Quality
    int RequiredConfirmations { get; }
    string GetConfirmationTimeframe(string primaryTimeframe);
    bool IsInvalidated(MarketContext context, out string reason);
    
    // Hard entry validation (setups)
    bool ValidateEntry(MarketContext context, out string reason);
    
    // Contextual penalties / bonuses
    float ApplyPenalties(MarketContext context, float score, out string reason);

    // Dynamic Thresholds (Sprint 4)
    (int Entry, int Prepare, int Context) GetAdjustedThresholds(double? winRate);
}
