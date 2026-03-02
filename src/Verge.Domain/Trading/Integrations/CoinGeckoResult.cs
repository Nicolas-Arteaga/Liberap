namespace Verge.Trading.Integrations;

public class CoinGeckoResult
{
    public decimal PriceUsd { get; set; }
    public decimal MarketCapUsd { get; set; }
    public decimal Volume24hUsd { get; set; }

    public decimal MarketCap => MarketCapUsd;
    public decimal TotalVolume => Volume24hUsd;
}
