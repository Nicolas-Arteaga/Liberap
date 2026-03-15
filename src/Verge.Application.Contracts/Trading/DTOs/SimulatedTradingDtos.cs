using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading.DTOs;

public class SimulatedTradeDto : EntityDto<Guid>
{
    public Guid UserId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Side { get; set; }
    public int Leverage { get; set; }
    public decimal Size { get; set; }
    public decimal Amount { get; set; }
    public decimal EntryPrice { get; set; }
    public decimal MarkPrice { get; set; }
    public decimal LiquidationPrice { get; set; }
    public decimal Margin { get; set; }
    public decimal MarginRate { get; set; }
    public decimal UnrealizedPnl { get; set; }
    public decimal ROIPercentage { get; set; }
    public TradeStatus Status { get; set; }
    public decimal? ClosePrice { get; set; }
    public decimal? RealizedPnl { get; set; }
    public decimal EntryFee { get; set; }
    public decimal ExitFee { get; set; }
    public decimal TotalFundingPaid { get; set; }
    public DateTime OpenedAt { get; set; }
    public DateTime? ClosedAt { get; set; }
    public Guid? TradingSignalId { get; set; }
}

public class OpenTradeInputDto
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Side { get; set; }
    public decimal Amount { get; set; } // In USDT
    public int Leverage { get; set; }
    public Guid? TradingSignalId { get; set; }
}

public class CloseTradeInputDto
{
    public Guid TradeId { get; set; }
}

public class SimulationPerformanceDto
{
    public decimal TotalGain { get; set; }
    public decimal WinRate { get; set; }
    public int TotalTrades { get; set; }
    public decimal AvgPerTrade { get; set; }
    public List<EquityPointDto> EquityCurve { get; set; } = new();
}

public class EquityPointDto
{
    public DateTime Timestamp { get; set; }
    public decimal Balance { get; set; }
}
