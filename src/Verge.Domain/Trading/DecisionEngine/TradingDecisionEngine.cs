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

        // 2. Setup Invalidation Check (Phase 2)
        if (session.CurrentStage == TradingStage.Prepared)
        {
            if (profile.IsInvalidated(context, out string invalidReason))
            {
                var invalidResult = new DecisionResult
                {
                    Decision = TradingDecision.Ignore,
                    Score = 0,
                    Reason = $"⚠️ SETUP INVALIDATED: {invalidReason}"
                };
                _logger.LogWarning("❌ Session {SessionId} invalidated: {Reason}", session.Id, invalidResult.Reason);
                return invalidResult;
            }
        }
        
        // 3. Validate Market Regime
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

        // 7. Decision Mapping based on Profile Thresholds (Phase 2.0 Base)
        int roundedScore = (int)Math.Clamp(finalScore, 0, 100);
        var decision = GetDecisionFromProfile(roundedScore, profile);

        // 7.1 Multi-Timeframe Confirmation (Phase 2)
        if (decision == TradingDecision.Entry)
        {
            if (!ValidateHTFConfirmation(context, session, style, profile, out string htfReason))
            {
                decision = TradingDecision.Prepare;
                roundedScore = Math.Min(roundedScore, profile.EntryThreshold - 1);
                penaltyReason += $" [HTF Conflict: {htfReason}]";
            }
        }

        // 8. Confidence Calculation (Phase 2)
        var confidence = CalculateConfidence(context, style);

        // 9. Temporal Persistence Check (Phase 2.1)
        if (decision == TradingDecision.Entry)
        {
            if (!CheckTemporalPersistence(session, profile, roundedScore, out string persistenceReason))
            {
                decision = TradingDecision.Prepare;
                penaltyReason += $" {persistenceReason}";
            }
        }

        var result = new DecisionResult
        {
            Decision = decision,
            Confidence = confidence,
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

        // 10. Entry Range Calculation (Sprint 4)
        if (result.Decision >= TradingDecision.Prepare)
        {
            var currentPrice = context.Candles.Last().Close;
            // 0.5% Zone window (+-0.25%)
            result.EntryMinPrice = currentPrice * 0.9975m;
            result.EntryMaxPrice = currentPrice * 1.0025m;
        }

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

    #region Phase 2: Intelligence Helpers
    private SignalConfidence CalculateConfidence(MarketContext context, TradingStyle style)
    {
        // 1. RSI Stability (Check recent variance if possible, otherwise look at ADX as proxy for trend quality)
        var adx = context.Technicals?.Adx ?? 0;
        var score = 0;

        if (adx > 30) score += 40; // High trend strength = high confidence in trend-following
        else if (adx > 20) score += 20;

        // 2. Regime Consistency
        if (context.MarketRegime != null && context.MarketRegime.TrendStrength > 60) score += 30;

        // 3. Sentiment Alignment
        if (context.GlobalSentiment?.Label == "positive" && context.MarketRegime?.Regime == MarketRegimeType.BullTrend) score += 30;
        if (context.GlobalSentiment?.Label == "negative" && context.MarketRegime?.Regime == MarketRegimeType.BearTrend) score += 30;

        if (score >= 80) return SignalConfidence.High;
        if (score >= 40) return SignalConfidence.Medium;
        return SignalConfidence.Low;
    }

    private bool CheckTemporalPersistence(TradingSession session, ITradingStyleProfile profile, int currentScore, out string reason)
    {
        reason = string.Empty;
        var requiredCount = profile.RequiredConfirmations;
        if (requiredCount <= 1) return true;

        // Persistence logic: Parse History
        var history = ParseHistory(session.EvaluationHistoryJson);
        history.Add(currentScore);
        
        // Keep last 10
        if (history.Count > 10) history = history.Skip(history.Count - 10).ToList();
        
        // Save back to session (Transiently)
        session.EvaluationHistoryJson = System.Text.Json.JsonSerializer.Serialize(history);

        // Check last N
        if (history.Count < requiredCount)
        {
            reason = $"[WAITING: Needs {requiredCount} cycles, have {history.Count}]";
            return false;
        }

        var lastN = history.TakeLast(requiredCount).ToList();
        bool allAbove = lastN.All(s => s >= profile.EntryThreshold);

        if (!allAbove)
        {
            reason = $"[CONSISTENCY: Latest sequence failed stability check]";
            return false;
        }

        return true;
    }

    private bool ValidateHTFConfirmation(MarketContext context, TradingSession session, TradingStyle style, ITradingStyleProfile profile, out string reason)
    {
        reason = string.Empty;
        var htfContext = context.HigherTimeframeContext;
        if (htfContext == null) return true; // Cannot validate if not present (log as warning in monitor)

        var htfRegime = htfContext.MarketRegime?.Regime ?? MarketRegimeType.Ranging;

        // Simple Contradiction Rules
        // 1. Long on lower TF while higher TF is BearTrend
        if (htfRegime == MarketRegimeType.BearTrend && style != TradingStyle.GridTrading)
        {
            reason = $"HTF contradiction: Cannot Long while HTF is in BearTrend";
            return false;
        }

        // 2. Short on lower TF while higher TF is BullTrend
        // (Assuming session direction logic exists elsewhere or we check RSI/MACD of HTF)

        return true;
    }

    private List<int> ParseHistory(string? json)
    {
        if (string.IsNullOrEmpty(json)) return new List<int>();
        try { return System.Text.Json.JsonSerializer.Deserialize<List<int>>(json) ?? new List<int>(); }
        catch { return new List<int>(); }
    }
    #endregion
}
