using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Nexus5;

public interface INexus5AppService : IApplicationService
{
    /// <summary>Obtiene el último análisis NEXUS-5 desde caché Redis.</summary>
    Task<Nexus5ResultDto?> GetLatestAsync(string symbol);

    /// <summary>Dispara un análisis NEXUS-5 on-demand para un símbolo con velas de 5m.</summary>
    Task<Nexus5ResultDto?> AnalyzeOnDemandAsync(string symbol);

    /// <summary>Escanea el mercado y retorna top 5 pares en Fase 1 (Compression) o Fase 2 (Ignition).</summary>
    Task<List<Nexus5ResultDto>> AnalyzeTopAvailableAsync(int topN = 5);

    /// <summary>
    /// Endpoint para el agente: retorna TODOS los pares en fase activa
    /// (Compression con phase_score > 60 o Ignition), ordenados por urgencia.
    /// </summary>
    Task<List<Nexus5ResultDto>> AnalyzeAllCandidatesAsync();

    /// <summary>Sweep on-demand: retorna resultado solo si sweep_detected=true.</summary>
    Task<Nexus5ResultDto?> AnalyzeSweepOnDemandAsync(string symbol);

    /// <summary>Top Sweep scan: escanea mercado y retorna pares con sweep detectado.</summary>
    Task<List<Nexus5ResultDto>> AnalyzeSweepTopAsync(int topN = 5);
}
