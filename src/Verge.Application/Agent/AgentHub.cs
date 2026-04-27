using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Volo.Abp.AspNetCore.SignalR;

namespace Verge.Agent;

[Authorize]
[HubRoute("/signalr-hubs/agent")]
public class AgentHub : AbpHub
{
    private readonly ILogger<AgentHub> _logger;

    public AgentHub(ILogger<AgentHub> logger)
    {
        _logger = logger;
    }

    public override async Task OnConnectedAsync()
    {
        _logger.LogInformation("✅ Cliente conectado al AgentHub: {ConnectionId} | Usuario: {User}", Context.ConnectionId, Context.User?.Identity?.Name);
        await base.OnConnectedAsync();
    }
    public async Task SendAgentLog(string message, string color = null)
    {
        await Clients.All.SendAsync("ReceiveAgentLog", message, color);
    }
}
