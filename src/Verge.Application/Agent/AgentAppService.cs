using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Net.Http;
using System.Net.Http.Json;
using System.Collections.Generic;
using System;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Text.Json;
using System.Linq;
using Verge.Trading;

namespace Verge.Agent;

[Authorize]
public class AgentAppService : VergeAppService, IAgentAppService
{
    private static readonly string[] DefaultMarketWsBaseUrls =
    {
        "http://127.0.0.1:8001",
        "http://host.docker.internal:8001",
        "http://localhost:8001"
    };

    private readonly IReadOnlyList<string> _marketWsBaseUrls;
    private readonly AgentProcessManager _processManager;
    private readonly IHubContext<AgentHub> _agentHubContext;
    private readonly IHubContext<TradingHub> _tradingHubContext;
    private readonly HttpClient _marketWsClient;
    private string _activeMarketWsBaseUrl = "";
    private DateTime _lastMarketWsProbeUtc = DateTime.MinValue;
    private object? _lastHealthSnapshot;
    private DateTime _lastHealthSnapshotUtc = DateTime.MinValue;
    private DateTime _nextFullProbeUtc = DateTime.MinValue;
    /// <summary>
    /// Cuando Market WS corre en Docker (sin proceso hijo en este host), guardamos UTC de primera detección para uptime en la UI.
    /// </summary>
    private DateTime? _externalMarketWsDetectedUtc;

    public AgentAppService(
        AgentProcessManager processManager,
        IHubContext<AgentHub> agentHubContext,
        IHubContext<TradingHub> tradingHubContext,
        IConfiguration configuration)
    {
        _processManager = processManager;
        _agentHubContext = agentHubContext;
        _tradingHubContext = tradingHubContext;
        _marketWsClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(3)
        };

        _marketWsBaseUrls = ResolveMarketWsBaseUrls(configuration);
        _activeMarketWsBaseUrl = _marketWsBaseUrls[0];
        Console.WriteLine($"[DEBUG] AgentAppService initialized. MarketWS URL: {_activeMarketWsBaseUrl}");
    }

    private static IReadOnlyList<string> ResolveMarketWsBaseUrls(IConfiguration configuration)
    {
        var section = configuration.GetSection("MarketWs:BaseUrls");
        var urls = new List<string>();
        foreach (var child in section.GetChildren())
        {
            var v = child.Value?.Trim();
            if (string.IsNullOrEmpty(v))
            {
                continue;
            }

            urls.Add(v.TrimEnd('/'));
        }

        if (urls.Count == 0)
        {
            return DefaultMarketWsBaseUrls.ToList();
        }

        return urls;
    }

    [AllowAnonymous]
    public async Task<object> GetSystemStateAsync()
    {
        try 
        {
            bool isServerRunning = _processManager.IsProcessRunning("MarketWS");
            bool isAgentRunning  = _processManager.IsProcessRunning("Agent");
            object? exchangeStatus = null;

            // Fetch health status from Python service, trying host/container routes.
            var health = await TryGetHealthAsync();
            Console.WriteLine($"[DEBUG] getSystemState: health check against {_activeMarketWsBaseUrl} returned {(health != null ? "OK" : "FAIL")}");
            if (health != null)
            {
                isServerRunning = true;
                exchangeStatus = health;
            }

            var marketWsLocalProcess = _processManager.IsProcessRunning("MarketWS");
            if (isServerRunning && !isAgentRunning && !marketWsLocalProcess)
            {
                _externalMarketWsDetectedUtc ??= DateTime.UtcNow;
            }
            else if (!isServerRunning && !isAgentRunning)
            {
                _externalMarketWsDetectedUtc = null;
            }

            string state = "STOPPED";
            if (isAgentRunning)  state = "AGENT_RUNNING";
            else if (isServerRunning) state = "SERVER_READY";

            var startTime = _processManager.GetStartTime(isAgentRunning ? "Agent" : "MarketWS");
            if (startTime == null && isServerRunning && !isAgentRunning)
            {
                startTime = _externalMarketWsDetectedUtc;
            }

            var marketWsExternal = isServerRunning && !marketWsLocalProcess && !isAgentRunning;

            return new {
                state,
                startTime = startTime?.ToString("yyyy-MM-ddTHH:mm:ss"),
                isServerHealthy = isServerRunning,
                health = exchangeStatus,
                marketWsExternal,
                logs = (marketWsExternal && state == "SERVER_READY") ? await TryGetMarketWsLogsAsync() : null
            };
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error getting system state: {Message}", ex.Message);
            return new { state = "STOPPED" };
        }
    }

    private async Task<List<string>?> TryGetMarketWsLogsAsync()
    {
        try
        {
            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(800));
            var response = await _marketWsClient.GetAsync($"{_activeMarketWsBaseUrl}/logs", cts.Token);
            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync(cts.Token);
                var parsed = JsonSerializer.Deserialize<JsonElement>(content);
                if (parsed.TryGetProperty("logs", out var logsArray))
                {
                    var logs = new List<string>();
                    foreach(var log in logsArray.EnumerateArray())
                    {
                        var s = log.GetString();
                        if (s != null) logs.Add(s);
                    }
                    return logs;
                }
            }
        }
        catch { }
        return null;
    }

    public async Task StartServerAsync()
    {
        await Task.Delay(300);
        await _processManager.StartProcessAsync("MarketWS", "market_ws_server.py");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
    }

    public async Task StopServerAsync()
    {
        await _processManager.StopAllAsync();
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "STOPPED");
    }

    public async Task StartAgentAsync()
    {
        await _processManager.StartProcessAsync("Agent", "verge_agent.py");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "AGENT_RUNNING");
    }

    public async Task StopAgentAsync()
    {
        await _processManager.StopProcessAsync("Agent");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
    }

    public async Task<object> GetAuditSummaryAsync()
    {
        try {
            return await _marketWsClient.GetFromJsonAsync<object>($"{_activeMarketWsBaseUrl}/audit/summary");
        } catch { return new { balance = 0, winRate = 0, trades = 0, pnlTotal = 0 }; }
    }

    public async Task<object> GetStrategyStatsAsync()
    {
        try {
            return await _marketWsClient.GetFromJsonAsync<object>($"{_activeMarketWsBaseUrl}/audit/stats");
        } catch { return new { }; }
    }

    public async Task<object> GetRecentTradesAsync(int limit = 10)
    {
        try {
            return await _marketWsClient.GetFromJsonAsync<object>($"{_activeMarketWsBaseUrl}/audit/trades?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetTopSymbolsAsync(int limit = 5)
    {
        try {
            return await _marketWsClient.GetFromJsonAsync<object>($"{_activeMarketWsBaseUrl}/audit/top-symbols?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetOpenPositionsAsync()
    {
        try {
            return await _marketWsClient.GetFromJsonAsync<object>($"{_activeMarketWsBaseUrl}/audit/open");
        } catch { return new List<object>(); }
    }

    private async Task<object?> TryGetHealthAsync()
    {
        // 1) Fast path: active URL only.
        try
        {
            using var fastCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(5)); 
            var fastResponse = await _marketWsClient.GetAsync($"{_activeMarketWsBaseUrl}/health", fastCts.Token);
            if (fastResponse.IsSuccessStatusCode)
            {
                var fastContent = await fastResponse.Content.ReadAsStringAsync(fastCts.Token);
                var parsed = JsonSerializer.Deserialize<JsonElement>(fastContent);
                _lastHealthSnapshot = parsed;
                _lastHealthSnapshotUtc = DateTime.UtcNow;
                return parsed;
            }
        }
        catch
        {
             // Continue to fallback.
        }

        // 2) Fallback to full probe if needed
        var candidateUrls = new List<string> { _activeMarketWsBaseUrl };
        candidateUrls.AddRange(_marketWsBaseUrls.Where(u => u != _activeMarketWsBaseUrl));

        foreach (var baseUrl in candidateUrls)
        {
            try
            {
                using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(5));
                var response = await _marketWsClient.GetAsync($"{baseUrl}/health", cts.Token);
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync(cts.Token);
                    _activeMarketWsBaseUrl = baseUrl;
                    var parsed = JsonSerializer.Deserialize<JsonElement>(content);
                    _lastHealthSnapshot = parsed;
                    _lastHealthSnapshotUtc = DateTime.UtcNow;
                    return parsed;
                }
            }
            catch
            {
                // Try next.
            }
        }

        return null;
    }

    public async Task BroadcastSignalAsync(object signal)
    {
        // IMPORTANT: Dashboard listens on TradingHub (/signalr-hubs/trading), not AgentHub.
        await _tradingHubContext.Clients.All.SendAsync("ReceiveSuperScore", signal);
    }

    public async Task BroadcastSignalsAsync(List<object> signals)
    {
        if (signals == null || signals.Count == 0)
        {
            return;
        }

        // Single SignalR event with the full batch to avoid 183 HTTP requests and reduce hub spam.
        await _tradingHubContext.Clients.All.SendAsync("ReceiveSuperScores", signals);
    }
}
