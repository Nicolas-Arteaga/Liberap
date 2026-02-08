using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradeOrderDto : FullAuditedEntityDto<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public decimal Amount { get; set; }
    public int Leverage { get; set; }
    public decimal EntryPrice { get; set; }
    public decimal? ExitPrice { get; set; }
    public decimal TakeProfitPrice { get; set; }
    public decimal StopLossPrice { get; set; }
    public OrderType OrderType { get; set; }
    public TradeStatus Status { get; set; }
    public decimal ProfitLoss { get; set; }
    public DateTime ExecutionDate { get; set; }
    public DateTime? CloseDate { get; set; }
}

public class ExecuteTradeDto
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public decimal Amount { get; set; }
    public int Leverage { get; set; }
    public decimal TakeProfitPercentage { get; set; }
    public decimal StopLossPercentage { get; set; }
    public OrderType OrderType { get; set; }
}
