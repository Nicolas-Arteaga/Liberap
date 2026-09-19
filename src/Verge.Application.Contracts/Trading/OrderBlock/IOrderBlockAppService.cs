using System.Threading.Tasks;
using System.Collections.Generic;
using Volo.Abp.Application.Services;

namespace Verge.Trading.OrderBlock;

public interface IOrderBlockAppService : IApplicationService
{
    /// <summary>Analiza un símbolo: devuelve los Order Block pendientes de mitigar (bullish/bearish).</summary>
    Task<ObAnalyzeResponseDto?> AnalyzeOnDemandAsync(string symbol, string interval = "15m");

    /// <summary>
    /// Escanea una lista de símbolos y devuelve el top-5 por score de confluencia.
    /// onlyValidated=true (default) filtra a solo bearish/SHORT (única dirección
    /// validada con backtest real, $92.26/mes estable).
    /// </summary>
    Task<ObScanResponseDto> ScanAsync(List<string> symbols, string interval = "15m", bool onlyValidated = true);
}
