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

    /// <summary>Cascada 15m (sesgo) -> 5m (confirmación) -> 1m (ejecución) para un símbolo.</summary>
    Task<FvgCascadeResultDto?> CascadeAsync(string symbol);

    /// <summary>Escanea una lista de símbolos con la cascada completa, top-5 de setups accionables.</summary>
    Task<FvgCascadeScanResponseDto> CascadeScanAsync(List<string> symbols);
}
