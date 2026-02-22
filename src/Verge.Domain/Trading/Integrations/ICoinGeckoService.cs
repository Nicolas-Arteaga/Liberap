using System.Threading.Tasks;

namespace Verge.Trading.Integrations;

public interface ICoinGeckoService
{
    Task<CoinGeckoResult?> GetTokenDataAsync(string symbol);
}
