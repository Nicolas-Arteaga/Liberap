using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.Nexus15;

public class Nexus15ResponseModel
{
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public DateTime AnalyzedAt { get; set; }
    public double AiConfidence { get; set; }     // 0-100
    public string Direction { get; set; }         // BULLISH / BEARISH / NEUTRAL
    public string Recommendation { get; set; }    // Long / Short / Wait
    public double Next5CandlesProb { get; set; }
    public double Next15CandlesProb { get; set; }
    public double Next20CandlesProb { get; set; }
    public double EstimatedRangePercent { get; set; }
    public string Regime { get; set; }
    public Nexus15GroupScoresModel GroupScores { get; set; }
    public Nexus15FeaturesModel Features { get; set; }
    public Dictionary<string, string> Detectivity { get; set; }
}

public class Nexus15GroupScoresModel
{
    public double G1PriceAction { get; set; }
    public double G2SmcIct { get; set; }
    public double G3Wyckoff { get; set; }
    public double G4Fractals { get; set; }
    public double G5Volume { get; set; }
    public double G6Ml { get; set; }
}

public class Nexus15FeaturesModel
{
    public double CandleBodyRatio { get; set; }
    public double UpperWickRatio { get; set; }
    public double LowerWickRatio { get; set; }
    public int ConsecutiveBullBars { get; set; }
    public bool OrderBlockDetected { get; set; }
    public bool FairValueGap { get; set; }
    public bool BosDetected { get; set; }
    public string WyckoffPhase { get; set; }
    public bool SpringDetected { get; set; }
    public bool UpthrustDetected { get; set; }
    public bool FractalHigh5 { get; set; }
    public bool FractalLow5 { get; set; }
    public int TrendStructure { get; set; }
    public double VolumeRatio20 { get; set; }
    public double CvdDelta { get; set; }
    public bool VolumeSurgeBullish { get; set; }
    public double PocProximity { get; set; }
    public double Rsi14 { get; set; }
    public double MacdHistogram { get; set; }
    public double AtrPercent { get; set; }
}

public interface IPythonNexus15Service
{
    Task<Nexus15ResponseModel?> AnalyzeNexus15Async(string symbol, List<MarketCandleModel> candles);
}
