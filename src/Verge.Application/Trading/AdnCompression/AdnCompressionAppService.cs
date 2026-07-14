using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Application.Services;

namespace Verge.Trading.AdnCompression;

public class AdnCompressionAppService : ApplicationService, IAdnCompressionAppService
{
    private readonly IPythonAdnCompressionService _pythonService;
    private readonly ILogger<AdnCompressionAppService> _logger;

    public AdnCompressionAppService(IPythonAdnCompressionService pythonService, ILogger<AdnCompressionAppService> logger)
    {
        _pythonService = pythonService;
        _logger = logger;
    }

    public async Task<AdnCompressionScanResponseDto> ScanAsync(List<string> symbols, string timeframe = "5m")
    {
        try
        {
            _logger.LogInformation("🧬 [ADN-COMPRESSION] Scanning {Count} symbols @ {Timeframe}...", symbols.Count, timeframe);

            var result = await _pythonService.ScanAsync(symbols, timeframe);
            if (result == null)
            {
                _logger.LogWarning("⚠️ [ADN-COMPRESSION] No results from Python service");
                return new AdnCompressionScanResponseDto
                {
                    Top10 = new List<AdnCompressionItemDto>(),
                    ScannedCount = symbols.Count,
                    QualifiedCount = 0,
                    AnalyzedAt = DateTime.UtcNow
                };
            }

            var dto = new AdnCompressionScanResponseDto
            {
                Top10 = result.Top10?.Select(item => new AdnCompressionItemDto
                {
                    Symbol = item.Symbol,
                    Timeframe = item.Timeframe,
                    Phase = item.Phase,
                    Direction = item.Direction,
                    Ma7Crossings = item.Ma7Crossings,
                    CompressionCandles = item.CompressionCandles,
                    IgnitionMultiplier = item.IgnitionMultiplier,
                    CandlesSinceIgnition = item.CandlesSinceIgnition,
                    CurrentPrice = item.CurrentPrice,
                    Ma7Now = item.Ma7Now,
                    Ma25Now = item.Ma25Now,
                    Ma99Now = item.Ma99Now,
                    DistToMa7Pct = item.DistToMa7Pct,
                    DistToMa25Pct = item.DistToMa25Pct,
                    TouchedMa25SinceIgnition = item.TouchedMa25SinceIgnition,
                    Reasons = item.Reasons ?? new List<string>()
                }).ToList() ?? new List<AdnCompressionItemDto>(),
                ScannedCount = result.ScannedCount,
                QualifiedCount = result.QualifiedCount,
                AnalyzedAt = result.AnalyzedAt
            };

            _logger.LogInformation("✅ [ADN-COMPRESSION] Scan complete: {Count} qualified", dto.QualifiedCount);
            return dto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ADN-COMPRESSION] Scan failed");
            return new AdnCompressionScanResponseDto
            {
                Top10 = new List<AdnCompressionItemDto>(),
                ScannedCount = symbols.Count,
                QualifiedCount = 0,
                AnalyzedAt = DateTime.UtcNow
            };
        }
    }
}
