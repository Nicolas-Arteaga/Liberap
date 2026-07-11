using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.Fvg;

/// <summary>
/// Llama a los endpoints /fvg/analyze y /fvg/scan del contenedor verge-python-ai.
/// Mismo patrón que PythonNexus15Service — aislado, degradación amable en error.
/// </summary>
public class PythonFvgService : IPythonFvgService
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonFvgService> _logger;

    public PythonFvgService(IHttpClientFactory factory, ILogger<PythonFvgService> logger)
    {
        _http = factory.CreateClient("PythonFvg");
        _logger = logger;
    }

    public async Task<FvgAnalyzeResponseModel?> AnalyzeAsync(string symbol, string interval)
    {
        try
        {
            var payload = new { symbol = symbol, interval = interval, limit = 200 };
            var response = await _http.PostAsJsonAsync("/fvg/analyze", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<FvgAnalyzeResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] Python Service call failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<FvgScanResponseModel?> ScanAsync(List<string> symbols, string interval)
    {
        try
        {
            var payload = new { symbols = symbols, interval = interval };
            var response = await _http.PostAsJsonAsync("/fvg/scan", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<FvgScanResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] Python Service scan call failed");
            return null;
        }
    }

    public async Task<FvgCascadeResultModel?> CascadeAsync(string symbol)
    {
        try
        {
            var payload = new { symbol = symbol, limit = 200 };
            var response = await _http.PostAsJsonAsync("/fvg/cascade", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<FvgCascadeResultModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] Python Service cascade call failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<FvgCascadeScanResponseModel?> CascadeScanAsync(List<string> symbols)
    {
        try
        {
            var payload = new { symbols = symbols };
            var response = await _http.PostAsJsonAsync("/fvg/cascade-scan", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<FvgCascadeScanResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [FVG] Python Service cascade-scan call failed");
            return null;
        }
    }
}
