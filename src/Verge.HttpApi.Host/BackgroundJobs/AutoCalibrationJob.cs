using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;
using Verge.Trading.DecisionEngine;

namespace Verge.Trading;

public class AutoCalibrationJob : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AutoCalibrationJob> _logger;

    public AutoCalibrationJob(IServiceProvider serviceProvider, ILogger<AutoCalibrationJob> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🧠 Auto-Calibration Job started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            // Run every 6 hours
            try
            {
                await PerformCalibrationAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in Auto-Calibration cycle");
            }

            await Task.Delay(TimeSpan.FromHours(6), stoppingToken);
        }
    }

    private async Task PerformCalibrationAsync()
    {
        using (var scope = _serviceProvider.CreateScope())
        {
            var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
            var calibrationRepository = scope.ServiceProvider.GetRequiredService<IRepository<StrategyCalibration, Guid>>();
            var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

            _logger.LogInformation("🔄 Starting Strategy Re-Calibration...");

            using (var uow = unitOfWorkManager.Begin())
            {
                var sessions = await sessionRepository.GetListAsync(s => !s.IsActive && s.Outcome != null);
                
                var styles = Enum.GetValues<TradingStyle>();
                var regimes = Enum.GetValues<MarketRegimeType>();

                foreach (var style in styles)
                {
                    foreach (var regime in regimes)
                    {
                        var contextSessions = sessions.Where(s => s.SelectedStyle == style && s.InitialRegime == regime).ToList();
                        
                        if (contextSessions.Count < 5) continue; // Not enough data to calibrate

                        int total = contextSessions.Count;
                        int wins = contextSessions.Count(s => s.Outcome == TradeStatus.Win);
                        double winRate = (double)wins / total;

                        var calibration = (await calibrationRepository.GetQueryableAsync())
                            .FirstOrDefault(c => c.Style == style && c.Regime == regime);

                        if (calibration == null)
                        {
                            calibration = new StrategyCalibration(Guid.NewGuid(), style, regime);
                            await calibrationRepository.InsertAsync(calibration);
                        }

                        // Adjustment Logic
                        if (winRate < 0.45)
                        {
                            // Performance is poor, tighten thresholds
                            calibration.EntryThresholdShift = Math.Min(30, calibration.EntryThresholdShift + 2);
                            _logger.LogWarning("🔍 Low WinRate ({winRate:P2}) for {Style} in {Regime}. Tightening thresholds (+2). Total Shift: {Shift}", winRate, style, regime, calibration.EntryThresholdShift);
                        }
                        else if (winRate > 0.65)
                        {
                            // Performance is great, loosen thresholds slightly
                            calibration.EntryThresholdShift = Math.Max(-15, calibration.EntryThresholdShift - 1);
                            _logger.LogInformation("🎯 High WinRate ({winRate:P2}) for {Style} in {Regime}. Loosening thresholds (-1). Total Shift: {Shift}", winRate, style, regime, calibration.EntryThresholdShift);
                        }

                        // Weight adjustments based on average score of wins vs losses could be added here
                        await calibrationRepository.UpdateAsync(calibration);
                    }
                }

                await uow.CompleteAsync();
            }

            _logger.LogInformation("✅ Strategy Re-Calibration completed.");
        }
    }
}
