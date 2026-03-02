using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine;

namespace Verge.Trading;

public class MacroCalendarJob : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<MacroCalendarJob> _logger;

    public MacroCalendarJob(IServiceProvider serviceProvider, ILogger<MacroCalendarJob> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🌍 Macro Calendar Sync Job started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using (var scope = _serviceProvider.CreateScope())
                {
                    var macroService = scope.ServiceProvider.GetRequiredService<IMacroSentimentService>();
                    _logger.LogInformation("🔄 Syncing economic calendar...");
                    await macroService.SyncEconomicCalendarAsync();
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in Macro Calendar cycle");
            }

            // Sync calendar every 4 hours
            await Task.Delay(TimeSpan.FromHours(4), stoppingToken);
        }
    }
}
