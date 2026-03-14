using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IMarketDataAppService : IApplicationService
{
    Task<List<MarketCandleDto>> GetCandlesAsync(GetMarketCandlesInput input);
    Task<MarketOrderBookDto> GetOrderBookAsync(GetMarketDataInput input);
    Task<List<RecentTradeDto>> GetRecentTradesAsync(GetMarketDataInput input);
}
