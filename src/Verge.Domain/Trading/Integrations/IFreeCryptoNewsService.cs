using System.Threading.Tasks;
using System.Collections.Generic;

namespace Verge.Trading.Integrations;

public interface IFreeCryptoNewsService
{
    Task<CryptoNewsResult?> GetNewsAsync(string symbol, int limit = 10);
    Task<SentimentAnalysis?> GetSentimentAsync(string symbol);
}
