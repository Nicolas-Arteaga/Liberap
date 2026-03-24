using System;
using System.Collections.Generic;
using Volo.Abp.EventBus;

namespace Verge.Trading.DTOs;

public class VergeAlertDto
{
    public string Id { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
    public bool Read { get; set; }

    // Trading specific data
    public string? Crypto { get; set; }
    public decimal? Price { get; set; }
    public SignalConfidence? Confidence { get; set; }
    public SignalDirection? Direction { get; set; }
    public TradingStage? Stage { get; set; }
    public int? Score { get; set; }
    
    public TargetZoneDto? TargetZone { get; set; }
    
    // Institutional 1% metrics
    public double? RiskRewardRatio { get; set; }
    public double? WinProbability { get; set; }
    public int? HistoricSampleSize { get; set; }
    public string? PatternSignal { get; set; }
    public decimal? StopLoss { get; set; }
    public decimal? TakeProfit { get; set; }
    public int? WhaleInfluenceScore { get; set; }
    public bool? IsSqueeze { get; set; }

    // Structure (Sprint 2)
    public string? Structure { get; set; }
    public bool BosDetected { get; set; }
    public bool ChochDetected { get; set; }
    public List<float> LiquidityZones { get; set; } = new();

    // UI
    public string Severity { get; set; } = "info"; 
    public string Icon { get; set; } = string.Empty;
}

public class TargetZoneDto
{
    public decimal Low { get; set; }
    public decimal High { get; set; }
}

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
