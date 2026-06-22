using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.Nexus5;

/// <summary>
/// Calls the Python /nexus5/analyze endpoint for NEXUS-5 Ignition Core analysis.
/// Completely isolated from PythonNexus15Service and PythonIntegrationService.
/// </summary>
public class PythonNexus5Service : IPythonNexus5Service
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonNexus5Service> _logger;

    public PythonNexus5Service(IHttpClientFactory factory, ILogger<PythonNexus5Service> logger)
    {
        _http = factory.CreateClient("PythonNexus5");
        _logger = logger;
    }

    public async Task<Nexus5ResponseModel?> AnalyzeNexus5Async(string symbol, List<MarketCandleModel> candles, List<MarketCandleModel>? candles15m = null)
    {
        try
        {
            var payload = new Dictionary<string, object>
            {
                ["symbol"] = symbol,
                ["timeframe"] = "5m",
                ["candles"] = candles.Select(c => new
                {
                    timestamp = DateTimeOffset.FromUnixTimeMilliseconds(c.Timestamp).ToString("o"),
                    open = (double)c.Open,
                    high = (double)c.High,
                    low = (double)c.Low,
                    close = (double)c.Close,
                    volume = (double)c.Volume,
                }).ToList()
            };

            // Add native 15m candles for structural MA50/MA99 (Bottom Sniper v10.0)
            if (candles15m != null && candles15m.Count >= 30)
            {
                payload["candles_15m"] = candles15m.Select(c => new
                {
                    timestamp = DateTimeOffset.FromUnixTimeMilliseconds(c.Timestamp).ToString("o"),
                    open = (double)c.Open,
                    high = (double)c.High,
                    low = (double)c.Low,
                    close = (double)c.Close,
                    volume = (double)c.Volume,
                }).ToList();
            }

            var response = await _http.PostAsJsonAsync("/nexus5/analyze", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            _logger.LogInformation("NEXUS-5: Raw JSON from Python for {Symbol}: {Json}", symbol, json);

            return JsonSerializer.Deserialize<Nexus5ResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [Nexus5] Python Service call failed for {Symbol}", symbol);
            return null; // Graceful degradation
        }
    }
}
