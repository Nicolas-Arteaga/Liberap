using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using StackExchange.Redis;
using Verge.Freqtrade.Hubs;
using Verge.Trading;

namespace Verge.BackgroundJobs;

public class BotDataPublisherService : BackgroundService
{
    private readonly IConnectionMultiplexer _redis;
    private readonly IHubContext<BotHub> _hubContext;
    private readonly IHubContext<TradingHub> _tradingHubContext;
    private readonly ILogger<BotDataPublisherService> _logger;

    private readonly IDatabase _db;

    public BotDataPublisherService(
        IConnectionMultiplexer redis,
        IHubContext<BotHub> hubContext,
        IHubContext<TradingHub> tradingHubContext,
        ILogger<BotDataPublisherService> logger)
    {
        _redis = redis;
        _hubContext = hubContext;
        _tradingHubContext = tradingHubContext;
        _logger = logger;
        _db = _redis.GetDatabase();
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 BotDataPublisherService: Starting and subscribing to Redis channels...");

        var subscriber = _redis.GetSubscriber();

        // Suscripción al Super Score
        await subscriber.SubscribeAsync(RedisChannel.Literal("verge:superscore"), async (channel, message) =>
        {
            try
            {
                var payload = message.ToString();
                _logger.LogInformation("📢 Received 'verge:superscore' from Redis: {Payload}", payload);
                
                // Guardarlo en Redis Hash para el endpoint GET
                using var doc = JsonDocument.Parse(payload);
                if (doc.RootElement.TryGetProperty("symbol", out var symbolProp))
                {
                    var symbol = symbolProp.GetString();
                    if (!string.IsNullOrEmpty(symbol))
                    {
                        await _db.HashSetAsync("verge:active_pairs", symbol, payload);
                        _logger.LogDebug("✅ Saved signal for {Symbol} to Redis Hash", symbol);
                    }
                }

                // Broadcast via SignalR to both Hubs
                await _hubContext.Clients.All.SendAsync("ReceiveSuperScore", payload);
                await _tradingHubContext.Clients.All.SendAsync("ReceiveSuperScore", payload);
                _logger.LogInformation("📡 Broadcasted SuperScore for {Channel} to SignalR clients (Both Hubs)", channel);

            }
            catch (System.Exception ex)
            {
                _logger.LogError(ex, "❌ Error processing 'verge:superscore' Pub/Sub");
            }
        });

        // Suscripción al Whale Signal
        await subscriber.SubscribeAsync(RedisChannel.Literal("verge:whale_signal"), async (channel, message) =>
        {
            try
            {
                _logger.LogInformation("🐋 Received 'verge:whale_signal' from Redis");
                var payload = message.ToString();
                await _hubContext.Clients.All.SendAsync("ReceiveWhaleSignal", payload);
                await _tradingHubContext.Clients.All.SendAsync("ReceiveWhaleSignal", payload);
            }
            catch (System.Exception ex)
            {
                _logger.LogError(ex, "❌ Error processing 'verge:whale_signal' Pub/Sub");
            }
        });

        // ─── NEXUS-15 subscription (nuevas señales predictivas 15m) ───────────────
        await subscriber.SubscribeAsync(RedisChannel.Pattern("verge:nexus15:*"), async (channel, message) =>
        {
            try
            {
                var payload = message.ToString();
                var symbol = channel.ToString().Replace("verge:nexus15:", "");

                _logger.LogInformation("🔭 [Nexus15] Received signal for {Symbol}", symbol);

                // Caché en Redis (TTL 20 min = 1 vela 15m + buffer)
                await _db.StringSetAsync($"verge:nexus15_cache:{symbol}", payload, TimeSpan.FromMinutes(20));

                // Broadcast via SignalR → método Nexus15Update
                await _tradingHubContext.Clients.All.SendAsync("Nexus15Update", payload);

                _logger.LogInformation("📡 [Nexus15] Broadcasted Nexus15Update for {Symbol}", symbol);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ [Nexus15] Error processing verge:nexus15:* Pub/Sub");
            }
        });

        // Suscripción a Logs del bot
        await subscriber.SubscribeAsync(RedisChannel.Literal("verge:bot_log"), async (channel, message) =>
        {
            try
            {
                var logMsg = message.ToString();
                _logger.LogInformation("📄 Received 'verge:bot_log': {Msg}", logMsg.Length > 50 ? logMsg.Substring(0, 50) + "..." : logMsg);
                await _hubContext.Clients.All.SendAsync("ReceiveBotLog", logMsg);
            }
            catch (System.Exception ex)
            {
                _logger.LogError(ex, "❌ Error processing 'verge:bot_log' Pub/Sub");
            }
        });
        
        // Wait and keep alive
        try 
        {
            await Task.Delay(Timeout.Infinite, stoppingToken);
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }
    }
}
