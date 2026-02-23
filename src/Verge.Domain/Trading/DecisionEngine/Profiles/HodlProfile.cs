using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class HodlProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.10f;
    public float QuantitativeWeight => 0.15f;
    public float SentimentWeight => 0.30f;
    public float FundamentalWeight => 0.45f;

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 35;

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

    public bool IsInvalidated(MarketContext context, out string reason)
    {
        reason = string.Empty;
        return false; // HODL never invalidates
    }

    public bool ValidateEntry(MarketContext context, out string reason)
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

    public float ApplyPenalties(MarketContext context, float score, out string reason)
    {
        reason = string.Empty;
        // HODL usually doesn't apply penalties, it accumulates
        return score;
    }
}
