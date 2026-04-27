using System;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;

namespace Verge.Agent;

[Authorize]
public class AgentAppService : VergeAppService, IAgentAppService
{
    private readonly AgentProcessManager _processManager;
    private readonly IHubContext<AgentHub> _hubContext;

    public AgentAppService(AgentProcessManager processManager, IHubContext<AgentHub> hubContext)
    {
        _processManager = processManager;
        _hubContext = hubContext;
    }

    public async Task StartServerAsync()
    {
        await Task.Delay(500); 
        await _processManager.StartProcessAsync("MarketWS", "market_ws_server.py");
        // State will be managed by the frontend based on the logs, 
        // but let's signal SERVER_READY immediately for the UI state machine if desired, 
        // OR better: wait for a specific log pattern? 
        // For now, let's just set it to READY so the user can start the agent.
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
}
