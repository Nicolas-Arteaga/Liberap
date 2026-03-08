using System;
using System.Collections.Generic;

namespace Verge.Trading;

public class PaperTradingReportDto
{
    public DateTime EvaluationDate { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public string Environment { get; set; } = "Binance_Testnet";
    public int SimulatedDays { get; set; }
    
    public int TotalExecutedTrades { get; set; }
    public BacktestResultDto TheoreticalBacktest { get; set; } = new();
    
    public decimal RealizedProfitFactor { get; set; }
    public decimal DeviationPercentage { get; set; } // Difference between Realized and Theoretical Backtest

    // Criteria
    public bool PassedPaperTrading => DeviationPercentage < 0.20m; // < 20% deviation
}

public class LiveShadowReportDto
{
    public DateTime EvaluationDate { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public int TotalSignalsGenerated { get; set; }
    
    public TimeSpan AverageLatentDelay { get; set; }
    public decimal SignalDeviationPercentage { get; set; } // Price difference between Signal and Real Market Print

    // Criteria
    public bool PassedLiveShadow => SignalDeviationPercentage < 0.15m; // < 15% deviation
}
