using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class BacktestResult : FullAuditedAggregateRoot<Guid>
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
    public decimal MaxDrawdown { get; set; }
    public double SharpeRatio { get; set; }
    public string EquityCurveJson { get; set; } = string.Empty; // Serialized curve data

    protected BacktestResult() { }

    public BacktestResult(Guid id, Guid tradingStrategyId, string symbol) : base(id)
    {
        TradingStrategyId = tradingStrategyId;
        Symbol = symbol;
    }
}
