using System.Collections.Generic;
using System.Threading.Tasks;
using Verge.Trading.Scar;

namespace Verge.Trading.Scar;

public interface IPythonScarService
{
    Task<List<ScarResponseModel>> ScanAsync(List<string> symbols);
    Task<ScarResponseModel?> GetScoreAsync(string symbol);
    Task<List<ScarResponseModel>> GetActiveAlertsAsync(int threshold);
    Task<List<ScarTopSetupModel>> GetTopSetupsAsync(int limit);

    Task<List<ScarPredictionModel>> GetPredictionsAsync(string? status, int limit);
    Task<ScarAccuracyModel> GetAccuracyAsync(string? symbol);
    Task SubmitFeedbackAsync(int predictionId, string result);
    Task<List<ScarTemplateAdjustmentModel>> GetAdjustmentsAsync(int limit);
}
