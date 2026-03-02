using System;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public interface IProbabilisticEngine
{
    Task<WinRateResult> GetWinRateAsync(
        TradingStyle style, 
        string symbol, 
        MarketRegimeType regime, 
        int score, 
        DateTime entryTime);
}

public class WinRateResult
{
    public double Probability { get; set; }
    public int SampleSize { get; set; }
    public string ConfidenceLevel { get; set; } = "Low"; // Low, Medium, High based on SampleSize
}
