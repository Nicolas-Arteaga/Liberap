using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Verge.Trading.DTOs;
using Volo.Abp.DependencyInjection;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.EventBus.Distributed;
using Microsoft.Extensions.DependencyInjection;

namespace Verge.Trading;

public class FractalPatternManager : IFractalPatternManager, ISingletonDependency
{
    private readonly ILogger<FractalPatternManager> _logger;
    private readonly IDistributedEventBus _eventBus;
    private readonly IServiceProvider _serviceProvider;
    
    // Memory cache for price history (Circular buffer)
    private readonly ConcurrentDictionary<string, List<decimal>> _priceHistory = new();
    private const int HistoryLimit = 1500; // Enough for several hours at 8s intervals
    
    // Psychological round numbers
    private readonly decimal[] _roundNumbers = { 0.1m, 0.2m, 0.5m, 1.0m, 2.0m, 5.0m, 10m, 50m, 100m, 500m, 1000m };

    public FractalPatternManager(
        ILogger<FractalPatternManager> logger,
        IDistributedEventBus eventBus,
        IServiceProvider serviceProvider)
    {
        _logger = logger;
        _eventBus = eventBus;
        _serviceProvider = serviceProvider;
    }

    public async Task ProcessPriceAsync(string symbol, decimal price)
    {
        var history = _priceHistory.GetOrAdd(symbol, _ => new List<decimal>());
        
        lock (history)
        {
            history.Add(price);
            if (history.Count > HistoryLimit) history.RemoveAt(0);
        }

        // Only run scan if we have enough data (e.g. at least 45 mins of 8s ticks = 337 points)
        if (history.Count >= 340)
        {
            await RunDetectionAsync(symbol, history.ToList());
        }
    }

    private async Task RunDetectionAsync(string symbol, List<decimal> history)
    {
        var currentPrice = history.Last();
        
        // 1. Prior Pump check (Was there a >15% move in history?)
        var maxPrice = history.Max();
        var minPrice = history.Min();
        var totalVolatility = (double)((maxPrice - minPrice) / minPrice) * 100;

        if (totalVolatility < 15.0) return;

        // 2. Stability Check (Last 45 mins ~ 337 samples at 8s)
        var stabilityWindow = history.Skip(Math.Max(0, history.Count - 340)).ToList();
        var stMax = stabilityWindow.Max();
        var stMin = stabilityWindow.Min();
        var stabilityRange = (double)((stMax - stMin) / stMin) * 100;

        if (stabilityRange > 4.5) return; // Not stable enough

        // 3. Panza / Curved Bottom (Higher Lows in 3 blocks of 15 min)
        int blockSize = 340 / 3;
        var b1 = stabilityWindow.Take(blockSize).Min();
        var b2 = stabilityWindow.Skip(blockSize).Take(blockSize).Min();
        var b3 = stabilityWindow.Skip(blockSize * 2).Min();

        bool hasPanza = b3 >= b2 && b2 >= b1;

        // 4. Psychological Level
        bool isNearRound = _roundNumbers.Any(rn => {
            var diff = (double)(Math.Abs(currentPrice - rn) / rn);
            return diff < 0.02; // Within 2%
        });

        if (hasPanza && stabilityRange < 4.5)
        {
            _logger.LogWarning("🎯 [NICOLAS FRACTAL] {Symbol} accumulation detected at {Price}! Sending alert...", symbol, currentPrice);
            await TriggerFractalAlertAsync(symbol, currentPrice, isNearRound, stabilityRange);
        }
    }

    private async Task TriggerFractalAlertAsync(string symbol, decimal price, bool nearRound, double range)
    {
        string message = nearRound 
            ? $"ESTABILIDAD DETECTADA en nivel psicológico (${price:F4}). Patrón de acumulación Nicolas-Fractal activo."
            : $"ACUMULACIÓN DETECTADA. El precio está consolidando con mínimos crecientes (Rango: {range:F1}%).";

        var alert = new VergeAlertDto
        {
            Id = Guid.NewGuid().ToString(),
            Type = "Fractal",
            Title = "🎯 FRACTAL DE ACUMULACIÓN",
            Message = message,
            Timestamp = DateTime.UtcNow,
            Read = false,
            Crypto = symbol,
            Price = price,
            Confidence = nearRound ? SignalConfidence.High : SignalConfidence.Medium,
            Direction = SignalDirection.Long,
            Severity = "success",
            Icon = "analytics-outline",
            Score = nearRound ? 85 : 75,
            PatternSignal = "Nicolas Fractal"
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
