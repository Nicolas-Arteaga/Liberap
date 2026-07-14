using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading.AdnCompression;

public interface IAdnCompressionAppService : IApplicationService
{
    /// <summary>
    /// Escanea una lista de símbolos buscando el patrón de compresión ADN
    /// (MA25/50/99 agrupadas + MA7 tejiendo >=2 cruces) seguido de ignición
    /// y régimen de pullback a MA7. timeframe="5m" (micro/scalp) o "1d" (macro/swing).
    /// </summary>
    Task<AdnCompressionScanResponseDto> ScanAsync(List<string> symbols, string timeframe = "5m");
}
