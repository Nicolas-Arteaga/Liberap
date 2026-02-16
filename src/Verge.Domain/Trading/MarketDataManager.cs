using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Services;

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
        try
        {
            var client = _httpClientFactory.CreateClient();
            
            // LOG: qué intervalo llegó
            Logger.LogInformation($"📥 GetCandlesAsync llamado para {symbol} con interval: '{interval}'");
            
            // LIMPIEZA DEL SÍMBOLO (saco / y espacios)
            symbol = symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
            
            // CONVERSIÓN DEL INTERVALO
            string binanceInterval = interval switch
            {
                "1" => "1m",
                "5" => "5m",
                "15" => "15m",
                "30" => "30m",
                "60" => "1h",
                "240" => "4h",
                "1D" => "1d",
                "1W" => "1w",
                "1M" => "1M",
                _ => interval // si ya viene en formato correcto
            };
            
            // LOG: a qué se convirtió
            Logger.LogInformation($"🔄 Interval convertido: '{interval}' -> '{binanceInterval}'");
            
            var url = $"{BinanceBaseUrl}/api/v3/klines?symbol={symbol}&interval={binanceInterval}&limit={limit}";
            Logger.LogInformation($"📡 URL final: {url}");

            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode)
            {
                var error = await response.Content.ReadAsStringAsync();
                Logger.LogError($"❌ Error de Binance: {response.StatusCode} - {error}");
                return new List<MarketCandleModel>(); // Devuelvo vacío en lugar de explotar
            }

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
        catch (Exception ex)
        {
            Console.WriteLine($"💥 EXCEPCIÓN en MarketDataManager: {ex.Message}");
            return new List<MarketCandleModel>(); // Devuelvo vacío
        }
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
