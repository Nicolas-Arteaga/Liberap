using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Net.Http;
using System.Net.Http.Json;
using System.Collections.Generic;
using System;
using Microsoft.Extensions.Logging;

namespace Verge.Agent;

[Authorize]
public class AgentAppService : VergeAppService, IAgentAppService
{
    private readonly AgentProcessManager _processManager;
    private readonly IHubContext<AgentHub> _hubContext;

    public AgentAppService(AgentProcessManager processManager, IHubContext<AgentHub> hubContext)
    {
        _processManager = processManager;
        _hubContext     = hubContext;
    }

    [AllowAnonymous]
    public async Task<string> GetSystemStateAsync()
    {
        try 
        {
            bool isServerRunning = _processManager.IsProcessRunning("MarketWS");
            bool isAgentRunning  = _processManager.IsProcessRunning("Agent");

            if (isAgentRunning)  return "AGENT_RUNNING";
            if (isServerRunning) return "SERVER_READY";
            return "STOPPED";
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error getting system state: {Message}", ex.Message);
            return "STOPPED";
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
            using var client = new HttpClient();
            return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/summary");
        } catch { return new { balance = 0, winRate = 0, trades = 0, pnlTotal = 0 }; }
    }

    public async Task<object> GetStrategyStatsAsync()
    {
        try {
            using var client = new HttpClient();
            return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/stats");
        } catch { return new { }; }
    }

    public async Task<object> GetRecentTradesAsync(int limit = 10)
    {
        try {
            using var client = new HttpClient();
            return await client.GetFromJsonAsync<object>($"http://localhost:8001/audit/trades?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetTopSymbolsAsync(int limit = 5)
    {
        try {
            using var client = new HttpClient();
            return await client.GetFromJsonAsync<object>($"http://localhost:8001/audit/top-symbols?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetOpenPositionsAsync()
    {
        try {
            using var client = new HttpClient();
            return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/open");
        } catch { return new List<object>(); }
    }
}
