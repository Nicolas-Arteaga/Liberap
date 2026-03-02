using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public interface IWhaleTrackerService
{
    Task<WhaleAnalysisResult> GetWhaleActivityAsync(string symbol);
    Task ProcessExternalMovementsAsync(); // Job called method to sync with APIs
    Task<double> GetInfluenceScoreAsync(string walletAddress);
}

public class WhaleAnalysisResult
{
    public string Symbol { get; set; }
    public double NetFlowScore { get; set; } // -1.0 (Distribution) to 1.0 (Accumulation)
    public List<WhaleSignal> RecentSignals { get; set; } = new();
    public string Summary { get; set; }
    public double MaxInfluenceDetected { get; set; }
}

public class WhaleSignal
{
    public string WalletAddress { get; set; }
    public decimal Amount { get; set; }
    public string Type { get; set; } // Inflow/Outflow/Accumulation/Distribution
    public double InfluenceScore { get; set; }
    public DateTime Timestamp { get; set; }
}
