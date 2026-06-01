using System;
using System.Threading.Tasks;
using Volo.Abp;
using Volo.Abp.Application.Services;
using Verge.Trading.DTOs;

namespace Verge.Trading
{
    public class BinanceTradeAppService : ApplicationService, IBinanceTradeAppService
    {
        private readonly BinanceFuturesManager _binanceFuturesManager;

        public BinanceTradeAppService(BinanceFuturesManager binanceFuturesManager)
        {
            _binanceFuturesManager = binanceFuturesManager;
        }

        public async Task<BinanceTradeResultDto> OpenBinanceTradeAsync(OpenBinanceTradeInputDto input)
        {
            if (string.IsNullOrEmpty(input.Symbol))
            {
                return new BinanceTradeResultDto { Success = false, Message = "Symbol is required" };
            }

            var result = await _binanceFuturesManager.OpenPositionAsync(
                input.Symbol,
                input.Side,
                input.Quantity,
                input.TpPrice,
                input.SlPrice
            );

            return new BinanceTradeResultDto
            {
                Success = result.Success,
                Message = result.Message
            };
        }

        public async Task<BinanceTradeResultDto> CloseBinanceTradeAsync(CloseBinanceTradeInputDto input)
        {
            if (string.IsNullOrEmpty(input.Symbol))
            {
                return new BinanceTradeResultDto { Success = false, Message = "Symbol is required" };
            }

            var result = await _binanceFuturesManager.ClosePositionAsync(input.Symbol);

            return new BinanceTradeResultDto
            {
                Success = result.Success,
                Message = result.Message
            };
        }
    }
}
