using System;
using System.Collections.Generic;
using Verge.Trading;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DecisionEngine.Factory;
using Microsoft.Extensions.Logging.Abstractions;
using Shouldly;
using Xunit;

namespace Verge.Trading.Trading;

public class DecisionEngine_Profile_Tests
{
    private readonly ITradingDecisionEngine _engine;

    public DecisionEngine_Profile_Tests()
    {
        _engine = new TradingDecisionEngine(NullLogger<TradingDecisionEngine>.Instance);
    }

    [Fact]
    public void Should_Ignore_Scalping_If_Invalid_Regime()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.Ranging }, // Scalping hates range
            Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 25 }
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.Scalping, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("Invalid Regime 'Ranging' for Scalping style");
    }

    [Fact]
    public void Should_Ignore_Scalping_If_RSI_Outside_Range()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend },
            Technicals = new TechnicalsResponseModel { Rsi = 45, Adx = 25 } // Scalping needs RSI 60-75
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.Scalping, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("outside momentum range (60-75)");
    }

    [Fact]
    public void Should_Accept_GridTrading_In_Ranging_Market()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.Ranging }, 
            Technicals = new TechnicalsResponseModel { Adx = 15 } // Grid loves ADX < 20
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.GridTrading, context);

        // Assert
        result.Decision.ShouldNotBe(TradingDecision.Ignore);
    }

    [Fact]
    public void Should_Ignore_Position_If_Extreme_Greed()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend },
            Technicals = new TechnicalsResponseModel { Adx = 30 },
            FearAndGreed = new Integrations.FearAndGreedResult { Value = 85 } // Position hates extremes
        };

        // Act
        var result = _engine.Evaluate(session, TradingStyle.PositionTrading, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("F&G 85 outside stable range (40-75)");
    }
}
