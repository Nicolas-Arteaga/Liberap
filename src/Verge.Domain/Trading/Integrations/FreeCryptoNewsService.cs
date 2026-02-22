using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Caching.Distributed;
using Volo.Abp.Domain.Services;
using Volo.Abp.Caching;
using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Verge.Trading.Integrations;

#region API DTOs
public class FreeNewsApiResponse
{
    public List<FreeNewsArticle> Articles { get; set; } = new();
    public int Total { get; set; }
}

public class FreeNewsArticle
{
    public string Title { get; set; } = string.Empty;
    public string Source { get; set; } = string.Empty;
    public DateTime PublishedAt { get; set; }
    public string Url { get; set; } = string.Empty;
}

public class SentimentApiResponse
{
    public string Label { get; set; } = string.Empty; // positive, negative, neutral
    public float Score { get; set; }
}

// CryptoCompare DTOs for Backup
public class CryptoCompareNewsResponse
{
    [JsonPropertyName("Data")]
    public List<CryptoCompareNewsItem> Data { get; set; } = new();
}

public class CryptoCompareNewsItem
{
    public string Title { get; set; } = string.Empty;
    public string Source { get; set; } = string.Empty;
    public long Published_on { get; set; }
    public string Url { get; set; } = string.Empty;
}
#endregion

#region Internal Models
public class CryptoNewsResult
{
    public List<CryptoNewsItem> News { get; set; } = new();
    public SentimentAnalysis? GlobalSentiment { get; set; }
}

public class CryptoNewsItem
{
    public string Title { get; set; } = string.Empty;
    public string Source { get; set; } = string.Empty;
    public DateTime PublishedAt { get; set; }
    public string Url { get; set; } = string.Empty;
}

public class SentimentAnalysis
{
    public string Label { get; set; } = string.Empty;
    public float Score { get; set; }
    public string Source { get; set; } = "FreeCryptoNews AI";
}
#endregion

public class FreeCryptoNewsService : DomainService, IFreeCryptoNewsService
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<FreeCryptoNewsService> _logger;
    private readonly IDistributedCache<CryptoNewsResult> _cache;
    private readonly IDistributedCache<SentimentAnalysis> _sentimentCache;
    private readonly MarketDataManager _marketDataManager;

    // Simple Circuit Breaker State (Static for cross-scope persistence in Host)
    private static readonly ConcurrentDictionary<string, (int FailCount, DateTime DisabledUntil)> _circuitBreakers = new();

    public FreeCryptoNewsService(
        HttpClient httpClient, 
        ILogger<FreeCryptoNewsService> logger,
        IDistributedCache<CryptoNewsResult> cache,
        IDistributedCache<SentimentAnalysis> sentimentCache,
        MarketDataManager marketDataManager)
    {
        _httpClient = httpClient;
        _logger = logger;
        _cache = cache;
        _sentimentCache = sentimentCache;
        _marketDataManager = marketDataManager;
        _httpClient.Timeout = TimeSpan.FromSeconds(2.5); // Architecture requirement
    }

    public async Task<CryptoNewsResult?> GetNewsAsync(string symbol, int limit = 10)
    {
        var ticker = symbol.Replace("USDT", "").Replace("USD", "").ToUpper();
        var cacheKey = $"News_{ticker}_{limit}";

        return await _cache.GetOrAddAsync(
            cacheKey,
            async () => await FetchAggregatedNewsAsync(ticker, limit),
            () => new DistributedCacheEntryOptions { AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(15) }
        );
    }

    public async Task<SentimentAnalysis?> GetSentimentAsync(string symbol)
    {
        var ticker = symbol.Replace("USDT", "").Replace("USD", "").ToUpper();
        var cacheKey = $"Sentiment_{ticker}";

        return await _sentimentCache.GetOrAddAsync(
            cacheKey,
            async () => await FetchAggregatedSentimentAsync(ticker),
            () => new DistributedCacheEntryOptions { AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(15) }
        );
    }

    private async Task<CryptoNewsResult?> FetchAggregatedNewsAsync(string ticker, int limit)
    {
        // 1. Primary: Cryptocurrency.cv
        var news = await TryFetchPrimaryNewsAsync(ticker, limit);
        if (news != null && news.Any())
        {
            return new CryptoNewsResult { News = news };
        }

        // 2. Backup: CryptoCompare (Public API)
        news = await TryFetchBackupNewsAsync(ticker, limit);
        if (news != null && news.Any())
        {
            return new CryptoNewsResult { News = news };
        }

        // 3. Synthetic: Based on Technicals
        return await GenerateSyntheticNewsAsync(ticker);
    }

    private async Task<SentimentAnalysis?> FetchAggregatedSentimentAsync(string ticker)
    {
        // 1. Try Primary
        if (IsActive("PrimarySentiment"))
        {
            try
            {
                var response = await _httpClient.GetFromJsonAsync<SentimentApiResponse>($"https://cryptocurrency.cv/api/ai/sentiment?asset={ticker}");
                if (response != null) return new SentimentAnalysis { Label = response.Label, Score = response.Score };
            }
            catch (Exception ex)
            {
                HandleFailure("PrimarySentiment", ex);
            }
        }

        // 2. If Primary Fails, use fallback label from Synthetic calculation
        var synthetic = await GenerateSyntheticNewsAsync(ticker);
        return synthetic?.GlobalSentiment;
    }

    #region Providers Implementation
    private async Task<List<CryptoNewsItem>?> TryFetchPrimaryNewsAsync(string ticker, int limit)
    {
        if (!IsActive("PrimaryNews")) return null;

        try
        {
            var response = await _httpClient.GetFromJsonAsync<FreeNewsApiResponse>($"https://cryptocurrency.cv/api/news?ticker={ticker}&limit={limit}");
            if (response != null && response.Articles != null)
            {
                return response.Articles.Select(a => new CryptoNewsItem
                {
                    Title = a.Title,
                    Source = a.Source,
                    PublishedAt = a.PublishedAt,
                    Url = a.Url
                }).ToList();
            }
        }
        catch (Exception ex)
        {
            HandleFailure("PrimaryNews", ex);
        }
        return null;
    }

    private async Task<List<CryptoNewsItem>?> TryFetchBackupNewsAsync(string ticker, int limit)
    {
        if (!IsActive("BackupNews")) return null;

        try
        {
            // CryptoCompare has a very stable free tier
            var response = await _httpClient.GetFromJsonAsync<CryptoCompareNewsResponse>($"https://min-api.cryptocompare.com/data/v2/news/?categories={ticker}&limit={limit}");
            if (response != null && response.Data != null)
            {
                return response.Data.Select(a => new CryptoNewsItem
                {
                    Title = a.Title,
                    Source = a.Source,
                    PublishedAt = DateTimeOffset.FromUnixTimeSeconds(a.Published_on).DateTime,
                    Url = a.Url
                }).ToList();
            }
        }
        catch (Exception ex)
        {
            HandleFailure("BackupNews", ex);
        }
        return null;
    }

    private async Task<CryptoNewsResult> GenerateSyntheticNewsAsync(string ticker)
    {
        _logger.LogInformation("🛠️ Generating Synthetic News for {Ticker}...", ticker);
        
        // Fetch last candles to deduce "news"
        var candles = await _marketDataManager.GetCandlesAsync(ticker + "USDT", "60", 2);
        
        var result = new CryptoNewsResult();
        string label = "neutral";
        float score = 0.5f;

        if (candles != null && candles.Count >= 2)
        {
            var last = candles.Last();
            var prev = candles[^2];
            var change = (last.Close - prev.Close) / prev.Close;

            if (change > 0.02m) // Pump > 2% in 1h
            {
                label = "positive";
                score = 0.75f;
                result.News.Add(new CryptoNewsItem { Title = $"{ticker} shows strong bullish momentum in last hour.", Source = "Synthetic Tech Analysis", PublishedAt = DateTime.UtcNow });
            }
            else if (change < -0.02m) // Dump > 2% in 1h
            {
                label = "negative";
                score = 0.25f;
                result.News.Add(new CryptoNewsItem { Title = $"{ticker} experiencing technical pressure as price drops.", Source = "Synthetic Tech Analysis", PublishedAt = DateTime.UtcNow });
            }
            else
            {
                result.News.Add(new CryptoNewsItem { Title = $"{ticker} market remains stable with minor price adjustments.", Source = "Synthetic Tech Analysis", PublishedAt = DateTime.UtcNow });
            }
        }
        else
        {
            result.News.Add(new CryptoNewsItem { Title = $"No recent news or technical data available for {ticker}.", Source = "System Fallback", PublishedAt = DateTime.UtcNow });
        }

        result.GlobalSentiment = new SentimentAnalysis 
        { 
            Label = label, 
            Score = score, 
            Source = "Synthetic Fallback (Low Weight)" 
        };

        return result;
    }
    #endregion

    #region Circuit Breaker Logic
    private bool IsActive(string provider)
    {
        if (_circuitBreakers.TryGetValue(provider, out var state))
        {
            if (state.DisabledUntil > DateTime.UtcNow) return false;
        }
        return true;
    }

    private void HandleFailure(string provider, Exception ex)
    {
        // 404 is Informational as per architecture decision
        if (ex.Message.Contains("404"))
        {
            _logger.LogInformation($"ℹ️ Provider {provider} returned 404 (Not Found). This is normal if no news exist for this symbol.");
        }
        else
        {
            _logger.LogWarning($"⚠️ Provider {provider} failed: {ex.Message}");
        }

        _circuitBreakers.AddOrUpdate(provider, 
            (1, DateTime.MinValue), 
            (_, s) => 
            {
                int newCount = s.FailCount + 1;
                if (newCount >= 3)
                {
                    _logger.LogError($"🚫 Circuit Breaker TRIP for {provider}. Disabling for 10 minutes.");
                    return (0, DateTime.UtcNow.AddMinutes(10));
                }
                return (newCount, DateTime.MinValue);
            });
    }
    #endregion
}
