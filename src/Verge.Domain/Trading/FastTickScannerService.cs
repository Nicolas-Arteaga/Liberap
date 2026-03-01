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

public class FastTickScannerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<FastTickScannerService> _logger;
    private readonly MarketDataManager _marketDataManager;
    private readonly ITickSpikeAlerter _spikeAlerter;
    
    // Configurable thresholds for the 1% Tier
    private const double PriceDeltaThreshold = 0.0035; // 0.35% in < 10s
    private const double VolumeSpikeThreshold = 1.8;   // 1.8x average volume

    public FastTickScannerService(
        IServiceProvider serviceProvider, 
        ILogger<FastTickScannerService> logger,
        MarketDataManager marketDataManager,
        ITickSpikeAlerter spikeAlerter)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _marketDataManager = marketDataManager;
        _spikeAlerter = spikeAlerter;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 [Institutional 1%] Fast Tick Scanner started (Every 8s).");

        var lastPrices = new Dictionary<string, decimal>();

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ScanTicksAsync(lastPrices);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in FastTickScanner cycle");
            }

            await Task.Delay(TimeSpan.FromSeconds(8), stoppingToken);
        }
    }

    private async Task ScanTicksAsync(Dictionary<string, decimal> lastPrices)
    {
        using var scope = _serviceProvider.CreateScope();
        using var uow = scope.ServiceProvider.GetRequiredService<Volo.Abp.Uow.IUnitOfWorkManager>().Begin();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        
        // Resolve all symbols to monitor (Individual and AUTO portfolio)
        var activeSessions = await sessionRepository.GetListAsync(x => x.IsActive);
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var activeSymbols = new HashSet<string>();

        foreach (var session in activeSessions)
        {
            if (session.Symbol != "AUTO")
            {
                activeSymbols.Add(session.Symbol);
            }
            else
            {
                var strategy = await strategyRepository.FirstOrDefaultAsync(x => x.TraderProfileId == session.TraderProfileId && x.IsActive);
                if (strategy != null)
                {
                    foreach (var s in strategy.GetSelectedCryptos()) activeSymbols.Add(s);
                }
            }
        }

        if (!activeSymbols.Any()) return;

        foreach (var symbol in activeSymbols)
        {
            var candles = await _marketDataManager.GetCandlesAsync(symbol, "1m", 2); // Get latest mini-candle
            if (!candles.Any()) continue;

            var currentPrice = candles.Last().Close;
            
            if (lastPrices.TryGetValue(symbol, out var lastPrice))
            {
                var delta = (double)Math.Abs((currentPrice - lastPrice) / lastPrice);
                
                if (delta >= PriceDeltaThreshold)
                {
                    _logger.LogWarning("⚡ [IMPULSE DETECTED] {Symbol} jumped {Delta:P2}! Alerting Engine...", symbol, delta);
                    _spikeAlerter.SignalSpike(symbol);
                }
            }

            lastPrices[symbol] = currentPrice;
        }
    }
}

public interface ITickSpikeAlerter
{
    string LastSpikedSymbol { get; }
    void SignalSpike(string symbol);
    Task WaitAsync(CancellationToken token);
}

public class TickSpikeAlerter : ITickSpikeAlerter
{
    private readonly SemaphoreSlim _signal = new SemaphoreSlim(0, 1);
    public string LastSpikedSymbol { get; private set; }

    public void SignalSpike(string symbol)
    {
        LastSpikedSymbol = symbol;
        if (_signal.CurrentCount == 0) _signal.Release();
    }

    public async Task WaitAsync(CancellationToken token)
    {
        await _signal.WaitAsync(token);
    }
}
