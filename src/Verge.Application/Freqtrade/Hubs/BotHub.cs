using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Volo.Abp.AspNetCore.SignalR;

namespace Verge.Freqtrade.Hubs;

[AllowAnonymous]
[HubRoute("/signalr-hubs/bot")]
public class BotHub : AbpHub
{
    public async Task RequestInitialState()
    {
        await Clients.Caller.SendAsync("ReceiveBotLog", "Connected to BotHub. Waiting for signals...");
    }
}
