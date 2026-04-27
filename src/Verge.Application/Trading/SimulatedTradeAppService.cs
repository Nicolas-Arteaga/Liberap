using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Volo.Abp;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;
using Verge.Trading.DTOs;
using AutoMapper;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Mvc;

namespace Verge.Trading;

public class SimulatedTradeAppService : ApplicationService, ISimulatedTradeAppService
{
    private readonly IRepository<SimulatedTrade, Guid> _tradeRepo;
    private readonly IRepository<TraderProfile, Guid> _profileRepo;
    private readonly MarketDataManager _marketDataManager;
    private readonly TradingSimulationService _simulationService;
    private readonly IHubContext<TradingHub> _hubContext;

    public SimulatedTradeAppService(
        IRepository<SimulatedTrade, Guid> tradeRepo,
        IRepository<TraderProfile, Guid> profileRepo,
        MarketDataManager marketDataManager,
        TradingSimulationService simulationService,
        IHubContext<TradingHub> hubContext)
    {
        _tradeRepo = tradeRepo;
        _profileRepo = profileRepo;
        _marketDataManager = marketDataManager;
        _simulationService = simulationService;
        _hubContext = hubContext;
    }

    public async Task<SimulatedTradeDto> OpenTradeAsync(OpenTradeInputDto input)
    {
        // 1. Get current user profile
        var userId = CurrentUser.Id!.Value;
        var profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId)
            ?? throw new UserFriendlyException("Trader profile not found. Please complete your profile first.");

        // 2. Normalize and get current mark price (Try fast WebSocket cache first)
        var symbol = input.Symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
        if (!symbol.EndsWith("USDT") && !symbol.Contains("USD")) symbol += "USDT";

        decimal entryPrice;
        var wsPrice = _marketDataManager.GetWebSocketPrice(symbol);
        if (wsPrice.HasValue && wsPrice.Value > 0)
        {
            entryPrice = wsPrice.Value;
        }
        else
        {
            var tickers = await _marketDataManager.GetTickersAsync();
            var ticker = tickers.FirstOrDefault(t => t.Symbol == symbol)
                ?? throw new UserFriendlyException($"Symbol '{symbol}' not found on Binance Futures. Asegurate de usar el par con USDT (ej: BTCUSDT)");
            entryPrice = ticker.LastPrice;
        }

        // 3. Calculate position values
        // input.Amount is now treated as MARGIN (the cost the user wants to risk)
        var margin = input.Amount;
        var exposureValue = margin * input.Leverage;
        var entryFee = _simulationService.CalculateEntryFee(exposureValue);
        var totalCost = margin + entryFee;

        // 4. Validate virtual balance
        if (profile.VirtualBalance < totalCost)
            throw new UserFriendlyException($"Insufficient virtual balance. Required: {totalCost:N2} USDT (Margin: {margin:N2} + Fee: {entryFee:N2}), Available: {profile.VirtualBalance:N2} USDT.");

        // 5. Calculate position size (quantity) and liquidation price
        var size = _simulationService.CalculatePositionSize(exposureValue, entryPrice);
        var liquidationPrice = _simulationService.CalculateLiquidationPrice(entryPrice, input.Leverage, input.Side);

        // 6. Deduct balance (margin + entry fee)
        profile.VirtualBalance -= totalCost;
        await _profileRepo.UpdateAsync(profile);

        // 7. Create trade record
        var trade = new SimulatedTrade(
            id: GuidGenerator.Create(),
            userId: userId,
            symbol: symbol,
            side: input.Side,
            leverage: input.Leverage,
            entryPrice: entryPrice,
            size: size, // Coin quantity
            amount: exposureValue, // Nominal exposure in USDT
            margin: margin,
            liquidationPrice: liquidationPrice,
            entryFee: entryFee,
            tpPrice: input.TpPrice,
            slPrice: input.SlPrice,
            tradingSignalId: input.TradingSignalId);

        await _tradeRepo.InsertAsync(trade, autoSave: true);

        var dto = MapToDto(trade);

        // 8. Broadcast new trade to user
        await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeOpened", dto);

        Logger.LogInformation("✅ [Simulation] Trade opened: {Side} {Symbol} x{Leverage} @ {Price} | Margin: {Margin} USDT",
            input.Side, symbol, input.Leverage, entryPrice, margin);

        return dto;
    }

    public async Task<SimulatedTradeDto> CloseTradeAsync(Guid tradeId)
    {
        var userId = CurrentUser.Id!.Value;
        var trade = await _tradeRepo.GetAsync(tradeId);

        if (trade.UserId != userId)
            throw new UserFriendlyException("You don't have permission to close this trade.");

        if (trade.Status != TradeStatus.Open)
        {
            Logger.LogWarning("⚠️ [Simulation] Attempted to close a trade that is already {Status}: {TradeId}", trade.Status, tradeId);
            return MapToDto(trade); // Devuelve el trade como esta (probablemente ya cerrado por stop loss/take profit/liquidacion)
        }

        // 1. Get current mark price (Try fast WebSocket cache first)
        decimal closePrice;
        var wsPrice = _marketDataManager.GetWebSocketPrice(trade.Symbol);
        if (wsPrice.HasValue && wsPrice.Value > 0)
        {
            closePrice = wsPrice.Value;
        }
        else
        {
            var tickers = await _marketDataManager.GetTickersAsync();
            var ticker = tickers.FirstOrDefault(t => t.Symbol == trade.Symbol)
                ?? throw new UserFriendlyException($"Could not fetch current price for {trade.Symbol}.");
            closePrice = ticker.LastPrice;
        }

        // 2. Calculate exit fee and realized PnL
        var exitFee = _simulationService.CalculateExitFee(trade.Size, closePrice);
        var realizedPnl = _simulationService.CalculateRealizedPnl(
            entryPrice: trade.EntryPrice,
            closePrice: closePrice,
            size: trade.Size,
            side: trade.Side,
            entryFee: trade.EntryFee,
            exitFee: exitFee,
            totalFundingPaid: trade.TotalFundingPaid);

        // 3. Update trade record
        trade.Status = realizedPnl >= 0 ? TradeStatus.Win : TradeStatus.Loss;
        trade.ClosePrice = closePrice;
        trade.RealizedPnl = realizedPnl;
        trade.ExitFee = exitFee;
        trade.ClosedAt = DateTime.UtcNow;
        trade.UnrealizedPnl = 0;
        trade.ROIPercentage = 0;

        await _tradeRepo.UpdateAsync(trade, autoSave: false);

        // 4. Return margin + realized PnL to user balance
        var profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
        if (profile != null)
        {
            profile.VirtualBalance += trade.Margin + realizedPnl;
            await _profileRepo.UpdateAsync(profile, autoSave: true);
        }

        var dto = MapToDto(trade);

        // 5. Broadcast closed trade
        await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeClosed", dto);

        Logger.LogInformation("✅ [Simulation] Trade closed: {Symbol} @ {Price} | PnL: {Pnl} USDT",
            trade.Symbol, closePrice, realizedPnl);

        return dto;
    }

    public async Task<List<SimulatedTradeDto>> GetActiveTradesAsync()
    {
        var userId = CurrentUser.Id!.Value;
        var trades = await _tradeRepo.GetListAsync(t => t.UserId == userId && t.Status == TradeStatus.Open);
        return trades.OrderByDescending(t => t.OpenedAt).Select(MapToDto).ToList();
    }

    public async Task<List<SimulatedTradeDto>> GetTradeHistoryAsync()
    {
        var userId = CurrentUser.Id!.Value;
        var trades = await _tradeRepo.GetListAsync(t => t.UserId == userId && t.Status != TradeStatus.Open);
        return trades.OrderByDescending(t => t.ClosedAt).Select(MapToDto).ToList();
    }

    public async Task<decimal> GetVirtualBalanceAsync()
    {
        var userId = CurrentUser.Id!.Value;
        var profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
        
        if (profile == null) return 0;

        // If balance is 0, we can assume it's a first-time user or we want to provide a default
        // For a more robust simulator, we only auto-initialize if they have no trades.
        if (profile.VirtualBalance == 0)
        {
            var hasTrades = await _tradeRepo.AnyAsync(t => t.UserId == userId);
            if (!hasTrades)
            {
                profile.VirtualBalance = 10000;
                await _profileRepo.UpdateAsync(profile, autoSave: true);
            }
        }

        return profile.VirtualBalance;
    }

    [HttpGet]
    public async Task<SimulationPerformanceDto> GetPerformanceStatsAsync()
    {
        var userId = CurrentUser.Id!.Value;
        var trades = await _tradeRepo.GetListAsync(t => t.UserId == userId && t.Status != TradeStatus.Open);
        
        var stats = new SimulationPerformanceDto();
        if (!trades.Any())
        {
            stats.EquityCurve.Add(new EquityPointDto { Timestamp = DateTime.UtcNow, Balance = 10000 });
            return stats;
        }

        stats.TotalTrades = trades.Count;
        stats.TotalGain = trades.Sum(t => t.RealizedPnl ?? 0);
        var wins = trades.Count(t => t.Status == TradeStatus.Win);
        stats.WinRate = stats.TotalTrades > 0 ? (decimal)wins / stats.TotalTrades * 100 : 0;
        stats.AvgPerTrade = stats.TotalTrades > 0 ? stats.TotalGain / stats.TotalTrades : 0;

        // Corrected Equity Curve: Initial 10k + cumulative realized PnL
        decimal currentBalance = 10000;
        stats.EquityCurve.Add(new EquityPointDto { Timestamp = trades.Min(t => t.OpenedAt).AddMinutes(-1), Balance = currentBalance });

        foreach (var trade in trades.OrderBy(t => t.ClosedAt))
        {
            currentBalance += (trade.RealizedPnl ?? 0);
            stats.EquityCurve.Add(new EquityPointDto 
            { 
                Timestamp = trade.ClosedAt ?? trade.OpenedAt, 
                Balance = currentBalance 
            });
        }

        return stats;
    }

    [HttpGet]
    public async Task<List<SimulatedTradeDto>> GetRecentTradesAsync(int limit = 20)
    {
        var userId = CurrentUser.Id!.Value;
        var trades = await _tradeRepo.GetListAsync(t => t.UserId == userId);
        return trades.OrderByDescending(t => t.OpenedAt)
                     .Take(limit)
                     .Select(MapToDto)
                     .ToList();
    }

    public async Task UpdateTpSlAsync(Guid tradeId, UpdateTpSlInputDto input)
    {
        var userId = CurrentUser.Id!.Value;
        var trade = await _tradeRepo.GetAsync(tradeId);

        if (trade.UserId != userId)
            throw new UserFriendlyException("You don't have permission to update this trade.");

        if (trade.Status != TradeStatus.Open)
            throw new UserFriendlyException("You can only update TP/SL for open trades.");

        trade.TpPrice = input.TpPrice;
        trade.SlPrice = input.SlPrice;

        await _tradeRepo.UpdateAsync(trade, autoSave: true);
        
        // Broadcast update to client
        await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeUpdate", MapToDto(trade));
        
        Logger.LogInformation("🎯 [Simulation] TP/SL updated for {Symbol}: TP {Tp}, SL {Sl}", 
            trade.Symbol, trade.TpPrice, trade.SlPrice);
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
        TradingSignalId = t.TradingSignalId
    };
}
