using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TraderProfileDto : FullAuditedEntityDto<Guid>
{
    public Guid UserId { get; set; }
    public string Name { get; set; }
    public string Email { get; set; }
    public TradingLevel Level { get; set; }
    public RiskTolerance RiskTolerance { get; set; }
    public decimal TotalProfit { get; set; }
    public double Accuracy { get; set; }
    public int ActiveStrategiesCount { get; set; }
}

public class UpdateTraderProfileDto
{
    public string Name { get; set; }
    public TradingLevel Level { get; set; }
    public RiskTolerance RiskTolerance { get; set; }
}
