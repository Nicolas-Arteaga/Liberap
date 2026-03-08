using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IExecutionAppService : IApplicationService
{
    Task<PaperTradingReportDto> RunPaperTradingSimulationAsync(string symbol, int simulatedDays = 30, bool runInBackground = true);
    Task<LiveShadowReportDto> RunLiveShadowAnalysisAsync(string symbol, int signalsToAnalyze = 100, bool runInBackground = true);
}
