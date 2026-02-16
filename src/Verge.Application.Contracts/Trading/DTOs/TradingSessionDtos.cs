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
}

public class StartSessionDto
{
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
}

public class AnalysisLogDto
{
    public string Message { get; set; }
    public string Level { get; set; }
    public DateTime Timestamp { get; set; }
    public string DataJson { get; set; }
}
