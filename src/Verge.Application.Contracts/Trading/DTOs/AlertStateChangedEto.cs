using System;
using Volo.Abp.EventBus;

namespace Verge.Trading.DTOs;

[EventName("Verge.Trading.AlertStateChanged")]
public class AlertStateChangedEto
{
    public Guid UserId { get; set; }
    public Guid SessionId { get; set; }
    public VergeAlertDto Alert { get; set; } = new();
    public DateTime TriggeredAt { get; set; }
    
    // Breakout specific info
    public bool IsBreakout { get; set; }
    public decimal? EntryZoneHigh { get; set; }
    public decimal? EntryZoneLow { get; set; }
}
