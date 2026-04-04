using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using StackExchange.Redis;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public class BotAppService : VergeAppService, IBotAppService
{
    private readonly IDatabase _db;
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<BotAppService> _logger;

    public BotAppService(IConnectionMultiplexer redis, ILogger<BotAppService> logger)
    {
        _redis = redis;
        _db = _redis.GetDatabase();
        _logger = logger;
    }

    public async Task<List<BotPairDto>> GetActivePairsAsync()
    {
        try
        {
            var hashEntries = await _db.HashGetAllAsync("verge:active_pairs");
            var results = new List<BotPairDto>();

            _logger.LogInformation("?? Loading {Count} pairs from Redis Hash 'verge:active_pairs'", hashEntries.Length);

            foreach (var entry in hashEntries)
            {
                var symbol = entry.Name.ToString();
                var json = entry.Value.ToString();
                
                try 
                {
                    var dto = JsonSerializer.Deserialize<BotPairDto>(json, new JsonSerializerOptions {
                        PropertyNameCaseInsensitive = true
                    });

                    if (dto != null)
                    {
                        dto.Symbol = symbol; // Force symbol match
                        results.Add(dto);
                        _logger.LogDebug("?? Parsed: {Symbol} | Score: {Score}", symbol, dto.Score);
                    }
                }
                catch (System.Exception ex)
                {
                    _logger.LogWarning("?? Error parsing Redis data for {Symbol}: {Error}", symbol, ex.Message);
                }
            }

            return results.OrderByDescending(x => x.Score).ToList();
        }
        catch (System.Exception ex)
        {
            _logger.LogError(ex, "?? Failed to fetch active pairs from Redis");
            return new List<BotPairDto>();
        }
    }


}
