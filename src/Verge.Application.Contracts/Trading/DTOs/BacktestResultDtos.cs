using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class BacktestResultDto : FullAuditedEntityDto<Guid>
{
    public Guid TradingStrategyId { get; set; }
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
    public int TotalTrades { get; set; }
    public int WinningTrades { get; set; }
    public int LosingTrades { get; set; }
    public double WinRate { get; set; }
    public decimal TotalProfit { get; set; }
    public decimal MaxDrawdown { get; set; }
    public double SharpeRatio { get; set; }
    public string EquityCurveJson { get; set; }
}

public class RunBacktestDto
{
    public Guid TradingStrategyId { get; set; }
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
}
