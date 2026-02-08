using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradingAlert : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Symbol { get; set; }
    public decimal TriggerPrice { get; set; }
    public string Message { get; set; }
    public AlertType Type { get; set; }
    public bool IsActive { get; set; }
    public string ChannelsJson { get; set; } // Serialized list of channels (push, email, telegram)

    protected TradingAlert() { }

    public TradingAlert(Guid id, Guid traderProfileId, string symbol, decimal triggerPrice, string message, AlertType type)
        : base(id)
    {
        TraderProfileId = traderProfileId;
        Symbol = symbol;
        TriggerPrice = triggerPrice;
        Message = message;
        Type = type;
        IsActive = true;
    }
}
