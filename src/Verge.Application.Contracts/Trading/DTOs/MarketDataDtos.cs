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
