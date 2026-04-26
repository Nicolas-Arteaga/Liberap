using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Scar;

public class ScarAppService : ApplicationService, IScarAppService
{
    private readonly IPythonScarService _pythonService;
    private readonly ILogger<ScarAppService> _logger;

    public ScarAppService(IPythonScarService pythonService, ILogger<ScarAppService> logger)
    {
        _pythonService = pythonService;
        _logger = logger;
    }

    public async Task<List<ScarResultDto>> ScanAsync(List<string> symbols)
    {
        _logger.LogInformation("🐋 [SCAR] Scanning {Count} symbols", symbols.Count);
        var models = await _pythonService.ScanAsync(symbols);
        return models.Select(MapToDto).ToList();
    }

    public async Task<ScarResultDto?> GetScoreAsync(string symbol)
    {
        _logger.LogInformation("🐋 [SCAR] Getting score for {Symbol}", symbol);
        var model = await _pythonService.GetScoreAsync(symbol);
        if (model == null) return null;
        return MapToDto(model);
    }

    public async Task<List<ScarResultDto>> GetActiveAlertsAsync(int threshold = 3)
    {
        _logger.LogInformation("🐋 [SCAR] Getting active alerts (threshold {Threshold})", threshold);
        var models = await _pythonService.GetActiveAlertsAsync(threshold);
        return models.Select(MapToDto).ToList();
    }

    public async Task<List<ScarTopSetupDto>> GetTopSetupsAsync(int limit = 10)
    {
        _logger.LogInformation("🐋 [SCAR] Getting top {Limit} setups", limit);
        var models = await _pythonService.GetTopSetupsAsync(limit);
        return models.Select(m => new ScarTopSetupDto
        {
            Symbol = m.Symbol,
            ScoreGrial = m.ScoreGrial,
            Prediction = m.Prediction,
            EstimatedHours = m.EstimatedHours,
            Mode = m.Mode
        }).ToList();
    }

    private ScarResultDto MapToDto(ScarResponseModel model)
    {
        return new ScarResultDto
        {
            Symbol = model.Symbol,
            ScoreGrial = model.ScoreGrial,
            Prediction = model.Prediction,
            EstimatedHours = model.EstimatedHours,
            FlagWhaleWithdrawal = model.FlagWhaleWithdrawal,
            FlagSupplyDrying = model.FlagSupplyDrying,
            FlagPriceStable = model.FlagPriceStable,
            FlagFundingNegative = model.FlagFundingNegative,
            FlagSilence = model.FlagSilence,
            DaysSinceLastPump = model.DaysSinceLastPump,
            EstimatedNextWindow = model.EstimatedNextWindow,
            WithdrawalDaysCount = model.WithdrawalDaysCount,
            TotalWithdrawnUsd = model.TotalWithdrawnUsd,
            Mode = model.Mode,
            AnalyzedAt = model.AnalyzedAt
        };
    }

    public async Task<List<ScarPredictionDto>> GetPredictionsAsync(string? status = null, int limit = 50)
    {
        var models = await _pythonService.GetPredictionsAsync(status, limit);
        return models.Select(m => new ScarPredictionDto
        {
            Id = m.Id,
            TokenSymbol = m.TokenSymbol,
            AlertDate = m.AlertDate,
            ScoreGrial = m.ScoreGrial,
            PriceAtAlert = m.PriceAtAlert,
            EstimatedHours = m.EstimatedHours,
            Status = m.Status,
            MaxPrice24h = m.MaxPrice24h,
            PatternDetected = m.PatternDetected,
            TraderRoiPct = m.TraderRoiPct,
            ResultDate = m.ResultDate
        }).ToList();
    }

    public async Task<ScarAccuracyDto> GetAccuracyAsync(string? symbol = null)
    {
        var m = await _pythonService.GetAccuracyAsync(symbol);
        return new ScarAccuracyDto
        {
            TokenSymbol = m.TokenSymbol,
            TotalPredictions = m.TotalPredictions,
            TotalHits = m.TotalHits,
            TotalFalseAlarms = m.TotalFalseAlarms,
            SystemHitRate = m.SystemHitRate,
            AvgTraderRoi = m.AvgTraderRoi,
            LastUpdated = m.LastUpdated
        };
    }

    public async Task SubmitFeedbackAsync(int predictionId, string result)
    {
        await _pythonService.SubmitFeedbackAsync(predictionId, result);
    }

    public async Task<List<ScarTemplateAdjustmentDto>> GetAdjustmentsAsync(int limit = 20)
    {
        var models = await _pythonService.GetAdjustmentsAsync(limit);
        return models.Select(m => new ScarTemplateAdjustmentDto
        {
            Id = m.Id,
            TokenSymbol = m.TokenSymbol,
            AdjustmentDate = m.AdjustmentDate,
            OldAvgDays = m.OldAvgDays,
            NewAvgDays = m.NewAvgDays,
            Reason = m.Reason
        }).ToList();
    }
}
