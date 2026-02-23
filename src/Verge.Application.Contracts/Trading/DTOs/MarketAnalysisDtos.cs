using System;

namespace Verge.Trading;

public class MarketAnalysisDto
{
    public string Symbol { get; set; }
    public double Rsi { get; set; }
    public string Trend { get; set; }
    public int Confidence { get; set; }
    public string Signal { get; set; }
    public string Sentiment { get; set; }
    public DateTime Timestamp { get; set; }
    public string Description { get; set; }
}

public class OpportunityDto
{
    public string Symbol { get; set; }
    public int Confidence { get; set; }
    public string Signal { get; set; }
    public string Reason { get; set; }
    public decimal? EntryMinPrice { get; set; }
    public decimal? EntryMaxPrice { get; set; }
}
