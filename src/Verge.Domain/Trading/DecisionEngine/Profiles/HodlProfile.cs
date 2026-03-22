using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class HodlProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.10f;
    public float QuantitativeWeight => 0.15f;
    public float SentimentWeight => 0.30f;
    public float FundamentalWeight => 0.40f;
    public float InstitutionalWeight => 0.0f;
    public float DecayFactor => 0.05f; // Extremely slow decay for HODL
    public float MaxStagnationMinutes => 10080f; // Alert after 7 days for HODL style

    public int EntryThreshold => 85;
    public int PrepareThreshold => 70;
    public int ContextThreshold => 50;
    public float TrailingMultiplier => 5.0f;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend,
        MarketRegimeType.Ranging,
        MarketRegimeType.HighVolatility,
        MarketRegimeType.LowVolatility
    };

    public int RequiredConfirmations => 1;

    public string GetConfirmationTimeframe(string primaryTimeframe) => primaryTimeframe; // No HTF for HODL

    public bool IsInvalidated(TradingSession session, MarketContext context, out string reason)
    {
        reason = string.Empty;
        return false; // HODL never invalidates
    }

    public bool ValidateEntry(TradingSession session, MarketContext context, out string reason)
    {
        reason = string.Empty;

        // 1. Fear Check - Buy when others are afraid
        if (context.FearAndGreed != null && context.FearAndGreed.Value > 30)
        {
            reason = $"HODL: F&G {context.FearAndGreed.Value} not low enough for accumulation (> 30)";
            return false;
        }

        // 2. Liquidity & Maturity (if available)
        if (context.CoinGeckoData != null)
        {
            // MCap check
            if (context.CoinGeckoData.MarketCapUsd > 0 && context.CoinGeckoData.MarketCapUsd < 100000000)
            {
                reason = $"HODL: Market Cap ${context.CoinGeckoData.MarketCapUsd:N0} below maturity threshold ($100M)";
                return false;
            }

            // Vol/MCap ratio
            if (context.CoinGeckoData.MarketCapUsd > 0)
            {
                decimal ratio = context.CoinGeckoData.Volume24hUsd / context.CoinGeckoData.MarketCapUsd;
                if (ratio < 0.05m)
                {
                    reason = $"HODL: Volume/MCap ratio {ratio*100:F1}% suggests low liquidity (< 5%)";
                    return false;
                }
            }
        }

        return true;
    }

    public float ApplyPenalties(TradingSession session, MarketContext context, float score, out string reason)
    {
        reason = string.Empty;
        // HODL usually doesn't apply penalties, it accumulates
        return score;
    }

    public (int Entry, int Prepare, int Context) GetAdjustedThresholds(double? winRate)
    {
        int entry = EntryThreshold;
        int prepare = PrepareThreshold;
        int context = ContextThreshold;

        if (winRate.HasValue)
        {
            if (winRate < 0.40) { entry += 10; prepare += 5; }
            else if (winRate > 0.80) { entry -= 5; }
        }

        return (entry, prepare, context);
    }
}
