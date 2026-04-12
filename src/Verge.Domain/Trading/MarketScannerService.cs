using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

using Verge.Trading.Integrations;
using Verge.Trading.DecisionEngine;
using Volo.Abp.EventBus.Distributed;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class MarketScannerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<MarketScannerService> _logger;
    private readonly IDistributedEventBus _eventBus;

    public MarketScannerService(
        IServiceProvider serviceProvider, 
        ILogger<MarketScannerService> logger,
        IDistributedEventBus eventBus)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _eventBus = eventBus;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 Market Scanner Service started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ScanMarketAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in market scanner cycle");
            }

            _logger.LogInformation("😴 Scanner sleeping for 30 seconds...");
            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }

    private async Task ScanMarketAsync()
    {
        _logger.LogInformation("🔍 Starting market scan at {time}", DateTime.UtcNow);

        using var scope = _serviceProvider.CreateScope();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var analysisService = scope.ServiceProvider.GetRequiredService<CryptoAnalysisService>();
        var freeNewsService = scope.ServiceProvider.GetRequiredService<IFreeCryptoNewsService>();
        var pythonService = scope.ServiceProvider.GetRequiredService<IPythonIntegrationService>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        var profileRepository = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var analysisLogRepo = scope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
        var alertHistoryRepo = scope.ServiceProvider.GetRequiredService<IRepository<AlertHistory, Guid>>();
        var whaleTracker = scope.ServiceProvider.GetRequiredService<IWhaleTrackerService>();
        var institutionalService = scope.ServiceProvider.GetRequiredService<IInstitutionalDataService>();
        var multiAgentConsensus = scope.ServiceProvider.GetRequiredService<IMultiAgentConsensusService>();
        var macroService = scope.ServiceProvider.GetRequiredService<IMacroSentimentService>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        var aniquilador = scope.ServiceProvider.GetRequiredService<IAniquiladorPatternManager>();

        using var uow = unitOfWorkManager.Begin();

        // 0. Macro Check (Sprint 5) - Affects entire scan cycle
        var macroData = await macroService.GetMacroSentimentAsync();
        if (macroData.IsInQuietPeriod) {
            _logger.LogWarning("🌍 QUIET PERIOD ACTIVE: {reason}. Skipping scanners or dampening entries...", macroData.QuietPeriodReason);
        }

        // Top 30 symbols by volume (Phase 4 Scaling)
        var topSymbols = await marketDataManager.GetTopSymbolsAsync(100);
        _logger.LogInformation("📊 Top 30 symbols to analyze ({count}). Analyzing...", topSymbols.Count);

        int analyzedCount = 0;
        var semaphore = new SemaphoreSlim(10); // Analyze 10 symbols concurrently

        var tasks = topSymbols.Select(async symbol =>
        {
            await semaphore.WaitAsync();
            try
            {
                using var innerScope = _serviceProvider.CreateScope();
                // Get fresh services for each parallel task to avoid DbContext threading issues
                var innerMarketManager = innerScope.ServiceProvider.GetRequiredService<MarketDataManager>();
                var innerAnalysisService = innerScope.ServiceProvider.GetRequiredService<CryptoAnalysisService>();
                var innerPython = innerScope.ServiceProvider.GetRequiredService<IPythonIntegrationService>();
                var innerConsensus = innerScope.ServiceProvider.GetRequiredService<IMultiAgentConsensusService>();
                var innerEventBus = innerScope.ServiceProvider.GetRequiredService<IDistributedEventBus>();
                var innerAlertRepo = innerScope.ServiceProvider.GetRequiredService<IRepository<AlertHistory, Guid>>();
                var innerProfileRepo = innerScope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                var innerAnalysisLogRepo = innerScope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
                var innerWhaleTracker = innerScope.ServiceProvider.GetRequiredService<IWhaleTrackerService>();
                var innerInstService = innerScope.ServiceProvider.GetRequiredService<IInstitutionalDataService>();
                var innerNewsService = innerScope.ServiceProvider.GetRequiredService<IFreeCryptoNewsService>();

                var innerAniquilador = innerScope.ServiceProvider.GetRequiredService<IAniquiladorPatternManager>();

                _logger.LogInformation("🧪 Analizando {symbol} (Parallel)...", symbol);
                
                var candles = await innerMarketManager.GetCandlesAsync(symbol, "15", 30);
                if (candles == null || candles.Count < 20) return;

                // 🎯 [ANIQUILADOR] Analyze hourly trend
                try {
                    var hourly = await innerMarketManager.GetCandlesAsync(symbol, "1h", 100);
                    if (hourly != null && hourly.Count >= 50)
                        await innerAniquilador.AnalyzeCandlesAsync(symbol, hourly);
                } catch { /* Isolated error */ }

                var prices = candles.Select(x => x.Close).ToList();
                var rsi = innerAnalysisService.CalculateRSI(prices);
                
                // 🕵️ AI Market Context (Python)
                var regime = await innerPython.DetectMarketRegimeAsync(symbol, "15", candles);
                var pythonTechs = await innerPython.AnalyzeTechnicalsAsync(symbol, "15", candles);

                // IA Local & Analysts
                var whaleData = await innerWhaleTracker.GetWhaleActivityAsync(symbol);
                var instData = await innerInstService.GetInstitutionalDataAsync(symbol);
                
                // 🧠 Multi-Agent Consensus
                int confidence = (int)rsi > 50 ? (int)(rsi - 50) : (int)(50 - rsi);
                SignalDirection signal = SignalDirection.Auto;

                if (regime != null)
                {
                    confidence += (int)(regime.TrendStrength * 50);
                    if (regime.BosDetected) confidence += 10;
                    
                    if (regime.Regime == MarketRegimeType.BullTrend) signal = SignalDirection.Long;
                    else if (regime.Regime == MarketRegimeType.BearTrend) signal = SignalDirection.Short;
                }

                // Add bonuses
                if (whaleData.NetFlowScore > 0.6) confidence += 10;
                if (instData.IsSqueezeDetected || instData.BidAskImbalance > 1.5) confidence += 10;
                confidence = Math.Clamp(confidence, 10, 95);

                var currentPrice = candles.LastOrDefault()?.Close ?? 0;
                var severity = confidence >= 70 ? "success" : (confidence >= 50 ? "warning" : "info");
                var icon = confidence >= 50 ? "search-outline" : "pulse-outline";

                // Final result broadcasting ASAP
                var profiles = await innerProfileRepo.GetListAsync();
                var innerSessionRepo = innerScope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
                var sessions = await innerSessionRepo.GetListAsync(x => x.IsActive);

                foreach (var profile in profiles)
                {
                    var userSessionId = sessions.FirstOrDefault(s => s.TraderProfileId == profile.Id)?.Id ?? Guid.Empty;
                    
                    await innerEventBus.PublishAsync(new AlertStateChangedEto
                    {
                        UserId = profile.UserId,
                        SessionId = userSessionId,
                        Alert = new VergeAlertDto
                        {
                            Id = Guid.NewGuid().ToString(),
                            Type = "ScannerUpdate", 
                            Title = $"Scanner: {symbol}",
                            Message = $"AI Score: {confidence}% | Regime: {regime?.Regime.ToString() ?? "Unknown"} | {whaleData.Summary}",
                            Crypto = symbol,
                            Price = currentPrice,
                            Confidence = (SignalConfidence)confidence,
                            Direction = signal,
                            Score = confidence,
                            Severity = severity,
                            Icon = icon,
                            Timestamp = DateTime.UtcNow,
                            TakeProfit = currentPrice * (signal == SignalDirection.Long ? 1.03m : 0.97m),
                            StopLoss = currentPrice * (signal == SignalDirection.Long ? 0.985m : 1.015m)
                        }
                    });

                    _logger.LogInformation("📢 [SignalR] Published AI alert {score}% for {symbol} to EventBus for User {uid}", confidence, symbol, profile.UserId);
                }
                
                Interlocked.Increment(ref analyzedCount);
            }
            catch (Exception ex)
            {
                _logger.LogWarning($"⚠️ Error analizando {symbol}: {ex.Message}");
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);

        await uow.CompleteAsync();
        _logger.LogInformation("🏁 Ciclo completado. Se analizaron {count} símbolos", analyzedCount);
    }
}
