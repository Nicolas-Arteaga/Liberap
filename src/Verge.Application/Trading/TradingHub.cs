using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Volo.Abp.AspNetCore.SignalR;
using Verge.Trading.DTOs;

namespace Verge.Trading;

[Authorize]
public class TradingHub : AbpHub
{
    public async Task SendSessionUpdate(string message)
    {
        await Clients.All.SendAsync("ReceiveSessionUpdate", message);
    }

    public async Task SendAlert(string userId, VergeAlertDto alert)
    {
        await Clients.User(userId).SendAsync("ReceiveAlert", alert);
    }
}
