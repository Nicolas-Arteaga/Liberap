using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Volo.Abp.DependencyInjection;
using Volo.Abp.EventBus.Distributed;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class AlertStateChangedEventHandler : IDistributedEventHandler<AlertStateChangedEto>, ITransientDependency
{
    private readonly IHubContext<TradingHub> _hubContext;

    public AlertStateChangedEventHandler(IHubContext<TradingHub> hubContext)
    {
        _hubContext = hubContext;
    }

    public async Task HandleEventAsync(AlertStateChangedEto eventData)
    {
        // Enviar la alerta unicamente al usuario correspondiente via SignalR
        // En SignalR para ABP, el User Identifier es usualmente el ID del usuario en formato de string guid
        var userIdStr = eventData.UserId.ToString().ToLowerInvariant();
        System.Console.WriteLine($"[SignalR] 📢 HubContext: Enviando alerta {eventData.Alert.Id} ({eventData.Alert.Type}) al usuario {userIdStr}");
        await _hubContext.Clients.User(userIdStr).SendAsync("ReceiveAlert", eventData.Alert);
    }
}
