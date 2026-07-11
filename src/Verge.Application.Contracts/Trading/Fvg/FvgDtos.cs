using System;
using System.Collections.Generic;

namespace Verge.Trading.Fvg;

public class VolumeProfileBinDto
{
    public double PriceLow { get; set; }
    public double PriceHigh { get; set; }
    public double Volume { get; set; }
    public bool IsPoc { get; set; }
    public bool IsHvn { get; set; }
}

public class FvgZoneDto
{
    public string Id { get; set; }
    public string Direction { get; set; } // bullish / bearish
    public double Top { get; set; }
    public double Bottom { get; set; }
    public double GapPct { get; set; }
    public DateTime FormedAt { get; set; }
    public long FormedAtMs { get; set; }
    public int CandleIndex { get; set; }
    public double FillProgressPct { get; set; }
    public bool PocConfluence { get; set; }
    public double PocDistancePct { get; set; }
    public string EntryStatus { get; set; } // IN_ZONE / APPROACHING / EXHAUSTED / FAR / TP_HIT
    public double DistToEntryPct { get; set; }
    public double TpProgressPct { get; set; }
    public double ConfluenceScore { get; set; }
    public double SlPrice { get; set; }
    public double TpPrice { get; set; }
    public bool IsIfvg { get; set; }
    public string SourceInterval { get; set; }
}

public class FvgAnalyzeResponseDto
{
    public string Symbol { get; set; }
    public string Interval { get; set; }
    public DateTime AnalyzedAt { get; set; }
    public double CurrentPrice { get; set; }
    public double PocPrice { get; set; }
    public List<FvgZoneDto> Zones { get; set; }
    public List<VolumeProfileBinDto> VolumeProfile { get; set; }
}

public class FvgScanItemDto
{
    public string Symbol { get; set; }
    public string Direction { get; set; }
    public double Top { get; set; }
    public double Bottom { get; set; }
    public double GapPct { get; set; }
    public double CurrentPrice { get; set; }
    public bool PocConfluence { get; set; }
    public double PocDistancePct { get; set; }
    public string EntryStatus { get; set; }
    public double DistToEntryPct { get; set; }
    public double TpPrice { get; set; }
    public double ConfluenceScore { get; set; }
    public double FillProgressPct { get; set; }
    public DateTime FormedAt { get; set; }
}

public class FvgScanResponseDto
{
    public List<FvgScanItemDto> Top5 { get; set; }
    public int ScannedCount { get; set; }
    public DateTime AnalyzedAt { get; set; }
}

public class FvgCascadeResultDto
{
    public string Symbol { get; set; }
    public string CascadeStatus { get; set; } // NONE / AWAITING_CONFIRMATION / AWAITING_EXECUTION / READY
    public FvgZoneDto BiasZone { get; set; }
    public FvgZoneDto ConfirmationZone { get; set; }
    public FvgZoneDto ExecutionZone { get; set; }
    public FvgZoneDto EntryPriceZone { get; set; }
    public double CurrentPrice { get; set; }
    public double ConfluenceScore { get; set; }
    public DateTime AnalyzedAt { get; set; }
}

public class FvgCascadeScanResponseDto
{
    public List<FvgCascadeResultDto> Top5 { get; set; }
    public int ScannedCount { get; set; }
    public DateTime AnalyzedAt { get; set; }
}
