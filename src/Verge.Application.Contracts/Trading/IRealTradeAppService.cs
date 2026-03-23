using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading
{
    public interface IRealTradeAppService : IApplicationService
    {
        Task<TradePreviewDto> GetPreviewAsync(TradeRequestDto input);
        Task<bool> ConfirmAsync(TradeConfirmationDto input);
    }
}
