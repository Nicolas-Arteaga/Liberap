using System;

namespace Verge.Trading.DTOs;

public class VergeAlertDto
{
    public string Id { get; set; } = string.Empty;
    
    /// <summary>
    /// String representation of AlertType or TradingStage.
    /// Needs to match frontend union type (e.g. Stage1-4 or Custom/System).
    /// </summary>
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
    
    public TargetZoneDto? TargetZone { get; set; }

    // UI
    public string Severity { get; set; } = "info"; // 'info' | 'warning' | 'success' | 'danger'
    public string Icon { get; set; } = string.Empty;
}

public class TargetZoneDto
{
    public decimal Low { get; set; }
    public decimal High { get; set; }
}
