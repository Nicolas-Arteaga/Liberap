using System;
using System.Collections.Generic;

namespace Verge.Trading;

public class MarketCandleDto
{
    public long Time { get; set; } // Unix timestamp in seconds for lightweight-charts
    public decimal Open { get; set; }
    public decimal High { get; set; }
    public decimal Low { get; set; }
    public decimal Close { get; set; }
}

public class GetMarketCandlesInput
{
    public string Symbol { get; set; } = "BTCUSDT";
    public string Interval { get; set; } = "1m";
    public int Limit { get; set; } = 100;
}

public class GetMarketDataInput
{
    public string Symbol { get; set; } = "BTCUSDT";
    public int Limit { get; set; } = 20;
}

public class MarketOrderBookDto
{
    public List<OrderBookEntryDto> Bids { get; set; } = new();
    public List<OrderBookEntryDto> Asks { get; set; } = new();
}

public class OrderBookEntryDto
{
    public decimal Price { get; set; }
    public decimal Amount { get; set; }
}

public class RecentTradeDto
{
    public long Id { get; set; }
    public decimal Price { get; set; }
    public decimal Amount { get; set; }
    public long Time { get; set; }
    public bool IsBuyerMaker { get; set; }
}
