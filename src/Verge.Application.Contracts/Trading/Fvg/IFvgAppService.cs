using System.Threading.Tasks;
using System.Collections.Generic;
using Volo.Abp.Application.Services;

namespace Verge.Trading.Fvg;

public interface IFvgAppService : IApplicationService
{
    /// <summary>Analiza un símbolo: devuelve todas las zonas FVG sin rellenar + volume profile.</summary>
    Task<FvgAnalyzeResponseDto?> AnalyzeOnDemandAsync(string symbol, string interval = "15m");

    /// <summary>Escanea una lista de símbolos y devuelve el top-5 por score de confluencia.</summary>
    Task<FvgScanResponseDto> ScanAsync(List<string> symbols, string interval = "15m");

    /// <summary>
    /// Cascada anclada a anchorInterval: "15m" -> cadena completa 15m->5m->1m (sesgo->confirmación->ejecución),
    /// "5m" -> cadena corta 5m->1m, "1m" -> análisis directo en 1m sin cascada.
    /// </summary>
    Task<FvgCascadeResultDto?> CascadeAsync(string symbol, string anchorInterval = "15m");

    /// <summary>Escanea una lista de símbolos con la cascada completa, top-5 de setups accionables.</summary>
    Task<FvgCascadeScanResponseDto> CascadeScanAsync(List<string> symbols);
}
