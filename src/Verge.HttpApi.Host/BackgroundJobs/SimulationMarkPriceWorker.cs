using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;
using Verge.Trading.DTOs;
using System.IO;

namespace Verge.Trading;

/// <summary>
/// Background worker that:
/// 1. Fetches current mark prices from Binance Futures
/// 2. Updates unrealized PnL + ROI for all open positions
/// 3. Checks for liquidation events and auto-closes them
/// 4. Every 8h applies funding rate payments
/// Broadcasts updates to all connected clients via SignalR.
/// </summary>
public class SimulationMarkPriceWorker : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IHubContext<TradingHub> _hubContext;
    private readonly ILogger<SimulationMarkPriceWorker> _logger;

    private static DateTime _lastFundingTime = DateTime.UtcNow;

    public SimulationMarkPriceWorker(
        IServiceProvider serviceProvider,
        IHubContext<TradingHub> hubContext,
        ILogger<SimulationMarkPriceWorker> logger)
    {
        _serviceProvider = serviceProvider;
        _hubContext = hubContext;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("📊 [SimulationWorker] Mark Price Worker started.");
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await UpdateOpenPositionsAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ [SimulationWorker] Error in mark price update cycle.");
            }

            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }

    private async Task UpdateOpenPositionsAsync()
    {
        try
        {
            using var scope = _serviceProvider.CreateScope();
            var tradeRepo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
            var profileRepo = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
            var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
            var simulationService = scope.ServiceProvider.GetRequiredService<TradingSimulationService>();
            var uowManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

            var openTrades = await tradeRepo.GetListAsync(t => t.Status == TradeStatus.Open);
            
            // Heartbeat log
            if (!openTrades.Any())
            {
                // _logger.LogInformation("📊 [SimulationWorker] No open trades found to update.");
                return;
            }

            _logger.LogInformation("📊 [SimulationWorker] Updating {Count} open positions...", openTrades.Count);
            
            // Screaming debug for the agent to find
            try { 
                await File.AppendAllTextAsync("C:\\Users\\Nicolas\\Desktop\\Verge\\Verge\\src\\Verge.HttpApi.Host\\Logs\\heartbeat_debug.txt", 
                    $"[{DateTime.UtcNow}] Heartbeat: {openTrades.Count} trades. First symbol: {openTrades.First().Symbol}\n"); 
            } catch { }

            bool applyFunding = (DateTime.UtcNow - _lastFundingTime).TotalHours >= 8;

            Dictionary<string, decimal> fallbackPriceMap = null!;

            foreach (var trade in openTrades)
            {
                _logger.LogInformation("🔍 [SimulationWorker] Processing trade {Id} for symbol {Symbol}", trade.Id, trade.Symbol);
                try
                {
                    using var uow = uowManager.Begin();
                    
                    // 🚀 ROBOTIC NORMALIZATION: Ensure 'ALPHA' becomes 'ALPHAUSDT' for cache hits
                    var cleanSymbol = trade.Symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
                    if (!cleanSymbol.EndsWith("USDT") && !cleanSymbol.Contains("USD")) cleanSymbol += "USDT";

                    var price = marketDataManager.GetWebSocketPrice(cleanSymbol);
                    string source = "WebSocket";
                    
                    if (price == null)
                    {
                        if (fallbackPriceMap == null)
                        {
                            _logger.LogInformation("[SimulationWorker] WS cache miss, fetching all tickers via REST...");
                            var tickers = await marketDataManager.GetTickersAsync();
                            fallbackPriceMap = tickers.GroupBy(t => t.Symbol).ToDictionary(g => g.Key, g => g.First().LastPrice);
                        }
                        
                        if (fallbackPriceMap.TryGetValue(cleanSymbol, out var restPrice))
                        {
                            price = restPrice;
                            source = "REST Tickers Fallback";
                        }
                    }

                    if (price == null)
                    {
                        _logger.LogWarning("❌ [SimulationWorker] PRICE NOT FOUND for {Symbol} (Cleaned: {Cleaned}) (WS=null, REST=null). Skipping update.", trade.Symbol, cleanSymbol);
                        continue;
                    }

                    var markPrice = price.Value;
                    _logger.LogInformation("✅ [SimulationWorker] Price resolved for {Symbol}: {Price} (Source: {Source})", trade.Symbol, markPrice, source);
                    
                    trade.MarkPrice = markPrice;

                    // Check liquidation
                    if (simulationService.IsLiquidationTriggered(markPrice, trade.LiquidationPrice, trade.Side))
                    {
                        _logger.LogWarning("💀 [SimulationWorker] LIQUIDATION TRIGGERED for {Id} | {Symbol} at {Price}", trade.Id, trade.Symbol, markPrice);
                        trade.Status = TradeStatus.Liquidated;
                        trade.ClosePrice = markPrice;
                        trade.ClosedAt = DateTime.UtcNow;
                        trade.RealizedPnl = -trade.Margin;

                        await tradeRepo.UpdateAsync(trade);
                        await uow.CompleteAsync();

                        _logger.LogInformation("📢 [SimulationWorker] SignalR: Sending Liquidation event to user {UserId}", trade.UserId);
                        await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
                        continue;
                    }

                    // Update unrealized PnL
                    trade.UnrealizedPnl = simulationService.CalculateUnrealizedPnl(trade.EntryPrice, markPrice, trade.Size, trade.Side);
                    trade.ROIPercentage = simulationService.CalculateROI(trade.UnrealizedPnl, trade.Margin);

                    if (applyFunding)
                    {
                        var funding = simulationService.CalculateFundingPayment(trade.Size, markPrice);
                        trade.TotalFundingPaid += funding;
                        _logger.LogInformation("💸 [SimulationWorker] Funding applied: {Amount} for {Symbol}", funding, trade.Symbol);
                    }

                    await tradeRepo.UpdateAsync(trade);
                    await uow.CompleteAsync();

                    _logger.LogInformation("📢 [SimulationWorker] SignalR: Sending update for {Symbol} (Price: {Price}, PnL: {PnL}) to user {UserId}", 
                        trade.Symbol, markPrice, trade.UnrealizedPnl, trade.UserId);
                        
                    await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "💥 [SimulationWorker] ERROR updating trade {Id}", trade.Id);
                }
            }

            if (applyFunding)
            {
                _lastFundingTime = DateTime.UtcNow;
                _logger.LogInformation("⏰ [Funding] Funding rate applied at {Time}", _lastFundingTime);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [SimulationWorker] General error in UpdateOpenPositionsAsync loop");
        }
    }

    private static SimulatedTradeDto MapToDto(SimulatedTrade t) => new SimulatedTradeDto
    {
        Id = t.Id,
        UserId = t.UserId,
        Symbol = t.Symbol,
        Side = t.Side,
        Leverage = t.Leverage,
        Size = t.Size,
        Amount = t.Amount,
        EntryPrice = t.EntryPrice,
        MarkPrice = t.MarkPrice,
        LiquidationPrice = t.LiquidationPrice,
        Margin = t.Margin,
        MarginRate = t.MarginRate,
        UnrealizedPnl = t.UnrealizedPnl,
        ROIPercentage = t.ROIPercentage,
        Status = t.Status,
        ClosePrice = t.ClosePrice,
        RealizedPnl = t.RealizedPnl,
        EntryFee = t.EntryFee,
        ExitFee = t.ExitFee,
        TotalFundingPaid = t.TotalFundingPaid,
        OpenedAt = t.OpenedAt,
        ClosedAt = t.ClosedAt,
        TradingSignalId = t.TradingSignalId
    };
}
