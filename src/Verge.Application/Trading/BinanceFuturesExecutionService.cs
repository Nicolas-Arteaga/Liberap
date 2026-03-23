using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Binance.Net.Clients;
using Binance.Net.Objects.Models.Futures;
using CryptoExchange.Net.Authentication;
using System.Collections.Generic;
using System.Linq;

namespace Verge.Trading
{
    public class BinanceFuturesExecutionService
    {
        private readonly ILogger<BinanceFuturesExecutionService> _logger;
        private readonly BinanceRestClient _client;
        private readonly bool _isSimulationMode;

        public BinanceFuturesExecutionService(IConfiguration configuration, ILogger<BinanceFuturesExecutionService> logger)
        {
            _logger = logger;
            var apiKey = configuration["BINANCE_API_KEY"];
            var apiSecret = configuration["BINANCE_API_SECRET"];

            if (string.IsNullOrEmpty(apiKey) || string.IsNullOrEmpty(apiSecret))
            {
                _logger.LogWarning("⚠️ No Binance API keys found. Running in SIMULATION MODE.");
                _isSimulationMode = true;
                _client = new BinanceRestClient();
            }
            else
            {
                _client = new BinanceRestClient(options => {
                    options.ApiCredentials = new ApiCredentials(apiKey, apiSecret);
                });
                _isSimulationMode = false;
            }
        }

        public async Task<decimal> GetAccountBalanceAsync()
        {
            if (_isSimulationMode) return 10000m; // Mock balance

            var result = await _client.UsdFuturesApi.Account.GetBalancesAsync();
            if (!result.Success)
            {
                _logger.LogError($"❌ Error fetching balance: {result.Error}");
                return 0;
            }

            return result.Data.FirstOrDefault(b => b.Asset == "USDT")?.AvailableBalance ?? 0;
        }

        public async Task<bool> PlaceMarketOrderAsync(string symbol, string side, decimal quantity)
        {
            if (_isSimulationMode)
            {
                _logger.LogInformation($"[SIM] Market Order: {side} {quantity} {symbol}");
                return true;
            }

            var orderSide = side.ToLower() == "buy" ? Binance.Net.Enums.OrderSide.Buy : Binance.Net.Enums.OrderSide.Sell;
            var result = await _client.UsdFuturesApi.Trading.PlaceOrderAsync(
                symbol.Replace("/", ""),
                orderSide,
                Binance.Net.Enums.FuturesOrderType.Market,
                quantity: quantity
            );

            if (!result.Success)
            {
                _logger.LogError($"❌ Order failed: {result.Error}");
                return false;
            }

            _logger.LogInformation($"✅ Order placed: {result.Data.Id}");
            return true;
        }

        public bool IsSimulationMode => _isSimulationMode;
    }
}
