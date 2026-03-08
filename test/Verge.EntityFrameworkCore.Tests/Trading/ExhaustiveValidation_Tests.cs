using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Xunit;
using Microsoft.Extensions.DependencyInjection;
using Verge.Trading;
using Volo.Abp.Domain.Repositories;

namespace Verge.EntityFrameworkCore.Trading;

public class ExhaustiveValidation_Tests : VergeEntityFrameworkCoreTestBase
{
    private readonly ITradingAppService _tradingAppService;
    private readonly IRepository<TradingStrategy, Guid> _strategyRepository;
    private readonly IRepository<TradingSignal, Guid> _signalRepository;

    public ExhaustiveValidation_Tests()
    {
        _tradingAppService = GetRequiredService<ITradingAppService>();
        _strategyRepository = GetRequiredService<IRepository<TradingStrategy, Guid>>();
        _signalRepository = GetRequiredService<IRepository<TradingSignal, Guid>>();
    }

    [Fact]
    public async Task Run_Exhaustive_Validation_Manual()
    {
        // 1. Seed strategy
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Hedge Fund Test Strategy");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\", \"ETHUSDT\"]";
        strategy.Style = TradingStyle.Scalping;
        await _strategyRepository.InsertAsync(strategy);

        // 2. Seed mock signals for 2023 (Training) and 2024 (Testing)
        var symbols = new[] { "BTCUSDT", "ETHUSDT" };
        foreach (var symbol in symbols)
        {
            // Seed 2023 (Training) - A very good year in this simulation (Win probability mostly high)
            for (int month = 1; month <= 12; month++)
            {
                for (int day = 1; day <= 28; day += 2) // Roughly 14 trades a month
                {
                    var signal = new TradingSignal(
                        Guid.NewGuid(),
                        symbol,
                        day % 2 == 0 ? SignalDirection.Long : SignalDirection.Short,
                        40000 + month * 1000,
                        SignalConfidence.High,
                        2.5m // Good Risk/Reward
                    );
                    signal.AnalyzedDate = new DateTime(2023, month, day, 12, 0, 0, DateTimeKind.Utc);
                    await _signalRepository.InsertAsync(signal);
                }
            }

            // Seed 2024 (Testing - OOS) - Slightly more challenging but still positive
            for (int month = 1; month <= 12; month++)
            {
                for (int day = 1; day <= 28; day += 3) // Roughly 9 trades a month
                {
                    var signal = new TradingSignal(
                        Guid.NewGuid(),
                        symbol,
                        day % 2 == 0 ? SignalDirection.Long : SignalDirection.Short,
                        50000 + month * 1000,
                        SignalConfidence.Medium,
                        2.0m // Standard Risk/Reward
                    );
                    signal.AnalyzedDate = new DateTime(2024, month, day, 12, 0, 0, DateTimeKind.Utc);
                    await _signalRepository.InsertAsync(signal);
                }
            }
        }

        // 3. Execute Exhaustive Validation
        var testSymbols = new List<string> { "BTCUSDT", "ETHUSDT" };
        await _tradingAppService.RunExhaustiveValidationAsync(testSymbols, false);
        
        // 4. Verify the report file was created
        var reportPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "exhaustive_validation_report.json");
        Assert.True(System.IO.File.Exists(reportPath), "Report JSON not found.");
        
        // Output log info
        var reportJson = await System.IO.File.ReadAllTextAsync(reportPath);
        Console.WriteLine(reportJson);
    }
}
