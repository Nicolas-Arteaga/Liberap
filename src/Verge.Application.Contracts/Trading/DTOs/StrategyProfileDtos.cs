using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading.DTOs;

public class StrategyProfileDto : EntityDto<Guid>
{
    public Guid UserId { get; set; }
    public string Name { get; set; } = string.Empty;
    public string Description { get; set; }
    public string Color { get; set; }
    public bool IsActive { get; set; }

    // Entry Filters
    public float MinConfluenceScore { get; set; }
    public float MinNexusConfidence { get; set; }
    public float MaxRsiLong { get; set; }
    public float MinRsiShort { get; set; }
    public float MaxMa7DistancePct { get; set; }
    public bool? RequireMacdPositive { get; set; }
    public string AllowedSources { get; set; } = "LSE,Nexus,Bridge";
    public bool AllowLong { get; set; }
    public bool AllowShort { get; set; }

    // Risk Management
    public decimal MarginPerTrade { get; set; }
    public float TpMultiplier { get; set; }
    public float SlMultiplier { get; set; }
    public float MinRR { get; set; }
    public int MaxOpenPositions { get; set; }
    public int MaxTradeDurationCandles { get; set; }

    // Advanced Filters
    public string? ActiveHoursStart { get; set; }
    public string? ActiveHoursEnd { get; set; }
    public List<string>? EnabledDays { get; set; }
    public bool ExtremeRsiVeto { get; set; }

    // Advanced Execution Constraints
    public float MaxEntrySlippagePct { get; set; }
    public float LseMaxEntrySlippagePct { get; set; }
    public float MinTpDistancePct { get; set; }
    public float MinSlDistancePct { get; set; }
    public float MinEstimatedRangePct { get; set; }
    public float MaxNexusSignalAgeSeconds { get; set; }
    public float NexusMaxPriceDriftPct { get; set; }

    // Metrics (Calculated)
    public double WinRate { get; set; }
    public int TotalTrades { get; set; }
    public double NetPnL { get; set; }
    public double AvgRR { get; set; }
}

public class CreateUpdateStrategyProfileDto
{
    public string Name { get; set; } = string.Empty;
    public string Description { get; set; }
    public string Color { get; set; } = "#00C47D";
    public bool IsActive { get; set; } = true;

    // Entry Filters
    public float MinConfluenceScore { get; set; } = 50f;
    public float MinNexusConfidence { get; set; } = 70f;
    public float MaxRsiLong { get; set; } = 80f;
    public float MinRsiShort { get; set; } = 20f;
    public float MaxMa7DistancePct { get; set; } = 3.5f;
    public bool? RequireMacdPositive { get; set; }
    public string AllowedSources { get; set; } = "LSE,Nexus,Bridge";
    public bool AllowLong { get; set; } = true;
    public bool AllowShort { get; set; } = true;

    // Risk Management
    public decimal MarginPerTrade { get; set; } = 150m;
    public float TpMultiplier { get; set; } = 3.0f;
    public float SlMultiplier { get; set; } = 0.8f;
    public float MinRR { get; set; } = 1.5f;
    public int MaxOpenPositions { get; set; } = 3;
    public int MaxTradeDurationCandles { get; set; } = 8;

    // Advanced Filters
    public string? ActiveHoursStart { get; set; }
    public string? ActiveHoursEnd { get; set; }
    public List<string>? EnabledDays { get; set; }
    public bool ExtremeRsiVeto { get; set; } = true;

    // Advanced Execution Constraints
    public float MaxEntrySlippagePct { get; set; } = 0.002f;
    public float LseMaxEntrySlippagePct { get; set; } = 0.015f;
    public float MinTpDistancePct { get; set; } = 0.003f;
    public float MinSlDistancePct { get; set; } = 0.002f;
    public float MinEstimatedRangePct { get; set; } = 3.0f;
    public float MaxNexusSignalAgeSeconds { get; set; } = 120.0f;
    public float NexusMaxPriceDriftPct { get; set; } = 0.025f;
}
