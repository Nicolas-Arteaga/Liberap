using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Agent;

public interface IAgentAppService : IApplicationService
{
    Task StartServerAsync();
    Task StopServerAsync();
    Task StartAgentAsync();
    Task StopAgentAsync();
    Task<object> GetSystemStateAsync();

    Task<object> GetAuditSummaryAsync();
    Task<object> GetStrategyStatsAsync();
    Task<object> GetRecentTradesAsync(int limit = 10);
    Task<object> GetTopSymbolsAsync(int limit = 5);
    Task<object> GetOpenPositionsAsync();
}
