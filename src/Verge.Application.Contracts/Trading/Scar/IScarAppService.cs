using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Scar;

public interface IScarAppService : IApplicationService
{
    /// <summary>Scan a list of symbols for the 5 SCAR whale-withdrawal signals.</summary>
    Task<List<ScarResultDto>> ScanAsync(List<string> symbols);

    /// <summary>Get SCAR score for a single symbol (triggers a fresh analysis).</summary>
    Task<ScarResultDto> GetScoreAsync(string symbol);

    /// <summary>Return today's signals with score_grial >= threshold (from DB cache).</summary>
    Task<List<ScarResultDto>> GetActiveAlertsAsync(int threshold = 3);

    /// <summary>Return top N tokens by score_grial from today's cached results.</summary>
    Task<List<ScarTopSetupDto>> GetTopSetupsAsync(int limit = 10);

    // --- Analytics & Feedback Loop ---
    Task<List<ScarPredictionDto>> GetPredictionsAsync(string? status = null, int limit = 50);
    Task<ScarAccuracyDto> GetAccuracyAsync(string? symbol = null);
    Task SubmitFeedbackAsync(int predictionId, string result);
    Task<List<ScarTemplateAdjustmentDto>> GetAdjustmentsAsync(int limit = 20);
}
