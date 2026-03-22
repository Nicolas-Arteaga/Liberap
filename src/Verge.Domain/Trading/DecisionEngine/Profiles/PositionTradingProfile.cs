using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class PositionTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.25f;
    public float QuantitativeWeight => 0.20f;
    public float SentimentWeight => 0.25f;
    public float FundamentalWeight => 0.30f;
    public float InstitutionalWeight => 0.0f;
    public float DecayFactor => 0.2f; // Very slow decay for position
    public float MaxStagnationMinutes => 720f; // Alert after 12 hours for position trading

    public int EntryThreshold => 80;
    public int PrepareThreshold => 60;
    public int ContextThreshold => 45;
    public float TrailingMultiplier => 4.0f;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend 
    };

    public int RequiredConfirmations => 4;

    public string GetConfirmationTimeframe(string primaryTimeframe) => "1d";

    public bool IsInvalidated(TradingSession session, MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.MarketRegime?.Regime == MarketRegimeType.Ranging)
        {
            reason = "Market changed to Ranging (unsuitable for Position)";
            return true;
        }

        if (context.FearAndGreed != null && (context.FearAndGreed.Value < 40 || context.FearAndGreed.Value > 75))
        {
            reason = $"F&G {context.FearAndGreed.Value} exited stable range (40-75)";
            return true;
        }

        return false;
    }

    public bool ValidateEntry(TradingSession session, MarketContext context, out string reason)
    {
        reason = string.Empty;

        // 1. Strong Trend Check
        if (context.Technicals?.Adx < 25)
        {
            reason = $"Position: ADX {context.Technicals.Adx:F1} too weak for trend entry (< 25)";
            return false;
        }

        // 2. No Extremes Check
        if (context.FearAndGreed != null)
        {
            if (context.FearAndGreed.Value < 40 || context.FearAndGreed.Value > 75)
            {
                reason = $"Position: F&G {context.FearAndGreed.Value} outside stable range (40-75)";
                return false;
            }
        }

        // 3. Market Cap Threshold (if available)
        if (context.CoinGeckoData != null && context.CoinGeckoData.MarketCapUsd > 0 && context.CoinGeckoData.MarketCapUsd < 500000000)
        {
            reason = $"Position: Market Cap ${context.CoinGeckoData.MarketCapUsd:N0} below minimum for long term ($500M)";
            return false;
        }

        return true;
    }

    public float ApplyPenalties(TradingSession session, MarketContext context, float score, out string reason)
    {
        reason = string.Empty;

        // Ranging Penalty - Strong
        if (context.MarketRegime?.Regime == MarketRegimeType.Ranging)
        {
            score *= 0.3f;
            reason += "[Ranging vs Position: -70%] ";
        }

        // Extreme Greed Penalty
        if (context.FearAndGreed?.Value > 80)
        {
            score *= 0.7f;
            reason += "[Greed > 80 vs Position: -30%] ";
        }

        return score;
    }

    public (int Entry, int Prepare, int Context) GetAdjustedThresholds(double? winRate)
    {
        int entry = EntryThreshold;
        int prepare = PrepareThreshold;
        int context = ContextThreshold;

        if (winRate.HasValue)
        {
            if (winRate < 0.45) { entry += 10; prepare += 10; }
            else if (winRate > 0.75) { entry -= 5; }
        }

        return (entry, prepare, context);
    }
}
