using System.Threading.Tasks;

namespace Verge.Trading.Integrations;

public interface IFearAndGreedService
{
    Task<FearAndGreedResult?> GetCurrentFearAndGreedAsync();
}
