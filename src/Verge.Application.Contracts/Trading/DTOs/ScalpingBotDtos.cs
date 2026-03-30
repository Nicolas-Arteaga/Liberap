using System;
using System.Collections.Generic;

namespace Verge.Trading.Bot;

// ─────────────────────────────────────────────────────────────────────────────
// DTOs DE ESTADO DEL BOT
// ─────────────────────────────────────────────────────────────────────────────

/// <summary>Estado completo del bot para el panel Angular.</summary>
public class ScalpingBotStatusDto
{
    public bool IsRunning { get; set; }
    public ScalpingBotConfigDto Config { get; set; } = new();
    public int OpenPositions { get; set; }
    public int MaxPositions { get; set; }
    public decimal DailyPnl { get; set; }
    public int DailyTrades { get; set; }
    public int DailyWins { get; set; }
    public int DailyLosses { get; set; }
    public double DailyWinRate => DailyTrades > 0 ? (double)DailyWins / DailyTrades * 100 : 0;
    public List<string> ActiveSymbols { get; set; } = new();
    public DateTime? LastCycleAt { get; set; }
    public List<BotTradeDto> OpenTrades { get; set; } = new();
    public List<BotActivityLogDto> RecentLogs { get; set; } = new();
}

/// <summary>Configuración editable desde el panel Angular.</summary>
public class ScalpingBotConfigDto
{
    public bool Enabled { get; set; } = false;
    public string Timeframe { get; set; } = "5";
    public bool DynamicSymbols { get; set; } = true;
    public int TopSymbolsCount { get; set; } = 10;
    public List<string> WhitelistSymbols { get; set; } = new();
    public List<string> BlacklistSymbols { get; set; } = new();
    public decimal RiskPercent { get; set; } = 1.0m;
    public int MinScore { get; set; } = 70;
    public int MaxOpenPositions { get; set; } = 5;
    public int MinLeverage { get; set; } = 8;
    public int MaxLeverage { get; set; } = 20;
    public decimal PartialCloseRR { get; set; } = 1.5m;
    public decimal FinalTpRR { get; set; } = 2.5m;
    public bool AllowQuietPeriodTrading { get; set; } = true;
    public bool RequireTrendConfirmation { get; set; } = false;
    public string BotName { get; set; } = "VERGE Scalper 5m";
}

// ─────────────────────────────────────────────────────────────────────────────
// DTOs DE TRADES DEL BOT
// ─────────────────────────────────────────────────────────────────────────────

/// <summary>Trade del bot para el panel (lista de posiciones abiertas e historial).</summary>
public class BotTradeDto
{
    public Guid Id { get; set; }
    public Guid UserId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string Direction { get; set; } = string.Empty;
    public string Timeframe { get; set; } = "5";

    // Precios
    public decimal EntryPrice { get; set; }
    public decimal StopLoss { get; set; }
    public decimal TakeProfit1 { get; set; }
    public decimal TakeProfit2 { get; set; }
    public decimal? TrailingStopPrice { get; set; }

    // Posición
    public int Leverage { get; set; }
    public decimal Margin { get; set; }
    public decimal PositionSize { get; set; }

    // Estado
    public string Status { get; set; } = "Open";
    public bool PartialCloseDone { get; set; }
    public bool TrailingActive { get; set; }

    // PnL
    public decimal? PartialPnl { get; set; }
    public decimal? FinalPnl { get; set; }
    public decimal? TotalPnl { get; set; }
    public string? CloseReason { get; set; }

    // Metadata
    public decimal ATR { get; set; }
    public decimal ATRPercent { get; set; }
    public decimal SLPercent { get; set; }
    public int ScannerScore { get; set; }

    // Tiempos
    public DateTime OpenedAt { get; set; }
    public DateTime? PartialClosedAt { get; set; }
    public DateTime? ClosedAt { get; set; }
    public int? DurationMinutes => ClosedAt.HasValue
        ? (int)(ClosedAt.Value - OpenedAt).TotalMinutes
        : (int)(DateTime.UtcNow - OpenedAt).TotalMinutes;

    // FK
    public Guid SimulatedTradeId { get; set; }
}

// ─────────────────────────────────────────────────────────────────────────────
// DTOs DE BACKTESTING DEL BOT
// ─────────────────────────────────────────────────────────────────────────────

public class BotBacktestInputDto
{
    public string Symbol { get; set; } = "BTCUSDT";
    public int Days { get; set; } = 30;
    public string Timeframe { get; set; } = "5";
    public int Leverage { get; set; } = 12;
    public decimal RiskPercent { get; set; } = 1.0m;
    public int MinScore { get; set; } = 70;
    public bool RequireTrendConfirmation { get; set; } = false;
}

public class BotBacktestResultDto
{
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = "5";
    public int Days { get; set; }
    public int TotalTrades { get; set; }
    public int Wins { get; set; }
    public int Losses { get; set; }
    public double WinRate { get; set; }
    public decimal TotalPnl { get; set; }
    public decimal MaxDrawdown { get; set; }
    public double ProfitFactor { get; set; }
    public double TradesPerDay { get; set; }
    public decimal BestDay { get; set; }
    public decimal WorstDay { get; set; }
    public List<BotEquityPointDto> EquityCurve { get; set; } = new();
}

public class BotEquityPointDto
{
    public DateTime Time { get; set; }
    public decimal Balance { get; set; }
    public decimal PnL { get; set; }
}
