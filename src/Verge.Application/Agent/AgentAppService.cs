using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Net.Http;
using System.Net.Http.Json;

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
        using var client = new HttpClient();
        return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/summary");
    }

    public async Task<object> GetStrategyStatsAsync()
    {
        using var client = new HttpClient();
        return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/stats");
    }

    public async Task<object> GetRecentTradesAsync(int limit = 10)
    {
        using var client = new HttpClient();
        return await client.GetFromJsonAsync<object>($"http://localhost:8001/audit/trades?limit={limit}");
    }

    public async Task<object> GetTopSymbolsAsync(int limit = 5)
    {
        using var client = new HttpClient();
        return await client.GetFromJsonAsync<object>($"http://localhost:8001/audit/top-symbols?limit={limit}");
    }

    public async Task<object> GetOpenPositionsAsync()
    {
        using var client = new HttpClient();
        return await client.GetFromJsonAsync<object>("http://localhost:8001/audit/open");
    }
}
