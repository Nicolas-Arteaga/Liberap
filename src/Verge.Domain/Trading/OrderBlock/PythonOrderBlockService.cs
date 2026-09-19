using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.OrderBlock;

/// <summary>
/// Llama a los endpoints /orderblock/analyze y /orderblock/scan del contenedor
/// verge-python-ai. Mismo patrón que PythonFvgService — aislado, degradación
/// amable en error.
/// </summary>
public class PythonOrderBlockService : IPythonOrderBlockService
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonOrderBlockService> _logger;

    public PythonOrderBlockService(IHttpClientFactory factory, ILogger<PythonOrderBlockService> logger)
    {
        _http = factory.CreateClient("PythonOrderBlock");
        _logger = logger;
    }

    public async Task<ObAnalyzeResponseModel?> AnalyzeAsync(string symbol, string interval)
    {
        try
        {
            var payload = new { symbol = symbol, interval = interval, limit = 300 };
            var response = await _http.PostAsJsonAsync("/orderblock/analyze", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<ObAnalyzeResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ORDERBLOCK] Python Service call failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<ObScanResponseModel?> ScanAsync(List<string> symbols, string interval, bool onlyValidated)
    {
        try
        {
            var payload = new { symbols = symbols, interval = interval, only_validated = onlyValidated };
            var response = await _http.PostAsJsonAsync("/orderblock/scan", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<ObScanResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ORDERBLOCK] Python Service scan call failed");
            return null;
        }
    }
}
