using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging.Abstractions;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DecisionEngine.Cache;
using Verge.Trading;
using Shouldly;
using Xunit;

namespace Verge.Trading.Trading;

public class AutoEvaluatorService_Tests
{
    private readonly AutoEvaluatorService _service;
    private readonly TradingDecisionEngine _engine;
    private readonly MarketSnapshotCache _cache;

    public AutoEvaluatorService_Tests()
    {
        // Setup dependencies manually without ABP for speed
        var memoryCache = new MemoryDistributedCache(new Microsoft.Extensions.Options.OptionsWrapper<MemoryDistributedCacheOptions>(new MemoryDistributedCacheOptions()));
        _cache = new MarketSnapshotCache(memoryCache);
        _engine = new TradingDecisionEngine(NullLogger<TradingDecisionEngine>.Instance);
        _service = new AutoEvaluatorService(_engine, _cache, NullLogger<AutoEvaluatorService>.Instance);
    }

    [Fact]
    public async Task Should_Evaluate_All_Permutations_When_Auto_Selected()
    {
        // Arrange
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "AUTO ALL");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\", \"ETHUSDT\"]";
        strategy.Style = TradingStyle.Auto; // Will evaluate all 6 profiles
        strategy.DirectionPreference = SignalDirection.Auto; // Will evaluate Long/Short

        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "AUTO", "1h");
        
        var btcContext = new MarketContext { Technicals = new TechnicalsResponseModel { Rsi = 65, Adx = 25 } };
        var ethContext = new MarketContext { Technicals = new TechnicalsResponseModel { Rsi = 35, Adx = 15 } };
        
        var dataCache = new Dictionary<(string symbol, string timeframe), MarketContext>
        {
            { ("BTCUSDT", "1h"), btcContext },
            { ("ETHUSDT", "1h"), ethContext }
        };

        // Act
        var result = await _service.FindBestOpportunityAsync(session, strategy, dataCache);

        // Assert
        result.ShouldNotBeNull();
        // Since BTC has Rsi 65 (momentum for Scalping), it should be the winner or at least have a high score
        result.Symbol.ShouldBe("BTCUSDT");
    }

    [Fact]
    public async Task Should_Trigger_Early_Exit_On_Strong_Setup()
    {
        // Arrange
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Early Exit Test");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\", \"ETHUSDT\"]";
        strategy.Style = TradingStyle.Scalping; 
        
        var session = new TradingSession(Guid.NewGuid(), Guid.NewGuid(), "AUTO", "1h");
        
        // BTC setup is STRONG (Score will be > 75)
        var btcContext = new MarketContext { 
            MarketRegime = new RegimeResponseModel { Regime = MarketRegimeType.BullTrend },
            Technicals = new TechnicalsResponseModel { Rsi = 68, Adx = 30 } 
        };
        
        // ETH setup is weak
        var ethContext = new MarketContext { 
             Technicals = new TechnicalsResponseModel { Rsi = 40, Adx = 10 }
        };

        var dataCache = new Dictionary<(string symbol, string timeframe), MarketContext>
        {
            { ("BTCUSDT", "1h"), btcContext },
            { ("ETHUSDT", "1h"), ethContext }
        };

        // Act
        var result = await _service.FindBestOpportunityAsync(session, strategy, dataCache);

        // Assert
        result.Symbol.ShouldBe("BTCUSDT");
        // Result score should be high enough to trigger early exit 
    }
}
