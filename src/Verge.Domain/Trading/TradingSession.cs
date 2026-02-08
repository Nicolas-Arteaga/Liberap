using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradingSession : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public TradingStage CurrentStage { get; set; }
    public DateTime StartTime { get; set; }
    public DateTime? EndTime { get; set; }
    public bool IsActive { get; set; }

    protected TradingSession() { }

    public TradingSession(Guid id, Guid traderProfileId, string symbol, string timeframe)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        Symbol = symbol;
        Timeframe = timeframe;
        CurrentStage = TradingStage.Evaluating;
        StartTime = DateTime.UtcNow;
        IsActive = true;
    }
}
