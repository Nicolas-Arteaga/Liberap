using System;
using System.Collections.Generic;

namespace Verge.Trading.OrderBlock;

public class ObZoneDto
{
    public string Id { get; set; }
    public string Direction { get; set; } // bullish / bearish
    public double Top { get; set; }
    public double Bottom { get; set; }
    public double BosPrice { get; set; }
    public DateTime FormedAt { get; set; }
    public long FormedAtMs { get; set; }
    public int CandleIndex { get; set; }
    public string EntryStatus { get; set; } // IN_ZONE / APPROACHING / FAR
    public double DistToEntryPct { get; set; }
    public bool PocConfluence { get; set; }
    public double PocDistancePct { get; set; }
    public double ConfluenceScore { get; set; }
    public double SlPrice { get; set; }
    public double TpPrice { get; set; }
    public double TpDistancePct { get; set; }
    public bool ValidatedStable { get; set; }
}

public class ObAnalyzeResponseDto
{
    public string Symbol { get; set; }
    public string Interval { get; set; }
    public DateTime AnalyzedAt { get; set; }
    public double CurrentPrice { get; set; }
    public List<ObZoneDto> Zones { get; set; }
}

public class ObScanItemDto
{
    public string Symbol { get; set; }
    public string Direction { get; set; }
    public double Top { get; set; }
    public double Bottom { get; set; }
    public double CurrentPrice { get; set; }
    public bool PocConfluence { get; set; }
    public double PocDistancePct { get; set; }
    public string EntryStatus { get; set; }
    public double DistToEntryPct { get; set; }
    public double SlPrice { get; set; }
    public double TpPrice { get; set; }
    public double TpDistancePct { get; set; }
    public double ConfluenceScore { get; set; }
    public DateTime FormedAt { get; set; }
    public bool ValidatedStable { get; set; }
}

public class ObScanResponseDto
{
    public List<ObScanItemDto> Top5 { get; set; }
    public int ScannedCount { get; set; }
    public DateTime AnalyzedAt { get; set; }
    public int ActionableCount { get; set; }
}
