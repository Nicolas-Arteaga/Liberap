using System.Collections.Generic;

namespace Verge.Trading.DecisionEngine.Profiles;

public class DayTradingProfile : ITradingStyleProfile
{
    public float TechnicalWeight => 0.50f;
    public float QuantitativeWeight => 0.25f;
    public float SentimentWeight => 0.15f;
    public float FundamentalWeight => 0.10f;
    public float InstitutionalWeight => 0.0f;
    public float DecayFactor => 1.5f; // Medium decay for day trading
    public float MaxStagnationMinutes => 30f; // Warn after 30 mins without signals

    public int EntryThreshold => 70;
    public int PrepareThreshold => 50;
    public int ContextThreshold => 35;
    public float TrailingMultiplier => 2.0f;

    public List<MarketRegimeType> ValidRegimes => new List<MarketRegimeType> 
    { 
        MarketRegimeType.BullTrend, 
        MarketRegimeType.BearTrend 
    };

    public int RequiredConfirmations => 2;

    public string GetConfirmationTimeframe(string primaryTimeframe) => "1h";

    public bool IsInvalidated(TradingSession session, MarketContext context, out string reason)
    {
        reason = string.Empty;
        if (context.Technicals == null) return false;

        if (context.Technicals.Rsi < 50 || context.Technicals.Rsi > 70)
        {
            reason = $"RSI {context.Technicals.Rsi:F1} exited stable zone (50-70)";
            return true;
        }

        if (context.Technicals.Adx < 25)
        {
            reason = $"ADX {context.Technicals.Adx:F1} dropped below 25";
            return true;
        }

        if (context.MarketRegime?.Regime == MarketRegimeType.Ranging)
        {
            reason = "Market structure changed to Ranging";
            return true;
        }

        return false;
    }

    public bool ValidateEntry(TradingSession session, MarketContext context, out string reason)
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

    public float ApplyPenalties(TradingSession session, MarketContext context, float score, out string reason)
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
