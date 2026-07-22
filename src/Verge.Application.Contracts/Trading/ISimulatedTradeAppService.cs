using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Verge.Trading.DTOs;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface ISimulatedTradeAppService : IApplicationService
{
    Task<SimulatedTradeDto> OpenTradeAsync(OpenTradeInputDto input);
    Task<SimulatedTradeDto> CloseTradeAsync(Guid tradeId);
    Task<List<SimulatedTradeDto>> GetActiveTradesAsync();
    Task<List<SimulatedTradeDto>> GetTradeHistoryAsync();
    Task<decimal> GetVirtualBalanceAsync();
    Task<SimulationPerformanceDto> GetPerformanceStatsAsync(Guid? strategyProfileId = null);
    Task<List<SimulatedTradeDto>> GetRecentTradesAsync(int limit = 20);
    Task UpdateTpSlAsync(Guid tradeId, UpdateTpSlInputDto input);
    Task UpdateMaxAdversePriceAsync(Guid tradeId, UpdateMaxAdversePriceInputDto input);
    Task UpdateMaxFavorablePriceAsync(Guid tradeId, UpdateMaxFavorablePriceInputDto input);
    Task UpdateExitInfoAsync(Guid tradeId, UpdateExitInfoInputDto input);
}
