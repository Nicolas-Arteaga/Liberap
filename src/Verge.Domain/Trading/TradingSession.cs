using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradingSession : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
    public TradingStage CurrentStage { get; set; }
    public DateTime StartTime { get; set; }
    public DateTime? EndTime { get; set; }
    public bool IsActive { get; set; }
    public decimal? EntryPrice { get; set; }
    public decimal? TakeProfitPrice { get; set; }
    public decimal? StopLossPrice { get; set; }
    public string? EvaluationHistoryJson { get; set; } // Circular buffer of last N evaluations
    
    public TradingStyle? SelectedStyle { get; set; }
    public SignalDirection? SelectedDirection { get; set; }
    
    public decimal? NetProfit { get; set; }
    public TradeStatus? Outcome { get; set; }
    public string? ExitReason { get; set; }
    public long? LastEvaluationTimestamp { get; set; }
    public DateTime? StageChangedTimestamp { get; set; }

    // Pro Trade Management (Sprint 3)
    public decimal? TrailingStopPrice { get; set; }
    public bool IsBreakEvenActive { get; set; } = false;
    public int PartialTpsCount { get; set; } = 0;
    public decimal? InitialStopLoss { get; set; }
    public decimal CurrentInvestment { get; set; }

    // Feedback Loop (Sprint 4)
    public int? InitialScore { get; set; }
    public MarketRegimeType? InitialRegime { get; set; }
    public SignalConfidence? InitialConfidence { get; set; }
    public decimal? InitialVolatility { get; set; }
    public decimal? InitialVolumeMcapRatio { get; set; }
    public int? EntryHour { get; set; }
    public DayOfWeek? EntryDayOfWeek { get; set; }

    // Institutional (Sprint 5)
    public double? WhaleInfluenceScore { get; set; }
    public string? WhaleSentiment { get; set; }
    public bool? MacroQuietPeriod { get; set; }
    public string? MacroReason { get; set; }

    protected TradingSession() { }

    public TradingSession(Guid id, Guid traderProfileId, string symbol, string timeframe)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        Symbol = symbol;
        Timeframe = timeframe;
        CurrentStage = TradingStage.Evaluating;
        StartTime = DateTime.UtcNow;
        StageChangedTimestamp = StartTime;
        IsActive = true;
    }
}
