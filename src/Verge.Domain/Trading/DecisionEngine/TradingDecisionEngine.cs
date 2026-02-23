using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine.Factory;
using Verge.Trading.DecisionEngine.Profiles;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.DecisionEngine;

public class TradingDecisionEngine : DomainService, ITradingDecisionEngine
{
    private readonly ILogger<TradingDecisionEngine> _logger;

    public TradingDecisionEngine(ILogger<TradingDecisionEngine> logger)
    {
        _logger = logger;
    }

    public DecisionResult Evaluate(TradingSession session, TradingStyle style, MarketContext context)
    {
        _logger.LogInformation("🧠 Profile-Based Evaluation: Session {SessionId} | Style: {Style}", session.Id, style);

        // 1. Get corresponding Profile
        var profile = TradingStyleProfileFactory.GetProfile(style);
        
        // 2. Validate Market Regime
        var currentRegime = context.MarketRegime?.Regime ?? MarketRegimeType.Ranging;
        if (!profile.ValidRegimes.Contains(currentRegime))
        {
            var invalidRegimeResult = new DecisionResult
            {
                Decision = TradingDecision.Ignore,
                Score = 0,
                Reason = $"IGNORE: Invalid Regime '{currentRegime}' for {style} style."
            };
            _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} | Reason: {Reason}", style, invalidRegimeResult.Decision, invalidRegimeResult.Reason);
            return invalidRegimeResult;
        }

        // 3. Hard Setup Validation (Setup Validator Phase)
        if (!profile.ValidateEntry(context, out string setupInvalidReason))
        {
            var setupInvalidResult = new DecisionResult
            {
                Decision = TradingDecision.Ignore,
                Score = 0,
                Reason = $"IGNORE: {setupInvalidReason}"
            };
            _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} | Reason: {Reason}", style, setupInvalidResult.Decision, setupInvalidResult.Reason);
            return setupInvalidResult;
        }

        // 4. Component Score Calculation (0-100)
        float technicalScore = CalculateTechnicalScore(context);
        float quantitativeScore = CalculateQuantitativeScore(context);
        float sentimentScore = CalculateSentimentScore(context);
        float fundamentalScore = CalculateFundamentalScore(context);

        // 5. Apply Profile Weights
        float finalScore = (technicalScore * profile.TechnicalWeight) +
                           (quantitativeScore * profile.QuantitativeWeight) +
                           (sentimentScore * profile.SentimentWeight) +
                           (fundamentalScore * profile.FundamentalWeight);

        // 6. Apply Profile Penalties
        finalScore = profile.ApplyPenalties(context, finalScore, out string penaltyReason);

        // 7. Decision Mapping based on Profile Thresholds
        int roundedScore = (int)Math.Clamp(finalScore, 0, 100);
        var decision = GetDecisionFromProfile(roundedScore, profile);

        var result = new DecisionResult
        {
            Decision = decision,
            Score = roundedScore,
            Reason = $"Score: {roundedScore}. Style: {style}. {penaltyReason}".Trim(),
            WeightedScores = new Dictionary<string, float>
            {
                { "Technical", technicalScore * profile.TechnicalWeight },
                { "Quantitative", quantitativeScore * profile.QuantitativeWeight },
                { "Sentiment", sentimentScore * profile.SentimentWeight },
                { "Fundamental", fundamentalScore * profile.FundamentalWeight }
            }
        };

        _logger.LogInformation("✅ Evaluation Result for {Style}: {Decision} (Score: {Score})", style, result.Decision, result.Score);
        return result;
    }

    private TradingDecision GetDecisionFromProfile(int score, ITradingStyleProfile profile)
    {
        if (score >= profile.EntryThreshold) return TradingDecision.Entry;
        if (score >= profile.PrepareThreshold) return TradingDecision.Prepare;
        if (score >= profile.ContextThreshold) return TradingDecision.Context;
        return TradingDecision.Ignore;
    }

    #region Component Calculations (Linear logic remains consistent for comparability)
    private float CalculateTechnicalScore(MarketContext context)
    {
        if (context.Technicals == null) return 50f;
        float score = 50f;
        
        if (context.Technicals.Rsi < 30) score += 20;
        else if (context.Technicals.Rsi > 70) score -= 20;
        
        if (context.Technicals.MacdHistogram > 0) score += 15;
        else score -= 15;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateQuantitativeScore(MarketContext context)
    {
        if (context.MarketRegime == null) return 50f;
        float score = 50f;
        
        score += (context.MarketRegime.TrendStrength / 2);
        
        if (context.MarketRegime.Regime == MarketRegimeType.BullTrend) score += 20;
        if (context.MarketRegime.Regime == MarketRegimeType.BearTrend) score -= 20;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateSentimentScore(MarketContext context)
    {
        float score = 50f;
        
        if (context.FearAndGreed != null)
        {
            if (context.FearAndGreed.Value < 20) score += 25;
            if (context.FearAndGreed.Value > 80) score -= 25;
        }

        if (context.GlobalSentiment != null)
        {
            if (context.GlobalSentiment.Label == "positive") score += 20;
            if (context.GlobalSentiment.Label == "negative") score -= 20;
        }

        return Math.Clamp(score, 0, 100);
    }

    private float CalculateFundamentalScore(MarketContext context)
    {
        return 50f; // Standardized fundamental base
    }
    #endregion
}
