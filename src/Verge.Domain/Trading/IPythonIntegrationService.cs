using System.Threading.Tasks;
using System.Collections.Generic;

namespace Verge.Trading;

public interface IPythonIntegrationService
{
    Task<RegimeResponseModel?> DetectMarketRegimeAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<TechnicalsResponseModel?> AnalyzeTechnicalsAsync(string symbol, string timeframe, List<MarketCandleModel> data);
    Task<bool> IsHealthyAsync();
}


public class RegimeResponseModel
{
    public string Regime { get; set; } = string.Empty;
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
