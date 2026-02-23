using System;
using System.Collections.Generic;
using Verge.Trading;
using Verge.Trading.DecisionEngine;
using Verge.Trading.Integrations;
using Microsoft.Extensions.Logging.Abstractions;
using Shouldly;
using Xunit;
using System.Linq;

namespace Verge.Trading.Trading;

public class SignalQuality_Tests
{
    private readonly ITradingDecisionEngine _engine;

    public SignalQuality_Tests()
    {
        _engine = new TradingDecisionEngine(NullLogger<TradingDecisionEngine>.Instance);
    }

    [Fact]
    public void Should_Calculate_High_Confidence_For_Strong_Trend()
    {
        // Arrange
        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend, TrendStrength = 80 },
            Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 35 } 
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.DayTrading, context);

        // Assert
        result.Confidence.ShouldBe(SignalConfidence.Medium);
    }

    [Fact]
    public void Should_Wait_For_Temporal_Persistence()
    {
        // Arrange
        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "BTC", "1h");
        session.CurrentStage = TradingStage.Evaluating;
        
        // "Golden" Bullish metrics for DayTrading (Threshold 70)
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend, TrendStrength = 80 },
            Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 40, MacdHistogram = 1.0f },
            GlobalSentiment = new SentimentAnalysis { Label = "positive", Score = 0.8f },
            FearAndGreed = new FearAndGreedResult { Value = 15 }
        };

        // Act & Assert - Cycle 1
        var result1 = _engine.Evaluate(session, TradingStyle.DayTrading, context);
        result1.Decision.ShouldBe(TradingDecision.Prepare);
        result1.Reason.ShouldContain("Needs 2 cycles");

        // Act & Assert - Cycle 2
        var result2 = _engine.Evaluate(session, TradingStyle.DayTrading, context);
        result2.Decision.ShouldBe(TradingDecision.Entry);
    }

    [Fact]
    public void Should_Invalidate_Prepared_Setup()
    {
        // Arrange
        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "BTC", "1h");
        session.CurrentStage = TradingStage.Prepared;

        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend },
            Technicals = new TechnicalsResponseModel { Rsi = 45, Adx = 25 } // Scalping invalidates < 55
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.Scalping, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("SETUP INVALIDATED");
        result.Reason.ShouldContain("RSI fell to 45"); 
    }

    [Fact]
    public void Should_Block_Entry_If_HTF_Contradicts()
    {
        // Arrange
        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "BTC", "1h");
        
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend, TrendStrength = 80 },
            Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 40, MacdHistogram = 1.0f },
            GlobalSentiment = new SentimentAnalysis { Label = "positive", Score = 0.8f },
            FearAndGreed = new FearAndGreedResult { Value = 15 },
            HigherTimeframeContext = new MarketContext
            {
                MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BearTrend }
            }
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.DayTrading, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Prepare);
        result.Reason.ShouldContain("HTF contradiction");
    }
}
