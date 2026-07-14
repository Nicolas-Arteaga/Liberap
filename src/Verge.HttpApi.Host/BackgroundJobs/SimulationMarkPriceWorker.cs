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

    // Un solo tick de precio no puede moverse más de esto en 1 segundo real
    // (ya generoso). Sin este filtro, un print corrupto o un flash de un
    // exchange de baja liquidez se tomaba tal cual: cerraba trades a un
    // precio inflado y corrompía para siempre MaxFavorablePrice/MaxTpProgressPct
    // (son ratchets monotónicos — un solo tick malo nunca se corregía solo).
    private const decimal MaxSingleTickMovePct = 0.15m; // 15%
    private static readonly Dictionary<Guid, decimal> _lastGoodPrice = new();

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
                await TradingSimulationService.ProfileLock.WaitAsync();
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

                    // ── Filtro de outlier: un solo tick no puede saltar más de
                    // MaxSingleTickMovePct respecto del último precio válido de
                    // ESTE trade. Si lo hace, es un print corrupto o un flash de
                    // baja liquidez — se descarta y se reintenta el próximo ciclo,
                    // en vez de cerrar el trade o corromper el ratchet con un dato malo.
                    // Se semilla desde trade.MarkPrice (persistido) si el proceso
                    // recién arrancó y no tiene baseline en memoria todavía —
                    // si no, el primer tick tras un restart siempre pasaba gratis.
                    if (!_lastGoodPrice.ContainsKey(trade.Id) && trade.MarkPrice > 0)
                    {
                        _lastGoodPrice[trade.Id] = trade.MarkPrice;
                    }
                    if (_lastGoodPrice.TryGetValue(trade.Id, out var lastGood) && lastGood > 0)
                    {
                        var moveFraction = Math.Abs(markPrice - lastGood) / lastGood;
                        if (moveFraction > MaxSingleTickMovePct)
                        {
                            _logger.LogWarning(
                                "🚫 [SimulationWorker] Tick descartado para {Symbol}: {Old} -> {New} ({Move:P1} en 1 tick, excede {Max:P0}). Probable outlier/flash.",
                                trade.Symbol, lastGood, markPrice, moveFraction, MaxSingleTickMovePct);
                            continue;
                        }
                    }
                    _lastGoodPrice[trade.Id] = markPrice;

                    _logger.LogInformation(
                        "✅ [SimulationWorker] Price for {Symbol}: {Price} (Source: {Source})",
                        trade.Symbol, markPrice, priceSource);

                    trade.MarkPrice = markPrice;

                    // ── MAE/MFE ratchet + TP/SL progress (server-side, monotonic) ──
                    // Runs every tick (1s) independent of the Python agent's process lifetime,
                    // so it survives agent restarts and doesn't depend on a fire-and-forget
                    // sync that only fired once at close time.
                    UpdateExcursionTracking(trade, markPrice);

                    // ── Liquidation check ──────────────────────────────────────────
                    if (simulationService.IsLiquidationTriggered(markPrice, trade.LiquidationPrice, trade.Side))
                    {
                        _logger.LogWarning("💀 [SimulationWorker] LIQUIDATION for {Id} | {Symbol} at {Price}", trade.Id, trade.Symbol, markPrice);
                        trade.Status = TradeStatus.Liquidated;
                        // Clampeado al precio de liquidación exacto, no al tick crudo
                        // que disparó la detección — un gap real no debe inflar/deflar
                        // el registro más allá del nivel mecánico que corresponde.
                        trade.ClosePrice = trade.LiquidationPrice;
                        trade.ClosedAt = DateTime.UtcNow;
                        trade.ExitReason = "liquidated";
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
                        // Clampeado al TpPrice/SlPrice exacto, no al tick crudo que
                        // disparó la detección — un gap o un tick apenas por encima
                        // del umbral no debe inflar/deflar el PnL registrado más allá
                        // de lo que el propio perfil pedía (ver bug de MaxTpProgressPct
                        // >100%, ej. RKLBUSDT/ONUSDT, corregido 2026-07-12).
                        var settlementPrice = closeReason == "Take Profit" ? trade.TpPrice!.Value : trade.SlPrice!.Value;

                        _logger.LogInformation("🎯 [SimulationWorker] {Reason} reached for {Symbol} — tick={Tick}, liquidado a {Price}.", closeReason, trade.Symbol, markPrice, settlementPrice);

                        var exitFee = simulationService.CalculateExitFee(trade.Size, settlementPrice);
                        var pnl = simulationService.CalculateUnrealizedPnl(trade.EntryPrice, settlementPrice, trade.Size, trade.Side);

                        // True NET PnL
                        var realizedPnl = pnl - trade.EntryFee - exitFee - trade.TotalFundingPaid;

                        // Log FEES
                        var totalFee = trade.EntryFee + exitFee;
                        _logger.LogInformation("[FEE] Entry={EntryFee:N4} | Exit={ExitFee:N4} | Total={TotalFee:N4} | Notional={Notional:N4}",
                            trade.EntryFee, exitFee, totalFee, trade.Amount);

                        trade.Status = closeReason == "Take Profit" ? TradeStatus.Win : TradeStatus.Loss;
                        trade.ClosePrice = settlementPrice;
                        trade.ClosedAt = DateTime.UtcNow;
                        trade.ExitReason = closeReason == "Take Profit" ? "tp_hit" : "sl_hit";
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
                finally
                {
                    TradingSimulationService.ProfileLock.Release();
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

    /// <summary>
    /// Updates MaxFavorablePrice/MaxAdversePrice monotonically from the current mark price,
    /// then derives TP/SL progress percentages from them. Entry price is the starting point
    /// for both ratchets so a trade with no ticks yet still reports 0%, not null.
    /// </summary>
    private static void UpdateExcursionTracking(SimulatedTrade trade, decimal markPrice)
    {
        bool isLong = trade.Side == SignalDirection.Long;

        var favorableBaseline = trade.MaxFavorablePrice ?? trade.EntryPrice;
        var adverseBaseline = trade.MaxAdversePrice ?? trade.EntryPrice;

        trade.MaxFavorablePrice = isLong
            ? Math.Max(favorableBaseline, markPrice)
            : Math.Min(favorableBaseline, markPrice);

        trade.MaxAdversePrice = isLong
            ? Math.Min(adverseBaseline, markPrice)
            : Math.Max(adverseBaseline, markPrice);

        if (trade.TpPrice.HasValue)
        {
            var tpRange = isLong
                ? trade.TpPrice.Value - trade.EntryPrice
                : trade.EntryPrice - trade.TpPrice.Value;

            if (tpRange != 0)
            {
                var liveDist = isLong ? markPrice - trade.EntryPrice : trade.EntryPrice - markPrice;
                var peakDist = isLong
                    ? trade.MaxFavorablePrice.Value - trade.EntryPrice
                    : trade.EntryPrice - trade.MaxFavorablePrice.Value;

                // Clampeado a 100: pasado el TP el trade ya debería estar
                // cerrado (ver settlementPrice más arriba) — más de 100% acá
                // es siempre un artefacto de un tick que rompió el TP y el
                // cierre todavía no se procesó ese mismo ciclo, nunca un
                // "avance real" mayor al propio objetivo.
                trade.TpProgressPct = Math.Round(Math.Min(liveDist / tpRange * 100m, 100m), 2);
                trade.MaxTpProgressPct = Math.Round(Math.Min(peakDist / tpRange * 100m, 100m), 2);
            }
        }

        if (trade.SlPrice.HasValue)
        {
            var slRange = isLong
                ? trade.EntryPrice - trade.SlPrice.Value
                : trade.SlPrice.Value - trade.EntryPrice;

            if (slRange != 0)
            {
                var peakAdverseDist = isLong
                    ? trade.EntryPrice - trade.MaxAdversePrice.Value
                    : trade.MaxAdversePrice.Value - trade.EntryPrice;

                trade.MaxSlProgressPct = Math.Round(peakAdverseDist / slRange * 100m, 2);
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
}
