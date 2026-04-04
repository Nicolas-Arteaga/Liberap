using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Memory;
using Volo.Abp;
using Volo.Abp.Application.Services;
using System.Linq;

namespace Verge.Trading
{
    public class RealTradeAppService : ApplicationService, IRealTradeAppService
    {
        private readonly BinanceFuturesExecutionService _executionService;
        private readonly IMemoryCache _confirmationCache;
        private readonly MarketDataManager _marketDataManager;

        public RealTradeAppService(
            BinanceFuturesExecutionService executionService, 
            IMemoryCache confirmationCache,
            MarketDataManager marketDataManager)
        {
            _executionService = executionService;
            _confirmationCache = confirmationCache;
            _marketDataManager = marketDataManager;
        }

        public async Task<TradePreviewDto> GetPreviewAsync(TradeRequestDto input)
        {
            // 1. Get current price
            var price = _marketDataManager.GetWebSocketPrice(input.Symbol) ?? 0;
            if (price == 0)
            {
                var tickers = await _marketDataManager.GetTickersAsync();
                price = tickers.FirstOrDefault(t => t.Symbol == input.Symbol.ToUpper().Replace("/", ""))?.LastPrice ?? 0;
            }

            if (price == 0) throw new UserFriendlyException("No se pudo obtener el precio actual para la previsualización.");

            // 2. Risk check (Hard-coded limits)
            var maxNotional = 100m;
            if (input.Quantity * price > maxNotional)
            {
                throw new UserFriendlyException($"Riesgo excedido: El valor nocional máximo es ${maxNotional}");
            }

            // 3. Generate token
            var token = Guid.NewGuid().ToString();
            var preview = new TradePreviewDto
            {
                Symbol = input.Symbol,
                Side = input.Side,
                Quantity = input.Quantity,
                EstimatedPrice = price,
                ConfirmationToken = token
            };

            // 4. Cache for confirmation (5 min TTL)
            _confirmationCache.Set(token, input, TimeSpan.FromMinutes(5));

            return preview;
        }

        public async Task<bool> ConfirmAsync(TradeConfirmationDto input)
        {
            if (!_confirmationCache.TryGetValue(input.ConfirmationToken, out TradeRequestDto cachedInput))
            {
                throw new UserFriendlyException("Token inválido o expirado. Por favor solicite una nueva previsualización.");
            }

            // Execute real trade
            var success = await _executionService.PlaceMarketOrderAsync(
                cachedInput.Symbol, 
                cachedInput.Side, 
                cachedInput.Quantity
            );

            if (success)
            {
                _confirmationCache.Remove(input.ConfirmationToken);
            }

            return success;
        }
    }
}
