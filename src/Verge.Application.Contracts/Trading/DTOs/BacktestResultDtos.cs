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
    public decimal InitialCapital { get; set; }
    public decimal TotalFeesPaid { get; set; }
    public decimal TotalSlippageLoss { get; set; }
    public double Expectancy { get; set; }
    public double TradeFrequencyPerDay { get; set; }
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
    
    // Hedge Fund Standards 
    public decimal FeePercentage { get; set; } = 0.1m; 
    public decimal SlippagePercentage { get; set; } = 0.1m; 
    public decimal InitialCapital { get; set; } = 1000m; 
}

public class ExhaustiveValidationReportDto
{
    public DateTime EvaluationDate { get; set; }
    public List<ExhaustiveValidationResultDto> Results { get; set; } = new();
}

public class ExhaustiveValidationResultDto
{
    public string Symbol { get; set; } = string.Empty;
    public string TradingStyle { get; set; } = string.Empty;
    public BacktestResultDto Training { get; set; } = new();
    public BacktestResultDto Testing { get; set; } = new();
    
    // Diferencias
    public double ProfitFactorDiff { get; set; }
    public double WinRateDiffPoints { get; set; }
    public double SharpeRatioDiff { get; set; }
    public double ExpectancyDiff { get; set; }
    public decimal MaxDrawdownDiffPoints { get; set; }
    public double TradeFrequencyDiff { get; set; }
    public decimal TotalFeesDiff { get; set; }
    public decimal TotalSlippageDiff { get; set; }
    
    // Criterios
    public bool PassedProfitFactor { get; set; }
    public bool PassedRobustness { get; set; }
    public bool PassedDrawdown { get; set; }
    public bool PassedExpectancy { get; set; }
    public bool IsApprovedForRealCapital => PassedProfitFactor && PassedRobustness && PassedDrawdown && PassedExpectancy;
}
