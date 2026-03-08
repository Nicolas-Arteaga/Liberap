using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading.DecisionEngine;

public class StrategyCalibration : FullAuditedEntity<Guid>
{
    public TradingStyle Style { get; set; }
    public MarketRegimeType Regime { get; set; }
    
    // Multipliers (Base = 1.0)
    public float TechnicalMultiplier { get; set; } = 1.0f;
    public float QuantitativeMultiplier { get; set; } = 1.0f;
    public float SentimentMultiplier { get; set; } = 1.0f;
    public float FundamentalMultiplier { get; set; } = 1.0f;
    public float InstitutionalMultiplier { get; set; } = 1.0f;

    // Serialized Calibrated Weights (Absolute)
    public string? WeightsJson { get; set; }
    
    // Performance Metrics from last calibration
    public double? ProfitFactor { get; set; }
    public double? SharpeRatio { get; set; }
    public double? WinRate { get; set; }
    public int? TotalTrades { get; set; }

    // Hard Optimized Thresholds (Absolute)
    public int? EntryThreshold { get; set; }
    public float? TrailingMultiplier { get; set; }

    // Threshold Shifts (Legacy/Manual)
    public int EntryThresholdShift { get; set; } = 0;
    public int TakeProfitMultiplier { get; set; } = 100; // Percentage 100 = 1.0x

    public DateTime LastRecalibrated { get; set; }

    protected StrategyCalibration() { }

    public StrategyCalibration(Guid id, TradingStyle style, MarketRegimeType regime)
        : base(id)
    {
        Style = style;
        Regime = regime;
        LastRecalibrated = DateTime.UtcNow;
    }
}
