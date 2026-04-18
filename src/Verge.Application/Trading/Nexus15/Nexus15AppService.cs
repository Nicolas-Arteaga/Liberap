using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using StackExchange.Redis;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Nexus15;

public class Nexus15AppService : ApplicationService, INexus15AppService
{
    private readonly IDatabase _db;
    private readonly IPythonNexus15Service _pythonService;
    private readonly MarketDataManager _marketData;
    private readonly ILogger<Nexus15AppService> _logger;

    public Nexus15AppService(
        IConnectionMultiplexer redis,
        IPythonNexus15Service pythonService,
        MarketDataManager marketData,
        ILogger<Nexus15AppService> logger)
    {
        _db = redis.GetDatabase();
        _pythonService = pythonService;
        _marketData = marketData;
        _logger = logger;
    }

    /// <summary>Lee el último resultado NEXUS-15 desde el caché Redis.</summary>
    public async Task<Nexus15ResultDto?> GetLatestAsync(string symbol)
    {
        var key = $"verge:nexus15_cache:{symbol.ToUpper()}";
        var cached = await _db.StringGetAsync(key);

        if (cached.IsNullOrEmpty)
        {
            _logger.LogWarning("⚠️ [Nexus15] No cached result for {Symbol}", symbol);
            return null;
        }

        return JsonSerializer.Deserialize<Nexus15ResultDto>(cached.ToString()!, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
    }

    /// <summary>Análisis on-demand: obtiene velas → llama al Python Service → retorna resultado.</summary>
    public async Task<Nexus15ResultDto?> AnalyzeOnDemandAsync(string symbol)
    {
        try
        {
            // Normalize symbol for Binance: "SIREN/USDT:USDT" → "SIRENUSDT"
            var normalized = symbol.Contains(':') ? symbol.Split(':')[0] : symbol;
            var cleanSymbol = normalized.ToUpper().Replace("/", "").Replace("-", "").Trim();

            var candles = await _marketData.GetCandlesAsync(cleanSymbol, "15", 50);
            if (candles == null || candles.Count < 25)
            {
                _logger.LogWarning("⚠️ [Nexus15] Insufficient candles for {Symbol} (got {Count})", cleanSymbol, candles?.Count ?? 0);
                return null;
            }

            _logger.LogInformation("🔍 [Nexus15] OnDemand: {Symbol} — {Count} candles loaded", cleanSymbol, candles.Count);

            var result = await _pythonService.AnalyzeNexus15Async(cleanSymbol, candles);
            if (result == null) return null;

            var dto = new Nexus15ResultDto
            {
                Symbol = result.Symbol,
                Timeframe = result.Timeframe,
                AnalyzedAt = result.AnalyzedAt,
                AiConfidence = result.AiConfidence,
                Direction = result.Direction,
                Recommendation = result.Recommendation,
                Next5CandlesProb = result.Next5CandlesProb,
                Next15CandlesProb = result.Next15CandlesProb,
                Next20CandlesProb = result.Next20CandlesProb,
                EstimatedRangePercent = result.EstimatedRangePercent,
                Regime = result.Regime,
                GroupScores = result.GroupScores == null ? new Nexus15GroupScoresDto() : new Nexus15GroupScoresDto
                {
                    G1PriceAction = result.GroupScores.G1PriceAction,
                    G2SmcIct = result.GroupScores.G2SmcIct,
                    G3Wyckoff = result.GroupScores.G3Wyckoff,
                    G4Fractals = result.GroupScores.G4Fractals,
                    G5Volume = result.GroupScores.G5Volume,
                    G6Ml = result.GroupScores.G6Ml
                },
                Features = result.Features == null ? new Nexus15FeaturesDto() : new Nexus15FeaturesDto
                {
                    CandleBodyRatio = result.Features.CandleBodyRatio,
                    UpperWickRatio = result.Features.UpperWickRatio,
                    LowerWickRatio = result.Features.LowerWickRatio,
                    ConsecutiveBullBars = result.Features.ConsecutiveBullBars,
                    OrderBlockDetected = result.Features.OrderBlockDetected,
                    FairValueGap = result.Features.FairValueGap,
                    BosDetected = result.Features.BosDetected,
                    WyckoffPhase = result.Features.WyckoffPhase,
                    SpringDetected = result.Features.SpringDetected,
                    UpthrustDetected = result.Features.UpthrustDetected,
                    FractalHigh5 = result.Features.FractalHigh5,
                    FractalLow5 = result.Features.FractalLow5,
                    TrendStructure = result.Features.TrendStructure,
                    VolumeRatio20 = result.Features.VolumeRatio20,
                    CvdDelta = result.Features.CvdDelta,
                    VolumeSurgeBullish = result.Features.VolumeSurgeBullish,
                    PocProximity = result.Features.PocProximity,
                    Rsi14 = result.Features.Rsi14,
                    MacdHistogram = result.Features.MacdHistogram,
                    AtrPercent = result.Features.AtrPercent
                },
                Detectivity = result.Detectivity ?? new Dictionary<string, string>()
            };

            // Cache the result in Redis so GetLatest also works for non-top symbols (e.g. SIREN)
            try
            {
                var cacheKey = $"verge:nexus15_cache:{cleanSymbol}";
                var json = System.Text.Json.JsonSerializer.Serialize(dto);
                await _db.StringSetAsync(cacheKey, json, TimeSpan.FromMinutes(20));
                _logger.LogInformation("✅ [Nexus15] Cached result for {Symbol}", cleanSymbol);
            }
            catch (Exception cacheEx)
            {
                _logger.LogWarning(cacheEx, "⚠️ [Nexus15] Failed to cache result for {Symbol}", cleanSymbol);
            }

            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [Nexus15] OnDemand analysis failed for {Symbol}", symbol);
            return null;
        }
    }

    /// <summary>Analiza el mercado top y recopila las mejores opciones.</summary>
    public async Task<List<Nexus15ResultDto>> AnalyzeTopAvailableAsync(int topN = 5)
    {
        _logger.LogInformation("🚀 [Nexus15] Initiating Top 20 Market Massive Scan... targeting top {Top}", topN);
        
        var tickers = await _marketData.GetTickersAsync();
        var topSymbols = tickers
            .Where(t => t.Volume > 1_000_000m)
            .OrderByDescending(t => Math.Abs(t.PriceChangePercent))
            .Take(40)
            .Select(t => t.Symbol)
            .ToList();


        var results = new ConcurrentBag<Nexus15ResultDto>();
        using var semaphore = new SemaphoreSlim(10); // analyze 10 concurrently max

        var tasks = topSymbols.Select(async symbol =>
        {
            await semaphore.WaitAsync();
            try
            {
                var res = await AnalyzeOnDemandAsync(symbol);
                if (res != null) results.Add(res);
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);

        _logger.LogInformation("✅ [Nexus15] Top scan finished successfully.");

        return results
            .Where(r => r.Direction == "BULLISH" || r.Direction == "BEARISH")
            .OrderByDescending(r => r.AiConfidence)
            .Take(topN)
            .ToList();
    }
}
