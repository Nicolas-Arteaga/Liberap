using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IValidationAppService : IApplicationService
{
    Task<WalkForwardReportDto> RunWalkForwardAnalysisAsync(string symbol, TradingStyle style, bool runInBackground = true);
    Task<MonteCarloReportDto> RunMonteCarloSimulationAsync(string symbol, TradingStyle style, int iterations = 10000, bool runInBackground = true);
    Task<StressTestReportDto> RunStressTestAsync(string symbol, TradingStyle style, bool runInBackground = true);
}
