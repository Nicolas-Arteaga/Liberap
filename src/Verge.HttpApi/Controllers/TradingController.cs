using System;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Volo.Abp.AspNetCore.Mvc;

namespace Verge.Trading
{
    [Route("api/app/real-trade")]
    public class RealTradeController : AbpController, IRealTradeAppService
    {
        private readonly IRealTradeAppService _tradeAppService;

        public RealTradeController(IRealTradeAppService tradeAppService)
        {
            _tradeAppService = tradeAppService;
        }

        [HttpPost("preview")]
        public virtual Task<TradePreviewDto> GetPreviewAsync([FromBody] TradeRequestDto input)
        {
            return _tradeAppService.GetPreviewAsync(input);
        }

        [HttpPost("confirm")]
        public virtual Task<bool> ConfirmAsync([FromBody] TradeConfirmationDto input)
        {
            return _tradeAppService.ConfirmAsync(input);
        }
    }
}
