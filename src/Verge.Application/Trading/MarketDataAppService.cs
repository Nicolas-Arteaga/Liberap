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

    public async Task<MarketOrderBookDto> GetOrderBookAsync(GetMarketDataInput input)
    {
        var model = await _marketDataManager.GetOrderBookAsync(input.Symbol, input.Limit);
        return new MarketOrderBookDto
        {
            Bids = model.Bids.Select(b => new OrderBookEntryDto { Price = b.Price, Amount = b.Amount }).ToList(),
            Asks = model.Asks.Select(a => new OrderBookEntryDto { Price = a.Price, Amount = a.Amount }).ToList()
        };
    }

    public async Task<List<RecentTradeDto>> GetRecentTradesAsync(GetMarketDataInput input)
    {
        var trades = await _marketDataManager.GetRecentTradesAsync(input.Symbol, input.Limit);
        return trades.Select(t => new RecentTradeDto
        {
            Id = t.Id,
            Price = t.Price,
            Amount = t.Amount,
            Time = t.Time,
            IsBuyerMaker = t.IsBuyerMaker
        }).ToList();
    }
}
