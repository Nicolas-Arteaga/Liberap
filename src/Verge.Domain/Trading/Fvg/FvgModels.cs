using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Verge.Trading.Fvg;

public class VolumeProfileBinModel
{
    [JsonPropertyName("price_low")]
    public double PriceLow { get; set; }
    [JsonPropertyName("price_high")]
    public double PriceHigh { get; set; }
    [JsonPropertyName("volume")]
    public double Volume { get; set; }
    [JsonPropertyName("is_poc")]
    public bool IsPoc { get; set; }
    [JsonPropertyName("is_hvn")]
    public bool IsHvn { get; set; }
}

public class FvgZoneModel
{
    [JsonPropertyName("id")]
    public string Id { get; set; }
    [JsonPropertyName("direction")]
    public string Direction { get; set; } // bullish / bearish
    [JsonPropertyName("top")]
    public double Top { get; set; }
    [JsonPropertyName("bottom")]
    public double Bottom { get; set; }
    [JsonPropertyName("gap_pct")]
    public double GapPct { get; set; }
    [JsonPropertyName("formed_at")]
    public DateTime FormedAt { get; set; }
    [JsonPropertyName("formed_at_ms")]
    public long FormedAtMs { get; set; }
    [JsonPropertyName("candle_index")]
    public int CandleIndex { get; set; }
    [JsonPropertyName("fill_progress_pct")]
    public double FillProgressPct { get; set; }
    [JsonPropertyName("poc_confluence")]
    public bool PocConfluence { get; set; }
    [JsonPropertyName("poc_distance_pct")]
    public double PocDistancePct { get; set; }
    [JsonPropertyName("entry_status")]
    public string EntryStatus { get; set; } // IN_ZONE / APPROACHING / EXHAUSTED / FAR / TP_HIT
    [JsonPropertyName("dist_to_entry_pct")]
    public double DistToEntryPct { get; set; }
    [JsonPropertyName("tp_progress_pct")]
    public double TpProgressPct { get; set; }
    [JsonPropertyName("confluence_score")]
    public double ConfluenceScore { get; set; }
    [JsonPropertyName("sl_price")]
    public double SlPrice { get; set; }
    [JsonPropertyName("tp_price")]
    public double TpPrice { get; set; }
    [JsonPropertyName("is_ifvg")]
    public bool IsIfvg { get; set; }
    [JsonPropertyName("source_interval")]
    public string SourceInterval { get; set; }
}

public class FvgAnalyzeResponseModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("interval")]
    public string Interval { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
    [JsonPropertyName("current_price")]
    public double CurrentPrice { get; set; }
    [JsonPropertyName("poc_price")]
    public double PocPrice { get; set; }
    [JsonPropertyName("zones")]
    public List<FvgZoneModel> Zones { get; set; }
    [JsonPropertyName("volume_profile")]
    public List<VolumeProfileBinModel> VolumeProfile { get; set; }
}

public class FvgScanItemModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("direction")]
    public string Direction { get; set; }
    [JsonPropertyName("top")]
    public double Top { get; set; }
    [JsonPropertyName("bottom")]
    public double Bottom { get; set; }
    [JsonPropertyName("gap_pct")]
    public double GapPct { get; set; }
    [JsonPropertyName("current_price")]
    public double CurrentPrice { get; set; }
    [JsonPropertyName("poc_confluence")]
    public bool PocConfluence { get; set; }
    [JsonPropertyName("poc_distance_pct")]
    public double PocDistancePct { get; set; }
    [JsonPropertyName("entry_status")]
    public string EntryStatus { get; set; }
    [JsonPropertyName("dist_to_entry_pct")]
    public double DistToEntryPct { get; set; }
    [JsonPropertyName("tp_price")]
    public double TpPrice { get; set; }
    [JsonPropertyName("confluence_score")]
    public double ConfluenceScore { get; set; }
    [JsonPropertyName("fill_progress_pct")]
    public double FillProgressPct { get; set; }
    [JsonPropertyName("formed_at")]
    public DateTime FormedAt { get; set; }
}

public class FvgScanResponseModel
{
    [JsonPropertyName("top_5")]
    public List<FvgScanItemModel> Top5 { get; set; }
    [JsonPropertyName("scanned_count")]
    public int ScannedCount { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
}

public class FvgCascadeResultModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("cascade_status")]
    public string CascadeStatus { get; set; } // NONE / AWAITING_CONFIRMATION / AWAITING_EXECUTION / READY
    [JsonPropertyName("bias_zone")]
    public FvgZoneModel BiasZone { get; set; }
    [JsonPropertyName("confirmation_zone")]
    public FvgZoneModel ConfirmationZone { get; set; }
    [JsonPropertyName("execution_zone")]
    public FvgZoneModel ExecutionZone { get; set; }
    [JsonPropertyName("entry_price_zone")]
    public FvgZoneModel EntryPriceZone { get; set; }
    [JsonPropertyName("current_price")]
    public double CurrentPrice { get; set; }
    [JsonPropertyName("confluence_score")]
    public double ConfluenceScore { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
}

public class FvgCascadeScanResponseModel
{
    [JsonPropertyName("top_5")]
    public List<FvgCascadeResultModel> Top5 { get; set; }
    [JsonPropertyName("scanned_count")]
    public int ScannedCount { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
}

public interface IPythonFvgService
{
    Task<FvgAnalyzeResponseModel?> AnalyzeAsync(string symbol, string interval);
    Task<FvgScanResponseModel?> ScanAsync(List<string> symbols, string interval);
    Task<FvgCascadeResultModel?> CascadeAsync(string symbol);
    Task<FvgCascadeScanResponseModel?> CascadeScanAsync(List<string> symbols);
}
