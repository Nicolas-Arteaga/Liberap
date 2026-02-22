using System;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Logging;
using Volo.Abp.Caching;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.Integrations;

public class AlternativeMeResponse
{
    public string Name { get; set; } = string.Empty;
    public Item[] Data { get; set; } = Array.Empty<Item>();

    public class Item
    {
        public string Value { get; set; } = string.Empty;
        public string Value_Classification { get; set; } = string.Empty;
        public string Timestamp { get; set; } = string.Empty;
        public string Time_Until_Update { get; set; } = string.Empty;
    }
}

public class FearAndGreedService : DomainService, IFearAndGreedService
{
    private readonly HttpClient _httpClient;
    private readonly IDistributedCache<FearAndGreedResult> _cache;
    private readonly ILogger<FearAndGreedService> _logger;
    private const string CacheKey = "GlobalFearAndGreedIndex";

    public FearAndGreedService(
        HttpClient httpClient,
        IDistributedCache<FearAndGreedResult> cache,
        ILogger<FearAndGreedService> logger)
    {
        _httpClient = httpClient;
        _cache = cache;
        _logger = logger;
    }

    public async Task<FearAndGreedResult?> GetCurrentFearAndGreedAsync()
    {
        try
        {
            return await _cache.GetOrAddAsync(
                CacheKey,
                async () => await FetchFromApiAsync(),
                () => new DistributedCacheEntryOptions
                {
                    AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(4) // El índice cambia una vez al día
                }
            );
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error retrieving Fear & Greed index");
            return null; // Fallback tolerante a fallos
        }
    }

    private async Task<FearAndGreedResult?> FetchFromApiAsync()
    {
        _logger.LogInformation("🌍 Fetching Fear & Greed index from Alternative.me API...");
        var response = await _httpClient.GetFromJsonAsync<AlternativeMeResponse>("https://api.alternative.me/fng/");
        
        if (response?.Data != null && response.Data.Length > 0)
        {
            var latest = response.Data.First();
            if (int.TryParse(latest.Value, out int value) && long.TryParse(latest.Timestamp, out long timestamp))
            {
                return new FearAndGreedResult
                {
                    Name = response.Name,
                    Value = value,
                    ValueClassification = latest.Value_Classification,
                    Timestamp = DateTimeOffset.FromUnixTimeSeconds(timestamp).UtcDateTime,
                    TimeUntilUpdate = latest.Time_Until_Update
                };
            }
        }

        return null;
    }
}
