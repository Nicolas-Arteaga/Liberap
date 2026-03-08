using System.Threading.Tasks;
using System.Collections.Generic;
using Verge.Trading;
using System.Text.Json.Serialization;
using System.Text.Json;
using System;

namespace Verge.Trading;

public interface IPythonIntegrationService
{
    Task<RegimeResponseModel?> DetectMarketRegimeAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<TechnicalsResponseModel?> AnalyzeTechnicalsAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<bool> IsHealthyAsync();
}

public class MarketRegimeTypeConverter : JsonConverter<MarketRegimeType>
{
    public override MarketRegimeType Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        string? value = reader.GetString()?.Replace("_", "").Replace(" ", "").ToLowerInvariant();
        
        if (string.IsNullOrEmpty(value)) return MarketRegimeType.Ranging;

        if (value.Contains("bull")) return MarketRegimeType.BullTrend;
        if (value.Contains("bear")) return MarketRegimeType.BearTrend;
        if (value.Contains("range") || value.Contains("ranging")) return MarketRegimeType.Ranging;
        if (value.Contains("volatility") || value.Contains("volatile")) return MarketRegimeType.HighVolatility;

        return MarketRegimeType.Ranging; // Fallback safe
    }

    public override void Write(Utf8JsonWriter writer, MarketRegimeType value, JsonSerializerOptions options)
    {
        writer.WriteStringValue(value.ToString());
    }
}

public class RegimeResponseModel
{
    [JsonConverter(typeof(MarketRegimeTypeConverter))]
    public MarketRegimeType Regime { get; set; }
    public float VolatilityScore { get; set; }
    public float TrendStrength { get; set; }
    public string Structure { get; set; } = "Neutral";
    public bool BosDetected { get; set; }
    public bool ChochDetected { get; set; }
    public List<float> LiquidityZones { get; set; } = new();
}

public class TechnicalsResponseModel
{
    public float MacdHistogram { get; set; }
    public float BbWidth { get; set; }
    public float Adx { get; set; }
    public float Rsi { get; set; }
    public float Atr { get; set; }
}
