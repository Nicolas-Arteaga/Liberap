using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingStrategyDto : FullAuditedEntityDto<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Name { get; set; } = string.Empty;
    public SignalDirection DirectionPreference { get; set; }
    public List<string> SelectedCryptos { get; set; } = new();
    public int Leverage { get; set; }
    public decimal Capital { get; set; }
    public RiskTolerance RiskLevel { get; set; }
    public bool AutoStopLoss { get; set; }
    public decimal TakeProfitPercentage { get; set; }
    public bool NotificationsEnabled { get; set; }
    public bool IsActive { get; set; }
}

public class CreateUpdateTradingStrategyDto
{
    public string Name { get; set; } = string.Empty;
    public SignalDirection DirectionPreference { get; set; }
    public List<string> SelectedCryptos { get; set; } = new();
    public int Leverage { get; set; }
    public decimal Capital { get; set; }
    public RiskTolerance RiskLevel { get; set; }
    public bool AutoStopLoss { get; set; }
    public decimal TakeProfitPercentage { get; set; }
    public bool NotificationsEnabled { get; set; }
}
