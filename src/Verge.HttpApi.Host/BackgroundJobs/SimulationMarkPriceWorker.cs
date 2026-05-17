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

    // Tracks consecutive WS misses per symbol to avoid log spam
    private static readonly Dictionary<string, int> _wsMissCount = new();

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

            await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
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
            
            if (!openTrades.Any()) return;

            _logger.LogInformation("📊 [SimulationWorker] Updating {Count} open positions...", openTrades.Count);

            // Pre-fetch all tickers once per cycle to avoid redundant REST calls in the loop
            List<SymbolTickerModel> allTickers = null;
            try
            {
                allTickers = await marketDataManager.GetTickersAsync();
            }
            catch (Exception ex)
            {
                _logger.LogWarning("⚠️ [SimulationWorker] Failed to pre-fetch tickers: {Message}", ex.Message);
            }

            bool applyFunding = (DateTime.UtcNow - _lastFundingTime).TotalHours >= 8;

            foreach (var trade in openTrades)
            {
                try
                {
                    using var uow = uowManager.Begin();
                    
                    // Normalize symbol (e.g. 'ALPHA' → 'ALPHAUSDT')
                    var cleanSymbol = trade.Symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
                    if (!cleanSymbol.EndsWith("USDT") && !cleanSymbol.Contains("USD")) cleanSymbol += "USDT";

                    decimal? price = null;
                    string priceSource = "none";

                    // 1) Primary: WebSocket in-memory cache (fastest)
                    price = marketDataManager.GetWebSocketPrice(cleanSymbol);
                    if (price.HasValue && price.Value > 0)
                    {
                        priceSource = "WebSocket";
                        _wsMissCount.Remove(cleanSymbol);
                    }
                    else
                    {
                        // 2) Secondary: Try to find in the pre-fetched ticker list
                        var ticker = allTickers?.FirstOrDefault(t => t.Symbol == cleanSymbol);
                        if (ticker != null && ticker.LastPrice > 0)
                        {
                            price = ticker.LastPrice;
                            priceSource = "REST (Pre-fetched)";
                        }

                        if (price == null)
                        {
                            // 3) Tertiary: Wait and retry WS (covers reconnection edge cases)
                            _wsMissCount.TryGetValue(cleanSymbol, out var misses);
                            _wsMissCount[cleanSymbol] = misses + 1;

                            for (int retry = 1; retry <= 2 && price == null; retry++)
                            {
                                await Task.Delay(1000);
                                price = marketDataManager.GetWebSocketPrice(cleanSymbol);
                                if (price.HasValue && price.Value > 0)
                                {
                                    priceSource = $"WebSocket (Retry {retry})";
                                    _wsMissCount.Remove(cleanSymbol);
                                }
                            }
                        }

                        if (price == null)
                        {
                            // Last resort: SKIP this trade cycle
                            _logger.LogWarning("⚠️ [SimulationWorker] No price for {Symbol}. Skipping.", cleanSymbol);
                            continue;
                        }
                    }

                    var markPrice = price.Value;
                    _logger.LogInformation(
                        "✅ [SimulationWorker] Price for {Symbol}: {Price} (Source: {Source})",
                        trade.Symbol, markPrice, priceSource);
                    
                    trade.MarkPrice = markPrice;

                    // ── Liquidation check ──────────────────────────────────────────
                    if (simulationService.IsLiquidationTriggered(markPrice, trade.LiquidationPrice, trade.Side))
                    {
                        _logger.LogWarning("💀 [SimulationWorker] LIQUIDATION for {Id} | {Symbol} at {Price}", trade.Id, trade.Symbol, markPrice);
                        trade.Status = TradeStatus.Liquidated;
                        trade.ClosePrice = markPrice;
                        trade.ClosedAt = DateTime.UtcNow;
                        trade.RealizedPnl = -trade.Margin;
                        trade.UnrealizedPnl = 0;
                        trade.ROIPercentage = simulationService.CalculateROI(-trade.Margin, trade.Margin); // -100%

                        await tradeRepo.UpdateAsync(trade);
                        await uow.CompleteAsync();
                        await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
                        continue;
                    }

                    // ── Take Profit / Stop Loss check ──────────────────────────────
                    bool isClosed = false;
                    string closeReason = "";

                    if (trade.TpPrice.HasValue && trade.TpPrice.Value > 0)
                    {
                        bool tpTriggered = trade.Side == SignalDirection.Long
                            ? markPrice >= trade.TpPrice.Value
                            : markPrice <= trade.TpPrice.Value;
                        if (tpTriggered) { isClosed = true; closeReason = "Take Profit"; }
                    }

                    if (!isClosed && trade.SlPrice.HasValue && trade.SlPrice.Value > 0)
                    {
                        bool slTriggered = trade.Side == SignalDirection.Long
                            ? markPrice <= trade.SlPrice.Value
                            : markPrice >= trade.SlPrice.Value;
                        if (slTriggered) { isClosed = true; closeReason = "Stop Loss"; }
                    }

                    if (isClosed)
                    {
                        _logger.LogInformation("🎯 [SimulationWorker] {Reason} reached for {Symbol} at {Price}.", closeReason, trade.Symbol, markPrice);
                        
                        var exitFee = simulationService.CalculateExitFee(trade.Size, markPrice);
                        var pnl = simulationService.CalculateUnrealizedPnl(trade.EntryPrice, markPrice, trade.Size, trade.Side);
                        
                        // True NET PnL
                        var realizedPnl = pnl - trade.EntryFee - exitFee - trade.TotalFundingPaid;

                        // Log FEES
                        var totalFee = trade.EntryFee + exitFee;
                        _logger.LogInformation("[FEE] Entry={EntryFee:N4} | Exit={ExitFee:N4} | Total={TotalFee:N4} | Notional={Notional:N4}", 
                            trade.EntryFee, exitFee, totalFee, trade.Amount);

                        trade.Status = closeReason == "Take Profit" ? TradeStatus.Win : TradeStatus.Loss;
                        trade.ClosePrice = markPrice;
                        trade.ClosedAt = DateTime.UtcNow;
                        trade.RealizedPnl = realizedPnl;
                        trade.ExitFee = exitFee;
                        trade.UnrealizedPnl = 0;
                        // ✅ FIX: Recalculate final ROI based on realized PnL (was left stale before)
                        trade.ROIPercentage = simulationService.CalculateROI(realizedPnl, trade.Margin);

                        // Credit margin + entry fee + net PnL back to user balance safely
                        int balanceRetries = 5;
                        bool balanceUpdated = false;
                        for (int br = 0; br < balanceRetries && !balanceUpdated; br++)
                        {
                            await TradingSimulationService.ProfileLock.WaitAsync();
                            try
                            {
                                using (var balanceScope = _serviceProvider.CreateScope())
                                {
                                    var bProfileRepo = balanceScope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                                    var profileToCredit = await bProfileRepo.FirstOrDefaultAsync(p => p.UserId == trade.UserId);
                                    if (profileToCredit != null)
                                    {
                                        profileToCredit.VirtualBalance += (trade.Margin + trade.EntryFee + realizedPnl);
                                        await bProfileRepo.UpdateAsync(profileToCredit, autoSave: true);
                                        balanceUpdated = true;
                                    }
                                }
                            }
                            catch (Volo.Abp.Data.AbpDbConcurrencyException)
                            {
                                if (br == balanceRetries - 1) throw;
                                _logger.LogWarning("[SimulationWorker] Concurrency exception crediting balance for {UserId}. Retry {0}/5", trade.UserId, br + 1);
                                await Task.Delay(200);
                            }
                            finally
                            {
                                TradingSimulationService.ProfileLock.Release();
                            }
                        }

                        await tradeRepo.UpdateAsync(trade);
                        await uow.CompleteAsync();

                        _logger.LogInformation(
                            "📢 [SimulationWorker] SignalR: {Reason} for {Symbol} | PnL: {Pnl} | ROI: {ROI}% → UserId {UserId}",
                            closeReason, trade.Symbol, realizedPnl, trade.ROIPercentage, trade.UserId);
                        await _hubContext.Clients.User(trade.UserId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
                        continue;
                    }

                    // ── Live unrealized PnL update ─────────────────────────────────
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

                    _logger.LogInformation(
                        "📢 [SimulationWorker] Update {Symbol} → Price: {Price} | PnL: {PnL} | ROI: {ROI}%",
                        trade.Symbol, markPrice, trade.UnrealizedPnl, trade.ROIPercentage);
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
        TpPrice = t.TpPrice,
        SlPrice = t.SlPrice,
        TradingSignalId = t.TradingSignalId,
        Exchange = t.Exchange,
        AgentDecisionJson = t.AgentDecisionJson,
        StrategyProfileId = t.StrategyProfileId
    };
}
