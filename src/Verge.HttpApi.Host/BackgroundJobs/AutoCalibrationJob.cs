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

                        // 🏆 Phase 4: Neural Weight Sensitivity Adjustment
                        var winsWithScores = contextSessions.Where(s => s.Outcome == TradeStatus.Win && !string.IsNullOrEmpty(s.InitialWeightedScoresJson)).ToList();
                        var lossesWithScores = contextSessions.Where(s => s.Outcome != TradeStatus.Win && !string.IsNullOrEmpty(s.InitialWeightedScoresJson)).ToList();

                        if (winsWithScores.Any() || lossesWithScores.Any())
                        {
                            _logger.LogInformation("🧠 [Neural Calibration] {Style} - {Regime}: Analyzing sensitivity across {Count} sessions...", style, regime, winsWithScores.Count + lossesWithScores.Count);
                            
                            // Simple Delta Analysis: Increase multiplier if a component was stronger in wins than in losses
                            AdjustComponentMultiplier(calibration, "Technical", winsWithScores, lossesWithScores, c => c.TechnicalMultiplier, (c, v) => c.TechnicalMultiplier = v);
                            AdjustComponentMultiplier(calibration, "Sentiment", winsWithScores, lossesWithScores, c => c.SentimentMultiplier, (c, v) => c.SentimentMultiplier = v);
                            AdjustComponentMultiplier(calibration, "Institutional", winsWithScores, lossesWithScores, c => c.InstitutionalMultiplier, (c, v) => c.InstitutionalMultiplier = v);
                            AdjustComponentMultiplier(calibration, "Quantitative", winsWithScores, lossesWithScores, c => c.QuantitativeMultiplier, (c, v) => c.QuantitativeMultiplier = v);
                        }

                        // Threshold adjustments based on raw WinRate
                        if (winRate < 0.45)
                        {
                            calibration.EntryThresholdShift = Math.Min(30, calibration.EntryThresholdShift + 2);
                        }
                        else if (winRate > 0.65)
                        {
                            calibration.EntryThresholdShift = Math.Max(-15, calibration.EntryThresholdShift - 1);
                        }

                        calibration.LastRecalibrated = DateTime.UtcNow;
                        await calibrationRepository.UpdateAsync(calibration);
                    }
                }

                await uow.CompleteAsync();
            }

            _logger.LogInformation("✅ Strategy Re-Calibration completed.");
        }
    }

    private void AdjustComponentMultiplier(
        StrategyCalibration calibration, 
        string component, 
        List<TradingSession> wins, 
        List<TradingSession> losses, 
        Func<StrategyCalibration, float> getter, 
        Action<StrategyCalibration, float> setter)
    {
        double avgWin = wins.Any() ? wins.Average(s => GetScoreForComponent(s, component)) : 0;
        double avgLoss = losses.Any() ? losses.Average(s => GetScoreForComponent(s, component)) : 0;

        float current = getter(calibration);
        if (avgWin > avgLoss + 5) // Strong positive correlation with winning
        {
            setter(calibration, Math.Min(2.5f, current + 0.05f));
        }
        else if (avgLoss > avgWin + 5) // Component often high in losing sessions
        {
            setter(calibration, Math.Max(0.5f, current - 0.05f));
        }
    }

    private float GetScoreForComponent(TradingSession session, string key)
    {
        try 
        {
            if (string.IsNullOrEmpty(session.InitialWeightedScoresJson)) return 0;
            var scores = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, float>>(session.InitialWeightedScoresJson);
            return scores != null && scores.TryGetValue(key, out float val) ? val : 0;
        }
        catch { return 0; }
    }
}
