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
using System.Net.Http;
using System.Text.Json;
using System.Globalization;

namespace Verge.Trading;

public class SimulatedTradeAppService : ApplicationService, ISimulatedTradeAppService
{
    private readonly IRepository<SimulatedTrade, Guid> _tradeRepo;
    private readonly IRepository<TraderProfile, Guid> _profileRepo;
    private readonly MarketDataManager _marketDataManager;
    private readonly TradingSimulationService _simulationService;
    private readonly IHubContext<TradingHub> _hubContext;
    private readonly HttpClient _priceClient = new() { Timeout = TimeSpan.FromSeconds(3) };

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

        // 2. Normalize and get current mark price (Try fast WebSocket cache first)
        var symbol = NormalizeSymbol(input.Symbol);
        var entryPrice = await ResolveCurrentPriceAsync(symbol)
            ?? throw new UserFriendlyException($"Could not fetch current price for {symbol}.");

        // 3. Calculate position values
        var margin = input.Amount;
        var exposureValue = margin * input.Leverage;
        var entryFee = _simulationService.CalculateEntryFee(exposureValue);
        var totalCost = margin + entryFee;

        // 4. Validate virtual balance (Loading here to minimize concurrency window)
        var profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId)
            ?? throw new UserFriendlyException("Trader profile not found.");

        if (profile.VirtualBalance < totalCost)
            throw new UserFriendlyException($"Insufficient virtual balance. Required: {totalCost:N2} USDT, Available: {profile.VirtualBalance:N2} USDT.");

        // 5. Calculate position size (quantity) and liquidation price
        var size = _simulationService.CalculatePositionSize(exposureValue, entryPrice);
        var liquidationPrice = _simulationService.CalculateLiquidationPrice(entryPrice, input.Leverage, input.Side);

        // 6. Deduct balance with Retry logic for Concurrency
        profile.VirtualBalance -= totalCost;
        
        try {
            await _profileRepo.UpdateAsync(profile, autoSave: true);
        } catch (Volo.Abp.Data.AbpDbConcurrencyException) {
            Logger.LogWarning("🔄 [Simulation] Concurrency conflict for profile {UserId}. Retrying...", userId);
            profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
            if (profile!.VirtualBalance < totalCost) throw new UserFriendlyException("Insufficient balance after retry.");
            profile.VirtualBalance -= totalCost;
            await _profileRepo.UpdateAsync(profile, autoSave: true);
        }

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
        var closePrice = await ResolveCurrentPriceAsync(trade.Symbol)
            ?? throw new UserFriendlyException($"Could not fetch current price for {trade.Symbol}.");

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
            try {
                await _profileRepo.UpdateAsync(profile, autoSave: true);
            } catch (Volo.Abp.Data.AbpDbConcurrencyException) {
                Logger.LogWarning("🔄 [Simulation] Concurrency conflict closing trade for {UserId}. Retrying...", userId);
                profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
                if (profile != null) {
                    profile.VirtualBalance += trade.Margin + realizedPnl;
                    await _profileRepo.UpdateAsync(profile, autoSave: true);
                }
            }
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
                try {
                    await _profileRepo.UpdateAsync(profile, autoSave: true);
                } catch (Volo.Abp.Data.AbpDbConcurrencyException) {
                    // Ignore, someone else might have initialized it
                }
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

    private static string NormalizeSymbol(string rawSymbol)
    {
        var symbol = rawSymbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
        if (!symbol.EndsWith("USDT") && !symbol.Contains("USD"))
        {
            symbol += "USDT";
        }
        return symbol;
    }

    private async Task<decimal?> ResolveCurrentPriceAsync(string rawSymbol)
    {
        var symbol = NormalizeSymbol(rawSymbol);

        for (int i = 0; i < 3; i++)
        {
            // 1) Fast path: in-memory WS cache
            var wsPrice = _marketDataManager.GetWebSocketPrice(symbol);
            if (wsPrice.HasValue && wsPrice.Value > 0) return wsPrice.Value;

            // 2) Local Python Service (Multi-exchange source)
            var pythonPrice = await TryFetchDirectPriceAsync($"http://127.0.0.1:8001/market/ticker/{symbol}");
            if (pythonPrice.HasValue && pythonPrice.Value > 0) return pythonPrice.Value;

            // 3) Aggregated 24h tickers
            try
            {
                var tickers = await _marketDataManager.GetTickersAsync();
                var ticker = tickers.FirstOrDefault(t => t.Symbol == symbol);
                if (ticker != null && ticker.LastPrice > 0) return ticker.LastPrice;
            }
            catch { }

            // 4) External Binance Fallbacks
            var futures = await TryFetchDirectPriceAsync($"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}");
            if (futures.HasValue && futures.Value > 0) return futures.Value;

            var spot = await TryFetchDirectPriceAsync($"https://api.binance.com/api/v3/ticker/price?symbol={symbol}");
            if (spot.HasValue && spot.Value > 0) return spot.Value;

            if (i < 2) await Task.Delay(500);
        }

        Logger.LogWarning("⚠️ [Simulation] No valid price source found for {Symbol} after retries.", symbol);
        return null;
    }

    private async Task<decimal?> TryFetchDirectPriceAsync(string url)
    {
        try
        {
            var response = await _priceClient.GetAsync(url);
            if (!response.IsSuccessStatusCode) return null;

            var content = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(content);
            
            string priceStr = null;
            if (doc.RootElement.TryGetProperty("price", out var pNode)) priceStr = pNode.GetString();
            else if (doc.RootElement.TryGetProperty("close", out var cNode)) 
            {
                if (cNode.ValueKind == JsonValueKind.Number) return cNode.GetDecimal();
                priceStr = cNode.GetString();
            }

            if (decimal.TryParse(priceStr, NumberStyles.Any, CultureInfo.InvariantCulture, out var value) && value > 0)
            {
                return value;
            }
        }
        catch { }
        return null;
    }
}
