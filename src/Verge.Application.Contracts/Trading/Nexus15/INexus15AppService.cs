using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Nexus15;

public interface INexus15AppService : IApplicationService
{
    /// <summary>Obtiene la última predicción NEXUS-15 desde el caché Redis.</summary>
    Task<Nexus15ResultDto?> GetLatestAsync(string symbol);

    /// <summary>Dispara un análisis NEXUS-15 on-demand para un símbolo.</summary>
    Task<Nexus15ResultDto?> AnalyzeOnDemandAsync(string symbol);

    /// <summary>Analiza el mercado y trae el top 5 de oportunidades Long/Short.</summary>
    Task<List<Nexus15ResultDto>> AnalyzeTopAvailableAsync(int topN = 5);
}
