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
using Verge.Trading.Bot;
using Verge.Trading.DTOs;
using Verge.Trading.Integrations;

namespace Verge.Trading;

/// <summary>
/// Hosted Service de monitoreo de posiciones abiertas.
/// 
/// Loop: cada 30 segundos (agresivo — reacciona rápido a movimientos).
/// Por cada BotTrade abierto:
///   1. Obtiene precio live desde BinanceWebSocketService (ZERO REST CALLS)
///   2. Verifica Stop Loss → cierra todo si se toca
///   3. Verifica TP1 → cierra 50% y activa trailing
///   4. Actualiza trailing stop siguiendo el HMA50 en tiempo real
///   5. Verifica TP2 → cierra el 50% restante
/// 
/// Optimización de CPU: usa precio del WebSocket en memoria,
/// recalcula HMA50 solo si el trailing está activo.
/// </summary>
public class BotPositionMonitorService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IBotStateService _botState;
    private readonly ILogger<BotPositionMonitorService> _logger;

    // Cache de HMA50 por símbolo para evitar recálculo en cada tick
    // Se actualiza cada vez que se recalcula
    private readonly Dictionary<string, (decimal Value, DateTime CachedAt)> _hma50Cache = new();
    private const int HMA50CacheSeconds = 60; // Recalcular máximo cada 1 minuto

    public BotPositionMonitorService(
        IServiceProvider serviceProvider,
        IBotStateService botState,
        ILogger<BotPositionMonitorService> logger)
    {
        _serviceProvider = serviceProvider;
        _botState = botState;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("👁️ [PositionMonitor] Service started. Monitoring every 30s.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (_botState.IsRunning)
                {
                    await MonitorOpenPositionsAsync(stoppingToken);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ [PositionMonitor] Error in monitoring cycle");
            }

            try 
            {
                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
            }
            catch (TaskCanceledException)
            {
                break;
            }
        }
    }

    private async Task MonitorOpenPositionsAsync(CancellationToken ct)
    {
        using var scope = _serviceProvider.CreateScope();
        var sp = scope.ServiceProvider;

        var botTradeRepo    = sp.GetRequiredService<IRepository<BotTrade, Guid>>();
        var simTradeRepo    = sp.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
        var profileRepo     = sp.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var webSocket       = sp.GetRequiredService<BinanceWebSocketService>();
        var marketDataMgr   = sp.GetRequiredService<MarketDataManager>();
        var simService      = sp.GetRequiredService<TradingSimulationService>();
        var uowManager      = sp.GetRequiredService<IUnitOfWorkManager>();
        var hubContext      = sp.GetRequiredService<IHubContext<TradingHub>>();

        // Cargar todos los BotTrades abiertos (Open o PartialClose)
        var openTrades = await botTradeRepo.GetListAsync(bt =>
            bt.Status == BotTradeStatus.Open || bt.Status == BotTradeStatus.PartialClose);

        if (!openTrades.Any()) return;

        _logger.LogDebug("👁️ [PositionMonitor] Monitoreando {Count} posiciones abiertas", openTrades.Count);

        foreach (var bt in openTrades)
        {
            if (ct.IsCancellationRequested) break;

            try
            {
                // ─── 1. Precio live desde WebSocket ───
                var markPrice = webSocket.GetLastPrice(bt.Symbol);
                if (markPrice == null || markPrice <= 0) continue;

                bool isLong = bt.Direction == SignalDirection.Long;

                // ─── 2. UPDATE UnrealizedPnL del SimulatedTrade (visual en el panel) ───
                await UpdateUnrealizedPnlAsync(simTradeRepo, uowManager, bt.SimulatedTradeId, markPrice.Value, simService);

                // ─── 3. STOP LOSS ───
                bool slTriggered = isLong
                    ? markPrice <= bt.StopLoss
                    : markPrice >= bt.StopLoss;

                if (slTriggered)
                {
                    _logger.LogWarning("🛑 [PositionMonitor] STOP LOSS: {Symbol} @ {Price} (SL: {SL})",
                        bt.Symbol, markPrice, bt.StopLoss);
                    await CloseFullPositionAsync(bt, markPrice.Value, "StopLoss",
                        simTradeRepo, profileRepo, botTradeRepo, uowManager, hubContext, simService);
                    continue;
                }

                // ─── 4. TAKE PROFIT 1 (cierre parcial 50%) ───
                if (!bt.PartialCloseDone)
                {
                    bool tp1Triggered = isLong
                        ? markPrice >= bt.TakeProfit1
                        : markPrice <= bt.TakeProfit1;

                    if (tp1Triggered)
                    {
                        _logger.LogInformation("🎯 [PositionMonitor] TP1 PARCIAL: {Symbol} @ {Price} (TP1: {TP1})",
                            bt.Symbol, markPrice, bt.TakeProfit1);
                        await ClosePartialPositionAsync(bt, markPrice.Value,
                            simTradeRepo, profileRepo, botTradeRepo, uowManager,
                            hubContext, simService, marketDataMgr);
                        continue;
                    }
                }

                // ─── 5. TRAILING STOP (activo después del cierre parcial) ───
                if (bt.TrailingActive)
                {
                    // Obtener HMA50 (desde cache o recalcular)
                    var hma50 = await GetHMA50CachedAsync(bt.Symbol, marketDataMgr, bt.Timeframe);
                    if (hma50 > 0)
                    {
                        // El trailing SL sigue al HMA50 con un buffer del 0.2%
                        decimal trailBuffer = hma50 * 0.002m;
                        decimal newTrailSL = isLong
                            ? hma50 - trailBuffer   // Longs: trailing debajo del HMA50
                            : hma50 + trailBuffer;  // Shorts: trailing encima del HMA50

                        // Solo mover el trailing en la dirección favorable (no lo bajamos)
                        bool shouldUpdate = isLong
                            ? (bt.TrailingStopPrice == null || newTrailSL > bt.TrailingStopPrice)
                            : (bt.TrailingStopPrice == null || newTrailSL < bt.TrailingStopPrice);

                        if (shouldUpdate)
                        {
                            bt.UpdateTrailingStop(newTrailSL);
                            await botTradeRepo.UpdateAsync(bt);
                        }

                        // ¿El precio violó el trailing stop?
                        bool trailHit = isLong
                            ? markPrice <= bt.TrailingStopPrice
                            : markPrice >= bt.TrailingStopPrice;

                        if (trailHit)
                        {
                            _logger.LogInformation("📈 [PositionMonitor] TRAILING STOP: {Symbol} @ {Price} (Trail: {Trail})",
                                bt.Symbol, markPrice, bt.TrailingStopPrice);
                            await CloseRemainingPositionAsync(bt, markPrice.Value, "TrailingStop",
                            simTradeRepo, profileRepo, botTradeRepo, uowManager,
                            hubContext, simService);
                            continue;
                        }
                    }
                }

                // ─── 6. TAKE PROFIT 2 (cierre total) ───
                bool tp2Triggered = isLong
                    ? markPrice >= bt.TakeProfit2
                    : markPrice <= bt.TakeProfit2;

                if (tp2Triggered)
                {
                    _logger.LogInformation("🏆 [PositionMonitor] TP2 FINAL: {Symbol} @ {Price}", bt.Symbol, markPrice);
                    await CloseRemainingPositionAsync(bt, markPrice.Value, "TakeProfit2",
                    simTradeRepo, profileRepo, botTradeRepo, uowManager,
                    hubContext, simService);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "⚠️ [PositionMonitor] Error procesando {Symbol}", bt.Symbol);
            }
        }
    }

    // ─────────────────────────────────────────────────────────
    // HELPERS DE CIERRE
    // ─────────────────────────────────────────────────────────

    /// <summary>Cierra el 100% de la posición (stop loss o entrada directa al TP2).</summary>
    private async Task CloseFullPositionAsync(
        BotTrade bt, decimal closePrice, string reason,
        IRepository<SimulatedTrade, Guid> simTradeRepo,
        IRepository<TraderProfile, Guid> profileRepo,
        IRepository<BotTrade, Guid> botTradeRepo,
        IUnitOfWorkManager uowManager,
        IHubContext<TradingHub> hubContext,
        TradingSimulationService simService)
    {
        using var uow = uowManager.Begin(requiresNew: true);

        var simTrade = await simTradeRepo.FindAsync(bt.SimulatedTradeId);
        if (simTrade == null || simTrade.Status != TradeStatus.Open)
        {
            await uow.RollbackAsync();
            return;
        }

        var profile = await profileRepo.FirstOrDefaultAsync(p => p.UserId == bt.UserId);
        if (profile == null) { await uow.RollbackAsync(); return; }

        var exitFee = simService.CalculateExitFee(simTrade.Size, closePrice);
        var realizedPnl = simService.CalculateRealizedPnl(
            simTrade.EntryPrice, closePrice, simTrade.Size,
            simTrade.Side, simTrade.EntryFee, exitFee, simTrade.TotalFundingPaid);

        // Actualizar SimulatedTrade
        simTrade.Status      = realizedPnl >= 0 ? TradeStatus.Win : TradeStatus.Loss;
        simTrade.ClosePrice  = closePrice;
        simTrade.RealizedPnl = realizedPnl;
        simTrade.ExitFee     = exitFee;
        simTrade.ClosedAt    = DateTime.UtcNow;
        simTrade.UnrealizedPnl = 0;
        await simTradeRepo.UpdateAsync(simTrade);

        // Devolver margin + pnl al balance
        profile.VirtualBalance += simTrade.Margin + realizedPnl;

        // Actualizar BotTrade
        bt.RegisterClose(realizedPnl, reason);
        await botTradeRepo.UpdateAsync(bt);

        await uow.CompleteAsync();

        _botState.RegisterClose(bt.Symbol);
        _botState.AddDailyPnl(realizedPnl);

        // Notificaciones estándar para el Dashboard
        var simDto = new SimulatedTradeDto
        {
            Id = simTrade.Id,
            UserId = bt.UserId,
            Symbol = bt.Symbol,
            Status = simTrade.Status,
            ClosePrice = closePrice,
            RealizedPnl = realizedPnl,
            ClosedAt = simTrade.ClosedAt,
            // ... otros campos si el Dashboard los necesita para el "ReceiveTradeClosed"
        };
        await hubContext.Clients.User(bt.UserId.ToString()).SendAsync("ReceiveTradeClosed", simDto);

        // Notificación específica para el panel del Bot
        await hubContext.Clients.All.SendAsync("BotTradeClosed", new {
            botTradeId  = bt.Id,
            symbol      = bt.Symbol,
            closePrice,
            realizedPnl,
            reason,
            totalPnl    = bt.TotalPnl,
            dailyPnl    = _botState.DailyPnl
        });

    }

    /// <summary>Cierra el 50% de la posición al alcanzar TP1 y activa el trailing.</summary>
    private async Task ClosePartialPositionAsync(
        BotTrade bt, decimal closePrice,
        IRepository<SimulatedTrade, Guid> simTradeRepo,
        IRepository<TraderProfile, Guid> profileRepo,
        IRepository<BotTrade, Guid> botTradeRepo,
        IUnitOfWorkManager uowManager,
        IHubContext<TradingHub> hubContext,
        TradingSimulationService simService,
        MarketDataManager marketDataMgr)
    {
        using var uow = uowManager.Begin(requiresNew: true);

        var simTrade = await simTradeRepo.FindAsync(bt.SimulatedTradeId);
        if (simTrade == null || simTrade.Status != TradeStatus.Open)
        {
            await uow.RollbackAsync();
            return;
        }

        var profile = await profileRepo.FirstOrDefaultAsync(p => p.UserId == bt.UserId);
        if (profile == null) { await uow.RollbackAsync(); return; }

        // PnL del 50% cerrado
        decimal halfSize = simTrade.Size * 0.5m;
        decimal exitFee  = simService.CalculateExitFee(halfSize, closePrice);
        bool isLong      = bt.Direction == SignalDirection.Long;
        decimal grossPnl = isLong
            ? (closePrice - bt.EntryPrice) * halfSize
            : (bt.EntryPrice - closePrice) * halfSize;
        decimal partialPnl = grossPnl - exitFee;

        // Reducir tamaño del SimulatedTrade (actualizar size)
        simTrade.Size    *= 0.5m;
        simTrade.Amount  *= 0.5m;
        simTrade.Margin  *= 0.5m;
        await simTradeRepo.UpdateAsync(simTrade);

        // Devolver la mitad del margin + pnl parcial
        profile.VirtualBalance += (bt.Margin * 0.5m) + partialPnl;

        // Calcular trailing inicial (HMA50)
        var hma50 = await GetHMA50CachedAsync(bt.Symbol, marketDataMgr, bt.Timeframe);
        decimal trailBuffer = hma50 > 0 ? hma50 * 0.002m : closePrice * 0.005m;
        decimal initialTrail = isLong ? hma50 - trailBuffer : hma50 + trailBuffer;

        bt.RegisterPartialClose(partialPnl, initialTrail);
        await botTradeRepo.UpdateAsync(bt);

        await uow.CompleteAsync();

        _botState.AddDailyPnl(partialPnl);

        await hubContext.Clients.User(bt.UserId.ToString()).SendAsync("ReceiveTradePartialClose", new {
            tradeId       = simTrade.Id,
            symbol        = bt.Symbol,
            closePrice,
            partialPnl,
            newSize       = simTrade.Size
        });

        await hubContext.Clients.All.SendAsync("BotTradePartialClose", new {
            botTradeId    = bt.Id,
            symbol        = bt.Symbol,
            closePrice,
            partialPnl,
            trailingStart = initialTrail
        });
    }

    /// <summary>Cierra el 50% restante (trailing o TP2).</summary>
    private async Task CloseRemainingPositionAsync(
        BotTrade bt, decimal closePrice, string reason,
        IRepository<SimulatedTrade, Guid> simTradeRepo,
        IRepository<TraderProfile, Guid> profileRepo,
        IRepository<BotTrade, Guid> botTradeRepo,
        IUnitOfWorkManager uowManager,
        IHubContext<TradingHub> hubContext,
        TradingSimulationService simService)
    {
        await CloseFullPositionAsync(bt, closePrice, reason,
            simTradeRepo, profileRepo, botTradeRepo, uowManager,
            hubContext, simService);
    }

    /// <summary>Actualiza el UnrealizedPnL del SimulatedTrade para mostrar en el panel.</summary>
    private async Task UpdateUnrealizedPnlAsync(
        IRepository<SimulatedTrade, Guid> simTradeRepo,
        IUnitOfWorkManager uowManager,
        Guid simTradeId, decimal markPrice,
        TradingSimulationService simService)
    {
        try
        {
            var simTrade = await simTradeRepo.FindAsync(simTradeId);
            if (simTrade == null || simTrade.Status != TradeStatus.Open) return;

            simTrade.MarkPrice = markPrice;
            simTrade.UnrealizedPnl = simService.CalculateUnrealizedPnl(
                simTrade.EntryPrice, markPrice, simTrade.Size, simTrade.Side);
            simTrade.ROIPercentage = simTrade.Margin > 0
                ? simTrade.UnrealizedPnl / simTrade.Margin * 100m
                : 0;

            await simTradeRepo.UpdateAsync(simTrade);
        }
        catch { /* No crítico */ }
    }

    /// <summary>
    /// Obtiene el HMA50 desde caché o lo recalcula.
    /// Cache de 60 segundos por símbolo para no saturar MarketDataManager.
    /// </summary>
    private async Task<decimal> GetHMA50CachedAsync(
        string symbol, MarketDataManager marketDataMgr, string timeframe)
    {
        if (_hma50Cache.TryGetValue(symbol, out var cached) &&
            (DateTime.UtcNow - cached.CachedAt).TotalSeconds < HMA50CacheSeconds)
        {
            return cached.Value;
        }

        try
        {
            var candles = await marketDataMgr.GetCandlesAsync(symbol, timeframe, 120);
            if (candles == null || candles.Count < 60) return 0;

            var closes = candles.Select(c => c.Close).ToList();
            var hma50  = IndicatorCalculator.HMA(closes, 50);

            _hma50Cache[symbol] = (hma50, DateTime.UtcNow);
            return hma50;
        }
        catch
        {
            return 0;
        }
    }
}
