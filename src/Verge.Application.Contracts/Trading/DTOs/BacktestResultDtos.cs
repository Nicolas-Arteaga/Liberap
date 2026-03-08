using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class BacktestResultDto : FullAuditedEntityDto<Guid>
{
    public Guid TradingStrategyId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
    public int TotalTrades { get; set; }
    public int WinningTrades { get; set; }
    public int LosingTrades { get; set; }
    public double WinRate { get; set; }
    public decimal TotalProfit { get; set; }
    public double ProfitFactor { get; set; }
    public decimal MaxDrawdown { get; set; }
    public double SharpeRatio { get; set; }
    public string EquityCurveJson { get; set; } = string.Empty;
}

public class ComparativeEvaluationResultDto
{
    public string Symbol { get; set; } = string.Empty;
    public string TradingStyle { get; set; } = string.Empty;
    
    public BacktestResultDto Baseline { get; set; } = new();
    public BacktestResultDto Optimized { get; set; } = new();
    
    public double WinRateImprovement { get; set; }
    public double ProfitFactorImprovement { get; set; }
    public double SharpeRatioImprovement { get; set; }
}

public class ComparativeEvaluationReportDto
{
    public List<ComparativeEvaluationResultDto> Results { get; set; } = new();
    public DateTime EvaluationDate { get; set; }
}

public class RunBacktestDto
{
    public Guid TradingStrategyId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }

    // Optimization Overrides
    public Dictionary<string, float>? WeightOverrides { get; set; }
    public int? EntryThresholdOverride { get; set; }
    public float? TrailingMultiplierOverride { get; set; }
}
