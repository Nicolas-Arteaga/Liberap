using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using StackExchange.Redis;

namespace Verge.Trading.Nexus15;

/// <summary>
/// BackgroundService AISLADO que analiza los top símbolos con NEXUS-15 cada 15 minutos.
/// NO toca MarketScannerService ni ningún flujo existente.
/// </summary>
public class Nexus15ScannerJob : BackgroundService
{
    private readonly IServiceProvider _services;
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<Nexus15ScannerJob> _logger;

    private static readonly TimeSpan ScanInterval = TimeSpan.FromMinutes(15);

    public Nexus15ScannerJob(
        IServiceProvider services,
        IConnectionMultiplexer redis,
        ILogger<Nexus15ScannerJob> logger)
    {
        _services = services;
        _redis = redis;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🔭 NEXUS-15 Scanner started. Interval: {Interval} min", ScanInterval.TotalMinutes);

        // Alinear al inicio de la próxima vela de 15 minutos
        var now = DateTime.UtcNow;
        var nextCandle = now.AddMinutes(15 - now.Minute % 15).AddSeconds(-now.Second);
        var initialDelay = nextCandle - now;
        if (initialDelay > TimeSpan.Zero)
            await Task.Delay(initialDelay, stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await RunScanAsync(stoppingToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ [Nexus15] Scan cycle failed");
            }

            await Task.Delay(ScanInterval, stoppingToken);
        }
    }

    private async Task RunScanAsync(CancellationToken ct)
    {
        using var scope = _services.CreateScope();
        var marketData = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var pythonSvc  = scope.ServiceProvider.GetRequiredService<IPythonNexus15Service>();

        _logger.LogInformation("🔭 [Nexus15] Starting scan cycle at {Time}", DateTime.UtcNow);

        // Top symbols por volumen (misma lógica que el scanner existente, no la duplicamos)
        var tickers = await marketData.GetTickersAsync();
        var topSymbols = tickers
            .Where(t => t.Volume > 1_000_000m)
            .OrderByDescending(t => Math.Abs(t.PriceChangePercent))
            .Take(20)   // NEXUS-15 analiza top 20 (conservador para no saturar el semáforo)
            .Select(t => t.Symbol)
            .ToList();

        var publisher = _redis.GetSubscriber();
        int analyzed = 0;

        // Semáforo local adicional (respetar el SemaphoreSlim(5,5) de Binance en MarketDataManager)
        var sem = new SemaphoreSlim(3, 3);

        var tasks = topSymbols.Select(async symbol =>
        {
            await sem.WaitAsync(ct);
            try
            {
                var candles = await marketData.GetCandlesAsync(symbol, "15", 50);
                if (candles == null || candles.Count < 25)
                {
                    _logger.LogDebug("⏭️ [Nexus15] Skipping {Symbol}: insufficient candles", symbol);
                    return;
                }

                var result = await pythonSvc.AnalyzeNexus15Async(symbol, candles);
                if (result == null) return;

                // Publicar en Redis bajo verge:nexus15:{symbol}
                var payload = JsonSerializer.Serialize(result);
                await publisher.PublishAsync(
                    RedisChannel.Literal($"verge:nexus15:{symbol}"),
                    payload
                );

                Interlocked.Increment(ref analyzed);
                _logger.LogInformation(
                    "📊 [Nexus15] {Symbol}: Confidence={Conf}% Dir={Dir} Rec={Rec}",
                    symbol, result.AiConfidence, result.Direction, result.Recommendation
                );
            }
            catch (Exception ex)
            {
                _logger.LogWarning("⚠️ [Nexus15] Error for {Symbol}: {Msg}", symbol, ex.Message);
            }
            finally
            {
                sem.Release();
            }
        });

        await Task.WhenAll(tasks);
        _logger.LogInformation("🏁 [Nexus15] Cycle complete. Analyzed: {Count}/{Total}", analyzed, topSymbols.Count);
    }
}
