using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingSessionDto : FullAuditedEntityDto<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
    public TradingStage CurrentStage { get; set; }
    public DateTime StartTime { get; set; }
    public bool IsActive { get; set; }
    public decimal? EntryPrice { get; set; }
    public decimal? TakeProfitPrice { get; set; }
    public decimal? StopLossPrice { get; set; }
    public TradingStyle? SelectedStyle { get; set; }
    public SignalDirection? SelectedDirection { get; set; }
    
    public decimal? NetProfit { get; set; }
    public TradeStatus? Outcome { get; set; }
    public string? ExitReason { get; set; }
    public long? LastEvaluationTimestamp { get; set; }
}

public class StartSessionDto
{
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
}

public class AnalysisLogDto
{
    public string Symbol { get; set; }
    public string Message { get; set; }
    public string Level { get; set; }
    public DateTime Timestamp { get; set; }
    public AnalysisLogType LogType { get; set; }
    public string DataJson { get; set; }
}
