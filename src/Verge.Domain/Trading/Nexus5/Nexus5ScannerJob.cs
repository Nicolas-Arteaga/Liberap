using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using StackExchange.Redis;

namespace Verge.Trading.Nexus5;

/// <summary>
/// BackgroundService que analiza los top símbolos con NEXUS-5 cada 5 minutos.
/// Alineado al cierre de vela de 5m. Totalmente aislado de NEXUS-15 y MarketScannerService.
/// </summary>
public class Nexus5ScannerJob : BackgroundService
{
    private readonly IServiceProvider _services;
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<Nexus5ScannerJob> _logger;

    private static readonly TimeSpan ScanInterval = TimeSpan.FromMinutes(5);

    public Nexus5ScannerJob(
        IServiceProvider services,
        IConnectionMultiplexer redis,
        ILogger<Nexus5ScannerJob> logger)
    {
        _services = services;
        _redis = redis;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("⚡ NEXUS-5 Ignition Scanner started. Interval: {Interval} min", ScanInterval.TotalMinutes);

        // Align to next 5-minute candle close
        var now = DateTime.UtcNow;
        var nextCandle = now.AddMinutes(5 - now.Minute % 5).AddSeconds(-now.Second);
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
                _logger.LogError(ex, "❌ [Nexus5] Scan cycle failed");
            }

            await Task.Delay(ScanInterval, stoppingToken);
        }
    }

    private async Task RunScanAsync(CancellationToken ct)
    {
        using var scope = _services.CreateScope();
        var marketData = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var pythonSvc = scope.ServiceProvider.GetRequiredService<IPythonNexus5Service>();

        _logger.LogInformation("⚡ [Nexus5] Starting scan cycle at {Time}", DateTime.UtcNow);

        var tickers = await marketData.GetTickersAsync();
        var topSymbols = tickers
            .Where(t => t.Volume > 1_000_000m)
            .OrderByDescending(t => Math.Abs(t.PriceChangePercent))
            .Take(30) // NEXUS-5 analyzes top 30 (more than NEXUS-15's 20)
            .Select(t => t.Symbol)
            .ToList();

        var publisher = _redis.GetSubscriber();
        var db = _redis.GetDatabase();
        int analyzed = 0;

        var sem = new SemaphoreSlim(5, 5); // Higher concurrency than NEXUS-15 (3)

        var tasks = topSymbols.Select(async symbol =>
        {
            await sem.WaitAsync(ct);
            try
            {
                // NEXUS-5 uses 5m candles for features (G1-G6), needs at least 30
                var candles = await marketData.GetCandlesAsync(symbol, "5", 500);
                if (candles == null || candles.Count < 30)
                {
                    _logger.LogDebug("⏭️ [Nexus5] Skipping {Symbol}: insufficient 5m candles ({Count})", symbol, candles?.Count ?? 0);
                    return;
                }

                // Fetch NATIVE 15m candles for structural Bottom Sniper v11.0
                var candles15m = await marketData.GetCandlesAsync(symbol, "15", 200);
                if (candles15m == null || candles15m.Count < 100)
                {
                    _logger.LogDebug("⚠️ [Nexus5] {Symbol}: insufficient 15m candles ({Count}). Structural analysis will use sentinel.", symbol, candles15m?.Count ?? 0);
                    candles15m = null;
                }

                var result = await pythonSvc.AnalyzeNexus5Async(symbol, candles, candles15m);
                if (result == null) return;

                // Skip IDLE phase — only publish active signals
                if (result.Phase == "IDLE") return;

                var payload = JsonSerializer.Serialize(result);
                await publisher.PublishAsync(
                    RedisChannel.Literal($"verge:nexus5:{symbol}"),
                    payload
                );
                await db.StringSetAsync($"verge:nexus5:cache:{symbol}", payload, TimeSpan.FromMinutes(6));

                Interlocked.Increment(ref analyzed);
                _logger.LogInformation(
                    "⚡ [Nexus5] {Symbol}: Phase={Phase}({PhaseScore:F0}) Conf={Conf}% Dir={Dir} Entry={EntryTF}",
                    symbol, result.Phase, result.PhaseScore, result.AiConfidence, result.Direction, result.EntryTimeframe
                );
            }
            catch (Exception ex)
            {
                _logger.LogWarning("⚠️ [Nexus5] Error for {Symbol}: {Msg}", symbol, ex.Message);
            }
            finally
            {
                sem.Release();
            }
        });

        await Task.WhenAll(tasks);
        _logger.LogInformation("🏁 [Nexus5] Cycle complete. Analyzed: {Count}/{Total}", analyzed, topSymbols.Count);
    }
}
