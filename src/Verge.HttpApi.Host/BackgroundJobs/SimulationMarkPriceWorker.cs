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
        using var scope = _serviceProvider.CreateScope();
        var tradeRepo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
        var profileRepo = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var simulationService = scope.ServiceProvider.GetRequiredService<TradingSimulationService>();
        var uowManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

        var openTrades = await tradeRepo.GetListAsync(t => t.Status == TradeStatus.Open);
        if (!openTrades.Any()) return;

        // Fetch current tickers in one batch
        var tickers = await marketDataManager.GetTickersAsync();
        var priceMap = tickers.ToDictionary(t => t.Symbol, t => t.LastPrice);

        bool applyFunding = (DateTime.UtcNow - _lastFundingTime).TotalHours >= 8;

        using var uow = uowManager.Begin();

        foreach (var trade in openTrades)
        {
            if (!priceMap.TryGetValue(trade.Symbol, out var markPrice)) continue;

            trade.MarkPrice = markPrice;

            // Check liquidation
            if (simulationService.IsLiquidationTriggered(markPrice, trade.LiquidationPrice, trade.Side))
            {
                _logger.LogWarning("💀 [SimulationWorker] Liquidating position {Id} for {Symbol} at {Price}", trade.Id, trade.Symbol, markPrice);
                trade.Status = TradeStatus.Liquidated;
                trade.ClosePrice = markPrice;
                trade.ClosedAt = DateTime.UtcNow;
                trade.RealizedPnl = -trade.Margin; // Total margin loss on liquidation

                // Return remaining margin (0) to user's balance
                var profile = await profileRepo.FirstOrDefaultAsync(p => p.UserId == trade.UserId);
                if (profile != null)
                {
                    // Balance already minus initial margin at open time — no refund on liquidation
                }

                await tradeRepo.UpdateAsync(trade);
                await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
                continue;
            }

            // Update unrealized PnL
            trade.UnrealizedPnl = simulationService.CalculateUnrealizedPnl(trade.EntryPrice, markPrice, trade.Size, trade.Side);
            trade.ROIPercentage = simulationService.CalculateROI(trade.UnrealizedPnl, trade.Margin);

            // Apply funding rate every 8h
            if (applyFunding)
            {
                var funding = simulationService.CalculateFundingPayment(trade.Size, markPrice);
                trade.TotalFundingPaid += funding;
                _logger.LogInformation("💸 [Funding] Charged {Amount} USDT for {Symbol} position {Id}", funding, trade.Symbol, trade.Id);
            }

            await tradeRepo.UpdateAsync(trade);

            // Broadcast to user's clients
            await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
        }

        if (applyFunding)
        {
            _lastFundingTime = DateTime.UtcNow;
            _logger.LogInformation("⏰ [Funding] Funding rate applied at {Time}", _lastFundingTime);
        }

        await uow.CompleteAsync();
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
