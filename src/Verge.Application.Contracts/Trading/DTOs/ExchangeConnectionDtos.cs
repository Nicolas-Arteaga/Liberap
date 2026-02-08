using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class ExchangeConnectionDto : FullAuditedEntityDto<Guid>
{
    public string ExchangeName { get; set; }
    public bool IsConnected { get; set; }
    public DateTime? LastSyncTime { get; set; }
}

public class ConnectExchangeDto
{
    public string ExchangeName { get; set; }
    public string ApiKey { get; set; }
    public string ApiSecret { get; set; }
}
