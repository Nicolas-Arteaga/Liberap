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
using Volo.Abp.EventBus.Distributed;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class FastTickScannerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<FastTickScannerService> _logger;
    private readonly MarketDataManager _marketDataManager;
    private readonly ITickSpikeAlerter _spikeAlerter;
    private readonly IDistributedEventBus _eventBus;
    
    // Configurable thresholds for the 1% Tier
    private const double PriceDeltaThreshold = 0.0035; // 0.35% in < 10s
    private const double VolumeSpikeThreshold = 1.8;   // 1.8x average volume

    public FastTickScannerService(
        IServiceProvider serviceProvider, 
        ILogger<FastTickScannerService> logger,
        MarketDataManager marketDataManager,
        ITickSpikeAlerter spikeAlerter,
        IDistributedEventBus eventBus)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _marketDataManager = marketDataManager;
        _spikeAlerter = spikeAlerter;
        _eventBus = eventBus;
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
                _logger.LogError(ex, "❌ Error in fast tick scanner cycle");
            }

            await Task.Delay(TimeSpan.FromSeconds(8), stoppingToken);
        }
    }

    private async Task ScanTicksAsync(Dictionary<string, decimal> lastPrices)
    {
        using var scope = _serviceProvider.CreateScope();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var strategy = (await strategyRepository.GetListAsync()).FirstOrDefault(x => x.IsActive);
        
        if (strategy == null) return;

        var symbols = strategy.GetSelectedCryptos() ?? new List<string> { "BTCUSDT", "ETHUSDT" };

        foreach (var symbol in symbols)
        {
            try
            {
                // 🔥 Optimization: Use WebSocket cache instead of REST
                var currentPrice = _marketDataManager.GetWebSocketPrice(symbol);
                
                // Fallback to REST only if WebSocket is not ready
                if (currentPrice == null)
                {
                    var tickers = await _marketDataManager.GetTickersAsync();
                    currentPrice = tickers.FirstOrDefault(t => t.Symbol == symbol)?.LastPrice;
                }
                
                if (currentPrice == null) continue;

                if (!lastPrices.ContainsKey(symbol))
                {
                    lastPrices[symbol] = currentPrice.Value;
                    continue;
                }

                var pricePrevious = lastPrices[symbol];
                lastPrices[symbol] = currentPrice.Value;

                var delta = (double)Math.Abs((currentPrice.Value - pricePrevious) / pricePrevious);

                if (delta >= PriceDeltaThreshold)
                {
                    _logger.LogWarning("⚡ [IMPULSE DETECTED] {Symbol} jumped {Delta:P2}! Alerting Engine...", symbol, delta);
                    _spikeAlerter.SignalSpike(symbol);

                    // 🚀 Pulse UI Restore: Send immediate toast to user
                    var profileRepository = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                    var profiles = await profileRepository.GetListAsync();
                    foreach (var profile in profiles)
                    {
                        await _eventBus.PublishAsync(new AlertStateChangedEto
                        {
                            UserId = profile.UserId,
                            SessionId = Guid.Empty,
                            Alert = new VergeAlertDto
                            {
                                Id = Guid.NewGuid().ToString(),
                                Type = "System", // High priority
                                Title = $"⚡ PULSO DETECTADO: {symbol}",
                                Message = $"Movimiento institucional de {delta:P2} detectado en < 10s. ¡Reacción inmediata!",
                                Timestamp = DateTime.UtcNow,
                                Read = false,
                                Crypto = symbol,
                                Price = currentPrice,
                                Severity = "warning",
                                Icon = "flash-outline",
                                IsSqueeze = true,
                                WhaleInfluenceScore = 80
                            }
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning("⚠️ Error scanning ticks for {Symbol}: {Message}", symbol, ex.Message);
            }
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
