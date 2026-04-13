using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Nexus15;

public interface INexus15AppService : IApplicationService
{
    /// <summary>Obtiene la última predicción NEXUS-15 desde el caché Redis.</summary>
    Task<Nexus15ResultDto?> GetLatestAsync(string symbol);

    /// <summary>Dispara un análisis NEXUS-15 on-demand para un símbolo.</summary>
    Task<Nexus15ResultDto?> AnalyzeOnDemandAsync(string symbol);
}
