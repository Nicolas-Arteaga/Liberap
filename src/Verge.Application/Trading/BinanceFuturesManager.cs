using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Binance.Net.Clients;
using Binance.Net.Objects.Models.Futures;
using Binance.Net.Enums;
using CryptoExchange.Net.Authentication;
using Volo.Abp.DependencyInjection;

namespace Verge.Trading
{
    public class BinanceFuturesManager : ISingletonDependency
    {
        private readonly ILogger<BinanceFuturesManager> _logger;
        private readonly BinanceRestClient _client;
        private readonly bool _useTestnet;
        private readonly bool _isSimulationMode;

        public BinanceFuturesManager(IConfiguration configuration, ILogger<BinanceFuturesManager> logger)
        {
            _logger = logger;
            var useTestnetStr = configuration["Binance:UseTestnet"] ?? configuration["BINANCE_USE_TESTNET"];
            _useTestnet = !string.IsNullOrEmpty(useTestnetStr) && bool.Parse(useTestnetStr);

            string apiKey, apiSecret;
            if (_useTestnet)
            {
                apiKey = configuration["BINANCE_TESTNET_API_KEY"] ?? configuration["BINANCE_API_KEY"];
                apiSecret = configuration["BINANCE_TESTNET_API_SECRET"] ?? configuration["BINANCE_API_SECRET"];
            }
            else
            {
                apiKey = configuration["BINANCE_MAINNET_API_KEY"] ?? configuration["BINANCE_API_KEY"];
                apiSecret = configuration["BINANCE_MAINNET_API_SECRET"] ?? configuration["BINANCE_API_SECRET"];
            }

            if (string.IsNullOrEmpty(apiKey) || string.IsNullOrEmpty(apiSecret))
            {
                _logger.LogWarning("⚠️ No Binance API keys found. BinanceFuturesManager running in SIMULATION MODE.");
                _isSimulationMode = true;
                _client = new BinanceRestClient();
            }
            else
            {
                _client = new BinanceRestClient(options => {
                    options.ApiCredentials = new ApiCredentials(apiKey, apiSecret);
                    if (_useTestnet)
                    {
                        options.Environment = Binance.Net.BinanceEnvironment.Testnet;
                    }
                });
                _isSimulationMode = false;
                _logger.LogInformation($"BinanceFuturesManager initialized. Mode: Real Trading. Environment: {(_useTestnet ? "TESTNET" : "MAINNET")}");
            }
        }

        public async Task<BinanceExecutionResult> OpenPositionAsync(string symbol, string side, decimal quantity, decimal? tpPrice, decimal? slPrice)
        {
            try
            {
                if (_isSimulationMode)
                {
                    _logger.LogInformation($"[SIMULATION] Entry Market Order: {side} {quantity} {symbol}");
                    if (tpPrice.HasValue) _logger.LogInformation($"[SIMULATION] TP Order: {tpPrice.Value}");
                    if (slPrice.HasValue) _logger.LogInformation($"[SIMULATION] SL Order: {slPrice.Value}");
                    return new BinanceExecutionResult { Success = true, Message = "Simulation entry success" };
                }

                var cleanSymbol = symbol.Replace("/", "").ToUpper();
                var orderSide = side.ToUpper() == "BUY" || side == "0" ? OrderSide.Buy : OrderSide.Sell;
                var oppositeSide = orderSide == OrderSide.Buy ? OrderSide.Sell : OrderSide.Buy;

                // Fetch Symbol Info for Precision Rounding
                try
                {
                    var exchangeInfoResult = await _client.UsdFuturesApi.ExchangeData.GetExchangeInfoAsync();
                    if (exchangeInfoResult.Success && exchangeInfoResult.Data != null)
                    {
                        var symbolInfo = exchangeInfoResult.Data.Symbols.FirstOrDefault(s => s.Name == cleanSymbol);
                        if (symbolInfo != null)
                        {
                            _logger.LogInformation($"[Binance] Precision rules for {cleanSymbol}: QtyPrecision={symbolInfo.QuantityPrecision}, PricePrecision={symbolInfo.PricePrecision}");
                            quantity = Math.Round(quantity, symbolInfo.QuantityPrecision);
                            if (tpPrice.HasValue)
                            {
                                tpPrice = Math.Round(tpPrice.Value, symbolInfo.PricePrecision);
                            }
                            if (slPrice.HasValue)
                            {
                                slPrice = Math.Round(slPrice.Value, symbolInfo.PricePrecision);
                            }
                        }
                        else
                        {
                            _logger.LogWarning($"[Binance] Symbol info not found for {cleanSymbol} in exchange info. Using default roundings.");
                            quantity = Math.Round(quantity, 2);
                            if (tpPrice.HasValue) tpPrice = Math.Round(tpPrice.Value, 4);
                            if (slPrice.HasValue) slPrice = Math.Round(slPrice.Value, 4);
                        }
                    }
                    else
                    {
                        _logger.LogWarning($"[Binance] Exchange info fetch unsuccessful: {exchangeInfoResult.Error?.Message}. Using default roundings.");
                        quantity = Math.Round(quantity, 2);
                        if (tpPrice.HasValue) tpPrice = Math.Round(tpPrice.Value, 4);
                        if (slPrice.HasValue) slPrice = Math.Round(slPrice.Value, 4);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"[Binance] Failed to fetch symbol rules from exchange info: {ex.Message}. Falling back to default rounding.");
                    quantity = Math.Round(quantity, 2);
                    if (tpPrice.HasValue) tpPrice = Math.Round(tpPrice.Value, 4);
                    if (slPrice.HasValue) slPrice = Math.Round(slPrice.Value, 4);
                }

                _logger.LogInformation($"[Binance] Opening {orderSide} position for {cleanSymbol} with qty {quantity} (TP: {tpPrice}, SL: {slPrice})");

                // 1. Entry Market Order
                var entryResult = await _client.UsdFuturesApi.Trading.PlaceOrderAsync(
                    cleanSymbol,
                    orderSide,
                    FuturesOrderType.Market,
                    quantity: quantity
                );

                if (!entryResult.Success)
                {
                    _logger.LogError($"[Binance] Entry Order failed: {entryResult.Error}");
                    return new BinanceExecutionResult { Success = false, Message = $"Entry failed: {entryResult.Error?.Message}" };
                }

                _logger.LogInformation($"[Binance] Entry Order success. OrderId: {entryResult.Data.Id}");

                // 2. TP Order (TAKE_PROFIT_MARKET)
                if (tpPrice.HasValue && tpPrice.Value > 0)
                {
                    _logger.LogInformation($"[Binance] Placing Take Profit at {tpPrice.Value} for {cleanSymbol}");
                    var tpResult = await _client.UsdFuturesApi.Trading.PlaceOrderAsync(
                        cleanSymbol,
                        oppositeSide,
                        FuturesOrderType.TakeProfitMarket,
                        quantity: null, // closePosition = true handles quantity
                        stopPrice: tpPrice.Value,
                        closePosition: true
                    );
                    if (!tpResult.Success)
                    {
                        _logger.LogWarning($"[Binance] TP Order failed: {tpResult.Error?.Message} (Code: {tpResult.Error?.Code})");
                    }
                    else
                    {
                        _logger.LogInformation($"[Binance] TP Order placed. OrderId: {tpResult.Data.Id}");
                    }
                }

                // 3. SL Order (STOP_MARKET)
                if (slPrice.HasValue && slPrice.Value > 0)
                {
                    _logger.LogInformation($"[Binance] Placing Stop Loss at {slPrice.Value} for {cleanSymbol}");
                    var slResult = await _client.UsdFuturesApi.Trading.PlaceOrderAsync(
                        cleanSymbol,
                        oppositeSide,
                        FuturesOrderType.StopMarket,
                        quantity: null,
                        stopPrice: slPrice.Value,
                        closePosition: true
                    );
                    if (!slResult.Success)
                    {
                        _logger.LogWarning($"[Binance] SL Order failed: {slResult.Error?.Message} (Code: {slResult.Error?.Code})");
                    }
                    else
                    {
                        _logger.LogInformation($"[Binance] SL Order placed. OrderId: {slResult.Data.Id}");
                    }
                }

                return new BinanceExecutionResult { Success = true, Message = "Position and TP/SL setup completed successfully" };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"[Binance] Critical error opening position for {symbol}");
                return new BinanceExecutionResult { Success = false, Message = $"Critical error: {ex.Message}" };
            }
        }

        public async Task<BinanceExecutionResult> ClosePositionAsync(string symbol)
        {
            try
            {
                if (_isSimulationMode)
                {
                    _logger.LogInformation($"[SIMULATION] Close Position: {symbol}");
                    return new BinanceExecutionResult { Success = true, Message = "Simulation exit success" };
                }

                var cleanSymbol = symbol.Replace("/", "").ToUpper();
                _logger.LogInformation($"[Binance] Closing position for {cleanSymbol}");

                // 1. Get Open Orders to find TP/SL
                var openOrdersResult = await _client.UsdFuturesApi.Trading.GetOpenOrdersAsync(cleanSymbol);
                if (openOrdersResult.Success && openOrdersResult.Data != null)
                {
                    // Find TP/SL orders
                    var targetOrders = openOrdersResult.Data.Where(o => 
                        o.Type == FuturesOrderType.StopMarket || 
                        o.Type == FuturesOrderType.TakeProfitMarket ||
                        o.Type == FuturesOrderType.TakeProfit ||
                        o.Type == FuturesOrderType.Stop
                    ).ToList();

                    foreach (var order in targetOrders)
                    {
                        _logger.LogInformation($"[Binance] Cancelling pending order {order.Id} ({order.Type}) for {cleanSymbol}");
                        var cancelResult = await _client.UsdFuturesApi.Trading.CancelOrderAsync(cleanSymbol, order.Id);
                        if (!cancelResult.Success)
                        {
                            _logger.LogWarning($"[Binance] Failed to cancel order {order.Id}: {cancelResult.Error?.Message}");
                        }
                    }
                }
                else
                {
                    _logger.LogWarning($"[Binance] Could not retrieve open orders to cancel TP/SL: {openOrdersResult.Error?.Message}");
                }

                // 2. Get current position details to determine size and direction
                var positionResult = await _client.UsdFuturesApi.Account.GetPositionInformationAsync(cleanSymbol);
                if (!positionResult.Success || positionResult.Data == null)
                {
                    _logger.LogError($"[Binance] Failed to fetch position information: {positionResult.Error?.Message}");
                    return new BinanceExecutionResult { Success = false, Message = $"Failed to fetch position details: {positionResult.Error?.Message}" };
                }

                // Find active position (Quantity != 0)
                var position = positionResult.Data.FirstOrDefault(p => p.Symbol == cleanSymbol && p.Quantity != 0);
                if (position == null)
                {
                    _logger.LogWarning($"[Binance] No active position found for {cleanSymbol} to close.");
                    return new BinanceExecutionResult { Success = true, Message = "No active position found" };
                }

                var currentQty = position.Quantity;
                var closeSide = currentQty > 0 ? OrderSide.Sell : OrderSide.Buy;
                var absoluteQty = Math.Abs(currentQty);

                _logger.LogInformation($"[Binance] Closing position of {currentQty} {cleanSymbol} with a {closeSide} order");

                // 3. Place Market Order to close position
                var closeResult = await _client.UsdFuturesApi.Trading.PlaceOrderAsync(
                    cleanSymbol,
                    closeSide,
                    FuturesOrderType.Market,
                    quantity: absoluteQty,
                    reduceOnly: true
                );

                if (!closeResult.Success)
                {
                    _logger.LogError($"[Binance] Close Market Order failed: {closeResult.Error?.Message}");
                    return new BinanceExecutionResult { Success = false, Message = $"Close failed: {closeResult.Error?.Message}" };
                }

                _logger.LogInformation($"[Binance] Position successfully closed. OrderId: {closeResult.Data.Id}");
                return new BinanceExecutionResult { Success = true, Message = "Position closed and TP/SL cancelled successfully" };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"[Binance] Critical error closing position for {symbol}");
                return new BinanceExecutionResult { Success = false, Message = $"Critical error: {ex.Message}" };
            }
        }
    }

    public class BinanceExecutionResult
    {
        public bool Success { get; set; }
        public string Message { get; set; } = string.Empty;
    }
}
