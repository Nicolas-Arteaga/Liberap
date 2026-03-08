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

namespace Verge.Trading.BackgroundJobs;

public class LiveSignalCollectorJob : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<LiveSignalCollectorJob> _logger;
    private const int CheckIntervalMinutes = 60; // Run every 1H

    public LiveSignalCollectorJob(IServiceProvider serviceProvider, ILogger<LiveSignalCollectorJob> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("📡 Live Signal Collector Job started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ProcessLiveSignalsAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in Live Signal Collector cycle");
            }

            await Task.Delay(TimeSpan.FromMinutes(CheckIntervalMinutes), stoppingToken);
        }
    }

    private async Task ProcessLiveSignalsAsync()
    {
        using var scope = _serviceProvider.CreateScope();
        var signalRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var decisionEngine = scope.ServiceProvider.GetRequiredService<ITradingDecisionEngine>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

        _logger.LogInformation("🔍 Starting Live Signal Processing cycle at {Time}", DateTime.UtcNow);

        using var uow = unitOfWorkManager.Begin();

        // 1. Monitor Open Signals
        var openSignals = await signalRepository.GetListAsync(s => s.Status == TradeStatus.Open);
        foreach (var signal in openSignals)
        {
            await MonitorSignalExitAsync(signal, marketDataManager, signalRepository);
        }

        // 2. Generate New Signals
        var strategy = (await strategyRepository.GetListAsync()).FirstOrDefault(x => x.IsActive);
        if (strategy != null)
        {
            var symbols = strategy.GetSelectedCryptos() ?? new List<string> { "BTCUSDT", "ETHUSDT" };
            foreach (var symbol in symbols)
            {
                await AnalyzeSymbolForSignalAsync(symbol, strategy, marketDataManager, decisionEngine, signalRepository);
            }
        }

        await uow.CompleteAsync();
        _logger.LogInformation("✅ Live Signal Processing cycle completed.");
    }

    private async Task MonitorSignalExitAsync(TradingSignal signal, MarketDataManager marketDataManager, IRepository<TradingSignal, Guid> repository)
    {
        try
        {
            var candles = await marketDataManager.GetCandlesAsync(signal.Symbol, "1h", 2);
            if (!candles.Any()) return;

            var lastCandle = candles.Last();
            bool exited = false;
            decimal exitPrice = lastCandle.Close;

            if (signal.Direction == SignalDirection.Long)
            {
                if (lastCandle.Low <= signal.StopLossPrice)
                {
                    signal.Status = TradeStatus.Loss;
                    exitPrice = signal.StopLossPrice ?? lastCandle.Low;
                    exited = true;
                }
                else if (lastCandle.High >= signal.TargetPrice)
                {
                    signal.Status = TradeStatus.Win;
                    exitPrice = signal.TargetPrice ?? lastCandle.High;
                    exited = true;
                }
            }
            else // Short
            {
                if (lastCandle.High >= signal.StopLossPrice)
                {
                    signal.Status = TradeStatus.Loss;
                    exitPrice = signal.StopLossPrice ?? lastCandle.High;
                    exited = true;
                }
                else if (lastCandle.Low <= signal.TargetPrice)
                {
                    signal.Status = TradeStatus.Win;
                    exitPrice = signal.TargetPrice ?? lastCandle.Low;
                    exited = true;
                }
            }

            if (exited)
            {
                signal.ExitPrice = exitPrice;
                signal.ExitTime = DateTime.UtcNow;
                signal.DurationMinutes = (int)(signal.ExitTime.Value - signal.AnalyzedDate).TotalMinutes;
                
                decimal pnlPct = signal.Direction == SignalDirection.Long 
                    ? (exitPrice - signal.EntryPrice) / signal.EntryPrice 
                    : (signal.EntryPrice - exitPrice) / signal.EntryPrice;
                
                signal.RealizedPnL = pnlPct * 100; // Store as percentage for simplicity in analytics
                
                await repository.UpdateAsync(signal);
                _logger.LogInformation("💰 Signal {Id} ({Symbol}) CLOSED as {Status} at {Price}", signal.Id, signal.Symbol, signal.Status, exitPrice);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error monitoring exit for signal {Id}", signal.Id);
        }
    }

    private async Task AnalyzeSymbolForSignalAsync(string symbol, TradingStrategy strategy, MarketDataManager marketDataManager, ITradingDecisionEngine decisionEngine, IRepository<TradingSignal, Guid> repository)
    {
        try
        {
            var candles = await marketDataManager.GetCandlesAsync(symbol, "1h", 100);
            if (candles == null || candles.Count < 50) return;

            // Simple context construction for live analysis
            // Optimization: In a real scenario, we'd fetch news/regime/etc. here
            // For now, using technicals-heavy context
            var context = new MarketContext
            {
                Candles = candles,
                // These would normally be populated by Python service or other integrations
                // Using empty or default values for live crawl
            };

            // Setup a virtual session for evaluation
            var virtualSession = new TradingSession(Guid.NewGuid(), strategy.TraderProfileId, symbol, "1h");
            
            var result = await decisionEngine.EvaluateAsync(virtualSession, strategy.Style, context, isAutoMode: true);

            if (result.Score >= 70)
            {
                var signalDirection = virtualSession.SelectedDirection ?? SignalDirection.Long;
                var signal = new TradingSignal(
                    Guid.NewGuid(),
                    symbol,
                    signalDirection,
                    candles.Last().Close,
                    result.Confidence,
                    (decimal)result.RiskRewardRatio
                )
                {
                    TargetPrice = result.EntryMaxPrice * 1.02m, // Placeholder TP
                    StopLossPrice = result.EntryMinPrice * 0.99m, // Placeholder SL
                    Score = result.Score,
                    Regime = context.MarketRegime?.Regime
                };

                await repository.InsertAsync(signal);
                _logger.LogInformation("🚀 NEW LIVE SIGNAL generated for {Symbol}. Score: {Score}", symbol, result.Score);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error analyzing {Symbol} for new signals", symbol);
        }
    }
}
