using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public interface IInstitutionalDataService
{
    Task<InstitutionalAnalysisResult> GetInstitutionalDataAsync(string symbol);
}

public class InstitutionalAnalysisResult
{
    public string Symbol { get; set; }
    
    // Liquidations
    public decimal TotalLiquidations24h { get; set; }
    public decimal BuyLiquidations1h { get; set; }
    public decimal SellLiquidations1h { get; set; }
    public bool IsSqueezeDetected { get; set; } // Cluster > $1M in short time
    public string SqueezeType { get; set; } // "Long Squeeze", "Short Squeeze", "None"

    // Order Flow
    public double BidAskImbalance { get; set; } // Ratio (e.g., 2.5 means 2.5x more bids than asks)
    public bool HasSignificantWall { get; set; }
    public string WallDirection { get; set; } // "Support", "Resistance"

    public string Summary { get; set; }
    public DateTime Timestamp { get; set; }
}
