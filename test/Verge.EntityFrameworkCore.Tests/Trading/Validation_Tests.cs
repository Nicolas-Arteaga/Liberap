using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Xunit;
using Microsoft.Extensions.DependencyInjection;
using Verge.Trading;
using Volo.Abp.Domain.Repositories;

namespace Verge.EntityFrameworkCore.Trading;

public class Validation_Tests : VergeEntityFrameworkCoreTestBase
{
    private readonly IValidationAppService _validationAppService;
    private readonly ITradingAppService _tradingAppService;
    private readonly IRepository<TradingStrategy, Guid> _strategyRepository;
    private readonly IRepository<TradingSignal, Guid> _signalRepository;

    public Validation_Tests()
    {
        _validationAppService = GetRequiredService<IValidationAppService>();
        _tradingAppService = GetRequiredService<ITradingAppService>();
        _strategyRepository = GetRequiredService<IRepository<TradingStrategy, Guid>>();
        _signalRepository = GetRequiredService<IRepository<TradingSignal, Guid>>();
    }

    [Fact]
    public async Task Run_HedgeFund_Validations_Manual()
    {
        // 1. Seed strategy
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Hedge Fund Test Strategy");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\"]";
        strategy.Style = TradingStyle.DayTrading;
        await _strategyRepository.InsertAsync(strategy);

        // 2. Seed mock signals across 2019-2023 for Walk-Forward
        var symbol = "BTCUSDT";
        for (int year = 2019; year <= 2023; year++)
        {
            for (int month = 1; month <= 12; month++)
            {
                for (int day = 1; day <= 28; day += 2) // High frequency of signals
                {
                    var signal = new TradingSignal(
                        Guid.NewGuid(),
                        symbol,
                        day % 2 == 0 ? SignalDirection.Long : SignalDirection.Short,
                        10000 + year * 1000 + month * 100, // Dummy price
                        SignalConfidence.High,
                        2.5m // Good Risk/Reward
                    );
                    signal.AnalyzedDate = new DateTime(year, month, day, 12, 0, 0, DateTimeKind.Utc);
                    await _signalRepository.InsertAsync(signal);
                }
            }
        }

        // 3. Execute Walk-Forward Analysis (WFA)
        var wfaReport = await _validationAppService.RunWalkForwardAnalysisAsync(symbol, TradingStyle.DayTrading, runInBackground: false);
        
        // 4. Verify WFA Report
        var wfaPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "walkforward_report.json");
        Assert.True(System.IO.File.Exists(wfaPath), "WFA Report JSON not found.");
        Console.WriteLine($"WFA Passed All Windows: {wfaReport.PassedAllWindows}");

        // 5. Execute Monte Carlo Simulation (MCS)
        var mcsReport = await _validationAppService.RunMonteCarloSimulationAsync(symbol, TradingStyle.DayTrading, iterations: 10000, runInBackground: false);

        // 6. Verify MCS Report
        var mcsPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "montecarlo_report.json");
        Assert.True(System.IO.File.Exists(mcsPath), "MCS Report JSON not found.");
        Console.WriteLine($"MCS Probability of Ruin: {mcsReport.ProbabilityOfRuin:P2}");
        Console.WriteLine($"MCS Worst Case Drawdown: {mcsReport.WorstCaseDrawdown:P2}");
    }

    [Fact]
    public async Task Run_StressTest_Manual()
    {
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Stress Test Strategy");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\"]";
        strategy.Style = TradingStyle.DayTrading;
        await _strategyRepository.InsertAsync(strategy);

        var symbol = "BTCUSDT";

        // Seed COVID Crash (March 2020) Mock Signals
        for (int day = 15; day <= 25; day++)
        {
            var signal = new TradingSignal(Guid.NewGuid(), symbol, SignalDirection.Short, 8000 - day * 100, SignalConfidence.High, 5m);
            signal.AnalyzedDate = new DateTime(2020, 3, day, 12, 0, 0, DateTimeKind.Utc);
            await _signalRepository.InsertAsync(signal);
        }

        var report = await _validationAppService.RunStressTestAsync(symbol, TradingStyle.DayTrading, runInBackground: false);

        var reportPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "stresstest_report.json");
        Assert.True(System.IO.File.Exists(reportPath), "Stress Test Report JSON not found.");
        Console.WriteLine($"Stress Test Passed All Events: {report.PassedAllEvents}");
    }
}
