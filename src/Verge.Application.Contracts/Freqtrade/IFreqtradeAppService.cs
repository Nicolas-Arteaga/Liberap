using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Freqtrade
{
    public interface IFreqtradeAppService : IApplicationService
    {
        Task StartBotAsync(FreqtradeCreateBotDto input);
        Task StopBotAsync();
        Task<FreqtradeStatusDto> GetStatusAsync();
        Task<List<FreqtradeTradeDto>> GetOpenTradesAsync();
        Task<FreqtradeProfitDto> GetProfitAsync();
        Task CloseTradeAsync(string tradeId);
        Task UpdateWhitelistAsync(string pair);
        Task ForceEnterAsync(string pair, string side, decimal stakeAmount, int leverage);
    }
}
