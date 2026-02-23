using System.Threading.Tasks;
using System.Collections.Generic;
using Verge.Trading;
using System.Text.Json.Serialization;

namespace Verge.Trading;

public interface IPythonIntegrationService
{
    Task<RegimeResponseModel?> DetectMarketRegimeAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<TechnicalsResponseModel?> AnalyzeTechnicalsAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<bool> IsHealthyAsync();
}


public class RegimeResponseModel
{
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public MarketRegimeType Regime { get; set; }
    public float VolatilityScore { get; set; }
    public float TrendStrength { get; set; }
}

public class TechnicalsResponseModel
{
    public float MacdHistogram { get; set; }
    public float BbWidth { get; set; }
    public float Adx { get; set; }
    public float Rsi { get; set; }
}
