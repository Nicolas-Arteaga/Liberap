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

    /// <summary>
    /// Analiza el mercado top usando la misma watchlist de 200 símbolos del agente,
    /// ordenada por cambio de precio absoluto (los más volátiles primero).
    /// Esto asegura que el Top 5 de la UI coincide con lo que el agente realmente ve.
    /// </summary>
    public async Task<List<Nexus15ResultDto>> AnalyzeTopAvailableAsync(int topN = 5)
    {
        _logger.LogInformation("🚀 [Nexus15] Initiating Top Market Scan (agent watchlist)... targeting top {Top}", topN);

        // Use ALL tickers from multi-exchange, no arbitrary volume cap, sorted by price movement.
        // This mirrors the agent's own scanning universe (200 symbols by volatility).
        var tickers = await _marketData.GetTickersAsync();
        var topSymbols = tickers
            .Where(t => t.Volume > 500_000m && t.Symbol.EndsWith("USDT"))
            .OrderByDescending(t => Math.Abs(t.PriceChangePercent))
            .Take(80)   // Scan 80 to ensure we fill top 5 with strong directional signals
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

        // Prefer directional signals (BULLISH/BEARISH) but fallback to best neutrals
        // so the button never appears broken during ranging/neutral markets.
        var directional = results
            .Where(r => r.Direction == "BULLISH" || r.Direction == "BEARISH")
            .OrderByDescending(r => r.AiConfidence)
            .ToList();

        if (directional.Count >= topN)
            return directional.Take(topN).ToList();

        // Fill remaining slots with highest-confidence neutral results
        var neutralFill = results
            .Where(r => r.Direction == "NEUTRAL")
            .OrderByDescending(r => r.AiConfidence)
            .Take(topN - directional.Count);

        return directional.Concat(neutralFill).Take(topN).ToList();
    }

    /// <summary>Analiza STRIKE 15m: detecta velas de ignición en MA99.</summary>
    public async Task<Strike15mResponseDto> AnalyzeStrike15mAsync(List<string> symbols)
    {
        try
        {
            _logger.LogInformation("⚡ [STRIKE15m] Initiating scan for {Count} symbols...", symbols.Count);

            var result = await _pythonService.AnalyzeStrike15mAsync(symbols);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [STRIKE15m] No results from Python service");
                return new Strike15mResponseDto
                {
                    Top5 = new List<Strike15mItemDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new Strike15mResponseDto
            {
                Top5 = result.Top5?.Select(item => new Strike15mItemDto
                {
                    Symbol = item.Symbol,
                    ForceScore = item.ForceScore,
                    Ma99DistancePct = item.Ma99DistancePct,
                    Volume15m = item.Volume15m,
                    CurrentPrice = item.CurrentPrice,
                    Ma99Value = item.Ma99Value,
                    CandleOpen = item.CandleOpen,
                    Atr20_15m = item.Atr20_15m,
                    IsPerfectShot = item.IsPerfectShot
                }).ToList() ?? new List<Strike15mItemDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [STRIKE15m] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [STRIKE15m] Analysis failed");
            return new Strike15mResponseDto
            {
                Top5 = new List<Strike15mItemDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }

    /// <summary>Analiza STAIRCASE: detecta patrones de escalera institucional (1D+15m).</summary>
    public async Task<StaircaseResponseDto> AnalyzeStaircaseAsync(List<string> symbols)
    {
        try
        {
            _logger.LogInformation("🪜 [STAIRCASE] Initiating scan for {Count} symbols...", symbols.Count);

            var result = await _pythonService.AnalyzeStaircaseAsync(symbols);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [STAIRCASE] No results from Python service");
                return new StaircaseResponseDto
                {
                    Top5 = new List<StaircaseItemDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new StaircaseResponseDto
            {
                Top5 = result.Top5?.Select(item => new StaircaseItemDto
                {
                    Symbol = item.Symbol,
                    OrderScore = item.OrderScore,
                    Trend1d = item.Trend1d,
                    Phase = item.Phase,
                    CurrentPrice = item.CurrentPrice,
                    Ema7Value = item.Ema7Value,
                    Ema25Value = item.Ema25Value,
                    ImpulseDetected = item.ImpulseDetected
                }).ToList() ?? new List<StaircaseItemDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [STAIRCASE] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [STAIRCASE] Analysis failed");
            return new StaircaseResponseDto
            {
                Top5 = new List<StaircaseItemDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }

    /// <summary>Analiza ARROW PEAK: detecta vértices de agotamiento (exhaustion reversals).</summary>
    public async Task<ArrowPeakResponseDto> AnalyzeArrowPeakAsync(List<string> symbols)
    {
        try
        {
            _logger.LogInformation("🏹 [ARROW PEAK] Initiating scan for {Count} symbols...", symbols.Count);

            var result = await _pythonService.AnalyzeArrowPeakAsync(symbols);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [ARROW PEAK] No results from Python service");
                return new ArrowPeakResponseDto
                {
                    Top5 = new List<ArrowPeakItemDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new ArrowPeakResponseDto
            {
                Top5 = result.Top5?.Select(item => new ArrowPeakItemDto
                {
                    Symbol = item.Symbol,
                    PrevRisePct = item.PrevRisePct,
                    DaysBleeding = item.DaysBleeding,
                    CurrentPrice = item.CurrentPrice,
                    PeakPrice = item.PeakPrice,
                    DistMa99Pct = item.DistMa99Pct
                }).ToList() ?? new List<ArrowPeakItemDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [ARROW PEAK] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ARROW PEAK] Analysis failed");
            return new ArrowPeakResponseDto
            {
                Top5 = new List<ArrowPeakItemDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }
}
