using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Volo.Abp.AspNetCore.SignalR;

namespace Verge.Trading;

[Authorize]
public class TradingHub : AbpHub
{
    public async Task SendSessionUpdate(string message)
    {
        await Clients.All.SendAsync("ReceiveSessionUpdate", message);
    }
}
