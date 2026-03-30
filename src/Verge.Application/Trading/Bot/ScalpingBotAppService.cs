using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Volo.Abp;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Verge.Trading.Bot;

namespace Verge.Trading;

/// <summary>
/// Application Service para el panel de control del bot en Angular.
/// Expone start/stop, configuración en caliente, estado en vivo, 
/// historial de trades y backtesting.
/// </summary>
public class ScalpingBotAppService : ApplicationService, IScalpingBotAppService
{
    private readonly IBotStateService _botState;
    private readonly IRepository<BotTrade, Guid> _botTradeRepo;
    private readonly ILogger<ScalpingBotAppService> _logger;

    public ScalpingBotAppService(
        IBotStateService botState,
        IRepository<BotTrade, Guid> botTradeRepo,
        ILogger<ScalpingBotAppService> logger)
    {
        _botState     = botState;
        _botTradeRepo = botTradeRepo;
        _logger       = logger;
    }

    /// <summary>Inicia el bot. Persiste el estado en Redis.</summary>
    public async Task StartBotAsync()
    {
        if (_botState.IsRunning)
            throw new UserFriendlyException("El bot ya está corriendo.");

        await _botState.StartAsync(CurrentUser.Id);
        _logger.LogInformation("🟢 [Bot Panel] Bot iniciado por usuario {User}", CurrentUser.UserName);
    }

    /// <summary>Detiene el bot. Las posiciones abiertas se siguen monitoreando hasta cerrar.</summary>
    public async Task StopBotAsync()
    {
        if (!_botState.IsRunning)
            throw new UserFriendlyException("El bot ya está detenido.");

        await _botState.StopAsync();
        _logger.LogInformation("🔴 [Bot Panel] Bot detenido por usuario {User}", CurrentUser.UserName);
    }

    /// <summary>Retorna el estado completo del bot para el panel Angular.</summary>
    public async Task<ScalpingBotStatusDto> GetStatusAsync()
    {
        var config     = _botState.GetConfig();
        var openTrades = await _botTradeRepo.GetListAsync(bt =>
            bt.Status == BotTradeStatus.Open || bt.Status == BotTradeStatus.PartialClose);

        return new ScalpingBotStatusDto
        {
            IsRunning      = _botState.IsRunning,
            Config         = MapConfig(config),
            OpenPositions  = _botState.GetOpenPositionCount(),
            MaxPositions   = config.MaxOpenPositions,
            DailyPnl       = _botState.DailyPnl,
            DailyTrades    = _botState.DailyTradeCount,
            DailyWins      = _botState.DailyWins,
            DailyLosses    = _botState.DailyLosses,
            ActiveSymbols  = _botState.GetActiveSymbols(),
            LastCycleAt    = _botState.LastCycleAt,
            OpenTrades     = openTrades.Select(MapTrade).ToList(),
            RecentLogs     = await _botState.GetRecentLogsAsync()
        };
    }

    /// <summary>Actualiza la configuración del bot en caliente (sin reiniciar).</summary>
    public async Task UpdateConfigAsync(ScalpingBotConfigDto input)
    {
        var config = new ScalpingConfig
        {
            Enabled                   = input.Enabled,
            Timeframe                 = input.Timeframe,
            DynamicSymbols            = input.DynamicSymbols,
            TopSymbolsCount           = Math.Clamp(input.TopSymbolsCount, 3, 20),
            WhitelistSymbols          = input.WhitelistSymbols ?? new(),
            BlacklistSymbols          = input.BlacklistSymbols ?? new(),
            RiskPercent               = Math.Clamp(input.RiskPercent, 0.1m, 3.0m),
            MinScore                  = Math.Clamp(input.MinScore, 10, 100),
            MaxOpenPositions          = Math.Clamp(input.MaxOpenPositions, 1, 10),
            MinLeverage               = Math.Clamp(input.MinLeverage, 1, 20),
            MaxLeverage               = Math.Clamp(input.MaxLeverage, 1, 20),
            PartialCloseRR            = Math.Clamp(input.PartialCloseRR, 1.0m, 3.0m),
            FinalTpRR                 = Math.Clamp(input.FinalTpRR, 1.5m, 5.0m),
            AllowQuietPeriodTrading   = input.AllowQuietPeriodTrading,
            RequireTrendConfirmation  = input.RequireTrendConfirmation,
            BotName                   = input.BotName ?? "VERGE Scalper"
        };

        await _botState.UpdateConfigAsync(config);
        await _botState.UpdateCreatorUserIdAsync(CurrentUser.Id);
        _logger.LogInformation("⚙️ [Bot Panel] Config actualizada por {User}", CurrentUser.UserName);
    }

    /// <summary>Retorna el historial de trades del bot (últimos N).</summary>
    public async Task<List<BotTradeDto>> GetTradesAsync(int limit = 50)
    {
        var trades = await _botTradeRepo.GetListAsync(_ => true);
        return trades
            .OrderByDescending(t => t.OpenedAt)
            .Take(limit)
            .Select(MapTrade)
            .ToList();
    }

    /// <summary>Cancela manualmente una posición abierta del bot.</summary>
    public async Task CancelTradeAsync(Guid botTradeId)
    {
        var trade = await _botTradeRepo.GetAsync(botTradeId);
        if (trade.Status != BotTradeStatus.Open && trade.Status != BotTradeStatus.PartialClose)
            throw new UserFriendlyException("Este trade ya no está abierto.");

        trade.Status      = BotTradeStatus.Cancelled;
        trade.CloseReason = "ManualCancel";
        trade.ClosedAt    = DateTime.UtcNow;
        await _botTradeRepo.UpdateAsync(trade, autoSave: true);

        _botState.RegisterClose(trade.Symbol);
        _logger.LogInformation("🚫 [Bot Panel] Trade {Id} cancelado manualmente por {User}",
            botTradeId, CurrentUser.UserName);
    }

    /// <summary>Retorna equity curve del día del bot.</summary>
    public async Task<List<BotEquityPointDto>> GetEquityCurveAsync()
    {
        var today = DateTime.UtcNow.Date;
        var trades = await _botTradeRepo.GetListAsync(bt =>
            bt.ClosedAt.HasValue && bt.ClosedAt.Value >= today);

        decimal balance = 10000m; // Balance inicial del día
        var points = new List<BotEquityPointDto>
        {
            new() { Time = today, Balance = balance, PnL = 0 }
        };

        foreach (var t in trades.OrderBy(t => t.ClosedAt))
        {
            balance += (t.TotalPnl ?? 0);
            points.Add(new BotEquityPointDto
            {
                Time    = t.ClosedAt ?? t.OpenedAt,
                Balance = balance,
                PnL     = t.TotalPnl ?? 0
            });
        }

        return points;
    }

    // ─── Mappers ───

    private static ScalpingBotConfigDto MapConfig(ScalpingConfig c) => new()
    {
        Enabled                   = c.Enabled,
        Timeframe                 = c.Timeframe,
        DynamicSymbols            = c.DynamicSymbols,
        TopSymbolsCount           = c.TopSymbolsCount,
        WhitelistSymbols          = c.WhitelistSymbols,
        BlacklistSymbols          = c.BlacklistSymbols,
        RiskPercent               = c.RiskPercent,
        MinScore                  = c.MinScore,
        MaxOpenPositions          = c.MaxOpenPositions,
        MinLeverage               = c.MinLeverage,
        MaxLeverage               = c.MaxLeverage,
        PartialCloseRR            = c.PartialCloseRR,
        FinalTpRR                 = c.FinalTpRR,
        AllowQuietPeriodTrading   = c.AllowQuietPeriodTrading,
        RequireTrendConfirmation  = c.RequireTrendConfirmation,
        BotName                   = c.BotName
    };

    private static BotTradeDto MapTrade(BotTrade t) => new()
    {
        Id                = t.Id,
        UserId            = t.UserId,
        Symbol            = t.Symbol,
        Direction         = t.Direction.ToString(),
        Timeframe         = t.Timeframe,
        EntryPrice        = t.EntryPrice,
        StopLoss          = t.StopLoss,
        TakeProfit1       = t.TakeProfit1,
        TakeProfit2       = t.TakeProfit2,
        TrailingStopPrice = t.TrailingStopPrice,
        Leverage          = t.Leverage,
        Margin            = t.Margin,
        PositionSize      = t.PositionSize,
        Status            = t.Status.ToString(),
        PartialCloseDone  = t.PartialCloseDone,
        TrailingActive    = t.TrailingActive,
        PartialPnl        = t.PartialPnl,
        FinalPnl          = t.FinalPnl,
        TotalPnl          = t.TotalPnl,
        CloseReason       = t.CloseReason,
        ATR               = t.ATR,
        ATRPercent        = t.ATRPercent,
        SLPercent         = t.SLPercent,
        ScannerScore      = t.ScannerScore,
        OpenedAt          = t.OpenedAt,
        PartialClosedAt   = t.PartialClosedAt,
        ClosedAt          = t.ClosedAt,
        SimulatedTradeId  = t.SimulatedTradeId
    };
}
