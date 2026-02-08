using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradeOrder : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Symbol { get; set; }
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

    protected TradeOrder() { }

    public TradeOrder(Guid id, Guid traderProfileId, string symbol, SignalDirection direction, decimal amount, int leverage, decimal entryPrice)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        Symbol = symbol;
        Direction = direction;
        Amount = amount;
        Leverage = leverage;
        EntryPrice = entryPrice;
        ExecutionDate = DateTime.UtcNow;
        Status = TradeStatus.Open;
    }
}
