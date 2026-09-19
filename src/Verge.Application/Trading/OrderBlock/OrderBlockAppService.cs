using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Application.Services;

namespace Verge.Trading.OrderBlock;

public class OrderBlockAppService : ApplicationService, IOrderBlockAppService
{
    private readonly IPythonOrderBlockService _pythonService;
    private readonly ILogger<OrderBlockAppService> _logger;

    public OrderBlockAppService(IPythonOrderBlockService pythonService, ILogger<OrderBlockAppService> logger)
    {
        _pythonService = pythonService;
        _logger = logger;
    }

    private static ObZoneDto MapZone(ObZoneModel z)
    {
        return new ObZoneDto
        {
            Id = z.Id,
            Direction = z.Direction,
            Top = z.Top,
            Bottom = z.Bottom,
            BosPrice = z.BosPrice,
            FormedAt = z.FormedAt,
            FormedAtMs = z.FormedAtMs,
            CandleIndex = z.CandleIndex,
            EntryStatus = z.EntryStatus,
            DistToEntryPct = z.DistToEntryPct,
            PocConfluence = z.PocConfluence,
            PocDistancePct = z.PocDistancePct,
            ConfluenceScore = z.ConfluenceScore,
            SlPrice = z.SlPrice,
            TpPrice = z.TpPrice,
            TpDistancePct = z.TpDistancePct,
            ValidatedStable = z.ValidatedStable
        };
    }

    public async Task<ObAnalyzeResponseDto?> AnalyzeOnDemandAsync(string symbol, string interval = "15m")
    {
        try
        {
            var normalized = symbol.Contains(':') ? symbol.Split(':')[0] : symbol;
            var cleanSymbol = normalized.ToUpper().Replace("/", "").Replace("-", "").Trim();

            _logger.LogInformation("🔍 [ORDERBLOCK] OnDemand: {Symbol} ({Interval})", cleanSymbol, interval);

            var result = await _pythonService.AnalyzeAsync(cleanSymbol, interval);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [ORDERBLOCK] No result from Python service for {Symbol}", cleanSymbol);
                return null;
            }

            return new ObAnalyzeResponseDto
            {
                Symbol = result.Symbol,
                Interval = result.Interval,
                AnalyzedAt = result.AnalyzedAt,
                CurrentPrice = result.CurrentPrice,
                Zones = result.Zones?.Select(MapZone).ToList() ?? new List<ObZoneDto>()
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ORDERBLOCK] OnDemand analysis failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<ObScanResponseDto> ScanAsync(List<string> symbols, string interval = "15m", bool onlyValidated = true)
    {
        try
        {
            _logger.LogInformation("📊 [ORDERBLOCK] Initiating scan for {Count} symbols ({Interval})...", symbols.Count, interval);

            var result = await _pythonService.ScanAsync(symbols, interval, onlyValidated);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [ORDERBLOCK] No results from Python service");
                return new ObScanResponseDto
                {
                    Top5 = new List<ObScanItemDto>(),
                    ScannedCount = symbols.Count,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new ObScanResponseDto
            {
                Top5 = result.Top5?.Select(item => new ObScanItemDto
                {
                    Symbol = item.Symbol,
                    Direction = item.Direction,
                    Top = item.Top,
                    Bottom = item.Bottom,
                    CurrentPrice = item.CurrentPrice,
                    PocConfluence = item.PocConfluence,
                    PocDistancePct = item.PocDistancePct,
                    EntryStatus = item.EntryStatus,
                    DistToEntryPct = item.DistToEntryPct,
                    SlPrice = item.SlPrice,
                    TpPrice = item.TpPrice,
                    TpDistancePct = item.TpDistancePct,
                    ConfluenceScore = item.ConfluenceScore,
                    FormedAt = item.FormedAt,
                    ValidatedStable = item.ValidatedStable
                }).ToList() ?? new List<ObScanItemDto>(),
                ScannedCount = result.ScannedCount,
                AnalyzedAt = result.AnalyzedAt,
                ActionableCount = result.ActionableCount
            };

            _logger.LogInformation("✅ [ORDERBLOCK] Scan complete: {Count} opportunities found", dto.Top5.Count);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ORDERBLOCK] Scan failed");
            return new ObScanResponseDto
            {
                Top5 = new List<ObScanItemDto>(),
                ScannedCount = symbols.Count,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }
}
