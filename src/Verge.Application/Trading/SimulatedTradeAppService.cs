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
using Volo.Abp.Data;
using Microsoft.Extensions.DependencyInjection;

namespace Verge.Trading;

public class SimulatedTradeAppService : ApplicationService, ISimulatedTradeAppService
{
    private readonly IRepository<SimulatedTrade, Guid> _tradeRepo;
    private readonly IRepository<TraderProfile, Guid> _profileRepo;
    private readonly MarketDataManager _marketDataManager;
    private readonly TradingSimulationService _simulationService;
    private readonly IHubContext<TradingHub> _hubContext;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly HttpClient _priceClient = new() { Timeout = TimeSpan.FromSeconds(3) };

    public SimulatedTradeAppService(
        IRepository<SimulatedTrade, Guid> tradeRepo,
        IRepository<TraderProfile, Guid> profileRepo,
        MarketDataManager marketDataManager,
        TradingSimulationService simulationService,
        IHubContext<TradingHub> hubContext,
        IServiceScopeFactory scopeFactory)
    {
        _tradeRepo = tradeRepo;
        _profileRepo = profileRepo;
        _marketDataManager = marketDataManager;
        _simulationService = simulationService;
        _hubContext = hubContext;
        _scopeFactory = scopeFactory;
    }

    public async Task<SimulatedTradeDto> OpenTradeAsync(OpenTradeInputDto input)
    {
        // 1. Get current user profile
        var userId = CurrentUser.Id!.Value;

        // 2. Normalize and get current mark price
        var symbol = NormalizeSymbol(input.Symbol);
        var entryPrice = await ResolveCurrentPriceAsync(symbol);

        if (!entryPrice.HasValue)
        {
            Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: Price not found in any source.", symbol);
            return null;
        }

        // 2.2 Validate SL/TP logic against live entry price to prevent immediate ghost trades due to price desync
        if (input.Side == SignalDirection.Long)
        {
            if (input.SlPrice.HasValue && input.SlPrice.Value >= entryPrice.Value)
            {
                Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: requested LONG SL ({Sl}) is >= live Entry ({Entry}).", symbol, input.SlPrice.Value, entryPrice.Value);
                return null;
            }
            if (input.TpPrice.HasValue && input.TpPrice.Value <= entryPrice.Value)
            {
                Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: requested LONG TP ({Tp}) is <= live Entry ({Entry}).", symbol, input.TpPrice.Value, entryPrice.Value);
                return null;
            }
        }
        else // Short
        {
            if (input.SlPrice.HasValue && input.SlPrice.Value <= entryPrice.Value)
            {
                Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: requested SHORT SL ({Sl}) is <= live Entry ({Entry}).", symbol, input.SlPrice.Value, entryPrice.Value);
                return null;
            }
            if (input.TpPrice.HasValue && input.TpPrice.Value >= entryPrice.Value)
            {
                Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: requested SHORT TP ({Tp}) is >= live Entry ({Entry}).", symbol, input.TpPrice.Value, entryPrice.Value);
                return null;
            }
        }

        await TradingSimulationService.ProfileLock.WaitAsync();
        try
        {
            // 2.5. SMART POSITION MANAGEMENT: If position exists for this strategy profile, ADD to it (Average Price) instead of blocking
            var existingTrade = await _tradeRepo.FirstOrDefaultAsync(t => 
                t.UserId == userId && 
                t.Symbol == symbol && 
                t.Status == TradeStatus.Open &&
                t.StrategyProfileId == input.StrategyProfileId);

            if (existingTrade != null)
            {
                if (existingTrade.Side == input.Side)
                {
                    Logger.LogInformation("➕ [Simulation] Increasing existing position for {Symbol} (User: {UserId}). Averaging entry price...", symbol, userId);

                    // Calculate new cost
                    var marginToAdd = input.Amount;
                    var exposureToAdd = marginToAdd * input.Leverage;
                    var entryFeeToAdd = _simulationService.CalculateEntryFee(exposureToAdd);
                    var totalCostToAdd = marginToAdd + entryFeeToAdd;

                    // Validate balance
                    var profileForUpdate = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId)
                        ?? throw new UserFriendlyException("Trader profile not found.");

                    // v11.12 NO MORE LIES: Ya no bloqueamos add-to-position por balance virtual.
                    Logger.LogInformation(
                        "[BILLETERA-REAL v11.12] AddToPosition {Symbol}: deducting {Amount:N2} USDT (virtual before: {Balance:N2})",
                        symbol, totalCostToAdd, profileForUpdate.VirtualBalance);

                    // Calculate new size and weighted entry price
                    var sizeToAdd = _simulationService.CalculatePositionSize(exposureToAdd, entryPrice.Value);
                    
                    var oldNotional = existingTrade.Size * existingTrade.EntryPrice;
                    var addedNotional = sizeToAdd * entryPrice.Value;
                    
                    var newTotalSize = existingTrade.Size + sizeToAdd;
                    var newEntryPrice = (oldNotional + addedNotional) / newTotalSize;

                    // Deduct balance safely
                    profileForUpdate.VirtualBalance -= totalCostToAdd;
                    await _profileRepo.UpdateAsync(profileForUpdate, autoSave: true);

                    // Update existing trade properties
                    existingTrade.EntryPrice = newEntryPrice;
                    existingTrade.Size = newTotalSize;
                    existingTrade.Margin += marginToAdd;
                    existingTrade.Amount += exposureToAdd;
                    existingTrade.EntryFee += entryFeeToAdd;
                    existingTrade.Leverage = input.Leverage; 
                    
                    existingTrade.LiquidationPrice = _simulationService.CalculateLiquidationPrice(newEntryPrice, existingTrade.Leverage, existingTrade.Side);

                    if (input.TpPrice.HasValue && input.TpPrice.Value > 0) existingTrade.TpPrice = input.TpPrice;
                    if (input.SlPrice.HasValue && input.SlPrice.Value > 0) existingTrade.SlPrice = input.SlPrice;
                    if (input.StrategyProfileId.HasValue) existingTrade.StrategyProfileId = input.StrategyProfileId;

                    await _tradeRepo.UpdateAsync(existingTrade, autoSave: true);
                    
                    var updatedDto = MapToDto(existingTrade);
                    await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeUpdate", updatedDto);

                    Logger.LogInformation("✅ [Simulation] Position updated for {Symbol}: New Entry {Price}, New Size {Size}", 
                        symbol, newEntryPrice, newTotalSize);

                    return updatedDto;
                }
                else 
                {
                    // POSITION FLIP: If side is different, automatically CLOSE the old one first.
                    Logger.LogInformation("🔄 [Simulation] Position Flip detected for {Symbol}. Closing {OldSide} to open {NewSide}.", 
                        symbol, existingTrade.Side, input.Side);
                    
                    TradingSimulationService.ProfileLock.Release();
                    try
                    {
                        await CloseTradeAsync(existingTrade.Id);
                    }
                    finally
                    {
                        await TradingSimulationService.ProfileLock.WaitAsync();
                    }
                    // After closing, we continue to the normal 'Open' logic below
                }
            }

            // 3. Calculate position values
            var margin = input.Amount;
            var exposureValue = margin * input.Leverage;
            var entryFee = _simulationService.CalculateEntryFee(exposureValue);
            var totalCost = margin + entryFee;

            // 5. Calculate position size (quantity) and liquidation price
            var size = _simulationService.CalculatePositionSize(exposureValue, entryPrice.Value);
            var liquidationPrice = _simulationService.CalculateLiquidationPrice(entryPrice.Value, input.Leverage, input.Side);

            if (input.TpPrice.HasValue)
            {
                var expectedProfit = Math.Abs(input.TpPrice.Value - entryPrice.Value) * size;
                var exitFeeEst = _simulationService.CalculateExitFee(size, input.TpPrice.Value);
                var expectedTotalFee = entryFee + exitFeeEst;

                if (expectedProfit <= expectedTotalFee * 1.2m)
                {
                    Logger.LogWarning("🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: expected profit {ExpectedProfit:N4} is <= total fees {ExpectedTotalFee:N4} * 1.2.", symbol, expectedProfit, expectedTotalFee);
                    return null;
                }
            }

            // 6. Anti-slippage guard: reject if SL/TP levels are already crossed at entry price
            if (input.SlPrice.HasValue && input.SlPrice.Value > 0)
            {
                bool slAlreadyCrossed = input.Side == SignalDirection.Long
                    ? entryPrice.Value <= input.SlPrice.Value   // Long: entry should be ABOVE SL
                    : entryPrice.Value >= input.SlPrice.Value;  // Short: entry should be BELOW SL

                if (slAlreadyCrossed)
                {
                    Logger.LogWarning(
                        "🚫 [Simulation-Veto] SKIPPED: {Symbol} is temporarily unavailable or filtered. Reason: {Side} Entry={Entry} SL={Sl} (SL already crossed).",
                        symbol, input.Side, entryPrice.Value, input.SlPrice.Value);
                    return null;
                }
            }

            // 7. Deduct balance safely
            var profile = await _profileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
            if (profile != null)
            {
                profile.VirtualBalance -= totalCost;
                await _profileRepo.UpdateAsync(profile, autoSave: true);
            }

            // 8. Create trade record
            var trade = new SimulatedTrade(
                id: GuidGenerator.Create(),
                userId: userId,
                symbol: symbol,
                side: input.Side,
                leverage: input.Leverage,
                entryPrice: entryPrice.Value,
                size: size, // Coin quantity
                amount: exposureValue, // Nominal exposure in USDT
                margin: margin,
                liquidationPrice: liquidationPrice,
                entryFee: entryFee,
                tpPrice: input.TpPrice,
                slPrice: input.SlPrice,
                tradingSignalId: input.TradingSignalId,
                exchange: input.Exchange ?? "Binance");

            if (!string.IsNullOrWhiteSpace(input.AgentDecisionJson))
                trade.AgentDecisionJson = input.AgentDecisionJson.Trim();
            
            if (input.StrategyProfileId.HasValue)
                trade.StrategyProfileId = input.StrategyProfileId;
            else
                Logger.LogWarning(
                    "⚠️ [Simulation] OpenTrade for {Symbol} sin AgentDecisionJson — la pantalla de auditoría no podrá mostrar el contexto Nexus/SCAR/LSE para este trade.",
                    symbol);

            if (input.StrategyProfileId.HasValue)
                trade.StrategyProfileId = input.StrategyProfileId;

            // Set MA7 distance at entry for Sniper filter validation
            if (input.Ma7DistancePctAtEntry.HasValue)
                trade.Ma7DistancePctAtEntry = input.Ma7DistancePctAtEntry;

            await _tradeRepo.InsertAsync(trade, autoSave: true);

            var dto = MapToDto(trade);

            // 8. Broadcast new trade to user
            await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeOpened", dto);

            Logger.LogInformation("✅ [Simulation] Trade opened: {Side} {Symbol} x{Leverage} @ {Price} | Margin: {Margin} USDT",
                input.Side, symbol, input.Leverage, entryPrice, margin);

            return dto;
        }
        finally
        {
            TradingSimulationService.ProfileLock.Release();
        }
    }

    /// <summary>
    /// AI-GRADE AUDIT: Update max favorable price (MFE) for a trade.
    /// </summary>
    [HttpPost("api/app/simulated-trade/update-max-favorable-price/{tradeId}")]
    public async Task UpdateMaxFavorablePriceAsync(Guid tradeId, [FromBody] UpdateMaxFavorablePriceInputDto input)
    {
        int maxRetries = 5;
        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                using (var scope = _scopeFactory.CreateScope())
                {
                    var repo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
                    var trade = await repo.GetAsync(tradeId);

                    // Monotonic guard: the mark-price worker already ratchets this every second.
                    // Only accept this push if it's actually more extreme, so a stale/reset value
                    // from the Python agent (e.g. after a restart) can't regress it.
                    bool isMoreFavorable = trade.Side == SignalDirection.Long
                        ? input.MaxFavorablePrice > (trade.MaxFavorablePrice ?? trade.EntryPrice)
                        : input.MaxFavorablePrice < (trade.MaxFavorablePrice ?? trade.EntryPrice);

                    if (!isMoreFavorable)
                    {
                        Logger.LogDebug("[AUDIT] MFE push for trade {TradeId} ignored (not more extreme than tracked {Current})", tradeId, trade.MaxFavorablePrice);
                        break;
                    }

                    trade.MaxFavorablePrice = input.MaxFavorablePrice;
                    await repo.UpdateAsync(trade, autoSave: true);
                    Logger.LogDebug("[AUDIT] MFE updated for trade {TradeId}: {Price}", tradeId, input.MaxFavorablePrice);
                    break;
                }
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency retry {0}/5 for updating MFE on trade {1}", i + 1, tradeId);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
        }
    }

    /// <summary>
    /// AI-GRADE AUDIT: Update exit reason, BTC price at close, and full exit audit block.
    /// </summary>
    [HttpPost("api/app/simulated-trade/update-exit-info/{tradeId}")]
    public async Task UpdateExitInfoAsync(Guid tradeId, [FromBody] UpdateExitInfoInputDto input)
    {
        int maxRetries = 5;
        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                using (var scope = _scopeFactory.CreateScope())
                {
                    var repo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
                    var trade = await repo.GetAsync(tradeId);
                    trade.ExitReason = input.ExitReason;
                    trade.BtcPriceAtClose = input.BtcPriceAtClose;
                    trade.ExitAuditJson = input.ExitAuditJson;
                    await repo.UpdateAsync(trade, autoSave: true);
                    Logger.LogDebug("[AUDIT] Exit info updated for trade {TradeId}: {Reason} | BTC={BTC}", tradeId, input.ExitReason, input.BtcPriceAtClose);
                    break;
                }
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency retry {0}/5 for updating exit info on trade {1}", i + 1, tradeId);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
        }
    }

    public async Task<SimulatedTradeDto> CloseTradeAsync(Guid tradeId)
    {
        var userId = CurrentUser.Id!.Value;
        
        // 1. Resolve current price FIRST (outside the DB lock/retry to keep it fast)
        // Fetch trade symbol once for price resolution (using a one-off scope to avoid tracking)
        string symbol;
        using (var scope = _scopeFactory.CreateScope())
        {
            var tRepo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
            var t = await tRepo.GetAsync(tradeId);
            symbol = t.Symbol;
        }
        
        var closePrice = await ResolveCurrentPriceAsync(symbol)
            ?? throw new UserFriendlyException($"Could not fetch current price for {symbol}.");

        SimulatedTradeDto resultDto = null;
        int maxRetries = 5;

        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                using (var scope = _scopeFactory.CreateScope())
                {
                    var tRepo = scope.ServiceProvider.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
                    var trade = await tRepo.GetAsync(tradeId);

                    if (trade.UserId != userId)
                        throw new UserFriendlyException("You don't have permission to close this trade.");

                    if (trade.Status != TradeStatus.Open)
                    {
                        Logger.LogWarning("⚠️ [Simulation] Trade {TradeId} already closed.", tradeId);
                        return MapToDto(trade);
                    }

                    // ── Sanity guard 2026-07-15: ResolveCurrentPriceAsync falls through
                    // unrelated external sources as a last resort (Binance Spot, Bybit,
                    // OKX) with no cross-validation between tiers. For thin-liquidity or
                    // synthetic symbols (found in prod: ONUSDT/LITUSDT/UBUSDT), one of
                    // those fallbacks can silently return a completely different
                    // instrument's price, closing the trade at a value wildly off from
                    // its own tracked history (one case landed 1000x off). trade.MarkPrice
                    // is continuously ticked every 1s by SimulationMarkPriceWorker, which
                    // already outlier-filters its own updates (2026-07-12 fix) — it's a
                    // trustworthy recent anchor. If the freshly resolved close price
                    // diverges too much from it, trust MarkPrice instead of the resolved
                    // value rather than persisting a fabricated PnL.
                    const decimal maxCloseDeviationRatio = 0.30m;
                    var priceAnchor = trade.MarkPrice > 0 ? trade.MarkPrice : trade.EntryPrice;
                    if (priceAnchor > 0)
                    {
                        var deviation = Math.Abs(closePrice - priceAnchor) / priceAnchor;
                        if (deviation > maxCloseDeviationRatio)
                        {
                            Logger.LogWarning(
                                "⚠️ [Simulation] Resolved close price for {Symbol} diverges {Deviation:P1} from last known price {Anchor} — using {Anchor} instead of resolved {Resolved} (likely bad/unrelated price source).",
                                trade.Symbol, deviation, priceAnchor, priceAnchor, closePrice);
                            closePrice = priceAnchor;
                        }
                    }

                    // 2. Calculate exit fee and realized PnL with the fetched trade data
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

                    // Calculate and save MaxAdversePrice if not already set
                    if (!trade.MaxAdversePrice.HasValue)
                    {
                        // Try to get the real MAE from the Python agent
                        try
                        {
                            using var httpClient = new HttpClient();
                            httpClient.Timeout = TimeSpan.FromSeconds(2);
                            var agentUrl = $"http://127.0.0.1:8002/position/{tradeId}/max-adverse-price";
                            var response = await httpClient.GetAsync(agentUrl);

                            if (response.IsSuccessStatusCode)
                            {
                                var content = await response.Content.ReadAsStringAsync();
                                var agentData = System.Text.Json.JsonDocument.Parse(content);
                                var maxAdv = agentData.RootElement.GetProperty("maxAdversePrice");

                                if (maxAdv.ValueKind != System.Text.Json.JsonValueKind.Null)
                                {
                                    trade.MaxAdversePrice = maxAdv.GetDecimal();
                                    Logger.LogInformation("📉 [Simulation] MaxAdversePrice retrieved from agent for manual close {Symbol}: {Price}",
                                        trade.Symbol, trade.MaxAdversePrice);
                                }
                                else
                                {
                                    Logger.LogWarning("⚠️ [Simulation] Agent returned null MaxAdversePrice for {Symbol}", trade.Symbol);
                                }
                            }
                            else
                            {
                                Logger.LogWarning("⚠️ [Simulation] Failed to get MaxAdversePrice from agent for {Symbol}: {StatusCode}",
                                    trade.Symbol, response.StatusCode);
                            }
                        }
                        catch (Exception ex)
                        {
                            Logger.LogWarning(ex, "⚠️ [Simulation] Error getting MaxAdversePrice from agent for {Symbol}", trade.Symbol);
                        }
                    }

                    await tRepo.UpdateAsync(trade, autoSave: true);
                    
                    // 4. Return margin + entryFee + realizedPnl to user balance
                    var bProfileRepo = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                    var profileToCredit = await bProfileRepo.FirstOrDefaultAsync(p => p.UserId == userId);
                    if (profileToCredit != null)
                    {
                        profileToCredit.VirtualBalance += (trade.Margin + trade.EntryFee + realizedPnl);
                        await bProfileRepo.UpdateAsync(profileToCredit, autoSave: true);
                    }

                    resultDto = MapToDto(trade);
                    
                    Logger.LogInformation("✅ [Simulation] Trade closed in fresh scope: {Symbol} @ {Price} | PnL: {Pnl}",
                        trade.Symbol, closePrice, realizedPnl);
                    
                    break; // Success!
                }
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency retry {0}/5 for closing trade {1}", i + 1, tradeId);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
        }

        if (resultDto != null)
        {
            await _hubContext.Clients.User(userId.ToString()).SendAsync("ReceiveTradeClosed", resultDto);
        }

        return resultDto;
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
    public async Task<SimulationPerformanceDto> GetPerformanceStatsAsync(Guid? strategyProfileId = null)
    {
        var userId = CurrentUser.Id!.Value;
        // Sin límite de cantidad — trae TODOS los trades del usuario, cerrados,
        // sin importar cuántos haya. Fix 2026-07-19: el Historial calculaba
        // estos mismos totales del lado del cliente sobre GetRecentTradesAsync
        // (capado a 1000), y con 1934 trades reales en la cuenta eso cortaba
        // en silencio los más viejos de cualquier estrategia — el "Total
        // Trades"/Win Rate/Ganancia mostrados quedaban incompletos sin que
        // nadie lo notara. Este endpoint agrega TODO del lado del server.
        var trades = await _tradeRepo.GetListAsync(t => t.UserId == userId && t.Status != TradeStatus.Open);

        // Get active strategies to filter trades
        var strategyProfileRepo = LazyServiceProvider.LazyGetRequiredService<IRepository<StrategyProfile, Guid>>();
        var activeStrategies = await strategyProfileRepo.GetListAsync(s => s.UserId == userId && s.IsActive);
        var activeStrategyIds = activeStrategies.Select(s => s.Id).ToHashSet();

        // Filter trades: include trades with no strategy (default) OR trades from active strategies
        var filteredTrades = trades.Where(t =>
            !t.StrategyProfileId.HasValue ||
            t.StrategyProfileId.Value == Guid.Empty ||
            activeStrategyIds.Contains(t.StrategyProfileId.Value)
        ).ToList();

        // Filtro opcional por estrategia puntual (mismo criterio que ya usaba
        // el Historial del lado del cliente: Guid.Empty = "sin estrategia").
        if (strategyProfileId.HasValue)
        {
            var targetId = strategyProfileId.Value;
            filteredTrades = filteredTrades.Where(t =>
                targetId == Guid.Empty
                    ? (!t.StrategyProfileId.HasValue || t.StrategyProfileId.Value == Guid.Empty)
                    : t.StrategyProfileId.HasValue && t.StrategyProfileId.Value == targetId
            ).ToList();
        }

        var stats = new SimulationPerformanceDto();
        if (!filteredTrades.Any())
        {
            stats.EquityCurve.Add(new EquityPointDto { Timestamp = DateTime.UtcNow, Balance = 10000 });
            return stats;
        }

        stats.TotalTrades = filteredTrades.Count;
        stats.TotalGain = filteredTrades.Sum(t => t.RealizedPnl ?? 0);
        var wins = filteredTrades.Count(t => t.Status == TradeStatus.Win);
        stats.WinRate = stats.TotalTrades > 0 ? (decimal)wins / stats.TotalTrades * 100 : 0;
        stats.AvgPerTrade = stats.TotalTrades > 0 ? stats.TotalGain / stats.TotalTrades : 0;

        // Corrected Equity Curve: Initial 10k + cumulative realized PnL
        decimal currentBalance = 10000;
        stats.EquityCurve.Add(new EquityPointDto { Timestamp = filteredTrades.Min(t => t.OpenedAt).AddMinutes(-1), Balance = currentBalance });

        foreach (var trade in filteredTrades.OrderBy(t => t.ClosedAt))
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

    public async Task UpdateMaxAdversePriceAsync(Guid tradeId, UpdateMaxAdversePriceInputDto input)
    {
        var userId = CurrentUser.Id!.Value;

        int maxRetries = 5;
        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                var trade = await _tradeRepo.GetAsync(tradeId);

                if (trade.UserId != userId)
                    throw new UserFriendlyException("You don't have permission to update this trade.");

                // Monotonic guard: the mark-price worker already ratchets this every second.
                // Only accept this push if it's actually more extreme, so a stale/reset value
                // from the Python agent (e.g. after a restart) can't regress it.
                bool isMoreAdverse = trade.Side == SignalDirection.Long
                    ? input.MaxAdversePrice < (trade.MaxAdversePrice ?? trade.EntryPrice)
                    : input.MaxAdversePrice > (trade.MaxAdversePrice ?? trade.EntryPrice);

                if (!isMoreAdverse)
                {
                    Logger.LogDebug("[AUDIT] MAE push for trade {TradeId} ignored (not more extreme than tracked {Current})", tradeId, trade.MaxAdversePrice);
                    return;
                }

                trade.MaxAdversePrice = input.MaxAdversePrice;
                await _tradeRepo.UpdateAsync(trade, autoSave: true);

                Logger.LogInformation("📉 [Simulation] MaxAdversePrice recorded for {Symbol}: {Price}",
                    trade.Symbol, input.MaxAdversePrice);
                return;
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency retry {0}/5 for updating MAE on trade {1}", i + 1, tradeId);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
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
        StrategyProfileId = t.StrategyProfileId,
        MaxAdversePrice = t.MaxAdversePrice,
        MaxFavorablePrice = t.MaxFavorablePrice,
        ExitReason = t.ExitReason,
        Ma7DistancePctAtEntry = t.Ma7DistancePctAtEntry,
        BtcPriceAtClose = t.BtcPriceAtClose,
        ExitAuditJson = t.ExitAuditJson,
        TpProgressPct = t.TpProgressPct,
        MaxTpProgressPct = t.MaxTpProgressPct,
        MaxSlProgressPct = t.MaxSlProgressPct
    };

    /// <summary>
    /// Resolves price EXCLUSIVELY from Binance sources (WebSocket cache → Binance Futures REST → Binance Spot REST).
    /// NEVER falls back to Python multi-exchange or other exchanges.
    /// Used by CloseTradeAsync to ensure manual closes use the same exchange as the original trade.
    /// </summary>
    public async Task<decimal?> ResolveBinancePriceOnlyAsync(string rawSymbol)
    {
        var symbol = NormalizeSymbol(rawSymbol);

        for (int attempt = 0; attempt < 3; attempt++)
        {
            // 1) WebSocket in-memory cache (zero REST calls, sub-millisecond)
            var wsPrice = _marketDataManager.GetWebSocketPrice(symbol);
            if (wsPrice.HasValue && wsPrice.Value > 0)
            {
                Logger.LogInformation("🎯 [BinanceOnly] Price resolved from WebSocket for {Symbol}: {Price}", symbol, wsPrice.Value);
                return wsPrice.Value;
            }

            // 2) Binance Futures REST (if WebSocket hasn't warmed up yet)
            var futures = await TryFetchDirectPriceAsync($"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}");
            if (futures.HasValue && futures.Value > 0)
            {
                Logger.LogInformation("🎯 [BinanceOnly] Price resolved from Binance Futures REST for {Symbol}: {Price}", symbol, futures.Value);
                return futures.Value;
            }

            // 3) Binance Spot REST (last resort within Binance ecosystem)
            var spot = await TryFetchDirectPriceAsync($"https://api.binance.com/api/v3/ticker/price?symbol={symbol}");
            if (spot.HasValue && spot.Value > 0)
            {
                Logger.LogInformation("🎯 [BinanceOnly] Price resolved from Binance Spot REST for {Symbol}: {Price}", symbol, spot.Value);
                return spot.Value;
            }

            // If all Binance sources fail: wait and retry. Do NOT try other exchanges.
            Logger.LogWarning("⏳ [BinanceOnly] No Binance price for {Symbol} on attempt {Attempt}/3. Waiting before retry...", symbol, attempt + 1);
            if (attempt < 2) await Task.Delay(1500);
        }

        Logger.LogError("❌ [BinanceOnly] FAILED to get Binance price for {Symbol} after 3 attempts. Trade will NOT be closed to avoid phantom close.", symbol);
        return null;
    }

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
            var pythonPrice = await TryFetchDirectPriceAsync($"{_marketDataManager.GetPythonBaseUrl()}/market/ticker/{symbol}");
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

            // 5) Dynamic Multi-Exchange Fallbacks (Bybit, OKX)
            // Bybit V5
            var bybit = await TryFetchDirectPriceAsync($"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}");
            if (bybit.HasValue && bybit.Value > 0) return bybit.Value;

            // OKX V5 (Requires instId format)
            var okxSymbol = symbol.Replace("USDT", "-USDT-SWAP");
            var okx = await TryFetchDirectPriceAsync($"https://www.okx.com/api/v5/market/ticker?instId={okxSymbol}");
            if (okx.HasValue && okx.Value > 0) return okx.Value;

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
            var root = doc.RootElement;

            // Helper to get price from a node
            string GetPrice(JsonElement node)
            {
                if (node.TryGetProperty("lastPrice", out var lp)) return lp.GetString();
                if (node.TryGetProperty("last", out var l)) return l.GetString();
                if (node.TryGetProperty("price", out var p)) return p.GetString();
                if (node.TryGetProperty("close", out var c)) 
                {
                    if (c.ValueKind == JsonValueKind.Number) return c.GetDecimal().ToString(CultureInfo.InvariantCulture);
                    return c.GetString();
                }
                return null;
            }

            string priceStr = GetPrice(root);

            // Handle nested structures (OKX uses "data", Bybit uses "result.list")
            if (priceStr == null)
            {
                if (root.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Array && data.GetArrayLength() > 0)
                {
                    priceStr = GetPrice(data[0]);
                }
                else if (root.TryGetProperty("result", out var result) && result.TryGetProperty("list", out var list) && list.ValueKind == JsonValueKind.Array && list.GetArrayLength() > 0)
                {
                    priceStr = GetPrice(list[0]);
                }
            }

            if (decimal.TryParse(priceStr, NumberStyles.Any, CultureInfo.InvariantCulture, out var value) && value > 0)
            {
                return value;
            }
        }
        catch { }
        return null;
    }

    private async Task DeductVirtualBalanceAsync(Guid userId, decimal amount)
    {
        int maxRetries = 5;
        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                // Usamos un nuevo scope para garantizar que leemos la versión más fresca de la DB
                // y no una cacheada en el Unit of Work actual.
                using (var scope = _scopeFactory.CreateScope())
                {
                    var repo = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                    var profile = await repo.FirstOrDefaultAsync(p => p.UserId == userId);
                    if (profile != null)
                    {
                        // v11.12 NO MORE LIES: Ya no bloqueamos por balance virtual.
                        // El balance real de Binance ($4882) es el que manda.
                        // Permitimos balance negativo para tracking contable.
                        Logger.LogInformation(
                            "[BILLETERA-REAL v11.12] Deducting {Amount:N2} USDT from virtual balance. Before: {Before:N2}, After: {After:N2}",
                            amount, profile.VirtualBalance, profile.VirtualBalance - amount);

                        profile.VirtualBalance -= amount;
                        await repo.UpdateAsync(profile, autoSave: true);
                    }
                }
                return;
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency exception in DeductVirtualBalance. Retrying {0}/{1}...", i + 1, maxRetries);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
        }
    }

    private async Task CreditVirtualBalanceAsync(Guid userId, decimal amount)
    {
        int maxRetries = 5;
        for (int i = 0; i < maxRetries; i++)
        {
            await TradingSimulationService.ProfileLock.WaitAsync();
            try
            {
                using (var scope = _scopeFactory.CreateScope())
                {
                    var repo = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
                    var profile = await repo.FirstOrDefaultAsync(p => p.UserId == userId);
                    if (profile != null)
                    {
                        profile.VirtualBalance += amount;
                        await repo.UpdateAsync(profile, autoSave: true);
                    }
                }
                return;
            }
            catch (AbpDbConcurrencyException)
            {
                if (i == maxRetries - 1) throw;
                Logger.LogWarning("[Simulation] Concurrency exception in CreditVirtualBalance. Retrying {0}/{1}...", i + 1, maxRetries);
                await Task.Delay(200);
            }
            finally
            {
                TradingSimulationService.ProfileLock.Release();
            }
        }
    }
}
