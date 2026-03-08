using System;
using System.Threading.Tasks;
using Xunit;
using Microsoft.Extensions.DependencyInjection;
using Verge.Trading;

namespace Verge.EntityFrameworkCore.Trading;

public class Execution_Tests : VergeEntityFrameworkCoreTestBase
{
    private readonly IExecutionAppService _executionAppService;

    public Execution_Tests()
    {
        _executionAppService = GetRequiredService<IExecutionAppService>();
    }

    [Fact]
    public async Task Run_ExecutionValidations_Manual()
    {
        var symbol = "BTCUSDT";

        // 1. Paper Trading Simulation
        var paperReport = await _executionAppService.RunPaperTradingSimulationAsync(symbol, simulatedDays: 30, runInBackground: false);
        
        var paperPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "papertrading_report.json");
        Assert.True(System.IO.File.Exists(paperPath), "Paper Trading Report JSON not found.");
        Console.WriteLine($"Paper Trading Passed: {paperReport.PassedPaperTrading} (Deviation: {paperReport.DeviationPercentage:P2})");
        Assert.True(paperReport.DeviationPercentage < 0.20m, "Paper Trading Deviation exceeded 20% limit.");

        // 2. Live Shadow Trading Simulation
        var shadowReport = await _executionAppService.RunLiveShadowAnalysisAsync(symbol, signalsToAnalyze: 100, runInBackground: false);

        var shadowPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "shadowtrading_report.json");
        Assert.True(System.IO.File.Exists(shadowPath), "Shadow Trading Report JSON not found.");
        Console.WriteLine($"Shadow Trading Passed: {shadowReport.PassedLiveShadow} (Signal Deviation: {shadowReport.SignalDeviationPercentage:P2})");
        Assert.True(shadowReport.SignalDeviationPercentage < 0.15m, "Shadow Trading Deviation exceeded 15% limit.");
    }
}
