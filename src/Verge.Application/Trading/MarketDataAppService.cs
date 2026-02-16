using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public class MarketDataAppService : ApplicationService, IMarketDataAppService
{
    private readonly MarketDataManager _marketDataManager;

    public MarketDataAppService(MarketDataManager marketDataManager)
    {
        _marketDataManager = marketDataManager;
    }

    public async Task<List<MarketCandleDto>> GetCandlesAsync(GetMarketCandlesInput input)
    {
        var candles = await _marketDataManager.GetCandlesAsync(input.Symbol, input.Interval, input.Limit);

        return candles.Select(c => new MarketCandleDto
        {
            Time = c.Timestamp / 1000, // Convert to seconds for lightweight-charts
            Open = c.Open,
            High = c.High,
            Low = c.Low,
            Close = c.Close
        }).ToList();
    }
}
