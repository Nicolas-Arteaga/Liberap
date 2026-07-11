using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Fvg;

public class FvgAppService : ApplicationService, IFvgAppService
{
    private readonly IPythonFvgService _pythonService;
    private readonly ILogger<FvgAppService> _logger;

    public FvgAppService(IPythonFvgService pythonService, ILogger<FvgAppService> logger)
    {
        _pythonService = pythonService;
        _logger = logger;
    }

    private static FvgZoneDto? MapZone(FvgZoneModel? z)
    {
        if (z == null) return null;
        return new FvgZoneDto
        {
            Id = z.Id,
            Direction = z.Direction,
            Top = z.Top,
            Bottom = z.Bottom,
            GapPct = z.GapPct,
            FormedAt = z.FormedAt,
            FormedAtMs = z.FormedAtMs,
            CandleIndex = z.CandleIndex,
            FillProgressPct = z.FillProgressPct,
            PocConfluence = z.PocConfluence,
            PocDistancePct = z.PocDistancePct,
            EntryStatus = z.EntryStatus,
            DistToEntryPct = z.DistToEntryPct,
            TpProgressPct = z.TpProgressPct,
            ConfluenceScore = z.ConfluenceScore,
            SlPrice = z.SlPrice,
            TpPrice = z.TpPrice,
            IsIfvg = z.IsIfvg,
            SourceInterval = z.SourceInterval
        };
    }

    public async Task<FvgAnalyzeResponseDto?> AnalyzeOnDemandAsync(string symbol, string interval = "15m")
    {
        try
        {
            // Normalize symbol for Binance: "SIREN/USDT:USDT" -> "SIRENUSDT"
            var normalized = symbol.Contains(':') ? symbol.Split(':')[0] : symbol;
            var cleanSymbol = normalized.ToUpper().Replace("/", "").Replace("-", "").Trim();

            _logger.LogInformation("🔍 [FVG] OnDemand: {Symbol} ({Interval})", cleanSymbol, interval);

            var result = await _pythonService.AnalyzeAsync(cleanSymbol, interval);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [FVG] No result from Python service for {Symbol}", cleanSymbol);
                return null;
            }

            return new FvgAnalyzeResponseDto
            {
                Symbol = result.Symbol,
                Interval = result.Interval,
                AnalyzedAt = result.AnalyzedAt,
                CurrentPrice = result.CurrentPrice,
                PocPrice = result.PocPrice,
                Zones = result.Zones?.Select(z => MapZone(z)!).ToList() ?? new List<FvgZoneDto>(),
                VolumeProfile = result.VolumeProfile?.Select(b => new VolumeProfileBinDto
                {
                    PriceLow = b.PriceLow,
                    PriceHigh = b.PriceHigh,
                    Volume = b.Volume,
                    IsPoc = b.IsPoc,
                    IsHvn = b.IsHvn
                }).ToList() ?? new List<VolumeProfileBinDto>()
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] OnDemand analysis failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<FvgScanResponseDto> ScanAsync(List<string> symbols, string interval = "15m")
    {
        try
        {
            _logger.LogInformation("📊 [FVG] Initiating scan for {Count} symbols ({Interval})...", symbols.Count, interval);

            var result = await _pythonService.ScanAsync(symbols, interval);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [FVG] No results from Python service");
                return new FvgScanResponseDto
                {
                    Top5 = new List<FvgScanItemDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new FvgScanResponseDto
            {
                Top5 = result.Top5?.Select(item => new FvgScanItemDto
                {
                    Symbol = item.Symbol,
                    Direction = item.Direction,
                    Top = item.Top,
                    Bottom = item.Bottom,
                    GapPct = item.GapPct,
                    CurrentPrice = item.CurrentPrice,
                    PocConfluence = item.PocConfluence,
                    PocDistancePct = item.PocDistancePct,
                    EntryStatus = item.EntryStatus,
                    DistToEntryPct = item.DistToEntryPct,
                    TpPrice = item.TpPrice,
                    ConfluenceScore = item.ConfluenceScore,
                    FillProgressPct = item.FillProgressPct,
                    FormedAt = item.FormedAt
                }).ToList() ?? new List<FvgScanItemDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [FVG] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] Scan failed");
            return new FvgScanResponseDto
            {
                Top5 = new List<FvgScanItemDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }

    private static FvgCascadeResultDto MapCascadeResult(FvgCascadeResultModel result)
    {
        return new FvgCascadeResultDto
        {
            Symbol = result.Symbol,
            CascadeStatus = result.CascadeStatus,
            BiasZone = MapZone(result.BiasZone),
            ConfirmationZone = MapZone(result.ConfirmationZone),
            ExecutionZone = MapZone(result.ExecutionZone),
            EntryPriceZone = MapZone(result.EntryPriceZone),
            CurrentPrice = result.CurrentPrice,
            ConfluenceScore = result.ConfluenceScore,
            AnalyzedAt = result.AnalyzedAt
        };
    }

    /// <summary>Cascada 15m (sesgo) -> 5m (confirmación) -> 1m (ejecución) para un símbolo.</summary>
    public async Task<FvgCascadeResultDto?> CascadeAsync(string symbol)
    {
        try
        {
            var normalized = symbol.Contains(':') ? symbol.Split(':')[0] : symbol;
            var cleanSymbol = normalized.ToUpper().Replace("/", "").Replace("-", "").Trim();

            _logger.LogInformation("🔀 [FVG-CASCADE] {Symbol}", cleanSymbol);

            var result = await _pythonService.CascadeAsync(cleanSymbol);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [FVG-CASCADE] No result from Python service for {Symbol}", cleanSymbol);
                return null;
            }

            return MapCascadeResult(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG-CASCADE] Cascade analysis failed for {Symbol}", symbol);
            return null;
        }
    }

    /// <summary>Escanea una lista de símbolos con la cascada completa, top-5 de setups accionables.</summary>
    public async Task<FvgCascadeScanResponseDto> CascadeScanAsync(List<string> symbols)
    {
        try
        {
            _logger.LogInformation("🔀 [FVG-CASCADE-SCAN] Initiating cascade scan for {Count} symbols...", symbols.Count);

            var result = await _pythonService.CascadeScanAsync(symbols);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [FVG-CASCADE-SCAN] No results from Python service");
                return new FvgCascadeScanResponseDto
                {
                    Top5 = new List<FvgCascadeResultDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new FvgCascadeScanResponseDto
            {
                Top5 = result.Top5?.Select(MapCascadeResult).ToList() ?? new List<FvgCascadeResultDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [FVG-CASCADE-SCAN] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG-CASCADE-SCAN] Cascade scan failed");
            return new FvgCascadeScanResponseDto
            {
                Top5 = new List<FvgCascadeResultDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }
}
