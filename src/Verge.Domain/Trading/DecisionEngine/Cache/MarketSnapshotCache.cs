using System;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Distributed;
using Volo.Abp.DependencyInjection;

namespace Verge.Trading.DecisionEngine.Cache;

public class MarketSnapshotCache : ITransientDependency
{
    private readonly IDistributedCache _cache;

    public MarketSnapshotCache(IDistributedCache cache)
    {
        _cache = cache;
    }

    public async Task<MarketContext?> GetAsync(string symbol, string timeframe, long timestamp)
    {
        var key = CreateKey(symbol, timeframe, timestamp);
        var json = await _cache.GetStringAsync(key);
        
        if (string.IsNullOrEmpty(json)) return null;
        
        return JsonSerializer.Deserialize<MarketContext>(json);
    }

    public async Task SetAsync(string symbol, string timeframe, long timestamp, MarketContext context, TimeSpan? ttl = null)
    {
        var key = CreateKey(symbol, timeframe, timestamp);
        var json = JsonSerializer.Serialize(context);
        
        var options = new DistributedCacheEntryOptions
        {
            AbsoluteExpirationRelativeToNow = ttl ?? TimeSpan.FromMinutes(5)
        };

        await _cache.SetStringAsync(key, json, options);
    }

    private string CreateKey(string symbol, string timeframe, long timestamp)
    {
        return $"MarketSnapshot_{symbol}_{timeframe}_{timestamp}";
    }
}
