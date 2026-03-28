using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading;

public interface IAniquiladorPatternManager
{
    Task AnalyzeCandlesAsync(string symbol, List<MarketCandleModel> hourlyCandles);
}
