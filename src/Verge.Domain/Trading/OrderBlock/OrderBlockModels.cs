using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Verge.Trading.OrderBlock;

public class ObZoneModel
{
    [JsonPropertyName("id")]
    public string Id { get; set; }
    [JsonPropertyName("direction")]
    public string Direction { get; set; } // bullish / bearish
    [JsonPropertyName("top")]
    public double Top { get; set; }
    [JsonPropertyName("bottom")]
    public double Bottom { get; set; }
    [JsonPropertyName("bos_price")]
    public double BosPrice { get; set; }
    [JsonPropertyName("formed_at")]
    public DateTime FormedAt { get; set; }
    [JsonPropertyName("formed_at_ms")]
    public long FormedAtMs { get; set; }
    [JsonPropertyName("candle_index")]
    public int CandleIndex { get; set; }
    [JsonPropertyName("entry_status")]
    public string EntryStatus { get; set; } // IN_ZONE / APPROACHING / FAR
    [JsonPropertyName("dist_to_entry_pct")]
    public double DistToEntryPct { get; set; }
    [JsonPropertyName("poc_confluence")]
    public bool PocConfluence { get; set; }
    [JsonPropertyName("poc_distance_pct")]
    public double PocDistancePct { get; set; }
    [JsonPropertyName("confluence_score")]
    public double ConfluenceScore { get; set; }
    [JsonPropertyName("sl_price")]
    public double SlPrice { get; set; }
    [JsonPropertyName("tp_price")]
    public double TpPrice { get; set; }
    [JsonPropertyName("tp_distance_pct")]
    public double TpDistancePct { get; set; }
    [JsonPropertyName("validated_stable")]
    public bool ValidatedStable { get; set; }
}

public class ObAnalyzeResponseModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("interval")]
    public string Interval { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
    [JsonPropertyName("current_price")]
    public double CurrentPrice { get; set; }
    [JsonPropertyName("zones")]
    public List<ObZoneModel> Zones { get; set; }
}

public class ObScanItemModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("direction")]
    public string Direction { get; set; }
    [JsonPropertyName("top")]
    public double Top { get; set; }
    [JsonPropertyName("bottom")]
    public double Bottom { get; set; }
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
    [JsonPropertyName("sl_price")]
    public double SlPrice { get; set; }
    [JsonPropertyName("tp_price")]
    public double TpPrice { get; set; }
    [JsonPropertyName("tp_distance_pct")]
    public double TpDistancePct { get; set; }
    [JsonPropertyName("confluence_score")]
    public double ConfluenceScore { get; set; }
    [JsonPropertyName("formed_at")]
    public DateTime FormedAt { get; set; }
    [JsonPropertyName("validated_stable")]
    public bool ValidatedStable { get; set; }
}

public class ObScanResponseModel
{
    [JsonPropertyName("top_5")]
    public List<ObScanItemModel> Top5 { get; set; }
    [JsonPropertyName("scanned_count")]
    public int ScannedCount { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
    [JsonPropertyName("actionable_count")]
    public int ActionableCount { get; set; }
}

public interface IPythonOrderBlockService
{
    Task<ObAnalyzeResponseModel?> AnalyzeAsync(string symbol, string interval);
    Task<ObScanResponseModel?> ScanAsync(List<string> symbols, string interval, bool onlyValidated);
}
