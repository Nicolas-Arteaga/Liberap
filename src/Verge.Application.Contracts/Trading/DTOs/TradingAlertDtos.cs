using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingAlertDto : FullAuditedEntityDto<Guid>
{
    public string Symbol { get; set; }
    public decimal TriggerPrice { get; set; }
    public string Message { get; set; }
    public AlertType Type { get; set; }
    public bool IsActive { get; set; }
    public List<string> Channels { get; set; }
}

public class CreateUpdateTradingAlertDto
{
    public string Symbol { get; set; }
    public decimal TriggerPrice { get; set; }
    public string Message { get; set; }
    public AlertType Type { get; set; }
    public List<string> Channels { get; set; }
}
