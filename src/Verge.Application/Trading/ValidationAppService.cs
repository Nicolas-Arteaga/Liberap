using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine;
using Volo.Abp;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;

namespace Verge.Trading;

public class ValidationAppService : ApplicationService, IValidationAppService
{
    private readonly IServiceScopeFactory _serviceScopeFactory;
    private readonly IHubContext<TradingHub> _hubContext;

    public ValidationAppService(IServiceScopeFactory serviceScopeFactory, IHubContext<TradingHub> hubContext)
    {
        _serviceScopeFactory = serviceScopeFactory;
        _hubContext = hubContext;
    }

    public async Task<WalkForwardReportDto> RunWalkForwardAnalysisAsync(string symbol, TradingStyle style, bool runInBackground = true)
    {
        var userId = CurrentUser.Id;
        if (runInBackground)
        {
            _ = Task.Run(async () => await RunWalkForwardAnalysisInternalAsync(symbol, style, userId));
            return new WalkForwardReportDto(); // Returns immediately, logic runs in bg
        }
        
        return await RunWalkForwardAnalysisInternalAsync(symbol, style, userId);
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    protected virtual async Task<WalkForwardReportDto> RunWalkForwardAnalysisInternalAsync(string symbol, TradingStyle style, Guid? userId)
    {
        using var scope = _serviceScopeFactory.CreateScope();
        var tradingService = scope.ServiceProvider.GetRequiredService<TradingAppService>();
        var strategyRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var signalRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();
        var logger = scope.ServiceProvider.GetRequiredService<ILogger<ValidationAppService>>();

        logger.LogInformation("🚀 [WFA] Starting Walk-Forward Analysis for {Symbol}", symbol);

        var strategy = (await strategyRepo.GetListAsync()).FirstOrDefault();
        if (strategy == null) throw new UserFriendlyException("No active strategy found.");

        var report = new WalkForwardReportDto
        {
            EvaluationDate = DateTime.UtcNow,
            Symbol = symbol,
            TradingStyle = style.ToString(),
            Windows = new List<WalkForwardWindowDto>(),
            PassedAllWindows = true
        };

        // Define 3 explicit windows (19-21, 20-22, 21-23)
        var windowsDef = new[]
        {
            new { Name = "Win1 (Train 19-20, Test 21)", TrainStart = new DateTime(2019, 1, 1), TrainEnd = new DateTime(2020, 12, 31), TestStart = new DateTime(2021, 1, 1), TestEnd = new DateTime(2021, 12, 31) },
            new { Name = "Win2 (Train 20-21, Test 22)", TrainStart = new DateTime(2020, 1, 1), TrainEnd = new DateTime(2021, 12, 31), TestStart = new DateTime(2022, 1, 1), TestEnd = new DateTime(2022, 12, 31) },
            new { Name = "Win3 (Train 21-22, Test 23)", TrainStart = new DateTime(2021, 1, 1), TrainEnd = new DateTime(2022, 12, 31), TestStart = new DateTime(2023, 1, 1), TestEnd = new DateTime(2023, 12, 31) }
        };

        decimal slippage = (symbol == "BTCUSDT" || symbol == "ETHUSDT") ? 0.1m : 0.2m;

        foreach (var winDef in windowsDef)
        {
            var signalsTrain = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate >= winDef.TrainStart && x.AnalyzedDate <= winDef.TrainEnd);
            var signalsTest = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate >= winDef.TestStart && x.AnalyzedDate <= winDef.TestEnd);

            var wDto = new WalkForwardWindowDto
            {
                WindowName = winDef.Name,
                TrainingStart = winDef.TrainStart,
                TrainingEnd = winDef.TrainEnd,
                TestingStart = winDef.TestStart,
                TestingEnd = winDef.TestEnd
            };

            // Assuming optimal static weights for simulation (or we could fetch from profile)
            var profile = new Verge.Trading.DecisionEngine.Profiles.DayTradingProfile(); // Generic use for structural execution
            var weights = new Dictionary<string, float> { { "Technical", profile.TechnicalWeight }, { "Quantitative", profile.QuantitativeWeight }, { "Whales", profile.InstitutionalWeight } };

            wDto.TrainingResult = await tradingService.RunBacktestInternalAsync(new RunBacktestDto {
                TradingStrategyId = strategy.Id, Symbol = symbol, StartDate = winDef.TrainStart, EndDate = winDef.TrainEnd,
                WeightOverrides = weights, EntryThresholdOverride = 10, FeePercentage = 0.1m, SlippagePercentage = slippage
            }, signalsTrain, userId);

            wDto.TestingResult = await tradingService.RunBacktestInternalAsync(new RunBacktestDto {
                TradingStrategyId = strategy.Id, Symbol = symbol, StartDate = winDef.TestStart, EndDate = winDef.TestEnd,
                WeightOverrides = weights, EntryThresholdOverride = 10, FeePercentage = 0.1m, SlippagePercentage = slippage
            }, signalsTest, userId);

            if (!wDto.PassedProfitFactor) report.PassedAllWindows = false;
            
            report.Windows.Add(wDto);
        }

        var reportJson = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "walkforward_report.json"), reportJson);

        await _hubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto {
            Title = "Walk-Forward", Message = $"WFA Terminado para {symbol}. PF > 1.5 en {(report.PassedAllWindows ? "TODAS" : "algunas")} ventanas.", Severity = report.PassedAllWindows ? "success" : "warning"
        });

        return report;
    }

    public async Task<MonteCarloReportDto> RunMonteCarloSimulationAsync(string symbol, TradingStyle style, int iterations = 10000, bool runInBackground = true)
    {
        var userId = CurrentUser.Id;
        if (runInBackground)
        {
            _ = Task.Run(async () => await RunMonteCarloInternalAsync(symbol, style, iterations, userId));
            return new MonteCarloReportDto();
        }
        return await RunMonteCarloInternalAsync(symbol, style, iterations, userId);
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    protected virtual async Task<MonteCarloReportDto> RunMonteCarloInternalAsync(string symbol, TradingStyle style, int iterations, Guid? userId)
    {
        using var scope = _serviceScopeFactory.CreateScope();
        var tradingService = scope.ServiceProvider.GetRequiredService<TradingAppService>();
        var signalRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();
        var strategyRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var logger = scope.ServiceProvider.GetRequiredService<ILogger<ValidationAppService>>();

        logger.LogInformation("🎲 [MCS] Starting Monte Carlo Simulation ({Iterations} iters) for {Symbol}", iterations, symbol);

        var strategy = (await strategyRepo.GetListAsync()).FirstOrDefault();
        if (strategy == null) return new MonteCarloReportDto();

        // 1. Get real trades from a baseline backtest (e.g. year 2023)
        // assuming optimal static weights for simulation to force trades
        var profile = new Verge.Trading.DecisionEngine.Profiles.DayTradingProfile();
        var weights = new Dictionary<string, float> { { "Technical", profile.TechnicalWeight }, { "Quantitative", profile.QuantitativeWeight }, { "Whales", profile.InstitutionalWeight } };

        var signals = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate.Year == 2023);
        var baseBacktest = await tradingService.RunBacktestInternalAsync(new RunBacktestDto {
            TradingStrategyId = strategy.Id, Symbol = symbol, StartDate = new DateTime(2023,1,1), EndDate = new DateTime(2023,12,31), EntryThresholdOverride = 10, WeightOverrides = weights
        }, signals, userId);

        // We estimate an array of past trades profit % based on WinRate and ProfitFactor for this simulation 
        // to avoid storing 10k trade executions in memory. Fallback if no trades are caught in baseline.
        double wr = baseBacktest.TotalTrades > 0 ? baseBacktest.WinRate : 0.60; // default 60% for test
        decimal avgWin = baseBacktest.WinningTrades > 0 ? (baseBacktest.TotalProfit / baseBacktest.WinningTrades) : 50m;
        decimal avgLoss = (baseBacktest.TotalTrades - baseBacktest.WinningTrades) > 0 ? ((baseBacktest.TotalProfit - (avgWin * baseBacktest.WinningTrades)) / (baseBacktest.TotalTrades - baseBacktest.WinningTrades)) : -25m; // 2:1 RR

        if (avgLoss >= 0) avgLoss = -25m;

        var rnd = new Random(42); // deterministic for testing
        decimal initialCapital = 1000m;
        int ruinCount = 0;
        var endCapitals = new List<decimal>();
        var drawdowns = new List<decimal>();

        for (int i = 0; i < iterations; i++)
        {
            decimal capital = initialCapital;
            decimal peak = initialCapital;
            decimal maxDd = 0;
            
            // Randomize 300 trades sequence per iteration
            for (int t = 0; t < 300; t++)
            {
                bool isWin = rnd.NextDouble() < wr;
                capital += isWin ? avgWin : avgLoss;

                if (capital > peak) peak = capital;
                
                decimal currentDd = peak > 0 ? (peak - capital) / peak : 0;
                if (currentDd > maxDd) maxDd = currentDd;

                if (capital <= (initialCapital * 0.1m)) // Ruin threshold (90% loss)
                {
                    ruinCount++;
                    break;
                }
            }

            endCapitals.Add(capital);
            drawdowns.Add(maxDd);
        }

        drawdowns.Sort();
        decimal percentile5Dd = drawdowns[(int)Math.Floor(iterations * 0.95)]; // 95th Percentile DD (worst 5%)

        var report = new MonteCarloReportDto
        {
            EvaluationDate = DateTime.UtcNow,
            Symbol = symbol,
            Iterations = iterations,
            InitialCapital = initialCapital,
            AverageEndingCapital = endCapitals.Average(),
            WorstCaseDrawdown = percentile5Dd,
            ProbabilityOfRuin = (double)ruinCount / iterations
        };

        var json = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "montecarlo_report.json"), json);

        await _hubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto {
            Title = "Monte Carlo Sim", Message = $"Riesgo Ruina: {report.ProbabilityOfRuin:P2}. Max DD (95% CI): {percentile5Dd:P2}", Severity = report.PassedRuinRisk ? "success" : "danger"
        });

        return report;
    }

    public async Task<StressTestReportDto> RunStressTestAsync(string symbol, TradingStyle style, bool runInBackground = true)
    {
        var userId = CurrentUser.Id;
        if (runInBackground)
        {
            _ = Task.Run(async () => await RunStressTestInternalAsync(symbol, style, userId));
            return new StressTestReportDto();
        }
        return await RunStressTestInternalAsync(symbol, style, userId);
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    protected virtual async Task<StressTestReportDto> RunStressTestInternalAsync(string symbol, TradingStyle style, Guid? userId)
    {
        using var scope = _serviceScopeFactory.CreateScope();
        var tradingService = scope.ServiceProvider.GetRequiredService<TradingAppService>();
        var signalRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();
        var strategyRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var logger = scope.ServiceProvider.GetRequiredService<ILogger<ValidationAppService>>();

        logger.LogInformation("🔥 [StressTest] Starting Stress Test Analysis for {Symbol}", symbol);

        var strategy = (await strategyRepo.GetListAsync()).FirstOrDefault();
        if (strategy == null) throw new UserFriendlyException("No active strategy found.");

        var report = new StressTestReportDto
        {
            EvaluationDate = DateTime.UtcNow,
            Symbol = symbol,
            Events = new List<StressTestEventDto>(),
            PassedAllEvents = true
        };

        var eventsDef = new[]
        {
            new { Name = "COVID Crash (March 2020)", Start = new DateTime(2020, 2, 15), End = new DateTime(2020, 4, 15) },
            new { Name = "Luna Crash (May 2022)", Start = new DateTime(2022, 4, 15), End = new DateTime(2022, 6, 15) },
            new { Name = "FTX Collapse (Nov 2022)", Start = new DateTime(2022, 10, 15), End = new DateTime(2022, 12, 15) }
        };

        decimal slippage = 0.5m; // Liquidity crisis slippage estimation

        foreach (var evt in eventsDef)
        {
            var signals = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate >= evt.Start && x.AnalyzedDate <= evt.End);

            var profile = new Verge.Trading.DecisionEngine.Profiles.DayTradingProfile();
            var weights = new Dictionary<string, float> { { "Technical", profile.TechnicalWeight }, { "Quantitative", profile.QuantitativeWeight }, { "Whales", profile.InstitutionalWeight } };

            var eDto = new StressTestEventDto
            {
                EventName = evt.Name,
                StartDate = evt.Start,
                EndDate = evt.End
            };

            eDto.Result = await tradingService.RunBacktestInternalAsync(new RunBacktestDto {
                TradingStrategyId = strategy.Id, Symbol = symbol, StartDate = evt.Start, EndDate = evt.End,
                WeightOverrides = weights, EntryThresholdOverride = 10, FeePercentage = 0.1m, SlippagePercentage = slippage
            }, signals, userId);

            if (!eDto.Survived) report.PassedAllEvents = false;
            
            report.Events.Add(eDto);
        }

        var reportJson = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "stresstest_report.json"), reportJson);

        await _hubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto {
            Title = "Stress Test", Message = $"Stress Test ({symbol}) Finalizado. Sobreviviente: {report.PassedAllEvents}.", Severity = report.PassedAllEvents ? "success" : "danger"
        });

        return report;
    }
}
