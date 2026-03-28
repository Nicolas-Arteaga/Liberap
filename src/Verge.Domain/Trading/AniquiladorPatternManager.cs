using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Verge.Trading.DTOs;
using Volo.Abp.DependencyInjection;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.EventBus.Distributed;

namespace Verge.Trading;

public class AniquiladorPatternManager : IAniquiladorPatternManager, ISingletonDependency
{
    private readonly ILogger<AniquiladorPatternManager> _logger;
    private readonly IDistributedEventBus _eventBus;
    private readonly IServiceProvider _serviceProvider;

    // Prevent spamming the same alert
    private readonly ConcurrentDictionary<string, DateTime> _lastAlertTimes = new();

    public AniquiladorPatternManager(
        ILogger<AniquiladorPatternManager> logger,
        IDistributedEventBus eventBus,
        IServiceProvider serviceProvider)
    {
        _logger = logger;
        _eventBus = eventBus;
        _serviceProvider = serviceProvider;
    }

    public async Task AnalyzeCandlesAsync(string symbol, List<MarketCandleModel> hourlyCandles)
    {
        if (hourlyCandles == null || hourlyCandles.Count < 100) return;

        var prices = hourlyCandles.Select(c => c.Close).ToList();
        
        // Calculate SMAs
        var ma7 = CalculateSMA(prices, 7);
        var ma25 = CalculateSMA(prices, 25);
        var ma99 = CalculateSMA(prices, 99);

        if (ma7.Count < 2 || ma25.Count < 2 || ma99.Count == 0) return;

        // Current and Previous values
        decimal currentMa7 = ma7.Last();
        decimal previousMa7 = ma7[ma7.Count - 2];
        
        decimal currentMa25 = ma25.Last();
        decimal previousMa25 = ma25[ma25.Count - 2];

        decimal currentMa99 = ma99.Last();
        decimal currentPrice = prices.Last();

        // 1. Check for the Golden Cross: MA7 crosses ABOVE MA25
        bool isCrossingUp = previousMa7 <= previousMa25 && currentMa7 > currentMa25;
        
        if (!isCrossingUp) return;

        // 2. Structural Check: We want a consolidation phase before this crossing.
        // During consolidation, MA7 and MA25 should have been relatively close or flat.
        // And importantly, they should be above or near MA99 (support).
        // Let's verify that the current price isn't too far below MA99.
        
        bool isSupportedByMA99 = currentPrice > (currentMa99 * 0.90m); // Price must not be in a deep abyss (more than 10% below MA99)
        if (!isSupportedByMA99) return;

        // 3. Debounce: Only 1 alert per symbol every 4 hours
        if (_lastAlertTimes.TryGetValue(symbol, out var lastTime))
        {
            if ((DateTime.UtcNow - lastTime).TotalHours < 4) return;
        }

        _logger.LogWarning("🔥 [ANIQUILADOR] {Symbol} Golden Cross detectado! MA7 cruzó sobre MA25.", symbol);
        
        _lastAlertTimes[symbol] = DateTime.UtcNow;
        await TriggerAniquiladorAlertAsync(symbol, currentPrice);
    }
    
    private List<decimal> CalculateSMA(List<decimal> data, int period)
    {
        var sma = new List<decimal>();
        if (data.Count < period) return sma;

        decimal sum = data.Take(period).Sum();
        sma.Add(sum / period);

        for (int i = period; i < data.Count; i++)
        {
            sum = sum - data[i - period] + data[i];
            sma.Add(sum / period);
        }

        return sma;
    }

    private async Task TriggerAniquiladorAlertAsync(string symbol, decimal price)
    {
        var alert = new VergeAlertDto
        {
            Id = Guid.NewGuid().ToString(),
            Type = "Aniquilador",
            Title = "🔥 ANIQUILADOR DETECTADO",
            Message = $"CRUCE MA7 > MA25. Patrón algorítmico extremo detectado post-consolidación a ${price:F4}. ¡EXPLOSIÓN INMINENTE!",
            Timestamp = DateTime.UtcNow,
            Read = false,
            Crypto = symbol,
            Price = price,
            Confidence = SignalConfidence.High,
            Direction = SignalDirection.Long,
            Severity = "danger", // We'll apply styling explicitly for the Aniquilador
            Icon = "flame-outline",
            Score = 98,
            PatternSignal = "Nicolas Aniquilador (MA7/25)"
        };

        using var scope = _serviceProvider.CreateScope();
        var profileRepository = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var profiles = await profileRepository.GetListAsync();

        foreach (var profile in profiles)
        {
            await _eventBus.PublishAsync(new AlertStateChangedEto
            {
                UserId = profile.UserId,
                SessionId = Guid.Empty,
                Alert = alert,
                TriggeredAt = DateTime.UtcNow
            });
        }
    }
}
