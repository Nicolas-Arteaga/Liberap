using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Volo.Abp.Domain.Services;
using Microsoft.Extensions.Http;

namespace Verge.Trading;

public class MarketDataManager : DomainService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private const string BinanceBaseUrl = "https://api.binance.com";

    public MarketDataManager(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    public async Task<List<MarketCandleModel>> GetCandlesAsync(string symbol, string interval, int limit = 100)
    {
        var client = _httpClientFactory.CreateClient();
        var url = $"{BinanceBaseUrl}/api/v3/klines?symbol={symbol.ToUpper()}&interval={interval}&limit={limit}";

        var response = await client.GetAsync(url);
        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        var rawCandles = JsonSerializer.Deserialize<List<List<JsonElement>>>(content);

        var result = new List<MarketCandleModel>();

        if (rawCandles != null)
        {
            foreach (var raw in rawCandles)
            {
                result.Add(new MarketCandleModel
                {
                    Timestamp = raw[0].GetInt64(),
                    Open = decimal.Parse(raw[1].GetString()!, System.Globalization.CultureInfo.InvariantCulture),
                    High = decimal.Parse(raw[2].GetString()!, System.Globalization.CultureInfo.InvariantCulture),
                    Low = decimal.Parse(raw[3].GetString()!, System.Globalization.CultureInfo.InvariantCulture),
                    Close = decimal.Parse(raw[4].GetString()!, System.Globalization.CultureInfo.InvariantCulture),
                    Volume = decimal.Parse(raw[5].GetString()!, System.Globalization.CultureInfo.InvariantCulture)
                });
            }
        }

        return result;
    }
}

public class MarketCandleModel
{
    public long Timestamp { get; set; }
    public decimal Open { get; set; }
    public decimal High { get; set; }
    public decimal Low { get; set; }
    public decimal Close { get; set; }
    public decimal Volume { get; set; }
}
