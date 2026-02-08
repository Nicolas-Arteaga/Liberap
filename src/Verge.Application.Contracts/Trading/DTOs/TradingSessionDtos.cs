using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingSessionDto : FullAuditedEntityDto<Guid>
{
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public TradingStage CurrentStage { get; set; }
    public DateTime StartTime { get; set; }
    public bool IsActive { get; set; }
}

public class StartSessionDto
{
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
}
