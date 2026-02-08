using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TraderProfile : FullAuditedAggregateRoot<Guid>
{
    public Guid UserId { get; set; }
    public string Name { get; set; }
    public string Email { get; set; }
    public TradingLevel Level { get; set; }
    public RiskTolerance RiskTolerance { get; set; }
    public decimal TotalProfit { get; set; }
    public double Accuracy { get; set; }
    public int ActiveStrategiesCount { get; set; }

    protected TraderProfile() { }

    public TraderProfile(Guid id, Guid userId, string name, string email, TradingLevel level, RiskTolerance riskTolerance)
        : base(id)
    {
        UserId = userId;
        Name = name;
        Email = email;
        Level = level;
        RiskTolerance = riskTolerance;
        TotalProfit = 0;
        Accuracy = 0;
        ActiveStrategiesCount = 0;
    }
}
