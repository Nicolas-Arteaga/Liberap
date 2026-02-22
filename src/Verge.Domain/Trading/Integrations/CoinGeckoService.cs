using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Logging;
using Volo.Abp.Caching;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.Integrations;

public class CoinGeckoService : DomainService, ICoinGeckoService
{
    private readonly HttpClient _httpClient;
    private readonly IDistributedCache<CoinGeckoResult> _cache;
    private readonly ILogger<CoinGeckoService> _logger;

    // Mapeo simple de simbolos a IDs de CoinGecko
    private static readonly Dictionary<string, string> _symbolToIdMap = new(StringComparer.OrdinalIgnoreCase)
    {
        { "BTC", "bitcoin" },
        { "ETH", "ethereum" },
        { "BNB", "binancecoin" },
        { "SOL", "solana" },
        { "XRP", "ripple" },
        { "ADA", "cardano" }
    };

    public CoinGeckoService(
        HttpClient httpClient,
        IDistributedCache<CoinGeckoResult> cache,
        ILogger<CoinGeckoService> logger)
    {
        _httpClient = httpClient;
        _cache = cache;
        _logger = logger;
        _httpClient.DefaultRequestHeaders.Add("User-Agent", "VergeTradingBot/1.0"); // CoinGecko requiere User-Agent
    }

    public async Task<CoinGeckoResult?> GetTokenDataAsync(string symbol)
    {
        string currency = symbol.Replace("USDT", "").Replace("USD", "").ToUpper();
        
        if (!_symbolToIdMap.TryGetValue(currency, out string? coinId))
        {
            _logger.LogWarning("⚠️ No CoinGecko mapping found for symbol {Symbol}", currency);
            return null;
        }

        string cacheKey = $"CoinGeckoData_{coinId}";

        try
        {
            return await _cache.GetOrAddAsync(
                cacheKey,
                async () => await FetchFromApiAsync(coinId),
                () => new DistributedCacheEntryOptions
                {
                    AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5) // Actualizar cada 5 minutos
                }
            );
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error retrieving CoinGecko data for {CoinId}", coinId);
            return null;
        }
    }

    private async Task<CoinGeckoResult?> FetchFromApiAsync(string coinId)
    {
        _logger.LogInformation("🦎 Fetching CoinGecko data for {CoinId}...", coinId);
        var url = $"https://api.coingecko.com/api/v3/simple/price?ids={coinId}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true";
        
        // El formato es dict[string, dict[string, decimal]] -> {"bitcoin": {"usd": 68000, "usd_market_cap": 1200000000, "usd_24h_vol": 30000000}}
        var response = await _httpClient.GetFromJsonAsync<Dictionary<string, Dictionary<string, decimal>>>(url);
        
        if (response != null && response.TryGetValue(coinId, out var data))
        {
            return new CoinGeckoResult
            {
                PriceUsd = data.GetValueOrDefault("usd"),
                MarketCapUsd = data.GetValueOrDefault("usd_market_cap"),
                Volume24hUsd = data.GetValueOrDefault("usd_24h_vol")
            };
        }

        return null;
    }
}
