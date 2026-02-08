using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradingSignal : FullAuditedAggregateRoot<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public decimal? TargetPrice { get; set; }
    public decimal? StopLossPrice { get; set; }
    public SignalConfidence Confidence { get; set; }
    public decimal ProfitPotential { get; set; }
    public DateTime AnalyzedDate { get; set; }
    public TradeStatus Status { get; set; }

    protected TradingSignal() { }

    public TradingSignal(Guid id, string symbol, SignalDirection direction, decimal entryPrice, SignalConfidence confidence, decimal profitPotential)
        : base(id)
    {
        Symbol = symbol;
        Direction = direction;
        EntryPrice = entryPrice;
        Confidence = confidence;
        ProfitPotential = profitPotential;
        AnalyzedDate = DateTime.UtcNow;
        Status = TradeStatus.Open;
    }
}
