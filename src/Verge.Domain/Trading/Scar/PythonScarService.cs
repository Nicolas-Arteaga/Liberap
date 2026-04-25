using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.Scar;

public class PythonScarService : IPythonScarService
{
    private readonly HttpClient _http;
    private readonly ILogger<PythonScarService> _logger;

    public PythonScarService(IHttpClientFactory factory, ILogger<PythonScarService> logger)
    {
        _http = factory.CreateClient("PythonScar");
        _logger = logger;
    }

    public async Task<List<ScarResponseModel>> ScanAsync(List<string> symbols)
    {
        try
        {
            var payload = new { symbols = symbols };
            var response = await _http.PostAsJsonAsync("/scar/scan", payload);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<List<ScarResponseModel>>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            }) ?? new List<ScarResponseModel>();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [SCAR] Python Scan call failed");
            return new List<ScarResponseModel>();
        }
    }

    public async Task<ScarResponseModel?> GetScoreAsync(string symbol)
    {
        try
        {
            var response = await _http.GetAsync($"/scar/score/{symbol}");
            if (!response.IsSuccessStatusCode) return null;

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<ScarResponseModel>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [SCAR] Python GetScore call failed for {Symbol}", symbol);
            return null;
        }
    }

    public async Task<List<ScarResponseModel>> GetActiveAlertsAsync(int threshold)
    {
        try
        {
            var response = await _http.GetAsync($"/scar/alerts?threshold={threshold}");
            if (!response.IsSuccessStatusCode) return new List<ScarResponseModel>();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<List<ScarResponseModel>>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            }) ?? new List<ScarResponseModel>();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [SCAR] Python GetActiveAlerts call failed");
            return new List<ScarResponseModel>();
        }
    }

    public async Task<List<ScarTopSetupModel>> GetTopSetupsAsync(int limit)
    {
        try
        {
            var response = await _http.GetAsync($"/scar/top-setups?limit={limit}");
            if (!response.IsSuccessStatusCode) return new List<ScarTopSetupModel>();

            var json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<List<ScarTopSetupModel>>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            }) ?? new List<ScarTopSetupModel>();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [SCAR] Python GetTopSetups call failed");
            return new List<ScarTopSetupModel>();
        }
    }
}
