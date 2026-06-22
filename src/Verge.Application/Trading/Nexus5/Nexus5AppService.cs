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

namespace Verge.Trading.Nexus5;

public class Nexus5AppService : ApplicationService, INexus5AppService
{
    private readonly IDatabase _db;
    private readonly IPythonNexus5Service _pythonService;
    private readonly MarketDataManager _marketData;
    private readonly ILogger<Nexus5AppService> _logger;

    public Nexus5AppService(
        IConnectionMultiplexer redis,
        IPythonNexus5Service pythonService,
        MarketDataManager marketData,
        ILogger<Nexus5AppService> logger)
    {
        _db = redis.GetDatabase();
        _pythonService = pythonService;
        _marketData = marketData;
        _logger = logger;
    }

    /// <summary>Read latest NEXUS-5 result from Redis cache.</summary>
    public async Task<Nexus5ResultDto?> GetLatestAsync(string symbol)
    {
        var key = $"verge:nexus5_cache:{symbol.ToUpper()}";
        var cached = await _db.StringGetAsync(key);

        if (cached.IsNullOrEmpty)
        {
            _logger.LogWarning("⚠️ [Nexus5] No cached result for {Symbol}", symbol);
            return null;
        }

        return JsonSerializer.Deserialize<Nexus5ResultDto>(cached.ToString()!, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
    }

    /// <summary>On-demand analysis: fetch 5m candles + 15m candles → call Python → return result.</summary>
    public async Task<Nexus5ResultDto?> AnalyzeOnDemandAsync(string symbol)
    {
        try
        {
            var normalized = symbol.Contains(':') ? symbol.Split(':')[0] : symbol;
            var cleanSymbol = normalized.ToUpper().Replace("/", "").Replace("-", "").Trim();

            // NEXUS-5 uses 5m candles for G1-G6 features
            var candles = await _marketData.GetCandlesAsync(cleanSymbol, "5", 500);
            if (candles == null || candles.Count < 450)
            {
                _logger.LogWarning("⚠️ [Nexus5] Insufficient 5m candles for {Symbol} (got {Count})", cleanSymbol, candles?.Count ?? 0);
                return null;
            }

            // Fetch NATIVE 15m candles for structural MA50/MA99 (Bottom Sniper v10.0)
            // Need at least 150 (99 for MA99 + 40 for slope lookback + buffer)
            var candles15m = await _marketData.GetCandlesAsync(cleanSymbol, "15", 200);
            if (candles15m == null || candles15m.Count < 100)
            {
                _logger.LogWarning("⚠️ [Nexus5] Insufficient 15m candles for {Symbol} (got {Count}). Structural MA99 will use sentinel.", cleanSymbol, candles15m?.Count ?? 0);
                candles15m = null; // Pass null → Python returns sentinel values (no veto)
            }

            _logger.LogInformation("⚡ [Nexus5] OnDemand: {Symbol} — {Count} 5m candles + {Count15m} 15m candles loaded", 
                cleanSymbol, candles.Count, candles15m?.Count ?? 0);

            var result = await _pythonService.AnalyzeNexus5Async(cleanSymbol, candles, candles15m);
            if (result == null) return null;

            var dto = MapToDto(result);

            // Cache the result in Redis
            try
            {
                var cacheKey = $"verge:nexus5_cache:{cleanSymbol}";
                var json = JsonSerializer.Serialize(dto);
                await _db.StringSetAsync(cacheKey, json, TimeSpan.FromMinutes(10));
                _logger.LogInformation("✅ [Nexus5] Cached result for {Symbol} Phase={Phase}", cleanSymbol, result.Phase);
            }
            catch (Exception cacheEx)
            {
                _logger.LogWarning(cacheEx, "⚠️ [Nexus5] Failed to cache result for {Symbol}", cleanSymbol);
            }

            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [Nexus5] OnDemand analysis failed for {Symbol}", symbol);
            return null;
        }
    }

    /// <summary>
    /// Top 5 scan: finds symbols closest to Phase 1 (Compression) and Phase 2 (Ignition).
    /// Prioritizes IGNITION over COMPRESSION. Filters out IDLE.
    /// </summary>
    public async Task<List<Nexus5ResultDto>> AnalyzeTopAvailableAsync(int topN = 5)
    {
        _logger.LogInformation("⚡ [Nexus5] Initiating Bottom Sniper Scan — targeting price below MA99, top {Top}", topN);

        var tickers = await _marketData.GetTickersAsync();

        // Bottom Sniper: queremos un universo amplio ordenado por volumen.
        // Los que ya subieron fuerte (>MA99) serán vetados automáticamente por el analizador.
        // Así capturamos también los que están acumulando silenciosamente debajo de MA99.
        // Tomamos los top 120 por volumen (excluye coins sin liquidez).
        var topSymbols = tickers
            .Where(t => t.Volume > 500_000m && t.Symbol.EndsWith("USDT"))
            .OrderByDescending(t => t.Volume)
            .Take(120)
            .Select(t => t.Symbol)
            .ToList();

        var results = new ConcurrentBag<Nexus5ResultDto>();
        using var semaphore = new SemaphoreSlim(10);

        var tasks = topSymbols.Select(async symbol =>
        {
            await semaphore.WaitAsync();
            try
            {
                var res = await AnalyzeOnDemandAsync(symbol);
                if (res != null && res.Phase != "IDLE")
                    results.Add(res);
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);
        _logger.LogInformation("✅ [Nexus5] Bottom Sniper scan finished. {Count} active signals found.", results.Count);

        // ── BOTTOM SNIPER ORDERING (v9.0) ───────────────────────────────────────
        // Prioridad absoluta: is_bottom_sniper=True + MA50/MA99 más cercanas
        // Luego: mayor confianza, luego más debajo de MA99 (más comprimido)
        var sorted = results
            .Where(r => r.Features != null)
            .OrderByDescending(r => r.AiConfidence >= 90 ? 1 : 0)  // Bottom Snipers primero (95+)
            .ThenBy(r => r.Features.Ma50Ma99Distance)               // Medias más cercanas = más comprimido
            .ThenBy(r => r.Features.PriceToMa99Pct)                 // Más debajo de MA99 primero
            .ThenByDescending(r => r.AiConfidence)                  // Mayor confianza al final
            .ToList();

        return sorted.Take(topN).ToList();
    }


    /// <summary>
    /// Agent endpoint: returns ALL qualifying pairs in Phase 1 or Phase 2.
    /// Ordered by urgency: IGNITION → COMPRESSION (high score) → EXPANSION.
    /// </summary>
    public async Task<List<Nexus5ResultDto>> AnalyzeAllCandidatesAsync()
    {
        _logger.LogInformation("⚡ [Nexus5] AnalyzeAllCandidates: full market scan for agent");

        var tickers = await _marketData.GetTickersAsync();
        var allSymbols = tickers
            .Where(t => t.Volume > 300_000m && t.Symbol.EndsWith("USDT"))
            .OrderByDescending(t => Math.Abs(t.PriceChangePercent))
            .Take(150)
            .Select(t => t.Symbol)
            .ToList();

        var results = new ConcurrentBag<Nexus5ResultDto>();
        using var semaphore = new SemaphoreSlim(12);

        var tasks = allSymbols.Select(async symbol =>
        {
            await semaphore.WaitAsync();
            try
            {
                var res = await AnalyzeOnDemandAsync(symbol);
                if (res == null) return;

                // Only include active phases with meaningful scores
                if (res.Phase == "IDLE") return;
                if (res.Phase == "COMPRESSION" && res.PhaseScore < 60) return;

                results.Add(res);
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);

        var sorted = results
            .OrderBy(r => r.Phase switch
            {
                "IGNITION" => 0,
                "EXPANSION" => 1,
                "COMPRESSION" => 2,
                _ => 3
            })
            .ThenByDescending(r => r.PhaseScore)
            .ThenByDescending(r => r.AiConfidence)
            .ToList();

        _logger.LogInformation("✅ [Nexus5] AllCandidates: {Count} qualifying symbols found", sorted.Count);
        return sorted;
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private static Nexus5ResultDto MapToDto(Nexus5ResponseModel result)
    {
        return new Nexus5ResultDto
        {
            Symbol = result.Symbol,
            Timeframe = result.Timeframe,
            AnalyzedAt = result.AnalyzedAt,
            AiConfidence = result.AiConfidence,
            Direction = result.Direction,
            Recommendation = result.Recommendation,
            Phase = result.Phase,
            PhaseScore = result.PhaseScore,
            EntryTimeframe = result.EntryTimeframe,
            CompressionState = result.CompressionState,
            IgnitionDetected = result.IgnitionDetected,
            BypassActive = result.BypassActive,
            Next3CandlesProb = result.Next3CandlesProb,
            Next5CandlesProb = result.Next5CandlesProb,
            Next10CandlesProb = result.Next10CandlesProb,
            EstimatedRangePercent = result.EstimatedRangePercent,
            Regime = result.Regime,
            VolumeExplosion = result.VolumeExplosion,
            GroupScores = result.GroupScores == null ? new Nexus5GroupScoresDto() : new Nexus5GroupScoresDto
            {
                G1PriceAction = result.GroupScores.G1PriceAction,
                G2SmcIct = result.GroupScores.G2SmcIct,
                G3Wyckoff = result.GroupScores.G3Wyckoff,
                G4Fractals = result.GroupScores.G4Fractals,
                G5Volume = result.GroupScores.G5Volume,
                G6Ml = result.GroupScores.G6Ml
            },
            Features = result.Features == null ? new Nexus5FeaturesDto() : new Nexus5FeaturesDto
            {
                CompressionRange = result.Features.CompressionRange,
                IgnitionCandle = result.Features.IgnitionCandle,
                EfficiencyCheck = result.Features.EfficiencyCheck,
                DisplacementFvg = result.Features.DisplacementFvg,
                MicroChoch = result.Features.MicroChoch,
                InstantOrderBlock = result.Features.InstantOrderBlock,
                CompressionZone = result.Features.CompressionZone,
                SosDetected = result.Features.SosDetected,
                JumpingCreek = result.Features.JumpingCreek,
                FractalHighBreak = result.Features.FractalHighBreak,
                Ema7Angle = result.Features.Ema7Angle,
                HhHlSequence = result.Features.HhHlSequence,
                RelativeVolMultiplier = result.Features.RelativeVolMultiplier,
                VolIntensity = result.Features.VolIntensity,
                BuyingImbalance = result.Features.BuyingImbalance,
                AtrExpansion = result.Features.AtrExpansion,
                ZScore = result.Features.ZScore,
                RsiVelocity = result.Features.RsiVelocity,
                // Estructural Analysis (v8.0)
                SlopeMa50 = result.Features.SlopeMa50,
                SlopeMa99 = result.Features.SlopeMa99,
                GravityMa99Safe = result.Features.GravityMa99Safe,
                VolRatio = result.Features.VolRatio,
                CompressionViper = result.Features.CompressionViper,
                Ma50Horizontal = result.Features.Ma50Horizontal,
                Ma50Ma99Distance = result.Features.Ma50Ma99Distance,
                PriceToMa99Pct = result.Features.PriceToMa99Pct
            },
            Detectivity = result.Detectivity ?? new Dictionary<string, string>()
        };
    }
}
