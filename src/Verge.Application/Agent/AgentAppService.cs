using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Net.Http;
using System.Net.Http.Json;
using System.Collections.Generic;
using System;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace Verge.Agent;

[Authorize]
public class AgentAppService : VergeAppService, IAgentAppService
{
    private static readonly string[] MarketWsBaseUrls =
    {
        "http://127.0.0.1:8001",
        "http://host.docker.internal:8001",
        "http://localhost:8001"
    };
    private readonly AgentProcessManager _processManager;
    private readonly IHubContext<AgentHub> _hubContext;
    private readonly HttpClient _marketWsClient;
    private string _activeMarketWsBaseUrl = MarketWsBaseUrls[0];
    private DateTime _lastMarketWsProbeUtc = DateTime.MinValue;
    private object? _lastHealthSnapshot;
    private DateTime _lastHealthSnapshotUtc = DateTime.MinValue;
    private DateTime _nextFullProbeUtc = DateTime.MinValue;

    public AgentAppService(AgentProcessManager processManager, IHubContext<AgentHub> hubContext)
    {
        _processManager = processManager;
        _hubContext     = hubContext;
        _marketWsClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(3)
        };
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
            if (health != null)
            {
                isServerRunning = true;
                exchangeStatus = health;
            }

            string state = "STOPPED";
            if (isAgentRunning)  state = "AGENT_RUNNING";
            else if (isServerRunning) state = "SERVER_READY";

            var startTime = _processManager.GetStartTime(isAgentRunning ? "Agent" : "MarketWS");

            return new {
                state,
                startTime = startTime?.ToString("yyyy-MM-ddTHH:mm:ss"),
                isServerHealthy = isServerRunning,
                health = exchangeStatus
            };
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error getting system state: {Message}", ex.Message);
            return new { state = "STOPPED" };
        }
    }

    public async Task StartServerAsync()
    {
        await Task.Delay(300);
        await _processManager.StartProcessAsync("MarketWS", "market_ws_server.py");
        await _hubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
    }

    public async Task StopServerAsync()
    {
        await _processManager.StopAllAsync();
        await _hubContext.Clients.All.SendAsync("ServerStateChanged", "STOPPED");
    }

    public async Task StartAgentAsync()
    {
        await _processManager.StartProcessAsync("Agent", "verge_agent.py");
        await _hubContext.Clients.All.SendAsync("ServerStateChanged", "AGENT_RUNNING");
    }

    public async Task StopAgentAsync()
    {
        await _processManager.StopProcessAsync("Agent");
        await _hubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
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
        // 1) Fast path: active URL only. Keep UI responsive.
        try
        {
            using var fastCts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(800));
            var fastResponse = await _marketWsClient.GetAsync($"{_activeMarketWsBaseUrl}/health", fastCts.Token);
            if (fastResponse.IsSuccessStatusCode)
            {
                var fastContent = await fastResponse.Content.ReadAsStringAsync(fastCts.Token);
                var parsed = JsonSerializer.Deserialize<dynamic>(fastContent);
                if (parsed != null)
                {
                    _lastHealthSnapshot = parsed;
                    _lastHealthSnapshotUtc = DateTime.UtcNow;
                    return parsed;
                }
            }
        }
        catch
        {
            // Continue to fallback strategy.
        }

        // 2) If we have a recent successful snapshot, use it instead of dropping to null.
        if (_lastHealthSnapshot != null && DateTime.UtcNow - _lastHealthSnapshotUtc < TimeSpan.FromSeconds(45))
        {
            return _lastHealthSnapshot;
        }

        // 3) Full probe no more than every 30s.
        if (DateTime.UtcNow < _nextFullProbeUtc)
        {
            return null;
        }
        _nextFullProbeUtc = DateTime.UtcNow.AddSeconds(30);
        _lastMarketWsProbeUtc = DateTime.UtcNow;

        var candidateUrls = new List<string> { _activeMarketWsBaseUrl };
        foreach (var candidate in MarketWsBaseUrls)
        {
            if (!string.Equals(candidate, _activeMarketWsBaseUrl, StringComparison.OrdinalIgnoreCase))
            {
                candidateUrls.Add(candidate);
            }
        }

        foreach (var baseUrl in candidateUrls)
        {
            try
            {
                using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(1200));
                var response = await _marketWsClient.GetAsync($"{baseUrl}/health", cts.Token);
                if (!response.IsSuccessStatusCode)
                {
                    continue;
                }

                var content = await response.Content.ReadAsStringAsync(cts.Token);
                _activeMarketWsBaseUrl = baseUrl;
                var parsed = JsonSerializer.Deserialize<dynamic>(content);
                if (parsed != null)
                {
                    _lastHealthSnapshot = parsed;
                    _lastHealthSnapshotUtc = DateTime.UtcNow;
                    return parsed;
                }
            }
            catch
            {
                // Try next candidate URL.
            }
        }

        return null;
    }
}
