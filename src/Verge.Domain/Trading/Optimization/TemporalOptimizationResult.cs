using System;
using System.Collections.Generic;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading.Optimization;

public class TemporalOptimizationResult : FullAuditedAggregateRoot<Guid>
{
    public string Regime { get; set; }
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    
    // Serialized JSON with optimal weights
    public string WeightsJson { get; set; }
    
    public double ProfitFactor { get; set; }
    public double SharpeRatio { get; set; }
    public double WinRate { get; set; }
    public int TotalTrades { get; set; }
    public decimal TotalPnL { get; set; }

    public int EntryThreshold { get; set; }
    public float TrailingMultiplier { get; set; }

    public TemporalOptimizationResult() { }

    public TemporalOptimizationResult(Guid id) : base(id) { }
}
