using System;
using System.Collections.Generic;
using Verge.Trading;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DecisionEngine.Factory;
using Microsoft.Extensions.Logging.Abstractions;
using Shouldly;
using Xunit;
using NSubstitute;
using Volo.Abp.Domain.Repositories;
using System.Threading.Tasks;

namespace Verge.Trading.Trading;

public class DecisionEngine_Profile_Tests
{
    private readonly ITradingDecisionEngine _engine;
    private readonly IProbabilisticEngine _probEngine;

    public DecisionEngine_Profile_Tests()
    {
        _probEngine = Substitute.For<IProbabilisticEngine>();
        _probEngine.GetWinRateAsync(Arg.Any<TradingStyle>(), Arg.Any<string>(), Arg.Any<MarketRegimeType>(), Arg.Any<int>(), Arg.Any<DateTime>())
            .Returns(new WinRateResult { Probability = 0.5, SampleSize = 0 });
        var calibRepo = Substitute.For<IRepository<StrategyCalibration, Guid>>();
        var whaleTracker = Substitute.For<IWhaleTrackerService>();
        var instService = Substitute.For<IInstitutionalDataService>();
        var macroService = Substitute.For<IMacroSentimentService>();

        var aiConsensus = Substitute.For<IMultiAgentConsensusService>();
        aiConsensus.GetConsensusAsync(Arg.Any<MarketContext>(), Arg.Any<TradingStyle>())
            .Returns(new AgentConsensusResult { Score = 50, Reasoning = "Test AI Opinion" });

        _engine = new TradingDecisionEngine(
            NullLogger<TradingDecisionEngine>.Instance,
            _probEngine,
            calibRepo,
            whaleTracker,
            instService,
            macroService,
            aiConsensus);
    }

    [Fact]
    public async Task Should_Ignore_Scalping_If_Invalid_Regime()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.Ranging }, // Scalping hates range
            Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 25 }
        };

        // Act
        var result = await _engine.EvaluateAsync(session, TradingStyle.Scalping, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("Invalid Regime 'Ranging' for Scalping style");
    }

    [Fact]
    public async Task Should_Ignore_Scalping_If_RSI_Outside_Range()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend },
            Technicals = new TechnicalsResponseModel { Rsi = 45, Adx = 25 } // Scalping needs RSI 60-75
        };

        // Act
        var result = await _engine.EvaluateAsync(session, TradingStyle.Scalping, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("outside momentum range (60-75)");
    }

    [Fact]
    public async Task Should_Accept_GridTrading_In_Ranging_Market()
    {
        // Arrange
        var session = new TradingSession(System.Guid.NewGuid(), System.Guid.NewGuid(), "BTC", "1h");
        var context = new MarketContext
        {
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.Ranging }, 
            Technicals = new TechnicalsResponseModel { Adx = 15 } // Grid loves ADX < 20
        };

        // Act
        var result = await _engine.EvaluateAsync(session, TradingStyle.GridTrading, context);

        // Assert
        result.Decision.ShouldNotBe(TradingDecision.Ignore);
    }

    [Fact]
    public async Task Should_Ignore_Position_If_Extreme_Greed()
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
        var result = await _engine.EvaluateAsync(session, TradingStyle.PositionTrading, context);

        // Assert
        result.Decision.ShouldBe(TradingDecision.Ignore);
        result.Reason.ShouldContain("F&G 85 outside stable range (40-75)");
    }
}
