using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using StackExchange.Redis;

namespace Verge.Trading.Bot;

/// <summary>
/// Implementación del servicio de estado del bot.
/// 
/// Estado en memoria: rápido para los loops de 5m y 30s.
/// Redis: persiste IsEnabled y Config para sobrevivir reinicios del proceso.
/// 
/// Registrado como Singleton en VergeDomainModule.
/// </summary>
public class BotStateService : IBotStateService
{
    private readonly ILogger<BotStateService> _logger;
    private readonly IDatabase _redis;

    private volatile bool _isRunning = false;
    private Guid? _creatorUserId;
    private ScalpingConfig _config = new();
    private List<string> _activeSymbols = new();

    // Posiciones abiertas por símbolo — evita duplicados en el mismo símbolo
    private readonly ConcurrentDictionary<string, int> _openPositions = new();

    // Estadísticas del día (se resetean a las 00:00 UTC)
    private decimal _dailyPnl = 0;
    private int _dailyTradeCount = 0;
    private int _dailyWins = 0;
    private int _dailyLosses = 0;

    private DateTime? _lastCycleAt;

    private const string RedisKeyEnabled = "bot:enabled";
    private const string RedisKeyConfig  = "bot:config";
    private const string RedisKeyUserId  = "bot:userid";
    private const string RedisKeyLogs    = "bot:activity_logs";
    private const string RedisPrefixScore = "bot:score:";

    public bool IsRunning => _isRunning;
    public Guid? CreatorUserId => _creatorUserId;
    public decimal DailyPnl => _dailyPnl;
    public int DailyTradeCount => _dailyTradeCount;
    public int DailyWins => _dailyWins;
    public int DailyLosses => _dailyLosses;
    public DateTime? LastCycleAt => _lastCycleAt;

    public BotStateService(ILogger<BotStateService> logger, IConnectionMultiplexer redis)
    {
        _logger = logger;
        _redis = redis.GetDatabase();

        // Intentar recuperar estado persistido en Redis (reinicio del proceso)
        _ = Task.Run(LoadStateFromRedisAsync);
    }

    private async Task LoadStateFromRedisAsync()
    {
        try
        {
            var enabledVal = await _redis.StringGetAsync(RedisKeyEnabled);
            if (enabledVal.HasValue && bool.TryParse(enabledVal, out bool enabled))
            {
                _isRunning = enabled;
            }

            var configVal = await _redis.StringGetAsync(RedisKeyConfig);
            if (configVal.HasValue)
            {
                var cfg = JsonSerializer.Deserialize<ScalpingConfig>((string)configVal!);
                if (cfg != null) _config = cfg;
            }

            var userIdVal = await _redis.StringGetAsync(RedisKeyUserId);
            if (userIdVal.HasValue && Guid.TryParse((string?)userIdVal, out var userId))
            {
                _creatorUserId = userId;
            }

            _logger.LogInformation("🤖 [BotState] Recovered from Redis: IsRunning={Running}, User={User}", _isRunning, _creatorUserId);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "⚠️ [BotState] Could not load state from Redis. Using defaults.");
        }
    }

    public async Task StartAsync(Guid? userId)
    {
        _isRunning = true;
        _creatorUserId = userId;
        await _redis.StringSetAsync(RedisKeyEnabled, "true");
        if (userId.HasValue)
        {
            await _redis.StringSetAsync(RedisKeyUserId, userId.Value.ToString());
        }
        _logger.LogInformation("🟢 [BotState] Bot STARTED by User {User}", userId);
    }

    public async Task UpdateCreatorUserIdAsync(Guid? userId)
    {
        _creatorUserId = userId;
        if (userId.HasValue)
            await _redis.StringSetAsync(RedisKeyUserId, userId.Value.ToString());
        else
            await _redis.KeyDeleteAsync(RedisKeyUserId);
    }

    public async Task StopAsync()
    {
        _isRunning = false;
        await _redis.StringSetAsync(RedisKeyEnabled, "false");
        _logger.LogInformation("🔴 [BotState] Bot STOPPED");
    }

    public ScalpingConfig GetConfig() => _config;

    public async Task UpdateConfigAsync(ScalpingConfig newConfig)
    {
        _config = newConfig;
        await _redis.StringSetAsync(RedisKeyConfig, JsonSerializer.Serialize(newConfig));
        _logger.LogInformation("⚙️ [BotState] Config updated: MinScore={Score}, MaxPos={Pos}, RiskPct={Risk}%",
            newConfig.MinScore, newConfig.MaxOpenPositions, newConfig.RiskPercent);
    }

    // ─── Control de posiciones ───

    public int GetOpenPositionCount() => _openPositions.Values.Sum();

    public void RegisterOpen(string symbol)
    {
        _openPositions.AddOrUpdate(symbol.ToUpper(), 1, (_, old) => old + 1);
        _dailyTradeCount++;
    }

    public void RegisterClose(string symbol)
    {
        var key = symbol.ToUpper();
        _openPositions.AddOrUpdate(key, 0, (_, old) => Math.Max(0, old - 1));
    }

    public bool IsSymbolAlreadyOpen(string symbol) 
        => _openPositions.TryGetValue(symbol.ToUpper(), out var count) && count > 0;

    public bool CanOpenNewPosition()
        => GetOpenPositionCount() < _config.MaxOpenPositions;

    // ─── Símbolos activos ───

    public List<string> GetActiveSymbols() => _activeSymbols.ToList();

    public Task RefreshActiveSymbolsAsync(List<string> topScannerSymbols)
    {
        var combined = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // Top del scanner (dinámico)
        if (_config.DynamicSymbols)
        {
            foreach (var s in topScannerSymbols.Take(_config.TopSymbolsCount))
                combined.Add(s);
        }

        // Whitelist siempre incluida
        foreach (var s in _config.WhitelistSymbols)
            combined.Add(s);

        // Excluir blacklist
        foreach (var s in _config.BlacklistSymbols)
            combined.Remove(s);

        _activeSymbols = combined.ToList();
        return Task.CompletedTask;
    }

    // ─── Estadísticas del día ───

    public void AddDailyPnl(decimal pnl)
    {
        _dailyPnl += pnl;
        if (pnl >= 0) _dailyWins++;
        else _dailyLosses++;
    }

    public void ResetDailyStats()
    {
        _dailyPnl = 0;
        _dailyTradeCount = 0;
        _dailyWins = 0;
        _dailyLosses = 0;
        _logger.LogInformation("📊 [BotState] Daily stats reset (new trading day)");
    }

    public void UpdateLastCycle() => _lastCycleAt = DateTime.UtcNow;

    // ─── Score del Scanner (Redis Sync) ───
    public async Task SetSymbolScoreAsync(string symbol, int score, int direction)
    {
        try
        {
            var key = $"{RedisPrefixScore}{symbol.ToUpper().Trim()}";
            var val = $"{score}|{direction}";
            // Expiración de 20 min para mantener data fresca y limpiar solos
            await _redis.StringSetAsync(key, val, TimeSpan.FromMinutes(20));
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "⚠️ [BotState] Error al guardar score en Redis para {Symbol}", symbol);
        }
    }
    
    public async Task<(int Score, int Direction)?> GetSymbolScoreAsync(string symbol)
    {
        try
        {
            var key = $"{RedisPrefixScore}{symbol.ToUpper().Trim()}";
            var val = await _redis.StringGetAsync(key);
            if (val.HasValue)
            {
                var parts = ((string)val!).Split('|');
                if (parts.Length == 2 && int.TryParse(parts[0], out int score) && int.TryParse(parts[1], out int direction))
                {
                    return (score, direction);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "⚠️ [BotState] Error al leer score de Redis para {Symbol}", symbol);
        }
        return null;
    }

    // ─── Historial de Actividad (Buffer para UI) ───
    public async Task AddLogAsync(string symbol, string message, string type)
    {
        try
        {
            var log = new BotActivityLogDto
            {
                Symbol = symbol,
                Message = message,
                Type = type,
                Timestamp = DateTime.UtcNow
            };

            var json = JsonSerializer.Serialize(log);
            
            // Push al final de la lista y recortar a los últimos 50
            await _redis.ListRightPushAsync(RedisKeyLogs, json);
            await _redis.ListTrimAsync(RedisKeyLogs, -50, -1);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "⚠️ [BotState] Could not save activity log to Redis");
        }
    }

    public async Task<List<BotActivityLogDto>> GetRecentLogsAsync()
    {
        try
        {
            var logsJson = await _redis.ListRangeAsync(RedisKeyLogs, 0, -1);
            return logsJson
                .Select(j => JsonSerializer.Deserialize<BotActivityLogDto>((string)j!))
                .Where(l => l != null)
                .ToList()!;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "⚠️ [BotState] Could not retrieve activity logs from Redis");
            return new List<BotActivityLogDto>();
        }
    }
}
