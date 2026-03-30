using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Verge.Trading.Bot;

namespace Verge.Trading;

/// <summary>Interface del App Service del bot de scalping.</summary>
public interface IScalpingBotAppService : IApplicationService
{
    Task StartBotAsync();
    Task StopBotAsync();
    Task<ScalpingBotStatusDto> GetStatusAsync();
    Task UpdateConfigAsync(ScalpingBotConfigDto input);
    Task<List<BotTradeDto>> GetTradesAsync(int limit = 50);
    Task CancelTradeAsync(Guid botTradeId);
    Task<List<BotEquityPointDto>> GetEquityCurveAsync();
}
