using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Xunit;
using Microsoft.Extensions.DependencyInjection;
using Verge.Trading;
using Volo.Abp.Domain.Repositories;
using System.Linq;

namespace Verge.EntityFrameworkCore.Trading;

public class ComparativeEvaluation_Tests : VergeEntityFrameworkCoreTestBase
{
    private readonly ITradingAppService _tradingAppService;
    private readonly IRepository<TradingStrategy, Guid> _strategyRepository;
    private readonly IRepository<TradingSignal, Guid> _signalRepository;

    public ComparativeEvaluation_Tests()
    {
        _tradingAppService = GetRequiredService<ITradingAppService>();
        _strategyRepository = GetRequiredService<IRepository<TradingStrategy, Guid>>();
        _signalRepository = GetRequiredService<IRepository<TradingSignal, Guid>>();
    }

    [Fact]
    public async Task Run_Comparative_Evaluation_Manual()
    {
        // 1. Seed necessary data
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Institutional Strategy");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\", \"ETHUSDT\"]";
        strategy.Style = TradingStyle.Scalping;
        await _strategyRepository.InsertAsync(strategy);

        // Seed some mock signals for the last 30 days
        var symbols = new[] { "BTCUSDT", "ETHUSDT" };
        foreach (var symbol in symbols)
        {
            for (int i = 0; i < 10; i++)
            {
                var signal = new TradingSignal(
                    Guid.NewGuid(),
                    symbol,
                    i % 2 == 0 ? SignalDirection.Long : SignalDirection.Short,
                    50000 + i * 100,
                    SignalConfidence.High,
                    2.5m
                );
                signal.AnalyzedDate = DateTime.UtcNow.AddDays(-i);
                await _signalRepository.InsertAsync(signal);
            }
        }

        // 2. Execute evaluation
        var testSymbols = new List<string> { "BTCUSDT", "ETHUSDT" };
        await _tradingAppService.RunComparativeEvaluationAsync(testSymbols, false);
        
        // 3. Verify the file was created
        var reportPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "comparative_evaluation_report.json");
        Assert.True(System.IO.File.Exists(reportPath));
        
        // Output some log info (optional, just to see what happened)
        var reportJson = await System.IO.File.ReadAllTextAsync(reportPath);
        Console.WriteLine(reportJson);
    }
}
