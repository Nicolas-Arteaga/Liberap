using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine;

namespace Verge.Trading;

public class WhaleMonitoringJob : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<WhaleMonitoringJob> _logger;

    public WhaleMonitoringJob(IServiceProvider serviceProvider, ILogger<WhaleMonitoringJob> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🐳 Whale Monitoring Job started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using (var scope = _serviceProvider.CreateScope())
                {
                    var whaleTracker = scope.ServiceProvider.GetRequiredService<IWhaleTrackerService>();
                    await whaleTracker.ProcessExternalMovementsAsync();
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in Whale Monitoring cycle");
            }

            // Check every 15 minutes (Refined Lead Time requirement)
            await Task.Delay(TimeSpan.FromMinutes(15), stoppingToken);
        }
    }
}
