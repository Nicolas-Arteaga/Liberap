using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.AdnCompression;

/// <summary>
/// Llama al endpoint /adn-compression/scan del contenedor verge-python-ai.
/// Mismo patrón que PythonFvgService — aislado, degradación amable en error.
/// </summary>
public class PythonAdnCompressionService : IPythonAdnCompressionService
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonAdnCompressionService> _logger;

    public PythonAdnCompressionService(IHttpClientFactory factory, ILogger<PythonAdnCompressionService> logger)
    {
        _http = factory.CreateClient("PythonAdnCompression");
        _logger = logger;
    }

    public async Task<AdnCompressionScanResponseModel?> ScanAsync(List<string> symbols, string timeframe)
    {
        try
        {
            var payload = new { symbols = symbols, timeframe = timeframe };
            var response = await _http.PostAsJsonAsync("/adn-compression/scan", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<AdnCompressionScanResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [ADN-COMPRESSION] Python Service scan call failed");
            return null;
        }
    }
}
