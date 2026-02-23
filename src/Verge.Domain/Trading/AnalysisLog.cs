using System;
using System.Collections.Generic;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class AnalysisLog : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public Guid? TradingSessionId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public AnalysisLogType LogType { get; set; }
    public string Message { get; set; } = string.Empty;
    public string Level { get; set; } = string.Empty; // "info", "warning", "success", "danger"
    public DateTime Timestamp { get; set; }
    public string DataJson { get; set; } = string.Empty; // Guardar como JSON string

    public AnalysisLog()
    {
    }

    public AnalysisLog(Guid id, Guid traderProfileId, Guid? tradingSessionId, string symbol, string message, string level, DateTime timestamp, AnalysisLogType logType, string dataJson = null)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        TradingSessionId = tradingSessionId;
        Symbol = symbol;
        Message = message;
        Level = level;
        Timestamp = timestamp;
        LogType = logType;
        DataJson = dataJson;
    }
}
