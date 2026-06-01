using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Verge.Trading.DTOs;

namespace Verge.Trading
{
    public interface IBinanceTradeAppService : IApplicationService
    {
        Task<BinanceTradeResultDto> OpenBinanceTradeAsync(OpenBinanceTradeInputDto input);
        Task<BinanceTradeResultDto> CloseBinanceTradeAsync(CloseBinanceTradeInputDto input);
    }
}
