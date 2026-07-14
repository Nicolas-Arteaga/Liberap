using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Verge.Trading.AdnCompression;

public class AdnCompressionItemModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("timeframe")]
    public string Timeframe { get; set; }
    [JsonPropertyName("phase")]
    public string Phase { get; set; } // COILED / PULLBACK_TO_MA7 / EXTENDED / EXHAUSTED
    [JsonPropertyName("direction")]
    public string Direction { get; set; } // LONG / SHORT / NONE
    [JsonPropertyName("ma7_crossings")]
    public int Ma7Crossings { get; set; }
    [JsonPropertyName("compression_candles")]
    public int CompressionCandles { get; set; }
    [JsonPropertyName("ignition_multiplier")]
    public double IgnitionMultiplier { get; set; }
    [JsonPropertyName("candles_since_ignition")]
    public int CandlesSinceIgnition { get; set; }
    [JsonPropertyName("current_price")]
    public double CurrentPrice { get; set; }
    [JsonPropertyName("ma7_now")]
    public double Ma7Now { get; set; }
    [JsonPropertyName("ma25_now")]
    public double Ma25Now { get; set; }
    [JsonPropertyName("ma99_now")]
    public double Ma99Now { get; set; }
    [JsonPropertyName("dist_to_ma7_pct")]
    public double DistToMa7Pct { get; set; }
    [JsonPropertyName("dist_to_ma25_pct")]
    public double DistToMa25Pct { get; set; }
    [JsonPropertyName("touched_ma25_since_ignition")]
    public bool TouchedMa25SinceIgnition { get; set; }
    [JsonPropertyName("reasons")]
    public List<string> Reasons { get; set; }
}

public class AdnCompressionScanResponseModel
{
    [JsonPropertyName("top_10")]
    public List<AdnCompressionItemModel> Top10 { get; set; }
    [JsonPropertyName("scanned_count")]
    public int ScannedCount { get; set; }
    [JsonPropertyName("qualified_count")]
    public int QualifiedCount { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
}

public interface IPythonAdnCompressionService
{
    Task<AdnCompressionScanResponseModel?> ScanAsync(List<string> symbols, string timeframe);
}
