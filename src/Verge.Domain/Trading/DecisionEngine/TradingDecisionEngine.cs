using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.Logging;
using Verge.Trading;
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
        _logger.LogInformation("🧠 Evaluating session {SessionId} with Style {Style}", session.Id, style);

        // 1. Get Weights based on Style
        var weights = GetWeightsForStyle(style);
        
        // 2. Calculate Component Scores (0-100)
        float technicalScore = CalculateTechnicalScore(context);
        float quantitativeScore = CalculateQuantitativeScore(context);
        float sentimentScore = CalculateSentimentScore(context);
        float fundamentalScore = CalculateFundamentalScore(context);

        // 3. Apply Weights
        float finalScore = (technicalScore * weights.Technical) +
                           (quantitativeScore * weights.Quantitative) +
                           (sentimentScore * weights.Sentiment) +
                           (fundamentalScore * weights.Fundamental);

        // 4. Apply Compatibility Rules / Modifiers
        finalScore = ApplyRules(session, style, context, finalScore, out string ruleReason);

        // 5. Final Decision
        int roundedScore = (int)Math.Clamp(finalScore, 0, 100);
        var decision = GetDecisionFromScore(roundedScore);

        var result = new DecisionResult
        {
            Decision = decision,
            Score = roundedScore,
            Reason = $"Score: {roundedScore}. Style: {style}. {ruleReason}".Trim(),
            WeightedScores = new Dictionary<string, float>
            {
                { "Technical", technicalScore * weights.Technical },
                { "Quantitative", quantitativeScore * weights.Quantitative },
                { "Sentiment", sentimentScore * weights.Sentiment },
                { "Fundamental", fundamentalScore * weights.Fundamental }
            }
        };

        _logger.LogInformation("✅ Evaluation Result: {Decision} (Score: {Score})", result.Decision, result.Score);
        return result;
    }

    private (float Technical, float Quantitative, float Sentiment, float Fundamental) GetWeightsForStyle(TradingStyle style)
    {
        return style switch
        {
            TradingStyle.Scalping => (0.50f, 0.30f, 0.15f, 0.05f),
            TradingStyle.DayTrading => (0.45f, 0.25f, 0.20f, 0.10f),
            TradingStyle.SwingTrading => (0.35f, 0.25f, 0.20f, 0.20f),
            TradingStyle.PositionTrading => (0.20f, 0.15f, 0.25f, 0.40f),
            TradingStyle.GridTrading => (0.30f, 0.30f, 0.20f, 0.20f),
            TradingStyle.HODL => (0.10f, 0.10f, 0.30f, 0.50f),
            _ => (0.40f, 0.20f, 0.20f, 0.20f) // Default para AUTO o Algorithmic
        };
    }

    private float CalculateTechnicalScore(MarketContext context)
    {
        if (context.Technicals == null) return 50f; // Neutral si no hay data

        float score = 50f;
        
        // RSI Logic
        if (context.Technicals.Rsi < 30) score += 20; // Oversold
        else if (context.Technicals.Rsi > 70) score -= 20; // Overbought
        
        // MACD Logic
        if (context.Technicals.MacdHistogram > 0) score += 15;
        else score -= 15;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateQuantitativeScore(MarketContext context)
    {
        if (context.MarketRegime == null) return 50f;

        float score = 50f;
        
        // Trend Strength (ADX)
        score += (context.MarketRegime.TrendStrength / 2); // ADX 0-100 -> adds up to 50
        
        // Regime Bias
        if (context.MarketRegime.Regime == "BullTrend") score += 20;
        if (context.MarketRegime.Regime == "BearTrend") score -= 20;
        
        return Math.Clamp(score, 0, 100);
    }

    private float CalculateSentimentScore(MarketContext context)
    {
        float score = 50f;
        
        // Fear & Greed (Contrast logic)
        if (context.FearAndGreed != null)
        {
            // At extreme fear, sentiment for buying increases (contrarian)
            if (context.FearAndGreed.Value < 20) score += 25;
            // At extreme greed, sentiment for buying decreases
            if (context.FearAndGreed.Value > 80) score -= 25;
        }

        // News Sentiment
        if (context.GlobalSentiment != null)
        {
            if (context.GlobalSentiment.Label == "positive") score += 20;
            if (context.GlobalSentiment.Label == "negative") score -= 20;
        }

        return Math.Clamp(score, 0, 100);
    }

    private float CalculateFundamentalScore(MarketContext context)
    {
        if (context.CoinGeckoData == null) return 50f;
        
        // Simple logic: Big market cap = safer = slightly higher fundamental score for long term
        // This could be improved with Volume/MCap ratios
        return 50f; 
    }

    private float ApplyRules(TradingSession session, TradingStyle style, MarketContext context, float score, out string reason)
    {
        reason = "";
        
        // Rule: Ranging Market + Swing = Reduce 50%
        if (context.MarketRegime?.Regime == "Ranging" && style == TradingStyle.SwingTrading)
        {
            score *= 0.5f;
            reason += "[Regime Ranging vs Swing: -50%] ";
        }
        
        // Rule: Ranging Market + Grid = Increase 30%
        if (context.MarketRegime?.Regime == "Ranging" && style == TradingStyle.GridTrading)
        {
            score *= 1.3f;
            reason += "[Regime Ranging vs Grid: +30%] ";
        }

        // Rule: Extreme Greed + Long Direction = Penalty
        if (context.FearAndGreed?.Value > 80)
        {
            score *= 0.8f;
            reason += "[Extreme Greed Penalty: -20%] ";
        }

        return score;
    }

    private TradingDecision GetDecisionFromScore(int score)
    {
        if (score >= 70) return TradingDecision.Entry;
        if (score >= 50) return TradingDecision.Prepare;
        if (score >= 30) return TradingDecision.Context;
        return TradingDecision.Ignore;
    }
}
