using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.Nexus15;

/// <summary>
/// Llama al endpoint /nexus15/analyze-nexus15 del contenedor verge-python-ai.
/// Totalmente aislado del PythonIntegrationService existente.
/// </summary>
public class PythonNexus15Service : IPythonNexus15Service
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonNexus15Service> _logger;

    public PythonNexus15Service(IHttpClientFactory factory, ILogger<PythonNexus15Service> logger)
    {
        _http = factory.CreateClient("PythonNexus15");
        _logger = logger;
    }
    public async Task<Nexus15ResponseModel?> AnalyzeNexus15Async(string symbol, List<MarketCandleModel> candles)
    {
        try
        {
            var payload = new
            {
                symbol = symbol,
                timeframe = "15m",
                candles = candles.Select(c => new
                {
                    timestamp = DateTimeOffset.FromUnixTimeMilliseconds(c.Timestamp).ToString("o"),
                    open = (double)c.Open,
                    high = (double)c.High,
                    low = (double)c.Low,
                    close = (double)c.Close,
                    volume = (double)c.Volume,
                })
            };

            var response = await _http.PostAsJsonAsync("/nexus15/analyze", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<Nexus15ResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });

        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [Nexus15] Python Service call failed for {Symbol}", symbol);
            return null;   // Graceful degradation: el scanner no se rompe
        }
    }
}
