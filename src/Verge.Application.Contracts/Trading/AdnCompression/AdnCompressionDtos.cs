using System;
using System.Collections.Generic;

namespace Verge.Trading.AdnCompression;

public class AdnCompressionItemDto
{
    public string Symbol { get; set; }
    public string Timeframe { get; set; }
    public string Phase { get; set; } // COILED / PULLBACK_TO_MA7 / EXTENDED / EXHAUSTED
    public string Direction { get; set; } // LONG / SHORT / NONE
    public int Ma7Crossings { get; set; }
    public int CompressionCandles { get; set; }
    public double IgnitionMultiplier { get; set; }
    public int CandlesSinceIgnition { get; set; }
    public double CurrentPrice { get; set; }
    public double Ma7Now { get; set; }
    public double Ma25Now { get; set; }
    public double Ma99Now { get; set; }
    public double DistToMa7Pct { get; set; }
    public double DistToMa25Pct { get; set; }
    public bool TouchedMa25SinceIgnition { get; set; }
    public List<string> Reasons { get; set; }
}

public class AdnCompressionScanResponseDto
{
    public List<AdnCompressionItemDto> Top10 { get; set; }
    public int ScannedCount { get; set; }
    public int QualifiedCount { get; set; }
    public DateTime AnalyzedAt { get; set; }
}
