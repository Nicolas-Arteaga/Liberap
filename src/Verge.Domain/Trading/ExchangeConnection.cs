using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class ExchangeConnection : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string ExchangeName { get; set; } = string.Empty;
    public string ApiKey { get; set; } = string.Empty; // Should be encrypted
    public string ApiSecret { get; set; } = string.Empty; // Should be encrypted
    public bool IsConnected { get; set; }
    public DateTime? LastSyncTime { get; set; }

    protected ExchangeConnection() { }

    public ExchangeConnection(Guid id, Guid traderProfileId, string exchangeName, string apiKey, string apiSecret)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        ExchangeName = exchangeName;
        ApiKey = apiKey;
        ApiSecret = apiSecret;
        IsConnected = true;
    }
}
